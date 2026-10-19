"""MIRROR-INTEGRATION-3: OBSERVE_ONLY sidecar over existing read interfaces.

Runs beside the PAPER runtime, never inside it:

* reads only through ``SQLiteStore.open_reader`` + ``read_snapshot`` (``query_only``,
  WAL; never takes the write lock and never waits for or calls the owner thread) —
  the same off-owner read path the A6 SHADOW observer uses;
* new Wedge candidates come from the durable Autopilot arrival audit
  (``load_robot_auto_decision_heads``) and the existing candidate envelopes
  (``robot_candidate_store.load_candidate``);
* the R0 account snapshot reuses ``paper_daily_equity_facts_in_transaction`` +
  ``robot_autopilot.daily_loss_gate_facts`` (the PAPER_AUTO gate facts, without
  runtime marks: open positions make it unavailable -> WAIT) and the existing
  open-trade / position / limit readers for obligations;
* closed candles come from a ``ClosedCandleSource`` (saved cache now; a live
  source is a separate runtime-acceptance step);
* journal writes go through the existing best-effort off-owner writer
  (``paper_runtime._BestEffortDiagnosticsWriter``): a full queue drops and counts.

STOP/TAKE priority: a cycle is skipped entirely (no read at all) whenever the
caller's ``protection_busy()`` says protection work is pending or unhealthy, or
cannot answer. The daily-loss headroom is only an upper bound for R0, never a
permission: every decision stays WAIT/BLOCK, ``executable=False``,
``admission_allowed=False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, PHASE_WAITING_BREAKOUT, Boundary
from mirror_retest_observer import (
    AccountFacts,
    Observation,
    ObservationJournal,
    boundaries_from_candidate_snapshot,
    observe_closed_candle,
)
from retest_account_risk import position_worst_case_loss_usdt
from robot_candidate_store import load_candidate
from terminal.application.paper_daily_equity import paper_daily_equity_facts_in_transaction
from terminal.application.robot_autopilot import daily_loss_gate_enabled, daily_loss_gate_facts
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_runtime import _BestEffortDiagnosticsWriter

WEDGE_PATTERNS = frozenset({"Rising Wedge", "Falling Wedge"})
COARSE_MS = 300_000
PAPER_FEE_RATE = Decimal("0.0006")   # documented PAPER per-side fee (paper_runtime.py plan fee)
OBSERVATION_QUEUE_LIMIT = 32
PROTECTION_RECHECK_EVERY = 10   # candidates between protection re-checks inside one cycle


class ClosedCandleSource(Protocol):
    def closed_candles(self, candidate_id: str, symbol: str, after_close_ms: int | None) -> Sequence[Mapping[str, Any]]:
        """Closed 5m candles with close time > ``after_close_ms`` (all when None), ascending."""


@dataclass(frozen=True)
class TrackedCandidate:
    candidate_id: str
    symbol: str
    formation_key: tuple[str, str]
    boundaries: tuple[Boundary, Boundary]


@dataclass
class SidecarMetrics:
    cycles: int = 0
    skipped_for_protection: int = 0
    read_failures: int = 0
    candidates_tracked: int = 0
    duplicates_ignored: int = 0
    candidates_unusable: int = 0
    observations_submitted: int = 0
    observations_dropped: int = 0
    fine_unavailable: int = 0


def _iso_ms(value: Any) -> int | None:
    try:
        return int(datetime.fromisoformat(str(value)).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def read_new_wedge_arrivals(
    reader: SQLiteStore, account: TradingAccountId, *, after_ms: int,
) -> list[tuple[str, int]]:
    """``(candidate_ref, evaluated_at_ms)`` of Wedge arrivals audited after ``after_ms``."""

    heads = reader.load_robot_auto_decision_heads(account, keep_mode="PAPER_AUTO", keep_outcome="ALLOW")
    first: dict[str, int] = {}
    for record in heads:
        if record.pattern in WEDGE_PATTERNS and record.evaluated_at_ms > after_ms:
            first.setdefault(record.candidate_ref, record.evaluated_at_ms)
    return sorted(first.items(), key=lambda item: (item[1], item[0]))


def read_account_facts(
    reader: SQLiteStore, account: TradingAccountId, *, now_ms: int,
    environ: Mapping[str, str] | None = None,
) -> AccountFacts:
    """Daily-loss gate facts and committed worst-case losses; unknown parts stay None (-> WAIT)."""

    equity = paper_daily_equity_facts_in_transaction(
        reader, account, as_of_ms=now_ms, marks={}, max_mark_age_ms=0)
    decisions = reader.load_robot_auto_decisions_for_admission(
        account, candidate_ref="", source_identity="", policy_version="",
        business_date_msk=str(equity.business_date_msk))
    gate = daily_loss_gate_facts(
        equity, decisions, enabled=daily_loss_gate_enabled(os.environ if environ is None else environ))

    committed: list[Any] = []
    trades = {trade.symbol.value: trade for trade in reader.load_open_robot_trades(account)}
    for position in reader.load_open_position_projections(account):
        trade = trades.get(position.position_key.symbol.value)
        if trade is None:
            committed.append(None)          # exposure without Robot STOP terms: unknown
            continue
        committed.append(position_worst_case_loss_usdt(
            direction=trade.direction, quantity=trade.entry_quantity, entry_price=trade.average_entry,
            stop_price=trade.stop_price, fee_rate=PAPER_FEE_RATE))
    for candidate in reader.load_robot_candidates_by_status(account, ("APPROVED", "OPEN")):
        if reader.load_active_paper_limits(account, Symbol(candidate.symbol.value)):
            committed.append(None)          # pending entry: worst case not proven from the record
    return AccountFacts(daily_gate=gate, committed_worst_case_usdt=committed)


@dataclass
class MirrorSidecar:
    database_path: Path
    account: TradingAccountId
    candidate_store_dir: Path
    candles: ClosedCandleSource
    journal: ObservationJournal
    protection_busy: Callable[[], bool]
    clock_ms: Callable[[], int]
    reader_factory: Callable[[Path], SQLiteStore] = SQLiteStore.open_reader
    writer: _BestEffortDiagnosticsWriter = field(
        default_factory=lambda: _BestEffortDiagnosticsWriter(OBSERVATION_QUEUE_LIMIT))
    metrics: SidecarMetrics = field(default_factory=SidecarMetrics)
    arrival_cursor_ms: int = 0
    tracked: dict[str, TrackedCandidate] = field(default_factory=dict)
    formations: set[tuple[str, str]] = field(default_factory=set)
    states: dict[str, dict] = field(default_factory=dict)
    candle_cursor: dict[str, int | None] = field(default_factory=dict)
    emitted: set[str] = field(default_factory=set)

    def _protection_has_priority(self) -> bool:
        try:
            return self.protection_busy() is not False
        except Exception:
            return True

    def cycle(self) -> list[Observation]:
        """One bounded pass. Returns the observations produced (also submitted to the journal)."""

        self.metrics.cycles += 1
        if self._protection_has_priority():
            self.metrics.skipped_for_protection += 1
            return []
        now = self.clock_ms()
        try:
            reader = self.reader_factory(self.database_path)
            try:
                with reader.read_snapshot():
                    arrivals = read_new_wedge_arrivals(reader, self.account, after_ms=self.arrival_cursor_ms)
                    try:
                        account = read_account_facts(reader, self.account, now_ms=now)
                    except Exception:
                        account = AccountFacts()          # R0 unavailable -> WAIT, never a pass
            finally:
                reader.close()
        except Exception:
            self.metrics.read_failures += 1
            return []
        for ref, evaluated_at in arrivals:
            self.arrival_cursor_ms = max(self.arrival_cursor_ms, evaluated_at)
            self._track(ref)
        produced: list[Observation] = []
        for index, candidate in enumerate(list(self.tracked.values())):
            if index and index % PROTECTION_RECHECK_EVERY == 0 and self._protection_has_priority():
                self.metrics.skipped_for_protection += 1
                break                                    # protection work started: yield immediately
            produced.extend(self._advance(candidate, account))
        return produced

    def _track(self, ref: str) -> None:
        if ref in self.tracked:
            self.metrics.duplicates_ignored += 1
            return
        try:
            envelope = load_candidate(ref, store_dir=self.candidate_store_dir)
        except Exception:
            self.metrics.candidates_unusable += 1
            return
        snapshot = envelope.get("signal_snapshot") or {}
        created = _iso_ms(envelope.get("created_at"))
        key = (str(envelope.get("symbol")), str(snapshot.get("scanner_formation_id") or ref))
        if key in self.formations:
            self.metrics.duplicates_ignored += 1
            return
        boundaries = None if created is None or str(envelope.get("timeframe")) != "5" else (
            boundaries_from_candidate_snapshot(candidate_id=ref, created_at_ms=created, signal_snapshot=snapshot))
        if boundaries is None:
            self.metrics.candidates_unusable += 1
            return
        self.formations.add(key)
        self.tracked[ref] = TrackedCandidate(ref, str(envelope["symbol"]), key, boundaries)
        # Start at the 5m boundary at/before the candidate was known: nothing earlier is ever read.
        self.candle_cursor.setdefault(ref, created - created % COARSE_MS)
        self.metrics.candidates_tracked += 1

    def _advance(self, candidate: TrackedCandidate, account: AccountFacts) -> list[Observation]:
        cursor = self.candle_cursor.get(candidate.candidate_id)
        candles = self.candles.closed_candles(candidate.candidate_id, candidate.symbol, cursor)
        produced: list[Observation] = []
        for candle in candles:
            blocked = False
            fine = None
            if any((self.states.get(b.boundary_id) or {}).get("phase") == PHASE_CAMPAIGN_ACTIVE
                   for b in candidate.boundaries) and hasattr(self.candles, "fine_candles"):
                try:
                    fine = self.candles.fine_candles(candidate.symbol, candle)
                except Exception:
                    # Without 1m proof an ambiguous touch would end the campaign as UNPROVEN:
                    # hold the cursor and retry this candle on a later cycle instead.
                    self.metrics.fine_unavailable += 1
                    break
            for boundary in candidate.boundaries:
                state = self.states.get(boundary.boundary_id)
                if state is not None and state["phase"] not in (PHASE_WAITING_BREAKOUT, PHASE_CAMPAIGN_ACTIVE):
                    continue
                state, record = observe_closed_candle(
                    boundary, state, candle, symbol=candidate.symbol, account=account, fine_candles=fine)
                self.states[boundary.boundary_id] = state
                if record is not None and record.observation_id not in self.emitted:
                    self.emitted.add(record.observation_id)
                    produced.append(record)
                    self._submit(record)
                blocked = blocked or state.get("data_blocked") is True
            if blocked:
                # A gap is not consumed: hold the cursor until the missing candle arrives.
                break
            self.candle_cursor[candidate.candidate_id] = int(candle["close_time_ms"])
        return produced

    def _submit(self, record: Observation) -> None:
        if record.executable or record.admission_allowed:
            raise ValueError("only OBSERVE_ONLY records are ever submitted")
        if self.writer.submit(lambda record=record: self.journal.append([record])):
            self.metrics.observations_submitted += 1
        else:
            self.metrics.observations_dropped += 1


class CachedKlineSource:
    """Saved RETEST-4 kline cache (``<candidate_id>_5.json``): replay of real history."""

    def __init__(self, klines_dir: Path, *, up_to_ms: Callable[[], int] | None = None) -> None:
        self._dir, self._up_to = Path(klines_dir), up_to_ms
        self._cache: dict[str, list[dict]] = {}

    def closed_candles(self, candidate_id, symbol, after_close_ms):
        if candidate_id not in self._cache:
            path = self._dir / f"{candidate_id}_5.json"
            if not path.exists():
                self._cache[candidate_id] = []
            else:
                from tools.research_mirror_retest_4 import candles
                self._cache[candidate_id] = candles(json.loads(path.read_text()), COARSE_MS)
        limit = None if self._up_to is None else self._up_to()
        return [c for c in self._cache[candidate_id]
                if (after_close_ms is None or c["close_time_ms"] > after_close_ms)
                and (limit is None or c["close_time_ms"] <= limit)]
