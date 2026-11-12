"""One-symbol native frozen-level Scanner/Robot over verified local M1.

Reuses native l_shape_scanner / geometry.double_extremum, robot_l_shape and
VirtualExchange; this is orchestration only, never a new strategy or PAPER
execution path. All submissions require original native confirmation and
explicit local instrument/risk terms. No network or private account access.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

import robot_l_shape
from research.historical_market_replay import Candle
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.frozen_level_adapter import (
    FrozenLevelSimulationBlocked, FrozenLevelSimulationPreview,
    preview_native_frozen_level,
)
from research.simulator_v2.frozen_level_observer import (
    FrozenLevelObservation, NativeFrozenLevelScanner,
)
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.report import ReplayReport, run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.trade_range import (
    TradeDayProof, _ordered_proofs, iter_pinned_trade_chunks,
)
from research.simulator_v2.wedge_backtest import _valid_window
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings

M5 = 300_000


@dataclass(frozen=True)
class FrozenLevelBacktestResult:
    report: ReplayReport
    requested_start_ms: int
    requested_end_inclusive_ms: int
    scanner_level_observations: int
    native_robot_confirmations: int
    submitted_protected_limits: int
    skipped_busy_entries: int
    rejected_risk_entries: int
    stop_exits: int
    take_exits: int
    archive_proofs: tuple[TradeDayProof, ...] = ()
    replay_document: dict[str, object] | None = None
    namespace: str = "SIMULATION"

    def to_payload(self) -> dict[str, object]:
        return {
            **self.report.to_payload(),
            "requested_start_ms": self.requested_start_ms,
            "requested_end_inclusive_ms": self.requested_end_inclusive_ms,
            "requested_minutes": (self.requested_end_inclusive_ms - self.requested_start_ms) // MINUTE_MS + 1,
            "scanner_level_observations": self.scanner_level_observations,
            "native_robot_confirmations": self.native_robot_confirmations,
            "submitted_protected_limits": self.submitted_protected_limits,
            "skipped_busy_entries": self.skipped_busy_entries,
            "rejected_risk_entries": self.rejected_risk_entries,
            "stop_exits": self.stop_exits,
            "take_exits": self.take_exits,
            "archive_proofs": [p.to_payload(symbol=self.report.symbol) for p in self.archive_proofs],
            **({"replay": self.replay_document} if self.replay_document is not None else {}),
            "execution_model": "SIMULATION_NATIVE_FROZEN_LEVEL_OHLC_STOP_FIRST_NOT_EXCHANGE_FILLS",
        }


class FrozenLevelVisualReplay:
    """Read-only projection of actual virtual exchange events, no trade decisions."""

    def __init__(
        self, *, run_id: str, symbol: str, start_ms: int, end_ms: int,
        on_events: Callable[[list[dict[str, object]]], None] | None = None,
    ):
        self.run_id, self.symbol = run_id, symbol
        self.start_ms, self.end_ms = start_ms, end_ms
        self._on_events = on_events
        self._items: list[dict[str, object]] = []
        self._published = 0
        self._event_count = 0
        self._fills = 0
        self._entries: dict[str, object] = {}
        self._orders: dict[str, FrozenLevelSimulationPreview] = {}
        self._precedence = {"CANDLE_CLOSED": 0, "ENTRY_SIGNAL": 1, "ENTRY_FILLED": 2, "EXIT_FILLED": 3}

    def _emit(self) -> None:
        if self._on_events is None or self._published >= len(self._items):
            return
        pending = sorted(self._items[self._published:],
                         key=lambda e: (e["time_ms"], self._precedence[e["kind"]]))
        self._on_events([
            {"source": "SIMULATION", "simulation_run_id": self.run_id,
             "sequence": self._published + i + 1, **event}
            for i, event in enumerate(pending)
        ])
        self._published += len(pending)

    def entry_submitted(self, preview: FrozenLevelSimulationPreview, at_ms: int) -> None:
        order = preview.protected.entry
        self._orders[order.order_id] = preview
        if self.start_ms <= at_ms < self.end_ms:
            self._items.append({
                "kind": "ENTRY_SIGNAL", "time_ms": at_ms,
                "strategy_id": {
                    "L-shape": "L_SHAPE", "Double Top": "DOUBLE_TOP",
                    "Double Bottom": "DOUBLE_BOTTOM",
                }[preview.pattern],
                "side": preview.direction, "price": float(order.limit_price),
                "stop": float(preview.protected.stop_price),
                "take": float(preview.protected.take_price),
                "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
            })

    def record(self, session: VirtualReplaySession, candle: Candle) -> None:
        if not self.start_ms <= candle.start_ms < self.end_ms:
            return
        if session.virtual_time_ms != candle.end_ms:
            raise ValueError("uncommitted visual replay minute")
        receipts = session.exchange.last_minute_fills
        events = session.exchange.last_minute_order_events
        if len(receipts) != len(events):
            raise ValueError("virtual fill/events diverged")
        for fill, event in zip(receipts, events):
            if fill.virtual_time_ms != candle.end_ms or event.virtual_time_ms != candle.end_ms:
                raise ValueError("visual fill was released before closed M1")
            original = self._orders.get(event.order_id)
            if original is None:
                raise ValueError("virtual fill lacks its original native protected LIMIT")
            is_entry = event.kind == "FILLED"
            if not is_entry and event.kind not in ("STOP_FILLED", "TAKE_FILLED"):
                raise ValueError("unclassified native frozen-level exit")
            values: dict[str, str] = {}
            if is_entry:
                if event.order_id in self._entries:
                    raise ValueError("duplicate virtual entry receipt")
                self._entries[event.order_id] = fill
            else:
                first = self._entries.pop(event.order_id, None)
                if first is None or first.quantity != fill.quantity:
                    raise ValueError("exit without matching native entry receipt")
                gross = (fill.price - first.price) * fill.quantity * (
                    1 if first.side == "BUY" else -1
                )
                net = gross - first.fee - fill.fee
                values = {
                    "net_usdt": format(net, "f"),
                    "pnl_percent": format(net * 100 / (first.price * first.quantity), "f"),
                }
            self._items.append({
                "kind": "ENTRY_FILLED" if is_entry else "EXIT_FILLED",
                "time_ms": fill.virtual_time_ms, "price": float(fill.price),
                "side": original.direction,
                "trade_id": f"SIMULATION:{self.run_id}:{event.order_id}",
                **({} if is_entry else {"reason": event.kind.replace("_FILLED", "")}),
                **values,
            })
            self._fills += 1

        frame = session.last_committed_frame
        if frame is None:
            raise ValueError("no committed M1/M5 visual source")
        m5 = frame.newly_closed_5m
        if m5 is not None and m5.start_ms >= self.start_ms:
            self._items.append({
                "kind": "CANDLE_CLOSED", "time_ms": m5.end_ms,
                "candle": {
                    "start_ms": m5.start_ms, "end_ms": m5.end_ms,
                    "open": float(m5.open), "high": float(m5.high),
                    "low": float(m5.low), "close": float(m5.close),
                    "volume": float(m5.volume),
                },
            })
            self._emit()

    def document(self, *, source_id: str, expected_fills: int) -> dict[str, object]:
        if self._fills != expected_fills:
            raise ValueError("native level replay does not account for every virtual fill")
        self._emit()
        items = sorted(self._items, key=lambda e: (e["time_ms"], self._precedence[e["kind"]]))
        if len(items) > 100_000 or not any(e["kind"] == "CANDLE_CLOSED" for e in items):
            raise ValueError("native frozen-level replay has no bounded completed M5")
        return {
            "source": "SIMULATION", "simulation_run_id": self.run_id,
            "mode": "STRATEGY", "demo": False, "timeframe": "5m",
            "symbol": self.symbol,
            "market_data_source": "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
            "source_id": source_id,
            "events": [
                {"source": "SIMULATION", "simulation_run_id": self.run_id,
                 "sequence": i, **item}
                for i, item in enumerate(items, 1)
            ],
        }


def run_verified_frozen_level_chunks(
    session: VirtualReplaySession, chunks: Iterable[HistoryChunk], *,
    start_ms: int, end_inclusive_ms: int,
    scanner: NativeFrozenLevelScanner, settings: SimWedgeRiskSettings,
    visual_recorder: FrozenLevelVisualReplay | None = None,
) -> FrozenLevelBacktestResult:
    """Observe original Scanner and Robot only AFTER each committed M1/M5 close.

    The virtual exchange owns fills, STOP/TAKE and fee attribution. A busy
    symbol cannot stack trades; an unverified native risk decision never
    submits a LIMIT. No warmup entry or order after selected last close.
    """
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    if (session.virtual_time_ms is not None or
            scanner.symbol != session.account.symbol or
            scanner.simulation_run_id != session.account.simulation_run_id or
            not isinstance(settings, SimWedgeRiskSettings)):
        raise ValueError("exact isolated native Scanner/Robot identity and risk required")
    if (settings.entry_fee_rate < max(session.exchange.maker_fee_rate, session.exchange.taker_fee_rate)
            or settings.exit_fee_rate < session.exchange.taker_fee_rate):
        raise ValueError("native risk assumptions underestimate virtual exchange fees")
    # All state transitions are delegated to the ORIGINAL robot_l_shape.
    waiting: dict[str, tuple[FrozenLevelObservation, dict]] = {}
    pending_owner: tuple[FrozenLevelObservation, FrozenLevelSimulationPreview] | None = None
    submitted = busy = denied = confirmations = 0

    def on_close(active: VirtualReplaySession, minute: Candle) -> None:
        nonlocal pending_owner, submitted, busy, denied, confirmations
        frame = active.last_committed_frame
        if frame is None or frame.virtual_time_ms != minute.end_ms:
            raise ValueError("native level Scanner received an uncommitted M1")
        selected_bars = {"1": frame.minute}
        if frame.newly_closed_5m is not None:
            selected_bars["5"] = frame.newly_closed_5m

        # The production native Robot can invalidate an unfilled GTC before
        # its next entry match. OHLC exchange matches on the committed minute
        # first; no invented intraminute ordering or retroactive fill removal.
        if pending_owner is not None:
            observed, preview = pending_owner
            if active.exchange.pending is None:
                pending_owner = None
            else:
                bar = selected_bars.get(observed.source_timeframe)
                if bar is not None and robot_l_shape.invalidation_event(
                    observed.candidate["signal_snapshot"],
                    {"time_ms": bar.end_ms, "high": bar.high, "low": bar.low},
                ) is not None:
                    active.cancel_pending(preview.protected.entry.order_id)
                    pending_owner = None

        ready: list[tuple[FrozenLevelObservation, dict]] = []
        for key, (observed, state) in tuple(waiting.items()):
            bar = selected_bars.get(observed.source_timeframe)
            if bar is None:
                continue
            new_state, _event = robot_l_shape.process_closed_candle(
                observed.candidate["signal_snapshot"], state,
                {"time_ms": bar.end_ms, "high": bar.high,
                 "low": bar.low, "close": bar.close},
            )
            if new_state["phase"] == robot_l_shape.PHASE_INVALIDATED:
                del waiting[key]
            elif new_state["phase"] == robot_l_shape.PHASE_RETEST_DETECTED:
                del waiting[key]
                ready.append((observed, new_state))
            else:
                waiting[key] = observed, new_state

        observed_now = scanner.observe_closed(frame)
        for observed in observed_now:
            state, _event = robot_l_shape.initialize_state(observed.candidate)
            if state["phase"] == robot_l_shape.PHASE_RETEST_DETECTED:
                ready.append((observed, state))
            elif len(waiting) < 256:
                waiting[observed.candidate_id] = (observed, state)

        for observed, state in ready:
            if not start_ms <= minute.start_ms < end_exclusive - MINUTE_MS:
                continue  # no backfilled warmup/final-close entries
            confirmations += 1
            try:
                preview = preview_native_frozen_level(
                    observed.candidate, state, settings=settings,
                    virtual_time_ms=minute.end_ms,
                )
            except (FrozenLevelSimulationBlocked, robot_l_shape.RobotLShapeError):
                denied += 1
                continue
            snapshot = active.account.snapshot(
                as_of_ms=active.virtual_time_ms, mark_price=minute.close,
            )
            if (active.exchange.pending is not None
                    or active.exchange.active_protection is not None
                    or snapshot.position_quantity != 0):
                busy += 1
                continue
            active.exchange.submit_protected_limit(
                preview.protected, submitted_at_ms=active.virtual_time_ms,
            )
            pending_owner = (observed, preview)
            if visual_recorder is not None:
                visual_recorder.entry_submitted(preview, minute.end_ms)
            submitted += 1

        if visual_recorder is not None:
            visual_recorder.record(active, minute)

    report = run_verified_chunks(session, chunks, on_committed_m1=on_close)
    if report.last_closed_ms != end_exclusive or report.first_open_ms > start_ms:
        raise ValueError("verified native level market window incomplete")
    result = FrozenLevelBacktestResult(
        report=replace(
            report, scenario_type="ORIGINAL_FROZEN_LEVEL_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
        ),
        requested_start_ms=start_ms,
        requested_end_inclusive_ms=end_inclusive_ms,
        scanner_level_observations=sum(
            start_ms <= item.available_at_ms <= end_exclusive
            for item in scanner.observations
        ),
        native_robot_confirmations=confirmations,
        submitted_protected_limits=submitted,
        skipped_busy_entries=busy,
        rejected_risk_entries=denied,
        stop_exits=sum(e.kind == "STOP_FILLED" for e in session.exchange.events),
        take_exits=sum(e.kind == "TAKE_FILLED" for e in session.exchange.events),
    )
    return result


def run_cached_frozen_level_trade_range(
    *, cache_dir: Path, symbol: str, proofs: tuple[TradeDayProof, ...],
    latest_closed_boundary_ms: int, simulation_run_id: str, initial_balance: Decimal,
    start_ms: int, end_inclusive_ms: int, selected: frozenset[str],
    scanner_window_bars: int, settings: SimWedgeRiskSettings,
    capture_replay: bool = False,
    on_replay_events: Callable[[list[dict[str, object]]], None] | None = None,
) -> FrozenLevelBacktestResult:
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    _, archive_start, archive_end = _ordered_proofs(
        proofs, symbol=symbol, latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if not archive_start <= start_ms < end_exclusive <= min(archive_end, latest_closed_boundary_ms):
        raise ValueError("native level range outside verified historical M1")
    scanner = NativeFrozenLevelScanner(
        symbol=symbol, simulation_run_id=simulation_run_id,
        selected=selected, window_bars=scanner_window_bars,
    )
    day_ms = 86_400_000
    warmup_start = max(
        archive_start, (start_ms - scanner_window_bars * M5) // day_ms * day_ms,
    )
    first = (warmup_start - archive_start) // day_ms
    last = (end_exclusive - archive_start + day_ms - 1) // day_ms
    chosen = proofs[first:last]
    if not chosen:
        raise ValueError("no pinned market days for native levels")

    def chunks():
        for chunk in iter_pinned_trade_chunks(
            cache_dir=cache_dir, symbol=symbol, proofs=chosen,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
        ):
            if chunk.end_ms <= end_exclusive:
                yield chunk
            else:
                keep = (end_exclusive - chunk.start_ms) // MINUTE_MS
                if not 0 < keep < len(chunk.candles):
                    raise ValueError("native level last-minute boundary invalid")
                candles = chunk.candles[:keep]
                yield HistoryChunk(
                    symbol=chunk.symbol, start_ms=chunk.start_ms,
                    end_ms=end_exclusive, source_id=chunk.source_id,
                    candles=candles, sha256=_checksum(_rows(candles)),
                )
                break

    session = VirtualReplaySession(
        simulation_run_id=simulation_run_id, symbol=symbol,
        initial_balance=initial_balance,
    )
    recorder = FrozenLevelVisualReplay(
        run_id=simulation_run_id, symbol=symbol, start_ms=start_ms,
        end_ms=end_exclusive, on_events=on_replay_events,
    ) if capture_replay else None
    result = run_verified_frozen_level_chunks(
        session, chunks(), start_ms=start_ms, end_inclusive_ms=end_inclusive_ms,
        scanner=scanner, settings=settings, visual_recorder=recorder,
    )
    replay = recorder.document(
        source_id=result.report.source_id, expected_fills=result.report.virtual_fills,
    ) if recorder is not None else None
    return replace(result, archive_proofs=chosen, replay_document=replay)
