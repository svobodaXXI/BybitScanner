"""Read-only market-flow overlay for already approved Robot pattern candidates.

One strictly bounded publicTrade-only probe on the EXISTING WebSocket,
or reuse an existing context. No extra orderbook, Scanner signal, candidate,
order, admission or STOP/TAKE authority. REST reads stay off-owner.
Missing or uncertain data never creates independent IMPULSE_FLOW trading.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from robot_entry_flow_evidence import (
    CandidateBoundFlowEvidence, FlowTransition, TakerPrint,
    aggregate_taker_prints, compare_flow_windows, existing_pattern_entry_scope,
    canonical_host_breakout_known_at_ms, observe_post_breakout_impulse_timing,
    PatternImpulseTimingResearch,
)
from terminal.domain.models import TradingAccountId
from terminal.market_data.impulse_observation import ObservedPrint
from terminal.market_data.pattern_flow_shadow_evidence import window_digest
from terminal.market_data.impulse_producer import certified_snapshot
from terminal.persistence.sqlite_store import SQLiteStore


LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.bybit.com"
_PAPER = TradingAccountId("paper")
MAX_CANDIDATES_PER_PASS = 1
PATTERN_FLOW_PAPER_OPT_IN = "BYBITSCANNER_ROBOT_PATTERN_FLOW_PAPER_AUTO"


def pattern_flow_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Explicit owner-approved PAPER opt-in; OFF for any other value."""
    values = os.environ if environ is None else environ
    return values.get(PATTERN_FLOW_PAPER_OPT_IN) == "1"



def source_coverage_audit(
    candidates: tuple, contexts: tuple, *, now_ms: int,
) -> dict[str, object]:
    """Read-only, aggregate pre-REST coverage for ALL executable Robot families.

    Diagnostics only: neither a market subscription nor two observed windows
    can prove complete prints. Counts NEVER authorize an entry or PAPER.
    No raw trade, candidate identity, symbol or private payload is returned.
    """
    if type(now_ms) is not int or now_ms < 120_000:
        raise ValueError("source coverage clock must be an integer >= 120000")
    closed = now_ms // 60_000 * 60_000
    subscribed = {ctx.symbol: ctx for ctx in contexts}
    counts = {
        "approved_exact_scope": 0,
        "missing_subscription": 0,
        "unready_subscription": 0,
        "invalid_observation": 0,
        "missing_two_closed_minutes": 0,
        "window_present_needs_rest_parity": 0,
        "buffer_at_limit": 0,
    }
    for candidate in candidates:
        scope = existing_pattern_entry_scope(candidate)
        if scope is None:
            continue
        counts["approved_exact_scope"] += 1
        context = subscribed.get(scope.symbol)
        if context is None:
            counts["missing_subscription"] += 1
            continue
        if (context.trades_subscription_state != "SUBSCRIBED"
                or context.trade_bootstrap_complete is not True):
            counts["unready_subscription"] += 1
            continue
        observed = context.impulse_observation.snapshot()
        prints = observed.get("prints") if isinstance(observed, dict) else None
        if (not isinstance(observed, dict)
                or observed.get("symbol") != scope.symbol
                or type(observed.get("generation")) is not int
                or type(observed.get("invalid_frames")) is not int
                or observed["invalid_frames"] != 0
                or not isinstance(prints, tuple)):
            counts["invalid_observation"] += 1
            continue
        capacity = observed.get("buffer_capacity", 512)
        if type(capacity) is not int or capacity not in (512, 1000):
            counts["invalid_observation"] += 1
            continue
        if len(prints) >= capacity:
            # Capacity is a warning, not a claim of source completeness.
            # The opt-in exact window can hold 1000, but REST must still
            # independently bracket both minutes with its own <=1000 page.
            counts["buffer_at_limit"] += 1
        previous = any(
            closed - 120_000 <= getattr(p, "timestamp_ms", -1) < closed - 60_000
            for p in prints
        )
        current = any(
            closed - 60_000 <= getattr(p, "timestamp_ms", -1) < closed
            for p in prints
        )
        if not previous or not current:
            counts["missing_two_closed_minutes"] += 1
        else:
            # Actual admission still needs exact REST and M1 parity, receipt
            # cutoff and same-generation proof. This is NOT source-complete.
            counts["window_present_needs_rest_parity"] += 1
    return {
        "status": "SOURCE_COVERAGE_DIAGNOSTIC_ONLY",
        "scope": "APPROVED_CANONICAL_PATTERN_ENTRY_CANDIDATES",
        "counts": counts,
        "source_complete": False,
        "trading_authorized": False,
    }


