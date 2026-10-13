"""A3-R4: Wedge source-terminal EXPIRED producer for the A3-R3b sidecar store.

A SHADOW ALLOW of a Rising/Falling Wedge is proven EXPIRED only by the existing
Robot lifecycle rule: closed 1m candles replayed through ``robot_state_machine``
from the frozen Scanner cursor anchor reach ``EXPIRED_AT_APEX`` with no RETEST on
the way. A BREAKOUT that was never retested before the apex ends the same way (the
Robot enters only on a retest); BREAKOUT -> RETEST_DETECTED is not expiry. Every
minute after the anchor up to and including the first candle at/after the apex must
be present, in order, and closed (the newest kline is treated as still forming, as
in ``scanner_geometry_cursor``). The event is appended only when the PAPER portfolio
collector proves no physical obligation (position, working LIMIT, Robot idea) on the
symbol. Anything else -- gap, unknown order, incomplete snapshot, identity mismatch,
out-of-reach history, unproven obligations -- appends nothing, so the virtual
reservation stays.

Runs on the CALLING thread, never on the PAPER owner: it reads decisions through a
read-only connection, loads candles itself and only appends to the sidecar file.
The portfolio collector consumes the event; no PAPER table is written here.

Each signal's own anchor..apex range is loaded with explicit start/end in at most
MAX_RANGE_PAGES pages, so historical ALLOWs are provable too; at most
MAX_FETCHES_PER_PASS signals are fetched per pass and an OS file lock refuses a
concurrent pass. A ``FetchRotation`` shared between passes makes that budget
round-robin: each pass starts after the last signal fetched by the previous one, so
NOT_PROVEN signals cannot starve the DEFERRED rest (NOT_PROVEN still appends
nothing). ``python -m terminal.application.wedge_source_terminal_producer``
runs one pass as a separate process (no backend involvement).

SHADOW-RESERVE-1: the event records that the observed trading OPPORTUNITY is over
(the source signal can no longer be traded), never that a position was closed; a
linked Robot candidate's CLOSED stays the only position-closure release. Two more
existing-rule terminals, each proven from closed 1m candles only:

* Wedge ``WEDGE_RETEST_TAKE_REACHED_AFTER_APEX``: BREAKOUT -> RETEST before the apex,
  then a candle strictly after the apex candle reaches the Robot's frozen TAKE
  (``frozen_take_90``). The Robot cancels an unfilled retest LIMIT at the apex, so
  after it either nothing was entered or the entered position meets its TAKE (or
  already met its STOP): every branch is over. A RETEST without that proof (STOP
  depends on the unprovable actual fill) stays reserved.
* Ikigai Box ``IKIGAI_BOX_FIRST_GRID_EXIT_REACHED``: the frozen plan's first grid
  LIMIT (P1) is touched, then a strictly later candle reaches the plan's common TAKE
  or shared STOP (#416 completion, plus the STOP beyond the full grid). A Box that is
  never entered has no terminal rule (no age-based expiry) and stays reserved.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping

import robot_protection
import robot_state_machine
from robot_candidate_store import load_candidate
from scanner_geometry_cursor import (
    ONE_MINUTE_MS, ScannerGeometryCursorError, _anchor_values, _frozen_apex_index,
    _state_candle_from_row,
)
from terminal.application.robot_admission import candidate_snapshot_sha256
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor, RobotBreakoutMonitorError
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import TradingAccountId
from terminal.persistence.source_terminal_events import (
    SourceTerminalEvent, SourceTerminalEventError, append_source_terminal_event,
    load_terminal_identities, source_terminal_events_path,
)
from terminal.persistence.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)

RULE = "WEDGE_EXPIRED_AT_APEX_NO_RETEST"
RULE_VERSION = "2"  # v1 (no BREAKOUT at all) was never appended; v2 admits an unretested BREAKOUT
TAKE_RULE = "WEDGE_RETEST_TAKE_REACHED_AFTER_APEX"
TAKE_RULE_VERSION = "1"
BOX_RULE = "IKIGAI_BOX_FIRST_GRID_EXIT_REACHED"
BOX_RULE_VERSION = "1"
BOX_PATTERN = "IKIGAI_BOX"
MAX_KLINE_LIMIT = 1000  # Bybit V5 kline page size
MAX_RANGE_PAGES = 3  # anchor..apex (or Box decision..) history of at most 3000 minutes per signal
MAX_POST_APEX_PAGES = 2  # after-apex TAKE search of a retested Wedge: at most 2000 minutes
MAX_FETCHES_PER_PASS = 5  # signals needing candles per pass; the rest are DEFERRED
_COLUMNS = {"time", "high", "low", "close"}
_EVIDENCE_ERRORS = (
    robot_state_machine.RobotStateMachineError, ScannerGeometryCursorError,
    robot_protection.RobotProtectionError, RobotBreakoutMonitorError,
    KeyError, TypeError, ValueError, OverflowError, AttributeError, ArithmeticError,
)


def _candles_digest(rows) -> str:
    return hashlib.sha256(json.dumps(
        [[row["time_ms"], row["high"], row["low"], row["close"]] for row in rows],
        separators=(",", ":")).encode("utf-8")).hexdigest()


def _replay_to_apex(signal_snapshot: Mapping[str, Any], frame):
    """Replay of the proven, gap-free closed anchor..apex candles; None when unproven.

    Raises the ``_EVIDENCE_ERRORS`` of malformed input; callers turn them into None.
    """
    anchor_index, source_time = _anchor_values(signal_snapshot)
    apex_index = _frozen_apex_index(signal_snapshot)
    state, _event = robot_state_machine.initialize_state({
        "status": "APPROVED", "timeframe": "1", "signal_snapshot": dict(signal_snapshot),
    })
    if (state["geometry_cursor"] != anchor_index
            or state["phase"] != robot_state_machine.PHASE_WAITING_BREAKOUT):
        return None
    if frame is None or len(frame) < 2 or not _COLUMNS.issubset(frame.columns):
        return None
    candles, expected = [], source_time + ONE_MINUTE_MS
    for position in range(len(frame) - 1):  # the newest row may still be forming
        row = frame.iloc[position]
        time_ms = int(row["time"])
        if time_ms <= source_time:
            continue
        if time_ms != expected:
            return None  # gap, duplicate or out-of-order evidence
        candle = _state_candle_from_row(signal_snapshot, row)
        candles.append(candle)
        expected += ONE_MINUTE_MS
        if candle["geometry_index"] >= apex_index:
            break
    else:
        return None  # the apex candle is not proven closed yet
    replayed, events = robot_state_machine.replay_closed_candles(signal_snapshot, state, candles)
    return replayed, events, candles, anchor_index, apex_index


def evaluate_wedge_apex_expiry(signal_snapshot: Mapping[str, Any], frame) -> dict[str, Any] | None:
    """Evidence dict when EXPIRED_AT_APEX is proven without RETEST, else None."""
    try:
        if signal_snapshot.get("pattern") not in robot_state_machine.SUPPORTED_PATTERNS:
            return None
        proof = _replay_to_apex(signal_snapshot, frame)
        if proof is None:
            return None
        replayed, events, candles, anchor_index, apex_index = proof
        if (replayed.get("phase") != robot_state_machine.PHASE_EXPIRED_AT_APEX
                or events[-1:] != (robot_state_machine.EVENT_EXPIRED_AT_APEX,)
                or robot_state_machine.EVENT_RETEST in events):
            return None
        breakout_index = (replayed.get("breakout_index")
                          if robot_state_machine.EVENT_BREAKOUT in events else None)
        return {
            "rule": RULE, "rule_version": RULE_VERSION, "apex_index": apex_index,
            "anchor_index": anchor_index, "breakout_index": breakout_index,
            "first_index": candles[0]["geometry_index"],
            "apex_candle_index": candles[-1]["geometry_index"], "candles": len(candles),
            "from_time_ms": candles[0]["time_ms"], "to_time_ms": candles[-1]["time_ms"],
            "candles_sha256": _candles_digest(candles),
        }
    except _EVIDENCE_ERRORS:
        return None


def wedge_retest_take(signal_snapshot: Mapping[str, Any], frame) -> dict[str, Any] | None:
    """Proven BREAKOUT -> RETEST before the apex plus the Robot's frozen TAKE; else None.

    The TAKE is the one the Robot arms after an entry fill (``frozen_take_90`` of the
    snapshot's frozen reference/target); it does not depend on the actual fill price.
    """
    try:
        if signal_snapshot.get("pattern") not in robot_state_machine.SUPPORTED_PATTERNS:
            return None
        proof = _replay_to_apex(signal_snapshot, frame)
        if proof is None:
            return None
        replayed, events, candles, anchor_index, apex_index = proof
        if (replayed.get("phase") != robot_state_machine.PHASE_RETEST_DETECTED
                or events[-1:] != (robot_state_machine.EVENT_RETEST,)):
            return None
        direction = replayed["direction"]
        reference, target = RobotBreakoutMonitor._frozen_prices(signal_snapshot, direction)
        take = robot_protection.frozen_take_90(
            direction, frozen_signal_reference_price=reference, frozen_scanner_target_price=target)
        retest_index = replayed["retest_index"]
        return {
            "direction": direction, "take_price": take, "anchor_index": anchor_index,
            "apex_index": apex_index, "breakout_index": replayed["breakout_index"],
            "retest_index": retest_index,
            "candles": [c for c in candles if c["geometry_index"] <= retest_index],
        }
    except _EVIDENCE_ERRORS:
        return None


def evaluate_wedge_take_after_apex(
    retest: Mapping[str, Any], post_frame, apex_open_ms: int,
) -> dict[str, Any] | None:
    """Evidence when a closed candle strictly after the apex candle reaches the frozen TAKE.

    The retest LIMIT is cancelled at the apex candle, so no entry can follow such a
    candle: whatever was entered meets its TAKE there, if its STOP did not end it first.
    """
    try:
        if post_frame is None or len(post_frame) < 2 or not _COLUMNS.issubset(post_frame.columns):
            return None
        take, long = retest["take_price"], retest["direction"] == robot_state_machine.DIRECTION_LONG
        rows, previous = [], int(apex_open_ms)
        for position in range(len(post_frame) - 1):  # the newest row may still be forming
            row = post_frame.iloc[position]
            time_ms = int(row["time"])
            if time_ms <= previous:
                return None  # not strictly after the apex candle, or out of order
            previous = time_ms
            high, low = Decimal(str(row["high"])), Decimal(str(row["low"]))
            if not high.is_finite() or not low.is_finite() or low <= 0 or low > high:
                return None
            rows.append({"time_ms": time_ms, "high": float(row["high"]),
                         "low": float(row["low"]), "close": float(row["close"])})
            if (high >= take) if long else (low <= take):
                replay = retest["candles"]
                return {
                    "rule": TAKE_RULE, "rule_version": TAKE_RULE_VERSION,
                    "outcome": "TAKE_REACHED_AFTER_APEX", "direction": retest["direction"],
                    "take_price": str(take), "anchor_index": retest["anchor_index"],
                    "apex_index": retest["apex_index"], "breakout_index": retest["breakout_index"],
                    "retest_index": retest["retest_index"], "take_candle_time_ms": time_ms,
                    "candles": len(replay) + len(rows), "from_time_ms": replay[0]["time_ms"],
                    "to_time_ms": time_ms, "candles_sha256": _candles_digest([*replay, *rows]),
                }
        return None
    except _EVIDENCE_ERRORS:
        return None


@dataclass(frozen=True, slots=True)
class BoxPlanTerms:
    """Frozen first-grid levels of one BOX_PLAN_ONLY source; no order, no admission."""

    direction: str
    entry_price: Decimal  # P1: the first grid LIMIT the market reaches
    take_price: Decimal
    stop_price: Decimal
    start_ms: int  # first 1m candle strictly after the plan's decision minute


def box_plan_terms(snapshot: Mapping[str, Any]) -> BoxPlanTerms | None:
    """The frozen plan's P1/TAKE/STOP, or None when the plan is not a consistent first grid."""
    try:
        if snapshot.get("pattern") != BOX_PATTERN:
            return None
        plan = snapshot["plan"]
        direction = str(plan["direction"])
        if direction not in ("LONG", "SHORT") or direction != snapshot["identity"]["direction"]:
            return None
        limits = [Decimal(str(price)) for price in plan["limit_prices"]]
        take, stop = Decimal(str(plan["take_price"])), Decimal(str(plan["stop_price"]))
        if not limits or not all(p.is_finite() and p > 0 for p in (*limits, take, stop)):
            return None
        if direction == "LONG":
            entry = max(limits)
            if not stop < min(limits) or not entry < take:
                return None
        else:
            entry = min(limits)
            if not take < entry or not max(limits) < stop:
                return None
        decision = snapshot["decision_time_ms"]
        if type(decision) is not int or decision < 0:
            return None
        start_ms = decision - decision % ONE_MINUTE_MS + ONE_MINUTE_MS
        return BoxPlanTerms(direction, entry, take, stop, start_ms)
    except _EVIDENCE_ERRORS:
        return None


def evaluate_box_first_grid_exit(terms: BoxPlanTerms, frame) -> dict[str, Any] | None:
    """Evidence when P1 is touched and a strictly later closed candle reaches TAKE or STOP.

    Gap-free closed 1m candles from ``terms.start_ms`` only. A candle that touches P1
    and an exit level at once is ambiguous and never counts as the exit itself.
    """
    try:
        if frame is None or len(frame) < 2 or not _COLUMNS.issubset(frame.columns):
            return None
        long = terms.direction == "LONG"
        rows, entered_ms, expected = [], None, terms.start_ms
        for position in range(len(frame) - 1):  # the newest row may still be forming
            row = frame.iloc[position]
            time_ms = int(row["time"])
            if time_ms != expected:
                return None  # gap, duplicate or out-of-order evidence
            expected += ONE_MINUTE_MS
            high, low = Decimal(str(row["high"])), Decimal(str(row["low"]))
            if not high.is_finite() or not low.is_finite() or low <= 0 or low > high:
                return None
            rows.append({"time_ms": time_ms, "high": float(row["high"]),
                         "low": float(row["low"]), "close": float(row["close"])})
            if entered_ms is None:
                if (low <= terms.entry_price) if long else (high >= terms.entry_price):
                    entered_ms = time_ms
                continue
            take_hit = (high >= terms.take_price) if long else (low <= terms.take_price)
            stop_hit = (low <= terms.stop_price) if long else (high >= terms.stop_price)
            if take_hit or stop_hit:
                outcome = ("TAKE_OR_STOP_REACHED" if take_hit and stop_hit
                           else "TAKE_REACHED" if take_hit else "STOP_REACHED")
                return {
                    "rule": BOX_RULE, "rule_version": BOX_RULE_VERSION, "outcome": outcome,
                    "direction": terms.direction, "entry_price": str(terms.entry_price),
                    "take_price": str(terms.take_price), "stop_price": str(terms.stop_price),
                    "entry_candle_time_ms": entered_ms, "exit_candle_time_ms": time_ms,
                    "candles": len(rows), "from_time_ms": rows[0]["time_ms"], "to_time_ms": time_ms,
                    "candles_sha256": _candles_digest(rows),
                }
        return None
    except _EVIDENCE_ERRORS:
        return None


class RangeLoadError(RuntimeError):
    """The closed 1m range could not be loaded completely within the page bound."""


def load_closed_1m_range(symbol: str, start_ms: int, end_ms: int, *, get_kline: Callable | None = None):
    """Closed-candidate 1m rows for [start_ms, end_ms], ascending, in bounded pages.

    Disjoint windows of at most MAX_KLINE_LIMIT minutes, each one Bybit V5 kline
    request with explicit start/end, at most MAX_RANGE_PAGES requests. Any API error,
    malformed row or out-of-order result raises; continuity is judged by the caller.
    """
    if end_ms < start_ms or start_ms % ONE_MINUTE_MS or end_ms % ONE_MINUTE_MS:
        raise RangeLoadError("range bounds are invalid or not minute-aligned")
    windows = math.ceil(((end_ms - start_ms) // ONE_MINUTE_MS + 1) / MAX_KLINE_LIMIT)
    if windows > MAX_RANGE_PAGES:
        raise RangeLoadError("range exceeds the bounded page budget")
    if get_kline is None:
        from bybit_api import session  # the project's existing proxied public client
        get_kline = session.get_kline
    import pandas as pd

    rows = []
    for page in range(windows):
        window_start = start_ms + page * MAX_KLINE_LIMIT * ONE_MINUTE_MS
        window_end = min(end_ms, window_start + (MAX_KLINE_LIMIT - 1) * ONE_MINUTE_MS)
        response = get_kline(category="linear", symbol=symbol, interval="1",
                             start=window_start, end=window_end, limit=MAX_KLINE_LIMIT)
        if not isinstance(response, Mapping) or response.get("retCode") != 0:
            raise RangeLoadError("kline request failed")
        try:
            page_rows = sorted((int(r[0]), float(r[2]), float(r[3]), float(r[4]))
                               for r in response["result"]["list"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise RangeLoadError("kline response is malformed") from error
        if any(not window_start <= row[0] <= window_end for row in page_rows):
            raise RangeLoadError("kline response is outside the requested window")
        rows.extend(page_rows)
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise RangeLoadError("kline rows are duplicated or out of order")
    return pd.DataFrame(rows, columns=["time", "high", "low", "close"])


@contextmanager
def producer_pass_lock(sidecar: str | Path):
    """Non-blocking OS file lock next to the sidecar; yields False when another pass holds it.

    The OS releases the lock if the holding process dies, so no stale lock remains.
    """
    handle = open(Path(str(sidecar) + ".lock"), "a+b")
    try:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class FetchRotation:
    """Round-robin cursor for the per-pass fetch budget, kept by the caller between passes.

    Holds only the identity of the last signal that consumed budget; the next pass
    starts right after it (from the start when it is unknown or no longer listed).
    """

    def __init__(self) -> None:
        self.last_fetched: tuple[str, str] | None = None


def run_wedge_terminal_producer_once(
    database_path: str | Path, account: TradingAccountId, *,
    candidate_store_dir: str | Path | None,
    candle_range_loader: Callable | None = None,
    now_ms: int | None = None,
    max_fetches: int = MAX_FETCHES_PER_PASS,
    should_stop: Callable[[], bool] | None = None,
    fetch_rotation: FetchRotation | None = None,
) -> dict[str, str]:
    """One pass over this account's Wedge and Box SHADOW ALLOWs; status per candidate_ref.

    Returns {} when another pass holds the lock or the sidecar is unreadable.
    ``should_stop`` is checked before every fetch and again right before every append:
    once it is true the pass appends nothing more and marks the rest STOPPED.
    With ``fetch_rotation`` the pass starts after the last signal fetched by the previous
    pass and records its own last fetch, so the budget visits every pending signal.
    """
    should_stop = should_stop or (lambda: False)
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    sidecar = source_terminal_events_path(database_path)
    with producer_pass_lock(sidecar) as acquired:
        if not acquired:
            LOGGER.info("another Wedge producer pass is running; this pass is skipped")
            return {}
        try:
            known = load_terminal_identities(sidecar, account.value) or frozenset()
        except SourceTerminalEventError:
            LOGGER.warning("source-terminal events store unavailable; Wedge producer pass skipped")
            return {}
        if candle_range_loader is None:
            candle_range_loader = load_closed_1m_range
        reader = SQLiteStore.open_reader(database_path)
        try:
            decisions = reader.load_robot_auto_decisions(account)
            pending, seen = [], set()
            for decision in decisions:
                identity = (decision.candidate_ref, decision.snapshot_sha256)
                if (decision.mode != "SHADOW" or decision.outcome != "ALLOW"
                        or decision.trading_account_id != account
                        or (decision.pattern not in robot_state_machine.SUPPORTED_PATTERNS
                            and decision.pattern != BOX_PATTERN)
                        or decision.snapshot_sha256 is None or identity in seen):
                    continue
                seen.add(identity)
                pending.append((identity, decision))
            # The frozen BOX_PLAN_ONLY sources, read in the same read-only session.
            box_sources = {decision.candidate_ref: reader.get_robot_candidate(decision.candidate_ref)
                           for _identity, decision in pending if decision.pattern == BOX_PATTERN}
        finally:
            reader.close()
        if fetch_rotation is not None and fetch_rotation.last_fetched is not None:
            start = next((i + 1 for i, (identity, _decision) in enumerate(pending)
                          if identity == fetch_rotation.last_fetched), 0)
            pending = pending[start:] + pending[:start]

        results: dict[str, str] = {}
        budget = [max_fetches]
        obligations: list = []  # this pass's physical-symbol proof, read once on first need

        def physical_symbols():
            if not obligations:
                obligations.append(_physical_obligation_symbols(database_path, account))
            return obligations[0]

        for identity, decision in pending:
            remaining = budget[0]
            if should_stop():
                results[decision.candidate_ref] = "STOPPED"
            elif decision.pattern == BOX_PATTERN:
                results[decision.candidate_ref] = _process_box(
                    decision, box_sources.get(decision.candidate_ref), account, known, sidecar,
                    candle_range_loader, now_ms, budget, should_stop, physical_symbols)
            else:
                results[decision.candidate_ref] = _process(
                    decision, account, known, sidecar, candidate_store_dir, candle_range_loader,
                    now_ms, budget, should_stop, physical_symbols)
            if fetch_rotation is not None and budget[0] < remaining:
                fetch_rotation.last_fetched = identity
        return results


def _physical_obligation_symbols(database_path, account: TradingAccountId) -> frozenset[str] | None:
    """Symbols with a position, working LIMIT or Robot idea; None when not proven."""
    try:
        reader = SQLiteStore.open_reader(database_path)
        try:
            facts = collect_portfolio_facts(reader, account)
        finally:
            reader.close()
        if facts.get("available") is not True:
            return None
        return frozenset(row["symbol"] for key in ("positions", "working_limits", "robot_ideas")
                         for row in facts[key])
    except Exception:
        return None


def _process(decision, account, known, sidecar, candidate_store_dir, candle_range_loader,
             now_ms, budget, should_stop, physical_symbols) -> str:
    ref, sha = decision.candidate_ref, decision.snapshot_sha256
    if (ref, sha) in known:
        return "ALREADY_TERMINAL"
    try:
        envelope = load_candidate(ref, store_dir=candidate_store_dir)
        snapshot = envelope["signal_snapshot"]
        if (candidate_snapshot_sha256(snapshot) != sha
                or str(envelope.get("symbol", "")).strip() != decision.symbol.value):
            return "IDENTITY_MISMATCH"
        anchor_index, source_time = _anchor_values(snapshot)
        apex_index = _frozen_apex_index(snapshot)
    except Exception:
        return "SOURCE_UNAVAILABLE"
    apex_open_ms = source_time + (math.ceil(apex_index) - anchor_index) * ONE_MINUTE_MS
    if now_ms < apex_open_ms + 2 * ONE_MINUTE_MS:
        return "NOT_DUE"  # the apex candle is not closed with a newer bar after it yet
    # anchor+1 .. one bar after the apex candle; that last bar is ignored as "newest",
    # so the apex candle itself is always a strictly older, closed bar.
    start_ms, end_ms = source_time + ONE_MINUTE_MS, apex_open_ms + ONE_MINUTE_MS
    pages = math.ceil(((end_ms - start_ms) // ONE_MINUTE_MS + 1) / MAX_KLINE_LIMIT)
    if pages > MAX_RANGE_PAGES:
        return "OUT_OF_REACH"  # beyond the bounded API budget: keep reserved
    if budget[0] <= 0:
        return "DEFERRED"
    budget[0] -= 1
    try:
        frame = candle_range_loader(decision.symbol.value, start_ms, end_ms)
    except Exception:
        return "FETCH_FAILED"
    evidence = evaluate_wedge_apex_expiry(snapshot, frame)
    if evidence is None:
        retest = wedge_retest_take(snapshot, frame)
        if retest is None:
            return "NOT_PROVEN"
        if should_stop():
            return "STOPPED"
        # Strictly after the apex candle, bounded; the newest row is ignored as forming.
        post_end_ms = min(apex_open_ms + MAX_POST_APEX_PAGES * MAX_KLINE_LIMIT * ONE_MINUTE_MS,
                          now_ms - now_ms % ONE_MINUTE_MS)
        try:
            post_frame = candle_range_loader(
                decision.symbol.value, apex_open_ms + ONE_MINUTE_MS, post_end_ms)
        except Exception:
            return "FETCH_FAILED"
        evidence = evaluate_wedge_take_after_apex(retest, post_frame, apex_open_ms)
        if evidence is None:
            return "NOT_PROVEN"
    return _append_proven(decision, account, sidecar, "SCANNER", evidence, now_ms,
                          should_stop, physical_symbols)


def _process_box(decision, source, account, known, sidecar, candle_range_loader,
                 now_ms, budget, should_stop, physical_symbols) -> str:
    ref, sha = decision.candidate_ref, decision.snapshot_sha256
    if (ref, sha) in known:
        return "ALREADY_TERMINAL"
    if source is None:
        return "SOURCE_UNAVAILABLE"
    if (source.status != "BOX_PLAN_ONLY" or source.trading_account_id != account
            or source.snapshot_sha256 != sha or source.symbol != decision.symbol):
        return "IDENTITY_MISMATCH"
    terms = box_plan_terms(source.signal_snapshot)
    if terms is None:
        return "SOURCE_UNAVAILABLE"
    now_floor_ms = now_ms - now_ms % ONE_MINUTE_MS
    if now_floor_ms < terms.start_ms + ONE_MINUTE_MS:
        return "NOT_DUE"  # not even the first candle after the decision is closed yet
    # Decision+1 .. at most MAX_RANGE_PAGES pages or the forming candle (ignored as newest).
    end_ms = min(terms.start_ms + (MAX_RANGE_PAGES * MAX_KLINE_LIMIT - 1) * ONE_MINUTE_MS,
                 now_floor_ms)
    if budget[0] <= 0:
        return "DEFERRED"
    budget[0] -= 1
    try:
        frame = candle_range_loader(decision.symbol.value, terms.start_ms, end_ms)
    except Exception:
        return "FETCH_FAILED"
    evidence = evaluate_box_first_grid_exit(terms, frame)
    if evidence is None:
        return "NOT_PROVEN"
    return _append_proven(decision, account, sidecar, "BOX_PLAN", evidence, now_ms,
                          should_stop, physical_symbols)


def _append_proven(decision, account, sidecar, source, evidence, now_ms,
                   should_stop, physical_symbols) -> str:
    """Append the proven source-terminal event unless a physical obligation is pending."""
    symbols = physical_symbols()
    if symbols is None:
        return "OBLIGATIONS_UNPROVEN"
    if decision.symbol.value in symbols:
        return "OBLIGATION_PENDING"
    if should_stop():
        return "STOPPED"  # closed while the request was in flight: never append afterwards
    try:
        _event, created = append_source_terminal_event(sidecar, SourceTerminalEvent(
            trading_account_id=account.value, candidate_ref=decision.candidate_ref,
            snapshot_sha256=decision.snapshot_sha256, source=source, terminal_status="EXPIRED",
            rule=evidence["rule"], rule_version=evidence["rule_version"],
            evidence_json=json.dumps(evidence, sort_keys=True), observed_at_ms=now_ms,
        ))
    except (SourceTerminalEventError, OSError, ValueError):
        return "APPEND_FAILED"
    return "APPENDED" if created else "ALREADY_TERMINAL"


DEFAULT_PRODUCER_INTERVAL_S = 300.0


class WedgeTerminalProducerWorker:
    """Background PaperRuntime worker: one producer pass per interval, SHADOW only.

    Same lifecycle pattern as ScannerControlRuntime/RobotBreakoutMonitor: its own
    thread and stop Event, a full interval is waited BEFORE the first pass, close()
    joins. Nothing here touches the PAPER owner; a failed pass or mode read is logged
    and the next interval tries again (no event = reservation kept).
    """

    THREAD_NAME = "wedge-terminal-producer"

    def __init__(self, database_path, account: TradingAccountId, *,
                 interval_s: float = DEFAULT_PRODUCER_INTERVAL_S,
                 run_pass: Callable = run_wedge_terminal_producer_once,
                 autopilot_mode: Callable[[], str | None] | None = None,
                 candidate_store_dir=None) -> None:
        self._database_path = database_path
        self._account = account
        self._interval_s = interval_s
        self._run_pass = run_pass
        self._autopilot_mode = autopilot_mode or self._read_autopilot_mode
        self._candidate_store_dir = candidate_store_dir
        self._fetch_rotation = FetchRotation()  # survives restarts of this worker
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Idempotent while running; refuses to start over a thread that is still closing."""
        if self._thread is not None and self._thread.is_alive():
            if self._stop.is_set():
                raise RuntimeError("the previous Wedge producer pass is still finishing")
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,),
                                        name=self.THREAD_NAME, daemon=True)
        self._thread.start()

    def close(self, timeout_s: float = 5.0) -> bool:
        """Stop and join for at most ``timeout_s``; False (and an ERROR log) if still running.

        A pass blocked in a Bybit request (pybit: 10 s timeout, 3 attempts, 3 s delay)
        may outlive the join; it is a daemon thread and its ``should_stop`` check
        discards the late result, so nothing is appended after close().
        """
        self._stop.set()
        thread = self._thread
        if thread is None or thread is threading.current_thread():
            return True
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            LOGGER.error("Wedge terminal producer did not stop within %.1f s; "
                         "its in-flight result will be discarded", timeout_s)
            return False
        return True

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _read_autopilot_mode(self) -> str | None:
        reader = SQLiteStore.open_reader(self._database_path)
        try:
            state = reader.get_robot_autopilot_state(self._account)
        finally:
            reader.close()
        return None if state is None else state.mode

    def _run(self, stop: threading.Event) -> None:
        while not stop.wait(self._interval_s):
            try:
                if self._autopilot_mode() != "SHADOW":
                    continue
                results = self._run_pass(self._database_path, self._account,
                                         candidate_store_dir=self._candidate_store_dir,
                                         should_stop=stop.is_set,
                                         fetch_rotation=self._fetch_rotation)
                if results:
                    LOGGER.info("Wedge terminal producer pass: %s", results)
            except Exception:
                LOGGER.warning("Wedge terminal producer pass failed; reservations kept", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    """One producer pass as a separate process; paths follow the PAPER runtime defaults."""
    import argparse

    parser = argparse.ArgumentParser(description="Wedge source-terminal EXPIRED producer (one pass)")
    parser.add_argument("--db", default=os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))
    parser.add_argument("--candidate-store-dir", default=None)
    parser.add_argument("--account", default="paper")
    args = parser.parse_args(argv)
    results = run_wedge_terminal_producer_once(
        Path(args.db), TradingAccountId(args.account), candidate_store_dir=args.candidate_store_dir)
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
