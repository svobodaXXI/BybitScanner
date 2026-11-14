"""Single-exchange bridge: a single M1 clock and SIMULATION-only account.

This composes the existing IsolatedTimeline and VirtualExchange without
implementing Scanner/Robot strategy or touching H-017/PAPER/MAIN/testnet.
The exchange runs as the LAST timeline stage, before that minute commits.
Orders may be supplied only after a committed closed minute. Future Robot
integration requires its own admission/decision wiring and step validation.
"""
from __future__ import annotations

from decimal import Decimal

from robot_entry_flow_evidence import CompletedFlowObserver, FlowTransition, TakerPrint, ImpulseProtectedPlan
from research.historical_market_replay import Candle
from research.simulator_v2.timeline import (
    IsolatedTimeline, MinuteFrame, SimulationEvent, StageFact, StepBlocked,
)
from research.simulator_v2.virtual_account import VirtualAccount, VirtualAccountSnapshot
from research.simulator_v2.virtual_exchange import MarketRequest, LimitRequest, ProtectedLimitRequest, VirtualExchange, L2PartialTakePolicy
from research.simulator_v2.reused_geometry import ReadOnlyReusedGeometry
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner, WedgeScannerConfig
from research.simulator_v2.ikigai_observer import ReadOnlyIkigaiScanner, IkigaiScannerConfig
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms, preview_box_plan
from research.simulator_v2.ikigai_observer import IkigaiObservation
from research.simulator_v2.wedge_robot_observer import ReadOnlyWedgeRobot, SimWedgeRobotConfig
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings, UnsubmittedProtectedWedgePreview