def read_approved_pattern_candidates(database_path: Path) -> tuple:
    """Read approved candidates from immutable, query-only SQLite connection.

    Crucially, SQLiteStore.open() is NOT used here: that can create indexes.
    No mutations, owner callbacks, runtime locks or schema changes.
    """
    path = Path(database_path)
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True,
        timeout=1, isolation_level=None,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=1000")
        store = SQLiteStore(connection, path, 1000)
        return store.load_robot_candidates_by_status(_PAPER, ("APPROVED",))
    finally:
        connection.close()



def read_active_pattern_candidates(database_path: Path) -> tuple:
    """Query-only source for the SAME Robot APPROVED and OPEN host IDs."""
    path = Path(database_path)
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True,
        timeout=1, isolation_level=None,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=1000")
        store = SQLiteStore(connection, path, 1000)
        return store.load_robot_candidates_by_status(_PAPER, ("APPROVED", "OPEN"))
    finally:
        connection.close()


def _open_wedge_flow_scope(record) -> bool:
    """Causal OPEN source observation only; no authority over its actual trade."""
    try:
        state, snapshot = record.robot_state, record.signal_snapshot
        return (
            record.status == "OPEN"
            and isinstance(state, Mapping) and isinstance(snapshot, Mapping)
            and snapshot.get("pattern") in ("Falling Wedge", "Rising Wedge")
            and state.get("direction") == (
                "LONG" if snapshot["pattern"] == "Falling Wedge" else "SHORT"
            )
            and state.get("pattern", snapshot.get("pattern")) == snapshot.get("pattern")
            and state.get("phase") in ("OPEN", "WAITING_RETEST", "RETEST_DETECTED")
            and isinstance(record.candidate_id, str) and bool(record.candidate_id)
            and type(record.state_revision) is int and record.state_revision >= 0
            and isinstance(record.symbol.value, str)
            and record.symbol.value.endswith("USDT")
        )
    except (AttributeError, KeyError, TypeError):
        return False


# Sub-minute observation only. These local windows are intentionally NOT
# equivalent to independent REST+closed-M1 certification or entry authority.
EARLY_PREVIEW_WINDOW_MS = 15_000
EARLY_PREVIEW_MAX_LAST_RECEIPT_AGE_MS = 5_000


@dataclass(frozen=True, slots=True)
class EarlyPatternFlowPreview:
    candidate_id: str
    state_revision: int
    symbol: str
    direction: str
    known_at_ms: int
    transport_generation: int
    transition: FlowTransition
    gap_or_truncation: bool
    source_complete: bool = False
    trading_authorized: bool = False
    window_sha256: str = ""  # raw-tape binding, not source-completeness proof



# Previewing a warming candidate is NOT canonical entry eligibility. Only
# wedges and the L-shape have established passive pre-retest states.
_PRE_RETEST_PREVIEW_PHASES = {
    "Falling Wedge": ("WAITING_BREAKOUT", "WAITING_RETEST"),
    "Rising Wedge": ("WAITING_BREAKOUT", "WAITING_RETEST"),
    "L-shape": ("L_SHAPE_WAITING_RETEST",),
}


def _early_preview_identity(record) -> tuple[str, int, str, str] | None:
    """Verify existing frozen host identity without extending entry scope."""
    scope = existing_pattern_entry_scope(record)
    if scope is not None:
        return (scope.candidate_id, scope.state_revision,
                scope.symbol, scope.direction)
    try:
        snapshot, state = record.signal_snapshot, record.robot_state
        if (record.status != "APPROVED"
                or not isinstance(snapshot, Mapping)
                or not isinstance(state, Mapping)):
            return None
        pattern = snapshot.get("pattern")
        if state.get("phase") not in _PRE_RETEST_PREVIEW_PHASES.get(pattern, ()):
            return None
        direction = state.get("direction")
        expected = {
            "Falling Wedge": "LONG",
            "Rising Wedge": "SHORT",
        }.get(pattern)
        if pattern == "L-shape":
            terms = snapshot.get("l_shape")
            if not isinstance(terms, Mapping):
                return None
            expected = terms.get("direction")
        candidate_id, revision = record.candidate_id, record.state_revision
        symbol = record.symbol.value
        if (direction not in ("LONG", "SHORT")
                or direction != expected
                or not isinstance(candidate_id, str) or not candidate_id
                or type(revision) is not int or revision < 0
                or not isinstance(symbol, str) or not symbol.isalnum()
                or not symbol.endswith("USDT")):
            return None
        return (candidate_id, revision, symbol, direction)
    except (AttributeError, TypeError, ValueError):
        return None


