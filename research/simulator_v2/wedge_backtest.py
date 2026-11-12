"""Original Wedge Scanner/Robot on *verified*, public Bybit trade-derived M1.

One symbol, a bounded UTC-minute window, an isolated virtual account, and
exactly the existing pinned-archive loader/report. No network, LIVE/PAPER DB,
credentials, bot, runtime imports, arbitrary prefilled signals or new pattern
algorithm. Real market history is a prerequisite, not proof of trade results.

A user-provided, explicit SIMULATION Wedge risk configuration MUST include
attested instrument terms and conversion from 1 working volume to contracts.
We never guess volume from account equity or claim exchange fill fidelity.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

from research.historical_market_replay import Candle
from robot_entry_flow_evidence import (
    FlowTransition, OI_MODES, OpenInterestChange, ImpulseProtectedPlan,
    open_interest_asof, permits_paper_entry, recognize_impulse_signal,
    plan_impulse_protected_entry,
)
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.report import ReplayReport, run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.taker_flow_archive import pinned_taker_minutes
from research.simulator_v2.oi_history import load_oi_csv
from research.simulator_v2.trade_range import (
    TradeDayProof, _ordered_proofs, iter_pinned_trade_chunks,
)
from research.simulator_v2.wedge_observer import WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from research.simulator_v2.wedge_visual_replay import WedgeVisualReplay


@dataclass(frozen=True)
class WedgeBacktestResult:
    report: ReplayReport
    requested_start_ms: int
    requested_end_inclusive_ms: int
    market_warmup_start_ms: int
    scanner_wedge_observations: int
    robot_retests_in_period: int
    submitted_protected_limits: int
    skipped_busy_entries: int
    stop_exits: int
    take_exits: int
    pending_protection: bool
    archive_proofs: tuple[TradeDayProof, ...] = ()
    replay_document: dict[str, object] | None = None
    paper_flow_gate_enabled: bool = False
    paper_flow_rejected_retests: int = 0
    paper_flow_permitted_retests: int = 0
    paper_oi_rejected_retests: int = 0
    paper_oi_mode: str = "OFF"
    paper_oi_sha256: str | None = None
    impulse_signals: int = 0
    impulse_risk_rejections: int = 0
    namespace: str = "SIMULATION"

    def to_payload(self) -> dict[str, object]:
        return {
            **self.report.to_payload(),
            **({"replay": self.replay_document} if self.replay_document is not None else {}),
            "requested_start_ms": self.requested_start_ms,
            "requested_end_inclusive_ms": self.requested_end_inclusive_ms,
            "requested_minutes": (self.requested_end_inclusive_ms - self.requested_start_ms) // MINUTE_MS + 1,
            "market_warmup_start_ms": self.market_warmup_start_ms,
            "scanner_wedge_observations": self.scanner_wedge_observations,
            "impulse_signals": self.impulse_signals,
            "impulse_risk_rejections": self.impulse_risk_rejections,
            "robot_retests_in_period": self.robot_retests_in_period,
            "submitted_protected_limits": self.submitted_protected_limits,
            "skipped_busy_entries": self.skipped_busy_entries,
            "stop_exits": self.stop_exits,
            "take_exits": self.take_exits,
            "pending_protection": self.pending_protection,
            "archive_proofs": [
                proof.to_payload(symbol=self.report.symbol)
                for proof in self.archive_proofs
            ],
            "execution_model": "SIMULATION_OHLC_STOP_FIRST_NOT_REAL_BYBIT_FILLS",
            **({"paper_flow_entry": {
                "permitted_retests": self.paper_flow_permitted_retests,
                "rejected_retests": self.paper_flow_rejected_retests,
                "oi_rejected_retests": self.paper_oi_rejected_retests,
                "oi_mode": self.paper_oi_mode,
                "oi_source_sha256": self.paper_oi_sha256,
                "execution": "EXISTING_PROTECTED_VIRTUAL_EXCHANGE",
            }} if self.paper_flow_gate_enabled else {}),
        }


def _valid_window(start_ms: int, end_inclusive_ms: int) -> int:
    if (type(start_ms) is not int or type(end_inclusive_ms) is not int
            or start_ms < 0 or end_inclusive_ms < start_ms
            or start_ms % MINUTE_MS or end_inclusive_ms % MINUTE_MS):
        raise ValueError("inclusive UTC minute window must be aligned and ordered")
    end_exclusive = end_inclusive_ms + MINUTE_MS
    if (end_exclusive - start_ms) // MINUTE_MS > 90 * 1440:
        raise ValueError("SIMULATION window exceeds 90 days")
    return end_exclusive


def run_verified_wedge_chunks(
    session: VirtualReplaySession,
    chunks: Iterable[HistoryChunk],
    *,
    start_ms: int, end_inclusive_ms: int,
    visual_recorder: WedgeVisualReplay | None = None,
    flow_on_close: Callable[[VirtualReplaySession, Candle], FlowTransition | None] | None = None,
    oi_mode: str = "OFF",
    oi_at_entry: Callable[[int], OpenInterestChange | None] | None = None,
    oi_source_sha256: str | None = None,
) -> WedgeBacktestResult:
    """Trade ONLY after native Scanner→Robot retest and native risk preview.

    Earlier verified M1 are warm-up; the account cannot trade before start.
    A new LIMIT must be submitted after a committed M1 and may fill only
    on a later M1. Open risk is never forced to close at the period end;
    any open virtual position/mark or pending LIMIT is reported honestly.
    """
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    if (not isinstance(session, VirtualReplaySession)
            or session.wedge_scanner is None or session.wedge_robot is None
            or session.wedge_robot.risk_settings is None):
        raise ValueError("original Wedge Scanner/Robot and explicit virtual risk terms required")
    if oi_mode not in OI_MODES or (
        oi_mode != "OFF" and (flow_on_close is None or oi_at_entry is None)
    ):
        raise ValueError("OI-filtered virtual entry requires authentic flow and OI series")
    skipped_busy = submitted = 0
    flow_rejected = flow_permitted = oi_rejected = 0
    consumed_preview_ids: set[str] = set()

    def on_close(active: VirtualReplaySession, candle: Candle) -> None:
        nonlocal submitted, skipped_busy, flow_rejected, flow_permitted, oi_rejected
        flow = (
            flow_on_close(active, candle)
            if flow_on_close is not None and start_ms <= candle.start_ms < end_exclusive
            else None
        )
        if candle.start_ms < start_ms:
            return
        if candle.end_ms >= end_exclusive:
            # The final closed M1 may fill an existing order; record it for
            # the chart, but never submit a NEW LIMIT after the chosen cutoff.
            if visual_recorder is not None:
                visual_recorder.record(active, candle)
            return
        if active.wedge_robot is None:
            raise ValueError("native virtual Wedge Robot disappeared")
        current_ids = {
            decision.candidate_id for decision in active.wedge_robot.decisions
            if decision.event == "RETEST"
            and decision.virtual_time_ms == candle.end_ms
        }
        if not current_ids:
            if visual_recorder is not None:
                visual_recorder.record(active, candle)
            return
        plans = {
            plan.request.client_action_id.value: plan.candidate_id
            for plan in active.wedge_robot.limit_plans
            if plan.candidate_id in current_ids
        }
        for preview in active.wedge_robot.risk_previews:
            key = preview.request.order_id
            if key not in plans or key in consumed_preview_ids:
                continue
            consumed_preview_ids.add(key)
            # One exchange and one position per symbol, fail-closed on
            # simultaneous competing entry candidates: do not stack.
            snapshot = active.account.snapshot(
                as_of_ms=active.virtual_time_ms,
                mark_price=candle.close,
            )
            if (active.exchange.pending is not None
                    or active.exchange.active_protection is not None
                    or snapshot.position_quantity != 0):
                skipped_busy += 1
                continue
            # Experimental PAPER rule is evaluated only where the original
            # Scanner->Robot has produced an independently risk-approved
            # protected LIMIT. Same Robot rule is imported into any PAPER
            # runner; no second entry plan or executor exists.
            if flow_on_close is not None:
                if not permits_paper_entry(preview.direction, flow):
                    flow_rejected += 1
                    continue
                if oi_mode != "OFF" and not permits_paper_entry(
                    preview.direction, flow, oi_mode=oi_mode,
                    oi=oi_at_entry(candle.end_ms),
                ):
                    oi_rejected += 1
                    continue
                flow_permitted += 1
            active.submit_protected_preview(preview)
            submitted += 1
        if visual_recorder is not None:
            visual_recorder.record(active, candle)

    report = run_verified_chunks(
        session, chunks, on_committed_m1=on_close,
    )
    if report.last_closed_ms != end_exclusive:
        raise ValueError("verified market history does not reach chosen inclusive end")
    if report.first_open_ms > start_ms:
        raise ValueError("verified market history begins after selected trade window")
    wedge = session.wedge_scanner
    robot = session.wedge_robot
    return WedgeBacktestResult(
        report=replace(
            report,
            scenario_type="ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
        ),
        requested_start_ms=start_ms,
        requested_end_inclusive_ms=end_inclusive_ms,
        market_warmup_start_ms=report.first_open_ms,
        scanner_wedge_observations=sum(
            o.available_at_ms >= start_ms and o.available_at_ms <= end_exclusive
            for o in wedge.observations
        ),
        robot_retests_in_period=sum(
            d.event == "RETEST"
            and start_ms <= d.virtual_time_ms <= end_exclusive
            for d in robot.decisions
        ),
        submitted_protected_limits=submitted,
        skipped_busy_entries=skipped_busy,
        stop_exits=sum(
            e.kind == "STOP_FILLED" for e in session.exchange.events
        ),
        take_exits=sum(
            e.kind == "TAKE_FILLED" for e in session.exchange.events
        ),
        pending_protection=session.exchange.active_protection is not None,
        paper_flow_gate_enabled=flow_on_close is not None,
        paper_flow_rejected_retests=flow_rejected,
        paper_flow_permitted_retests=flow_permitted,
        paper_oi_rejected_retests=oi_rejected,
        paper_oi_mode=oi_mode,
        paper_oi_sha256=oi_source_sha256,
    )



def run_verified_impulse_chunks(
    session: VirtualReplaySession,
    chunks: Iterable[HistoryChunk],
    *, start_ms: int, end_inclusive_ms: int,
    risk_settings: SimWedgeRiskSettings,
    flow_on_close: Callable[[VirtualReplaySession, Candle], FlowTransition | None],
    oi_mode: str = "OFF",
    oi_at_entry: Callable[[int], OpenInterestChange | None] | None = None,
    oi_source_sha256: str | None = None,
    visual_recorder: WedgeVisualReplay | None = None,
    impulse_plans: dict[str, ImpulseProtectedPlan] | None = None,
) -> WedgeBacktestResult:
    """Pure Scanner impulse + shared Robot risk → original protected venue.

    Executes only after a fully verified committed closed M1. Signals are
    based on contiguous original taker prints. Trades fill no earlier than
    the NEXT M1, with the same stop-first/fee mechanics as native Wedge.
    """
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    if not isinstance(session, VirtualReplaySession) or not isinstance(risk_settings, SimWedgeRiskSettings):
        raise ValueError("isolated virtual Robot and explicit risk terms required")
    if not callable(flow_on_close) or oi_mode not in OI_MODES:
        raise ValueError("real taker flow callback and valid OI mode required")
    if oi_mode != "OFF" and oi_at_entry is None:
        raise ValueError("active OI filter requires original 5m OI")
    if (risk_settings.entry_fee_rate < session.exchange.taker_fee_rate
            or risk_settings.exit_fee_rate < session.exchange.taker_fee_rate):
        raise ValueError("impulse risk fee assumptions must cover virtual venue taker fees")
    detected = rejected = permitted = oi_rejected = risk_rejected = busy = submitted = 0

    def on_close(active: VirtualReplaySession, candle: Candle) -> None:
        nonlocal detected, rejected, permitted, oi_rejected, risk_rejected, busy, submitted
        if not start_ms <= candle.start_ms < end_exclusive:
            return
        transition = flow_on_close(active, candle)
        signal = recognize_impulse_signal(
            transition, closed_at_ms=candle.end_ms,
            candle_open=candle.open, candle_close=candle.close,
            candle_low=candle.low, candle_high=candle.high,
        )
        # Last closed minute cannot submit a new order beyond this range.
        if signal is not None and candle.end_ms < end_exclusive:
            detected += 1
            if (active.exchange.pending is not None
                    or active.exchange.active_protection is not None
                    or active.account.snapshot(
                        as_of_ms=active.virtual_time_ms,
                        mark_price=candle.close,
                    ).position_quantity != 0):
                busy += 1
            elif not permits_paper_entry(signal.direction, transition):
                rejected += 1
            elif oi_mode != "OFF" and not permits_paper_entry(
                signal.direction, transition, oi_mode=oi_mode,
                oi=oi_at_entry(candle.end_ms),
            ):
                oi_rejected += 1
            else:
                try:
                    plan = plan_impulse_protected_entry(
                        signal, tick_size=risk_settings.tick_size,
                        quantity=risk_settings.contracts_per_working_volume,
                        max_notional_usdt=risk_settings.max_notional_usdt,
                        max_risk_usdt=risk_settings.max_risk_usdt,
                        entry_fee_rate=risk_settings.entry_fee_rate,
                        exit_fee_rate=risk_settings.exit_fee_rate,
                        quantity_step=risk_settings.quantity_step,
                        minimum_quantity=risk_settings.minimum_quantity,
                    )
                except ValueError:
                    # Invalid quantity, notional, STOP or fee-aware RR is
                    # rejected, never replaced by a naked virtual order.
                    risk_rejected += 1
                else:
                    active.submit_protected_impulse(plan)
                    if impulse_plans is not None:
                        impulse_plans[f"IMPULSE_{candle.end_ms}"] = plan
                    submitted += 1
                    permitted += 1
        if visual_recorder is not None:
            visual_recorder.record(active, candle)

    report = run_verified_chunks(session, chunks, on_committed_m1=on_close)
    if report.last_closed_ms != end_exclusive or report.first_open_ms > start_ms:
        raise ValueError("verified historical impulse trade window was not complete")
    return WedgeBacktestResult(
        report=replace(report,scenario_type="IMPULSE_FLOW_SHARED_ROBOT_PROTECTED_VIRTUAL_SIMULATION"),
        requested_start_ms=start_ms, requested_end_inclusive_ms=end_inclusive_ms,
        market_warmup_start_ms=report.first_open_ms,
        scanner_wedge_observations=0, robot_retests_in_period=0,
        submitted_protected_limits=submitted, skipped_busy_entries=busy,
        stop_exits=sum(e.kind == "STOP_FILLED" for e in session.exchange.events),
        take_exits=sum(e.kind == "TAKE_FILLED" for e in session.exchange.events),
        pending_protection=session.exchange.active_protection is not None,
        paper_flow_gate_enabled=True,
        paper_flow_rejected_retests=rejected,
        paper_flow_permitted_retests=permitted,
        paper_oi_rejected_retests=oi_rejected,
        paper_oi_mode=oi_mode, paper_oi_sha256=oi_source_sha256,
        impulse_signals=detected, impulse_risk_rejections=risk_rejected,
    )


def run_cached_wedge_trade_range(
    *, cache_dir: Path, symbol: str,
    proofs: tuple[TradeDayProof, ...], latest_closed_boundary_ms: int,
    simulation_run_id: str, initial_balance: Decimal,
    start_ms: int, end_inclusive_ms: int,
    scanner_config: WedgeScannerConfig,
    robot_config: SimWedgeRobotConfig,
    risk_settings: SimWedgeRiskSettings,
    taker_fee_rate: Decimal = Decimal("0.0006"),
    maker_fee_rate: Decimal = Decimal("0.0002"),
    capture_replay: bool = False,
    on_replay_events: Callable[[list[dict[str, object]]], None] | None = None,
    flow_archive_dir: Path | None = None,
    oi_mode: str = "OFF",
    oi_history_path: Path | None = None,
    impulse_mode: bool = False,
) -> WedgeBacktestResult:
    """Offline Bybit public-trade M1 with an exact inclusive minute cutoff.

    Proofs must cover EVERY UTC day from warmup to the selected last minute.
    The final day may be truncated in replay, but is fully checked in cache
    before truncation. Source provenance remains 'trade-derived M1', never
    silently relabeled as official Bybit Kline.
    """
    end_exclusive = _valid_window(start_ms, end_inclusive_ms)
    _, archive_start, archive_end = _ordered_proofs(
        proofs, symbol=symbol,
        latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if not (archive_start <= start_ms < end_exclusive <= archive_end):
        raise ValueError("selected minute window lies outside pinned trade days")
    if end_exclusive > latest_closed_boundary_ms:
        raise ValueError("selected end includes an unclosed M1")
    # Load no more than the Scanner's explicit M5 lookback plus a closed-day
    # buffer. Do not force the requested end to equal the full manifest end.
    # The subset gets its OWN checksum-derived source ID; unselected days
    # are neither read nor claimed in the final report.
    day_ms = 86_400_000
    lookback_ms = scanner_config.window_bars * 5 * MINUTE_MS
    warmup_start = max(archive_start, (start_ms - lookback_ms) // day_ms * day_ms)
    first_index = (warmup_start - archive_start) // day_ms
    last_index = (end_exclusive - archive_start + day_ms - 1) // day_ms
    selected_proofs = proofs[first_index:last_index]
    if not selected_proofs:
        raise ValueError("selected UTC range has no verified archive days")

    def cut_to_selected_end():
        for chunk in iter_pinned_trade_chunks(
            cache_dir=cache_dir, symbol=symbol, proofs=selected_proofs,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
        ):
            if chunk.end_ms <= end_exclusive:
                yield chunk
            else:
                keep = (end_exclusive - chunk.start_ms) // MINUTE_MS
                if not 0 < keep < len(chunk.candles):
                    raise ValueError("invalid selected last-minute boundary")
                candles = chunk.candles[:keep]
                yield HistoryChunk(
                    symbol=chunk.symbol,
                    start_ms=chunk.start_ms,
                    end_ms=end_exclusive,
                    source_id=chunk.source_id,
                    candles=candles,
                    sha256=_checksum(_rows(candles)),
                )
                break

    session = VirtualReplaySession(
        simulation_run_id=simulation_run_id, symbol=symbol,
        initial_balance=initial_balance,
        taker_fee_rate=taker_fee_rate, maker_fee_rate=maker_fee_rate,
        wedge_scanner_config=None if impulse_mode else scanner_config,
        wedge_robot_config=None if impulse_mode else robot_config,
        wedge_risk_settings=None if impulse_mode else risk_settings,
    )
    impulse_plans: dict[str, ImpulseProtectedPlan] = {}
    recorder = WedgeVisualReplay(
        run_id=simulation_run_id, symbol=symbol,
        start_ms=start_ms, end_ms=end_exclusive,
        on_events=on_replay_events,
        impulse_plans=impulse_plans if impulse_mode else None,
    ) if capture_replay else None
    if oi_mode not in OI_MODES or (
        (oi_mode != "OFF" and (flow_archive_dir is None or oi_history_path is None))
        or (impulse_mode and flow_archive_dir is None)
    ):
        raise ValueError("OI mode requires validated trade tape and local OI CSV")
    oi_at_entry = None
    oi_sha256 = None
    if oi_mode != "OFF":
        oi_points, oi_sha256 = load_oi_csv(oi_history_path, symbol=symbol)
        def oi_at_entry(known_at_ms: int) -> OpenInterestChange | None:
            return open_interest_asof(oi_points, decision_ms=known_at_ms)

    flow_callback = None
    if flow_archive_dir is not None:
        # The optional read-only tape comes from exactly the same pinned
        # raw day files as the immutable M1 cache. No network or substitute.
        tape = pinned_taker_minutes(
            archive_dir=flow_archive_dir, symbol=symbol, proofs=selected_proofs,
            start_ms=start_ms, end_ms=end_exclusive,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
        )
        source_id, _, _ = _ordered_proofs(
            selected_proofs, symbol=symbol,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
        )

        def flow_callback(active: VirtualReplaySession, minute: Candle):
            return active.observe_committed_taker_prints(
                tape[minute.start_ms], source_id=source_id,
            )

    if impulse_mode:
        result = run_verified_impulse_chunks(
            session, cut_to_selected_end(),
            start_ms=start_ms, end_inclusive_ms=end_inclusive_ms,
            risk_settings=risk_settings, flow_on_close=flow_callback,
            visual_recorder=recorder, impulse_plans=impulse_plans,
            oi_mode=oi_mode, oi_at_entry=oi_at_entry,
            oi_source_sha256=oi_sha256,
        )
    else:
        result = run_verified_wedge_chunks(
            session, cut_to_selected_end(),
            start_ms=start_ms, end_inclusive_ms=end_inclusive_ms,
            visual_recorder=recorder, flow_on_close=flow_callback,
            oi_mode=oi_mode, oi_at_entry=oi_at_entry,
            oi_source_sha256=oi_sha256,
        )
    replay = recorder.document(
        source_id=result.report.source_id, expected_fills=result.report.virtual_fills,
    ) if recorder is not None else None
    return replace(result, archive_proofs=selected_proofs, replay_document=replay)
