"""Market-only bridge: a single M1 clock and a single SIMULATION account.

This composes the existing IsolatedTimeline and VirtualExchange without
implementing Scanner/Robot strategy or touching H-017/PAPER/MAIN/testnet.
The exchange runs as the LAST timeline stage, before that minute commits.
Orders may be supplied only after a committed closed minute. Future Robot
integration requires its own admission/decision wiring and step validation.
"""
from __future__ import annotations

from decimal import Decimal

from research.historical_market_replay import Candle
from research.simulator_v2.timeline import (
    IsolatedTimeline, MinuteFrame, SimulationEvent, StageFact, StepBlocked,
)
from research.simulator_v2.virtual_account import VirtualAccount, VirtualAccountSnapshot
from research.simulator_v2.virtual_exchange import MarketRequest, VirtualExchange
from research.simulator_v2.reused_geometry import ReadOnlyReusedGeometry
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner, WedgeScannerConfig


class VirtualReplaySession:
    """One-symbol, single-writer synchronous replay; no network or storage.

    This is a local integration harness, *not* an actual Robot adapter.
    The only producer of orders is an explicit caller; nothing decides trades.
    """

    def __init__(
        self, *, simulation_run_id: str, symbol: str,
        initial_balance: Decimal, taker_fee_rate: Decimal = Decimal("0.0006"),
        enable_reused_geometry: bool = False,
        wedge_scanner_config: WedgeScannerConfig | None = None,
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
        self.account = VirtualAccount(
            simulation_run_id=simulation_run_id, symbol=symbol,
            initial_balance=initial_balance,
        )
        self.exchange = VirtualExchange(
            account=self.account, taker_fee_rate=taker_fee_rate,
        )
        self.timeline = IsolatedTimeline(
            simulation_run_id=simulation_run_id, symbol=symbol,
            scanner=(self._on_readonly_scanner_stage
                     if self.reused_geometry is not None or self.wedge_scanner is not None
                     else None),
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
        return ()

    def _on_closed_exchange_stage(
        self, frame: MinuteFrame, _staged: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        receipt = self.exchange.on_closed_minute(frame.minute)
        if receipt is None:
            return ()
        return (StageFact(
            kind="VIRTUAL_MARKET_FILLED", entity_id=receipt.fill_id,
            details=(
                ("side", receipt.side),
                ("quantity", str(receipt.quantity)),
                ("price", str(receipt.price)),
                ("fee", str(receipt.fee)),
            ),
        ),)

    @property
    def virtual_time_ms(self) -> int | None:
        return self.timeline.virtual_time_ms

    @property
    def events(self) -> tuple[SimulationEvent, ...]:
        return self.timeline.events

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
            raise
        if self.reused_geometry is not None:
            self.reused_geometry.commit_after_m1()
        if self.wedge_scanner is not None:
            self.wedge_scanner.commit_after_m1(frame)
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks diverged; stop this replay")
        return self.account.snapshot(
            as_of_ms=minute.end_ms, mark_price=minute.close,
        )

    def submit(self, request: MarketRequest) -> None:
        if self.timeline.paused_stage is not None:
            raise StepBlocked("SIMULATION paused; cannot submit new virtual order")
        if self.timeline.virtual_time_ms != self.exchange.virtual_time_ms:
            raise StepBlocked("SIMULATION clocks disagree; cannot submit")
        if self.virtual_time_ms is None:
            raise ValueError("first close a historical M1 candle")
        self.exchange.submit(request, submitted_at_ms=self.virtual_time_ms)

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
