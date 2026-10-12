"""A3-R4: Wedge source-terminal EXPIRED producer for the A3-R3b sidecar store.

A SHADOW ALLOW of a Rising/Falling Wedge is proven EXPIRED only by the existing
Robot lifecycle rule: closed 1m candles replayed through ``robot_state_machine``
from the frozen Scanner cursor anchor reach ``EXPIRED_AT_APEX`` with no BREAKOUT
or RETEST on the way. Every minute after the anchor up to and including the first
candle at/after the apex must be present, in order, and closed (the newest kline
is treated as still forming, as in ``scanner_geometry_cursor``). Anything else --
gap, unknown order, incomplete snapshot, identity mismatch, out-of-reach history --
appends nothing, so the virtual reservation stays.

Runs on the CALLING thread, never on the PAPER owner: it reads decisions through a
read-only connection, loads candles itself and only appends to the sidecar file.
The portfolio collector consumes the event; no PAPER table is written here.

Each signal's own anchor..apex range is loaded with explicit start/end in at most
MAX_RANGE_PAGES pages, so historical ALLOWs are provable too; at most
MAX_FETCHES_PER_PASS signals are fetched per pass and an OS file lock refuses a
concurrent pass. ``python -m terminal.application.wedge_source_terminal_producer``
runs one pass as a separate process (no backend involvement).
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping

import robot_state_machine
from robot_candidate_store import load_candidate
from scanner_geometry_cursor import (
    ONE_MINUTE_MS, ScannerGeometryCursorError, _anchor_values, _frozen_apex_index,
    _state_candle_from_row,
)
from terminal.application.robot_admission import candidate_snapshot_sha256
from terminal.domain.models import TradingAccountId
from terminal.persistence.source_terminal_events import (
    SourceTerminalEvent, SourceTerminalEventError, append_source_terminal_event,
    load_terminal_identities, source_terminal_events_path,
)
from terminal.persistence.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)

RULE = "WEDGE_APEX_NO_BREAKOUT"
RULE_VERSION = "1"
MAX_KLINE_LIMIT = 1000  # Bybit V5 kline page size
MAX_RANGE_PAGES = 3  # anchor..apex history of at most 3000 minutes per signal
MAX_FETCHES_PER_PASS = 5  # signals needing candles per pass; the rest are DEFERRED
_COLUMNS = {"time", "high", "low", "close"}


def evaluate_wedge_apex_expiry(signal_snapshot: Mapping[str, Any], frame) -> dict[str, Any] | None:
    """Evidence dict when EXPIRED_AT_APEX is proven without BREAKOUT, else None."""
    try:
        if signal_snapshot.get("pattern") not in robot_state_machine.SUPPORTED_PATTERNS:
            return None
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
        if (replayed.get("phase") != robot_state_machine.PHASE_EXPIRED_AT_APEX
                or events[-1:] != (robot_state_machine.EVENT_EXPIRED_AT_APEX,)
                or robot_state_machine.EVENT_BREAKOUT in events
                or robot_state_machine.EVENT_RETEST in events):
            return None
        digest = hashlib.sha256(json.dumps(
            [[c["time_ms"], c["high"], c["low"], c["close"]] for c in candles],
            separators=(",", ":")).encode("utf-8")).hexdigest()
        return {
            "rule": RULE, "rule_version": RULE_VERSION, "apex_index": apex_index,
            "anchor_index": anchor_index, "first_index": candles[0]["geometry_index"],
            "apex_candle_index": candles[-1]["geometry_index"], "candles": len(candles),
            "from_time_ms": candles[0]["time_ms"], "to_time_ms": candles[-1]["time_ms"],
            "candles_sha256": digest,
        }
    except (robot_state_machine.RobotStateMachineError, ScannerGeometryCursorError,
            KeyError, TypeError, ValueError, OverflowError, AttributeError):
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


def run_wedge_terminal_producer_once(
    database_path: str | Path, account: TradingAccountId, *,
    candidate_store_dir: str | Path | None,
    candle_range_loader: Callable | None = None,
    now_ms: int | None = None,
    max_fetches: int = MAX_FETCHES_PER_PASS,
) -> dict[str, str]:
    """One pass over this account's Wedge SHADOW ALLOWs; returns status per candidate_ref.

    Returns {} when another pass holds the lock or the sidecar is unreadable.
    """
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
        finally:
            reader.close()

        results: dict[str, str] = {}
        seen = set()
        budget = [max_fetches]
        for decision in decisions:
            identity = (decision.candidate_ref, decision.snapshot_sha256)
            if (decision.mode != "SHADOW" or decision.outcome != "ALLOW"
                    or decision.trading_account_id != account
                    or decision.pattern not in robot_state_machine.SUPPORTED_PATTERNS
                    or decision.snapshot_sha256 is None or identity in seen):
                continue
            seen.add(identity)
            results[decision.candidate_ref] = _process(
                decision, account, known, sidecar, candidate_store_dir, candle_range_loader,
                now_ms, budget)
        return results


def _process(decision, account, known, sidecar, candidate_store_dir, candle_range_loader,
             now_ms, budget) -> str:
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
        return "NOT_PROVEN"
    try:
        _event, created = append_source_terminal_event(sidecar, SourceTerminalEvent(
            trading_account_id=account.value, candidate_ref=ref, snapshot_sha256=sha,
            source="SCANNER", terminal_status="EXPIRED", rule=RULE, rule_version=RULE_VERSION,
            evidence_json=json.dumps(evidence, sort_keys=True), observed_at_ms=now_ms,
        ))
    except (SourceTerminalEventError, OSError, ValueError):
        return "APPEND_FAILED"
    return "APPENDED" if created else "ALREADY_TERMINAL"


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
