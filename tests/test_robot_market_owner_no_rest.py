"""P0-B slice 2: Robot PAPER Market entry / full-close never performs network
I/O on the serialized owner thread.

Before: RobotPaperActionExecutor.market()/full_close() (Robot monitor thread)
dispatched onto the owner, which ran TerminalCommandApi -> TradingApplication
.submit() -> persist SUBMITTING -> PaperMarketExecutor.execute() ->
LiveOrderBookProvider.get_book(): a synchronous Bybit REST request (10 s
timeout) whenever the Workspace was not streaming the symbol, held by the
owner mid-command.

After: execution evidence is read on the calling (monitor) thread and handed
to the owner as an immutable book; the owner uses the current streamed book
or that evidence, never the provider. Evidence is validated (symbol,
freshness) before any command is persisted, so missing/stale evidence leaves
no SUBMITTING command and no fill.

These tests run a real SerializedPaperRuntime so "owner thread" is the real
paper-runtime-owner thread; REST calls are attributed by thread name.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import threading
import time
import unittest

from terminal.api.models import (
    ClientActionId, CommandResultStatus, FullCloseCommandRequest, MarketCommandRequest,
    VolumeRequest, VolumeUnit,
)
from terminal.domain.models import Category, OrderSide, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.runtime.paper_http_server import (
    LiveOrderBookProvider, PublicOrderBookBuffer, SerializedPaperRuntime,
)
from terminal.runtime.paper_runtime import PaperRuntime, RobotPaperActionExecutor
from tests.test_robot_protection_close_no_rest import _Context, _Hub, _SlowRestSession, _stream
from tests.test_terminal_paper_runtime import _instrument


SYMBOL = "BTCUSDT"
ACCOUNT = TradingAccountId("paper")
OWNER_THREAD = "paper-runtime-owner"


def _entry(action_id: str = "robot-market-entry") -> MarketCommandRequest:
    return MarketCommandRequest(
        ClientActionId(action_id), SYMBOL, OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
        "Percent", Decimal("0.5"),
    )


class _Fixture:
    """Robot monitor-side executor over a real serialized owner. The
    Workspace shows ONGUSDT; REST would answer BTCUSDT after ``rest_delay_s``."""

    def __init__(self, temp: str, *, hub: bool = False, rest_delay_s: float = 2.0,
                 rest_bid: str = "64249.5", rest_ask: str = "64250.5") -> None:
        self.coverage = PublicOrderBookBuffer(SYMBOL)
        _stream(self.coverage, bid="64299.5", ask="64300.5")
        workspace = PublicOrderBookBuffer("ONGUSDT")
        _stream(workspace, bid="0.2", ask="0.21")
        self.session = _SlowRestSession(delay_s=rest_delay_s, bid=rest_bid, ask=rest_ask)
        self.provider = LiveOrderBookProvider(
            workspace, rest_session=self.session,
            hub=_Hub(_Context(SYMBOL, self.coverage)) if hub else None,
        )
        primary = _instrument()
        holder: dict[str, PaperRuntime] = {}

        def factory() -> PaperRuntime:
            holder["owner"] = PaperRuntime(
                Path(temp) / "paper.sqlite3", book_provider=self.provider,
                instrument_snapshot=primary,
                instrument_provider=lambda symbol: replace(primary, symbol=symbol),
            )
            return holder["owner"]

        self.serialized = SerializedPaperRuntime(factory)
        self.owner = holder["owner"]
        self.serialized.call(
            lambda owner: setattr(owner, "_robot_command_dispatcher", self.serialized.call)
        )
        self.executor = RobotPaperActionExecutor(self.owner)

    def owner_rest_calls(self) -> list:
        return [call for call in self.session.calls if call[0] == OWNER_THREAD]

    def slowest_owner_ms(self) -> float:
        return float(self.serialized.protection_ingress_metrics()["slowest_task_ms"])

    def executions(self):
        return self.serialized.call(lambda owner: [
            (item.side, item.price.value, item.quantity.value)
            for item in owner.store.load_executions()
        ])

    def position(self):
        key = PositionKey(ACCOUNT, Category.LINEAR, Symbol(SYMBOL), 0)
        return self.serialized.call(lambda owner: owner.store.get_position_projection(key))

    def close(self) -> None:
        self.serialized.close()


class RobotMarketEntryOwnerIoTests(unittest.TestCase):
    def test_entry_executes_on_handed_in_evidence_with_zero_owner_rest(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                result = fixture.executor.market(_entry())
                self.assertEqual(result.status, CommandResultStatus.COMPLETED)
                # Evidence was read once, on the calling (monitor) thread.
                self.assertEqual(fixture.owner_rest_calls(), [])
                self.assertEqual(len(fixture.session.calls), 1)
                self.assertNotEqual(fixture.session.calls[0][0], OWNER_THREAD)
                self.assertLess(fixture.slowest_owner_ms(), 1000)
                # Execution price is the handed-in REST evidence ask.
                [(side, price, _quantity)] = fixture.executions()
                self.assertEqual((side, price), (OrderSide.BUY, Decimal("64250.5")))
            finally:
                fixture.close()

    def test_streamed_book_is_preferred_and_needs_no_network(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, hub=True)
            try:
                _stream(fixture.coverage, bid="64299.5", ask="64300.5")
                result = fixture.executor.market(_entry())
                self.assertEqual(result.status, CommandResultStatus.COMPLETED)
                self.assertEqual(fixture.session.calls, [])
                self.assertEqual(fixture.executions()[0][1], Decimal("64300.5"))
            finally:
                fixture.close()

    def test_missing_evidence_persists_nothing_and_fills_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            fixture.provider._rest_session = None  # REST unavailable, no stream
            try:
                result = fixture.executor.market(_entry())
                self.assertNotEqual(result.status, CommandResultStatus.COMPLETED)
                self.assertEqual(fixture.executions(), [])
                self.assertIsNone(fixture.position())
                self.assertEqual(
                    fixture.serialized.call(
                        lambda owner: owner.store._connection.execute(
                            "SELECT COUNT(*) FROM trading_commands"
                        ).fetchone()[0]
                    ),
                    0,
                )
            finally:
                fixture.close()

    def test_stale_evidence_persists_nothing_and_fills_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_delay_s=0.0)
            stale = replace(
                fixture.provider.get_book(Symbol(SYMBOL)),
                received_at_ms=int(time.time() * 1000) - 5000,
            )
            fixture.session.calls.clear()
            try:
                result = fixture.serialized.call(
                    lambda owner: owner._robot_market(_entry(), evidence=stale)
                )
                self.assertNotEqual(result.status, CommandResultStatus.COMPLETED)
                self.assertEqual(fixture.owner_rest_calls(), [])
                self.assertEqual(fixture.executions(), [])
                self.assertEqual(
                    fixture.serialized.call(
                        lambda owner: owner.store._connection.execute(
                            "SELECT COUNT(*) FROM trading_commands"
                        ).fetchone()[0]
                    ),
                    0,
                )
            finally:
                fixture.close()

    def test_stable_identity_replay_does_not_double_fill(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, hub=True)
            try:
                from terminal.application.command_identity import CommandIdentityFactory
                identity = CommandIdentityFactory().create()
                _stream(fixture.coverage, bid="64299.5", ask="64300.5")
                first = fixture.owner._dispatch_robot_market_submit(_entry("late-1"), identity)
                second = fixture.owner._dispatch_robot_market_submit(_entry("late-1"), identity)
                self.assertEqual(first.status, CommandResultStatus.COMPLETED)
                self.assertEqual(second.status, CommandResultStatus.COMPLETED)
                self.assertEqual(len(fixture.executions()), 1)
                self.assertEqual(fixture.session.calls, [])
            finally:
                fixture.close()


class RobotFullCloseOwnerIoTests(unittest.TestCase):
    def test_full_close_executes_on_handed_in_evidence_and_cannot_reverse(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_bid="64100", rest_ask="64101")
            try:
                self.assertEqual(
                    fixture.executor.market(_entry()).status, CommandResultStatus.COMPLETED,
                )
                fixture.session.calls.clear()
                result = fixture.executor.full_close(
                    FullCloseCommandRequest(ClientActionId("robot-full-close"), SYMBOL),
                )
                self.assertEqual(result.status, CommandResultStatus.COMPLETED)
                self.assertEqual(fixture.owner_rest_calls(), [])
                self.assertEqual(len(fixture.session.calls), 1)
                self.assertLess(fixture.slowest_owner_ms(), 1000)
                entry, close = fixture.executions()
                self.assertEqual(close[:2], (OrderSide.SELL, Decimal("64100")))
                self.assertEqual(close[2], entry[2])
                position = fixture.position()
                self.assertEqual((position.side, position.quantity.value), (PositionSide.FLAT, Decimal("0")))

                # Repeated full-close on a flat position is a no-op, never a reversal.
                fixture.session.calls.clear()
                again = fixture.executor.full_close(
                    FullCloseCommandRequest(ClientActionId("robot-full-close-2"), SYMBOL),
                )
                self.assertEqual(again.status, CommandResultStatus.COMPLETED)
                self.assertEqual(len(fixture.executions()), 2)
                self.assertEqual(fixture.position().side, PositionSide.FLAT)
                self.assertEqual(fixture.owner_rest_calls(), [])
            finally:
                fixture.close()

    def test_owner_originated_full_close_without_stream_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                fixture.executor.market(_entry())
                fixture.session.calls.clear()
                # robot_close_all/_DirectRobotActionExecutor run ON the owner:
                # with no streamed book there is no evidence and no REST.
                result = fixture.serialized.call(
                    lambda owner: owner._robot_full_close(
                        FullCloseCommandRequest(ClientActionId("owner-close"), SYMBOL),
                    )
                )
                self.assertNotEqual(result.status, CommandResultStatus.COMPLETED)
                self.assertEqual(fixture.session.calls, [])
                self.assertEqual(len(fixture.executions()), 1)
                self.assertEqual(fixture.position().side, PositionSide.LONG)
            finally:
                fixture.close()


if __name__ == "__main__":
    unittest.main()
