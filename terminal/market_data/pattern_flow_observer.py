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
from pathlib import Path
from typing import Callable, Mapping

from robot_entry_flow_evidence import (
    CandidateBoundFlowEvidence, FlowTransition, existing_pattern_entry_scope,
)
from terminal.domain.models import TradingAccountId
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
            lambda: read_approved_pattern_candidates(self._db_path)
        )
        self._lock = threading.Lock()
        self._receipts: dict[str, CandidateBoundFlowEvidence] = {}
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
            "Double Top", "Double Bottom", "IKIGAI_BOX",
        }
        # Prefer the exact canonical entry phase over earlier warm-up.
        chosen = None
        priority = None
        for record in candidates:
            if (record.status != "APPROVED"
                    or record.signal_snapshot.get("pattern") not in allowed):
                continue
            symbol = record.symbol.value
            state = record.robot_state or {}
            if state.get("phase") not in (
                    "WAITING_RETEST", "RETEST_DETECTED", "BOX_ENTRY_READY"):
                continue
            score = (0 if existing_pattern_entry_scope(record) is not None else 1,
                     str(record.candidate_id))
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

    def get(self, record) -> CandidateBoundFlowEvidence | None:
        """Read-only, lock-bounded lookup; no REST or SQLite on Robot tick."""
        with self._lock:
            evidence = self._receipts.get(record.candidate_id)
        if evidence is None:
            return None
        now_ms = self._clock()
        if (type(now_ms) is not int or now_ms < evidence.decision_ms
                or now_ms - evidence.closed_at_ms > 120_000):
            return None
        return evidence

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
            # Exact approved-entry scope, including frozen direction. Sources
            # without an executable linked Robot ID (Box plan) are excluded.
            if (existing_pattern_entry_scope(record) is not None
                    and record.symbol.value in contexts):
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
                result = certified_snapshot(
                    before, recent, previous, current,
                    closed_at_ms=closed, decision_ms=decision,
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
                    direction=observed_flow["direction"],
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
                    self._receipts[record.candidate_id] = receipt
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
