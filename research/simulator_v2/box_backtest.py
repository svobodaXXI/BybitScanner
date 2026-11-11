"""Verified archive runner for native Ikigai Box Scanner/Robot lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.ikigai_observer import IkigaiScannerConfig
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms
from research.simulator_v2.report import ReplayReport, run_verified_chunks
from research.simulator_v2.robot_sandbox import ConnectedSimulationRobot
from research.simulator_v2.box_visual_replay import BoxVisualReplay
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.trade_range import (
    TradeDayProof, _ordered_proofs, iter_pinned_trade_chunks,
)
from research.simulator_v2.wedge_backtest import _valid_window


@dataclass(frozen=True)
class BoxBacktestResult:
    report: ReplayReport
    requested_start_ms: int
    requested_end_inclusive_ms: int
    scanner_box_observations: int
    admitted_box_candidates: int
    entry_fills: int
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
            "scanner_box_observations": self.scanner_box_observations,
            "admitted_box_candidates": self.admitted_box_candidates,
            "box_entry_fills": self.entry_fills,
            "stop_exits": self.stop_exits,
            "take_exits": self.take_exits,
            "archive_proofs": [
                proof.to_payload(symbol=self.report.symbol)
                for proof in self.archive_proofs
            ],
            **({"replay": self.replay_document}
               if self.replay_document is not None else {}),
            "execution_model": (
                "SIMULATION_OHLC_ONE_BOX_FILL_PER_CLOSED_M1_STOP_FIRST_"
                "NOT_REAL_BYBIT_FILLS"
            ),
        }


def run_verified_box_chunks(
    session: VirtualReplaySession, chunks: Iterable[HistoryChunk], *,
    start_ms: int, end_inclusive_ms: int, terms: BoxSimulationRiskTerms,
    visual_recorder: BoxVisualReplay | None = None,
) -> BoxBacktestResult:
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    if session.ikigai_scanner is None:
        raise ValueError("native Ikigai Scanner is required")
    robot: ConnectedSimulationRobot | None = None
    admitted = 0
    consumed: set[str] = set()

    def on_close(active: VirtualReplaySession, candle) -> None:
        nonlocal robot, admitted
        if robot is not None:
            robot.after_committed_minute()
        if candle.start_ms < start_ms or candle.end_ms >= end_exclusive:
            if visual_recorder is not None:
                visual_recorder.record(active, robot, candle)
            return
        observations = [
            item for item in active.ikigai_scanner.observations
            if item.available_at_ms == candle.end_ms and item.formation_id not in consumed
        ]
        for observation in observations:
            consumed.add(observation.formation_id)
            if robot is not None and not robot.can_admit:
                # One native symbol owner at a time. A later signal is observed
                # but cannot stack onto an active Robot campaign.
                continue
            if robot is None:
                robot = ConnectedSimulationRobot(
                    active, tick_size=terms.tick_size, terms=terms,
                )
            robot.admit(observation)
            admitted += 1
        if visual_recorder is not None:
            visual_recorder.record(active, robot, candle)

    try:
        report = run_verified_chunks(session, chunks, on_committed_m1=on_close)
        if report.last_closed_ms != end_exclusive:
            raise ValueError("verified market history does not reach chosen inclusive end")
        events = session.exchange.events
        roles = robot.ownership_roles() if robot is not None else {}
        replay = visual_recorder.document(
            source_id=report.source_id, expected_fills=report.virtual_fills,
        ) if visual_recorder is not None else None
        return BoxBacktestResult(
            report=replace(
                report,
                scenario_type="ORIGINAL_IKIGAI_BOX_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
            ),
            requested_start_ms=start_ms,
            requested_end_inclusive_ms=end_inclusive_ms,
            scanner_box_observations=sum(
                start_ms <= item.available_at_ms <= end_exclusive
                for item in session.ikigai_scanner.observations
            ),
            admitted_box_candidates=admitted,
            entry_fills=sum(
                event.kind == "FILLED" and roles.get(event.order_id) == "ENTRY"
                for event in events
            ),
            stop_exits=sum(event.kind == "STOP_FILLED" for event in events),
            take_exits=sum(
                event.kind == "FILLED" and roles.get(event.order_id) == "EXIT"
                for event in events
            ),
            replay_document=replay,
        )
    finally:
        if robot is not None:
            robot.close()


def run_cached_box_trade_range(
    *, cache_dir: Path, symbol: str, proofs: tuple[TradeDayProof, ...],
    latest_closed_boundary_ms: int, simulation_run_id: str,
    initial_balance: Decimal, start_ms: int, end_inclusive_ms: int,
    scanner_config: IkigaiScannerConfig, terms: BoxSimulationRiskTerms,
    taker_fee_rate: Decimal = Decimal("0.0006"),
    maker_fee_rate: Decimal = Decimal("0.0002"),
    capture_replay: bool = False,
    on_replay_events: Callable[[list[dict[str, object]]], None] | None = None,
) -> BoxBacktestResult:
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    _, archive_start, archive_end = _ordered_proofs(
        proofs, symbol=symbol,
        latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if not (archive_start <= start_ms < end_exclusive <= archive_end):
        raise ValueError("selected minute window lies outside pinned trade days")
    if end_exclusive > latest_closed_boundary_ms:
        raise ValueError("selected end includes an unclosed M1")
    lookback_ms = scanner_config.window_bars * 5 * MINUTE_MS
    day_ms = 86_400_000
    warmup_start = max(archive_start, (start_ms - lookback_ms) // day_ms * day_ms)
    first_index = (warmup_start - archive_start) // day_ms
    last_index = (end_exclusive - archive_start + day_ms - 1) // day_ms
    selected = proofs[first_index:last_index]
    if not selected:
        raise ValueError("selected UTC range has no verified archive days")

    def chunks():
        for chunk in iter_pinned_trade_chunks(
            cache_dir=cache_dir, symbol=symbol, proofs=selected,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
        ):
            if chunk.end_ms <= end_exclusive:
                yield chunk
                continue
            keep = (end_exclusive - chunk.start_ms) // MINUTE_MS
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
        taker_fee_rate=taker_fee_rate, maker_fee_rate=maker_fee_rate,
        ikigai_scanner_config=scanner_config,
    )
    recorder = BoxVisualReplay(
        run_id=simulation_run_id, symbol=symbol,
        start_ms=start_ms, end_ms=end_exclusive,
        on_events=on_replay_events,
    ) if capture_replay else None
    return replace(
        run_verified_box_chunks(
            session, chunks(), start_ms=start_ms,
            end_inclusive_ms=end_inclusive_ms, terms=terms,
            visual_recorder=recorder,
        ),
        archive_proofs=selected,
    )