class VirtualReplaySession:
    """One-symbol, single-writer synchronous replay; no network or storage.

    This is a local integration harness, *not* an actual Robot adapter.
    The only producer of orders is an explicit caller; nothing decides trades.
    """

    def __init__(
        self, *, simulation_run_id: str, symbol: str,
        initial_balance: Decimal, taker_fee_rate: Decimal = Decimal("0.0006"),
        maker_fee_rate: Decimal = Decimal("0.0002"),
        enable_reused_geometry: bool = False,
        wedge_scanner_config: WedgeScannerConfig | None = None,
        ikigai_scanner_config: IkigaiScannerConfig | None = None,
        wedge_robot_config: SimWedgeRobotConfig | None = None,
        wedge_risk_settings: SimWedgeRiskSettings | None = None,
        execution_mode: str = "OHLC_M1",
        l2_partial_take_policy: L2PartialTakePolicy | None = None,
    ) -> None:
        if type(enable_reused_geometry) is not bool:
            raise TypeError("explicit boolean for optional research geometry required")
        self.reused_geometry = (
            ReadOnlyReusedGeometry() if enable_reused_geometry else None
        )
        self.wedge_scanner = (
            ReadOnlyWedgeScanner(wedge_scanner_config)
            if wedge_scanner_config is not None else None
        )
        self.ikigai_scanner = (ReadOnlyIkigaiScanner(ikigai_scanner_config)
                               if ikigai_scanner_config is not None else None)
        if wedge_robot_config is not None and self.wedge_scanner is None:
            raise ValueError("SIMULATION Wedge Robot requires original Wedge Scanner stage")
        if wedge_risk_settings is not None:
            if wedge_robot_config is None:
                raise ValueError("Wedge risk preview requires explicit virtual Robot")
            if not isinstance(wedge_risk_settings, SimWedgeRiskSettings):
                raise TypeError("SIMULATION Wedge risk settings required")
            if (wedge_risk_settings.entry_fee_rate < max(taker_fee_rate, maker_fee_rate)
                    or wedge_risk_settings.exit_fee_rate < taker_fee_rate):
                raise ValueError("Wedge risk preview fees must cover virtual exchange fees")
        self.wedge_robot = (
            ReadOnlyWedgeRobot(
                scanner=self.wedge_scanner, config=wedge_robot_config,
                risk_settings=wedge_risk_settings,
            )
            if wedge_robot_config is not None else None
        )
        self.account = VirtualAccount(
            simulation_run_id=simulation_run_id, symbol=symbol,
            initial_balance=initial_balance,
        )
        self._last_committed_minute: Candle | None = None
        self._entry_flow_observer = CompletedFlowObserver(symbol=symbol, window_ms=60_000)
        self.exchange = VirtualExchange(
            account=self.account, taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            execution_mode=execution_mode,
            l2_partial_take_policy=l2_partial_take_policy,
        )
        self.timeline = IsolatedTimeline(
            simulation_run_id=simulation_run_id, symbol=symbol,
            scanner=(self._on_readonly_scanner_stage
                     if (self.reused_geometry is not None or self.wedge_scanner is not None
                         or self.ikigai_scanner is not None) else None),
            robot=(self.wedge_robot.observe_staged
                   if self.wedge_robot is not None else None),
            exchange=self._on_closed_exchange_stage,
        )

    def _on_readonly_scanner_stage(
        self, frame: MinuteFrame, staged: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        # Both observers stage on copies / pending values; no production code
        # with I/O is invoked and neither submits a trading decision.
        if self.reused_geometry is not None:
            self.reused_geometry.observe_staged(frame, staged)
        if self.wedge_scanner is not None:
            self.wedge_scanner.observe_staged(frame, staged)
        ikigai_facts: tuple[StageFact, ...] = ()
        if self.ikigai_scanner is not None:
            ikigai_facts = self.ikigai_scanner.observe_staged(frame, staged)
        return ikigai_facts

    def _on_closed_exchange_stage(
        self, frame: MinuteFrame, _staged: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        self.exchange.on_closed_minute(frame.minute)
        receipts = self.exchange.last_minute_fills
        order_events = self.exchange.last_minute_order_events
        if len(receipts) != len(order_events):
            raise StepBlocked("SIMULATION fill/event batch mismatched")
        if any(event.virtual_time_ms != frame.virtual_time_ms
               or event.kind not in ("FILLED", "STOP_FILLED", "TAKE_FILLED")
               for event in order_events):
            raise StepBlocked("SIMULATION fill event not consistent with closed M1")
        return tuple(StageFact(
            kind=("VIRTUAL_" + event.order_type + "_FILLED"
                  if event.kind == "FILLED" else "VIRTUAL_" + event.kind),
            entity_id=receipt.fill_id,
            details=(
                ("side", receipt.side),
                ("quantity", str(receipt.quantity)),
                ("price", str(receipt.price)),
                ("fee", str(receipt.fee)),
            ),
        ) for receipt, event in zip(receipts, order_events))

    @property
    def virtual_time_ms(self) -> int | None:
        return self.timeline.virtual_time_ms

    @property
    def events(self) -> tuple[SimulationEvent, ...]:
        return self.timeline.events

    @property
    def last_committed_minute(self) -> Candle | None:
        """Only the exact closed M1 whose full shared timeline committed."""
        return self._last_committed_minute

    @property
    def latest_entry_flow(self) -> FlowTransition | None:
        """Read-only market-flow evidence; never affects virtual admission."""
        return self._entry_flow_observer.last_transition

    def observe_committed_taker_prints(
        self, prints: tuple[TakerPrint, ...], *, source_id: str,
    ) -> FlowTransition | None:
        """Optional SIMULATION observer of authentic prints for the last CLOSED M1.

        This is an input adapter for the SAME Robot-owned flow evidence module.
        The caller must prove completeness/provenance of the historical tape;
        market-only M1 data cannot be re-labelled as taker executions. No
        virtual orders, protected entry policy or journal are modified.
        """
        minute = self._last_committed_minute
        if (minute is None or self.timeline.paused_stage is not None
                or self.timeline.virtual_time_ms != self.exchange.virtual_time_ms
                or self.timeline.virtual_time_ms != minute.end_ms):
            raise StepBlocked("closed, committed M1 required before flow observation")
        return self._entry_flow_observer.observe_closed(
            prints, start_ms=minute.start_ms, end_ms=minute.end_ms,
            observed_at_ms=minute.end_ms, source_id=source_id,
        )

    def step(self, minute: Candle) -> VirtualAccountSnapshot:
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; no new M1 is permitted")
        try:
            frame = self.timeline.step(minute)
        except Exception:
            if self.reused_geometry is not None:
                self.reused_geometry.discard_failed_m1()
            if self.wedge_scanner is not None:
                self.wedge_scanner.discard_failed_m1()
            if self.ikigai_scanner is not None:
                self.ikigai_scanner.discard_failed_m1()
            if self.wedge_robot is not None:
                self.wedge_robot.discard_failed_m1()
            raise
        if self.reused_geometry is not None:
            self.reused_geometry.commit_after_m1()
        if self.wedge_scanner is not None:
            self.wedge_scanner.commit_after_m1(frame)
        if self.ikigai_scanner is not None:
            self.ikigai_scanner.commit_after_m1(frame)
        if self.wedge_robot is not None:
            self.wedge_robot.commit_after_m1()
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks diverged; stop this replay")
        self._last_committed_minute = minute
        return self.account.snapshot(
            as_of_ms=minute.end_ms, mark_price=minute.close,
        )

    def preview_ikigai_grid(
        self, observation: IkigaiObservation, terms: BoxSimulationRiskTerms,
    ):
        """Original Box P1..P4/risk validation, never submit."""
        if self.ikigai_scanner is None or self.virtual_time_ms is None:
            raise ValueError("confirmed local Ikigai Scanner required")
        if self.timeline.paused_stage is not None or (
            self.virtual_time_ms != self.exchange.virtual_time_ms
        ):
            raise StepBlocked("SIMULATION uncommitted minute")
        if not isinstance(observation, IkigaiObservation) or not any(
            item is observation for item in self.ikigai_scanner.observations
        ):
            raise ValueError("Box is not committed by this Scanner")
        if observation.available_at_ms != self.virtual_time_ms:
            raise ValueError("stale Box needs separate late-admission policy")
        if self.exchange.pending is not None or self.exchange.active_protection is not None:
            raise ValueError("virtual exchange is occupied")
        if self.account.snapshot(
            as_of_ms=self.virtual_time_ms,
            mark_price=Decimal(str(observation.formation.fibonacci_1_0)),
        ).position_quantity != 0:
            raise ValueError("virtual account is not flat")
        return preview_box_plan(observation, terms=terms)

    def submit(self, request: MarketRequest) -> None:
        if self.timeline.paused_stage is not None:
            raise StepBlocked("SIMULATION paused; cannot submit new virtual order")
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; cannot submit")
        if self.virtual_time_ms is None:
            raise ValueError("first close a historical M1 candle")
        self.exchange.submit(request, submitted_at_ms=self.virtual_time_ms)

    def submit_limit(self, request: LimitRequest) -> None:
        """Caller must already own a fully admitted and protected LIMIT plan.

        The real Wedge Robot observer intentionally does NOT invoke this until
        its STOP/TAKE and RR gates can be proven.
        """
        if self.timeline.paused_stage is not None:
            raise StepBlocked("SIMULATION paused; cannot submit LIMIT")
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; cannot submit LIMIT")
        if self.virtual_time_ms is None:
            raise ValueError("first close a historical M1 candle")
        self.exchange.submit_limit(request, submitted_at_ms=self.virtual_time_ms)

    def submit_protected_preview(
        self, preview: UnsubmittedProtectedWedgePreview,
    ) -> None:
        """Explicit isolated preview→GTC+STOP/TAKE request after native RETEST.

        A preview is not production admission. This method accepts only one
        native Robot risk preview generated on the MOST RECENT committed
        virtual M1, with a currently flat single-symbol virtual account.
        No Robot approval or trading capability is implied outside this
        local SIMULATION account.
        """
        if self.timeline.paused_stage is not None:
            raise StepBlocked("SIMULATION paused; protected entry forbidden")
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clock mismatch")
        if self.wedge_robot is None or self.virtual_time_ms is None:
            raise ValueError("original virtual Robot RETEST required")
        if not isinstance(preview, UnsubmittedProtectedWedgePreview):
            raise TypeError("native Wedge protected risk preview required")
        if not any(
            item == preview for item in self.wedge_robot.risk_previews
        ):
            raise ValueError("preview is not a recorded native Scanner/Robot Wedge result")
        candidate_ids = {
            plan.candidate_id for plan in self.wedge_robot.limit_plans
            if plan.request.client_action_id.value == preview.request.order_id
        }
        if not candidate_ids:
            raise ValueError("protected preview does not match native Robot LIMIT")
        if not any(
            d.event == "RETEST"
            and d.virtual_time_ms == self.virtual_time_ms
            and d.candidate_id in candidate_ids
            for d in self.wedge_robot.decisions
        ):
            raise ValueError("only immediate committed RETEST previews may trade")
        if self.wedge_robot.risk_settings is None:
            raise ValueError("SIMULATION protective settings are not enabled")
        if self.account.snapshot(
            as_of_ms=self.virtual_time_ms,
            mark_price=preview.request.limit_price,
        ).position_quantity != 0:
            raise ValueError("virtual account must be flat before a new protected entry")
        request = ProtectedLimitRequest(
            entry=preview.request,
            stop_price=preview.stop_price,
            take_price=preview.take_price,
        )
        self.exchange.submit_protected_limit(
            request, submitted_at_ms=self.virtual_time_ms,
        )

    def submit_protected_impulse(self, plan: ImpulseProtectedPlan) -> None:
        """Execute a pure Robot impulse plan through the EXISTING virtual venue.

        Unlike the wedge-retest method, this accepts only the dedicated
        checked shared Robot signal/plan from the most recent committed M1.
        It does not create any PAPER or LIVE order authority.
        """
        if not isinstance(plan, ImpulseProtectedPlan):
            raise TypeError("shared Robot protected impulse plan required")
        if self.timeline.paused_stage is not None or (
            self.virtual_time_ms is None
            or self.timeline.virtual_time_ms != self.exchange.virtual_time_ms
            or plan.signal.known_at_ms != self.virtual_time_ms
        ):
            raise StepBlocked("uncommitted or stale impulse plan forbidden")
        if self._last_committed_minute is None or (
            self._last_committed_minute.end_ms != self.virtual_time_ms
        ):
            raise StepBlocked("impulse must follow a committed closed M1")
        if self.account.snapshot(
            as_of_ms=self.virtual_time_ms, mark_price=plan.entry_price,
        ).position_quantity != 0:
            raise ValueError("virtual impulse account must be flat")
        # The shared Robot plan has checked worst-loss and fee-aware minimum
        # RR. The same venue executes STOP-first, not an alternate matcher.
        entry = LimitRequest(
            order_id=f"IMPULSE_{self.virtual_time_ms}",
            side="BUY" if plan.signal.direction == "LONG" else "SELL",
            quantity=plan.quantity, limit_price=plan.entry_price,
        )
        self.exchange.submit_protected_limit(
            ProtectedLimitRequest(entry, plan.stop_price, plan.take_price),
            submitted_at_ms=self.virtual_time_ms,
        )

    def amend_limit(self, request: LimitRequest) -> None:
        if self.timeline.paused_stage is not None:
            raise StepBlocked("SIMULATION paused; cannot amend LIMIT")
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; cannot amend LIMIT")
        if self.virtual_time_ms is None:
            raise ValueError("first close a historical M1 candle")
        self.exchange.amend_limit(request, amended_at_ms=self.virtual_time_ms)

    def cancel_pending(self, order_id: str) -> None:
        """A failed fill may be cancelled at the last committed minute."""
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; cannot cancel")
        if self.virtual_time_ms is None:
            raise ValueError("no closed historical M1 candle")
        self.exchange.cancel_pending(order_id, cancelled_at_ms=self.virtual_time_ms)

    def resume(self) -> None:
        """Retry the exact failed candle after the rejected order is resolved."""
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; cannot resume")
        self.timeline.resume()