class PatternFlowObserver:
    """Source-complete two-minute evidence cache bound to existing pattern IDs."""

    def __init__(
        self, hub, rest_session, database_path: Path,
        *, clock_ms: Callable[[], int] | None = None,
        get_candidates: Callable[[], tuple] | None = None,
    ) -> None:
        self._hub = hub
        self._rest = rest_session
        self._db_path = Path(database_path)
        self._clock = clock_ms or (lambda: int(time.time() * 1000))
        self._get_candidates = get_candidates or (
            lambda: read_active_pattern_candidates(self._db_path)
        )
        self._lock = threading.Lock()
        # A certificate is usable only while its originating observation
        # object AND transport generation are still the live source.
        # Never let a reconnect, release or same-symbol replacement reuse it.
        self._receipts: dict[str, tuple[CandidateBoundFlowEvidence, object, int]] = {}
        self._attempted: set[tuple[str, int, int]] = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="robot-pattern-flow-readonly", daemon=True,
        )
        self._started = False
        self._flow_probe_symbol: str | None = None

    def _sync_flow_probe(self, candidates: tuple) -> None:
        """Warm one APPROVED candidate, including before its first retest.

        Source warming alone grants no flow proof or order authority. When
        another candidate takes priority, release ONLY our passive topic.
        """
        subscribe = getattr(self._hub, "subscribe_flow_only", None)
        release = getattr(self._hub, "release_flow_only", None)
        if subscribe is None or release is None:
            return
        allowed = {
            "Falling Wedge", "Rising Wedge", "L-shape", "MIRROR",
            "IKIGAI_BOX",
        }
        # Prefer the exact canonical entry phase over earlier warm-up.
        chosen = None
        priority = None
        for record in candidates:
            if (record.status not in ("APPROVED", "OPEN")
                    or record.signal_snapshot.get("pattern") not in allowed
                    or (record.status == "OPEN" and not _open_wedge_flow_scope(record))):
                continue
            symbol = record.symbol.value
            state = record.robot_state or {}
            phase = state.get("phase")
            pattern = record.signal_snapshot.get("pattern")
            # Wedges can stay WAITING_BREAKOUT for multiple M1; warming only
            # after breakout loses the entire initial impulse window. L-shape
            # uses a DISTINCT state name, not Wedge's WAITING_RETEST.
            # These phases warm data ONLY; REST certification and entry
            # remain restricted to exact durable approved-entry scope.
            warmable = {
                "Falling Wedge": ("WAITING_BREAKOUT", "WAITING_RETEST", "RETEST_DETECTED", "OPEN"),
                "Rising Wedge": ("WAITING_BREAKOUT", "WAITING_RETEST", "RETEST_DETECTED", "OPEN"),
                "L-shape": ("L_SHAPE_WAITING_RETEST", "RETEST_DETECTED"),
                "MIRROR": ("RETEST_DETECTED",),
                "IKIGAI_BOX": ("BOX_ENTRY_READY",)
            }
            if phase not in warmable[pattern]:
                continue
            score = (
                -1 if _open_wedge_flow_scope(record)
                else 0 if existing_pattern_entry_scope(record) is not None else 1,
                str(record.candidate_id),
            )
            if priority is None or score < priority:
                chosen, priority = symbol, score
        if chosen != self._flow_probe_symbol:
            if self._flow_probe_symbol is not None:
                release(self._flow_probe_symbol)
            self._flow_probe_symbol = None
        if chosen is not None:
            context = subscribe(chosen)
            if context is not None:
                self._flow_probe_symbol = chosen

    def start(self) -> None:
        if self._started:
            raise RuntimeError("pattern flow observer is already started")
        self._started = True
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout=18)
        release = getattr(self._hub, "release_flow_only", None)
        if release is not None and self._flow_probe_symbol is not None:
            release(self._flow_probe_symbol)
            self._flow_probe_symbol = None
        # Never close a requests.Session while the observer is still using it.
        if not self._thread.is_alive():
            self._rest.close()

    def early_preview(self, record) -> EarlyPatternFlowPreview | None:
        """Read-only 15s/15s observed taker transition before M1 closure.

        No REST, new subscription, owner callback, candidate mutation or
        trade authority. A bounded observed tape is not source-complete;
        missing prints are not silently reconstructed.
        """
        identity = _early_preview_identity(record)
        now_ms = self._clock()
        if identity is None or type(now_ms) is not int or now_ms < 2 * EARLY_PREVIEW_WINDOW_MS:
            return None
        candidate_id, revision, symbol, direction = identity
        list_contexts = getattr(self._hub, "list_flow_contexts", None)
        if list_contexts is None:
            list_contexts = getattr(self._hub, "list_contexts", None)
        if not callable(list_contexts):
            return None
        context = next((ctx for ctx in list_contexts()
                        if ctx.symbol == symbol), None)
        if (context is None or context.trades_subscription_state != "SUBSCRIBED"
                or context.trade_bootstrap_complete is not True):
            return None
        snapshot = context.impulse_observation.snapshot()
        if (not isinstance(snapshot, dict)
                or snapshot.get("symbol") != symbol
                or type(snapshot.get("generation")) is not int
                or type(snapshot.get("invalid_frames")) is not int
                or snapshot["invalid_frames"] != 0
                or snapshot.get("order_authority") is not False
                or snapshot.get("continuity") != "UNPROVEN"
                or not isinstance(snapshot.get("prints"), tuple)):
            return None

        middle = now_ms - EARLY_PREVIEW_WINDOW_MS
        start = middle - EARLY_PREVIEW_WINDOW_MS
        prior, current = [], []
        seen = set()
        last_event_ms = -1
        last_current_receipt_ms = -1
        for item in snapshot["prints"]:
            if not isinstance(item, ObservedPrint):
                return None
            if not start <= item.timestamp_ms < now_ms:
                continue
            receipt = item.received_at_ms
            # Require observed-before-decision local receipt and nonfuture
            # exchange time. Clock uncertainty fails closed.
            if (type(receipt) is not int or not item.timestamp_ms <= receipt <= now_ms
                    or item.trade_id in seen or item.timestamp_ms < last_event_ms):
                return None
            seen.add(item.trade_id)
            last_event_ms = item.timestamp_ms
            trade = TakerPrint(
                symbol, item.trade_id, item.timestamp_ms,
                item.side, item.price, item.quantity,
            )
            if item.timestamp_ms < middle:
                prior.append(trade)
            else:
                current.append(trade)
                last_current_receipt_ms = max(last_current_receipt_ms, receipt)
        if (not prior or not current or
                now_ms - last_current_receipt_ms > EARLY_PREVIEW_MAX_LAST_RECEIPT_AGE_MS):
            return None

        previous_window = aggregate_taker_prints(
            tuple(prior), symbol=symbol, start_ms=start, end_ms=middle,
        )
        current_window = aggregate_taker_prints(
            tuple(current), symbol=symbol, start_ms=middle, end_ms=now_ms,
        )
        if previous_window is None or current_window is None:
            return None
        transition = compare_flow_windows(
            previous_window, current_window, decision_ms=now_ms,
        )
        try:
            tape_digest = window_digest(snapshot["prints"], now_ms)
        except ValueError:
            tape_digest = ""  # descriptive preview remains non-authoritative
        return EarlyPatternFlowPreview(
            candidate_id=candidate_id,
            state_revision=revision,
            symbol=symbol, direction=direction,
            known_at_ms=now_ms, transport_generation=snapshot["generation"],
            transition=transition,
            gap_or_truncation=snapshot.get("gap_or_truncation") is not False,
            window_sha256=tape_digest,
        )

    def get(self, record) -> CandidateBoundFlowEvidence | None:
        """Only live same-epoch evidence; no REST or SQLite on Robot tick."""
        with self._lock:
            cached = self._receipts.get(record.candidate_id)
        if cached is None:
            return None
        evidence, source, generation = cached
        now_ms = self._clock()
        if (type(now_ms) is not int or now_ms < evidence.decision_ms
                or now_ms - evidence.closed_at_ms > 120_000):
            return None
        list_contexts = getattr(
            self._hub, "list_flow_contexts", self._hub.list_contexts,
        )
        # Passive/full promotions retain the SAME PublicTradeObservation.
        # Reconnect, release or replacement invalidate its lineage.
        context = next((
            c for c in list_contexts()
            if c.symbol == evidence.symbol and c.impulse_observation is source
        ), None)
        if (context is None
                or context.trades_subscription_state != "SUBSCRIBED"
                or context.trade_bootstrap_complete is not True):
            return None
        snapshot = source.snapshot()
        if (snapshot.get("generation") != generation
                or snapshot.get("invalid_frames") != 0):
            return None
        return evidence

    def research_timing(self, record) -> PatternImpulseTimingResearch | None:
        """Read already-certified early flow only; no trading/REST/DB authority.

        The original approved host must itself establish the post-breakout
        time. A missing certified source yields WAIT_SOURCE, not a market entry.
        """
        breakout = canonical_host_breakout_known_at_ms(record)
        if breakout is None:
            return None
        now_ms = self._clock()
        return observe_post_breakout_impulse_timing(
            record, self.get(record),
            breakout_known_at_ms=breakout, decision_ms=now_ms,
        )

    def reentry_research(
        self, record, proposal, *, previous_stop_at_ms: int,
    ) -> PatternImpulseTimingResearch | None:
        """Research the next impulse using ONLY this host's cached receipt.

        The caller must supply the canonical, previously attested STOP retry
        proposal. Neither an observer nor this result may reserve an attempt,
        enter PAPER, modify STOP/TAKE, or infer an executable fill. This path
        performs no REST, SQLite, subscription or owner-thread mutation.
        """
        from terminal.application.robot_reentry_adapter import (
            observe_post_stop_campaign_renewal,
        )

        breakout_ms = canonical_host_breakout_known_at_ms(record)
        if breakout_ms is None:
            return None
        return observe_post_stop_campaign_renewal(
            proposal, record, self.get(record),
            previous_stop_at_ms=previous_stop_at_ms,
            breakout_known_at_ms=breakout_ms,
            decision_ms=self._clock(),
        )

    def _json(self, endpoint: str, *, params: dict) -> dict:
        if getattr(self._rest, "verify", True) is False:
            raise ValueError("unverified REST TLS")
        response = self._rest.get(
            BASE_URL + endpoint, params=params, timeout=(2, 4),
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("Bybit REST did not return HTTP 200")
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("malformed Bybit REST response")
        return value

    def source_coverage(self) -> dict[str, object]:
        """Offline/read-only diagnostic of missing source, without subscriptions."""
        list_contexts = getattr(
            self._hub, "list_flow_contexts", self._hub.list_contexts,
        )
        return source_coverage_audit(
            tuple(self._get_candidates()), tuple(list_contexts()),
            now_ms=self._clock(),
        )

    def once(self) -> int:
        """At most one existing approved Robot pattern per M1; zero owner/DB writes."""
        now = self._clock()
        if type(now) is not int or now < 180_000:
            return 0
        closed = now // 60_000 * 60_000
        with self._lock:
            # Drop old candidates proactively: the Robot may never call get()
            # for closed/invalidated IDs. Do not hold source objects forever.
            self._receipts = {
                cid: cached for cid, cached in self._receipts.items()
                if 0 <= now - cached[0].closed_at_ms <= 120_000
            }
        if not 2_000 <= now - closed <= 45_000:
            return 0

        candidates = tuple(self._get_candidates())
        self._sync_flow_probe(candidates)
        list_contexts = getattr(
            self._hub, "list_flow_contexts", self._hub.list_contexts,
        )
        contexts = {context.symbol: context for context in list_contexts()}
        eligible = []
        for record in candidates:
            # Also observe a PROVEN host breakout before the old retest
            # entry phase, without changing its Robot order authorization.
            # No guessed Box/foreign breakout timestamps are admitted.
            entry_scope = existing_pattern_entry_scope(record)
            breakout_ms = canonical_host_breakout_known_at_ms(record)
            if (_open_wedge_flow_scope(record)
                    or entry_scope is not None
                    or (breakout_ms is not None and breakout_ms <= closed)):
                if record.symbol.value in contexts:
                    eligible.append(record)

        attempts = 0
        for record in eligible:
            if self._stop.is_set() or attempts >= MAX_CANDIDATES_PER_PASS:
                break
            key = (record.candidate_id, record.state_revision, closed)
            if key in self._attempted:
                continue
            self._attempted = {k for k in self._attempted if k[2] >= closed - 60_000}
            self._attempted.add(key)
            attempts += 1
            context = contexts[record.symbol.value]
            # This method is available on real PublicTradeObservation, and
            # only when this opt-in observer was explicitly created. Never
            # increase the default ingress buffer in the normal PAPER path.
            enable_window = getattr(
                context.impulse_observation, "enable_certification_buffer", None,
            )
            if enable_window is not None:
                enable_window()
            if (context.trades_subscription_state != "SUBSCRIBED"
                    or context.trade_bootstrap_complete is not True):
                continue
            before = context.impulse_observation.snapshot()
            # Hub SymbolContext.generation is not the publicTrade cursor.
            # Only PublicTradeObservation's own before/after generation
            # comparison proves absence of a reconnect during REST reads.
            if before.get("invalid_frames") != 0:
                continue
            # Without BOTH closed-minute prints, independent parity cannot
            # succeed. Avoid network calls and ingress pressure entirely.
            prints = before.get("prints")
            if (not isinstance(prints, tuple)
                    or not any(closed - 120_000 <= p.timestamp_ms < closed - 60_000
                               for p in prints)
                    or not any(closed - 60_000 <= p.timestamp_ms < closed
                               for p in prints)):
                continue
            try:
                recent = self._json("/v5/market/recent-trade", params={
                    "category": "linear", "symbol": record.symbol.value, "limit": 1000,
                })
                previous = self._json("/v5/market/kline", params={
                    "category": "linear", "symbol": record.symbol.value,
                    "interval": "1", "start": closed - 120_000,
                    "end": closed - 60_001, "limit": 1,
                })
                current = self._json("/v5/market/kline", params={
                    "category": "linear", "symbol": record.symbol.value,
                    "interval": "1", "start": closed - 60_000,
                    "end": closed - 1, "limit": 1,
                })
                decision = self._clock()
                after = context.impulse_observation.snapshot()
                # A changed generation, removed old print, or newly discovered
                # pre-close print invalidates the pre-fetch source snapshot.
                original = {p.trade_id: p for p in before.get("prints", ())
                            if p.timestamp_ms < closed}
                observed = {p.trade_id: p for p in after.get("prints", ())
                            if p.timestamp_ms < closed}
                if (context.trades_subscription_state != "SUBSCRIBED"
                        or context.trade_bootstrap_complete is not True
                        or after.get("generation") != before.get("generation")
                        or after.get("invalid_frames") != before.get("invalid_frames")
                        or original != observed):
                    continue
                # OPEN Wedge needs certified FADING facts, not a fresh
                # standalone acceleration/entry signal.
                open_wedge = _open_wedge_flow_scope(record)
                result = certified_snapshot(
                    before, recent, previous, current,
                    closed_at_ms=closed, decision_ms=decision,
                    source_only=open_wedge,
                )
                if result is None:
                    continue
                source = result["flow_source"]
                observed_flow = result["flow_observation"]
                transition = observed_flow["transition"]
                if not isinstance(transition, FlowTransition):
                    continue
                receipt = CandidateBoundFlowEvidence(
                    candidate_id=record.candidate_id,
                    symbol=record.symbol.value,
                    direction=(
                        record.robot_state["direction"]
                        if open_wedge else observed_flow["direction"]
                    ),
                    state_revision=record.state_revision,
                    source_kind=source["kind"],
                    closed_at_ms=source["closed_at_ms"],
                    decision_ms=source["decision_ms"],
                    print_facts_sha256=source["print_facts_sha256"],
                    source_complete=source["source_complete"],
                    receipt_cutoff_proven=source["receipt_cutoff_proven"],
                    transport_generation_proven=source["transport_generation_proven"],
                    transition=transition,
                )
                # Evidence is advisory until the Robot independently checks
                # exact candidate/revision/direction and normal entry gates.
                with self._lock:
                    self._receipts[record.candidate_id] = (
                        receipt, context.impulse_observation,
                        before["generation"],
                    )
                return 1
            except Exception as error:
                LOGGER.warning(
                    "Pattern flow read-only source unavailable: %s",
                    type(error).__name__,
                )
                continue
        return 0

    def _run(self) -> None:
        while not self._stop.wait(8):
            try:
                self.once()
            except Exception as error:
                LOGGER.warning(
                    "Pattern flow observer skipped: %s", type(error).__name__,
                )
