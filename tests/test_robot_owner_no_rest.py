"""P0-B: no provider REST on the PAPER owner thread in Robot dispatch.

Before: every Robot monitor tick dispatched robot_match_symbol() for each
RETEST_DETECTED candidate with a resting entry LIMIT onto the serialized
owner, which read LiveOrderBookProvider.get_book() -- a synchronous Bybit
REST request (10 s timeout) whenever the Workspace was not showing that
symbol. _dispatch_robot_market_book() likewise routed a plain provider read
(with the same REST fallback) through the owner.

After: robot_match_symbol() matches only the already-streamed book (entry
coverage is armed before the LIMIT exists); the monitor's market-book read
runs on the monitor's own thread, and on the owner only a streamed book is
ever used.
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
    ClientActionId, CommandResultStatus, LimitCommandRequest, TimeInForce,
    VolumeRequest, VolumeUnit,
)
from terminal.domain.models import OrderSide, TradingAccountId
from terminal.runtime.paper_http_server import LiveOrderBookProvider, PublicOrderBookBuffer
from terminal.runtime.paper_runtime import PaperRuntime, RobotPaperActionExecutor
from tests.test_robot_protection_close_no_rest import _Context, _Hub, _SlowRestSession, _stream
from tests.test_terminal_paper_runtime import _instrument


SYMBOL = "BTCUSDT"
ACCOUNT = TradingAccountId("paper")


class _Fixture:
    """A Robot resting entry BUY LIMIT on BTCUSDT while the Workspace shows
    ONGUSDT -- the normal case for a Robot candidate."""

    def __init__(self, temp: str, *, hub: bool = True, workspace_symbol: str = "ONGUSDT",
                 rest_delay_s: float = 2.0) -> None:
        self.coverage = PublicOrderBookBuffer(SYMBOL)
        _stream(self.coverage, bid="64260", ask="64261")  # above the LIMIT: no fill yet
        workspace = PublicOrderBookBuffer(workspace_symbol)
        if workspace_symbol == SYMBOL:
            self.coverage = workspace
            _stream(workspace, bid="64260", ask="64261")
        else:
            _stream(workspace, bid="0.2", ask="0.21")
        # REST would report a crossing ask: any fill from it would be fabricated
        # relative to the streamed evidence.
        self.session = _SlowRestSession(delay_s=rest_delay_s, bid="64240", ask="64241")
        self.provider = LiveOrderBookProvider(
            workspace, rest_session=self.session,
            hub=_Hub(_Context(SYMBOL, self.coverage)) if hub else None,
        )
        primary = _instrument()
        self.runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3", book_provider=self.provider,
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(primary, symbol=symbol),
        )
        self.runtime._robot_command_dispatcher = lambda operation: operation(self.runtime)
        submitted = RobotPaperActionExecutor(self.runtime).create_limit(LimitCommandRequest(
            ClientActionId("robot-entry-limit"), SYMBOL, OrderSide.BUY,
            VolumeRequest(VolumeUnit.USDT, Decimal("321")),
            Decimal("64250.5"), Decimal("64250.5"), TimeInForce.GTC,
        ))
        assert submitted.status is CommandResultStatus.COMPLETED
        self.order_id = submitted.order_id
        self.session.calls.clear()

    def match(self) -> tuple[int, float]:
        started = time.perf_counter()
        applied = self.runtime.robot_match_symbol(SYMBOL)
        return applied, (time.perf_counter() - started) * 1000

    def fills(self):
        return [
            (item.price.value, item.quantity.value)
            for item in self.runtime.store.load_executions()
        ]


class RobotMatchSymbolOwnerIoTests(unittest.TestCase):
    def test_match_uses_streamed_coverage_book_with_zero_rest(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                self.assertEqual(fixture.match()[0], 0)  # streamed ask above LIMIT
                _stream(fixture.coverage, bid="64249.5", ask="64250.5")
                applied, owner_ms = fixture.match()
                self.assertEqual(applied, 1)
                self.assertEqual(fixture.session.calls, [])
                self.assertLess(owner_ms, 1000)
                self.assertEqual(len(fixture.fills()), 1)
                self.assertEqual(fixture.fills()[0][0], Decimal("64250.5"))

                # Replay of the same streamed evidence never fills twice.
                self.assertEqual(fixture.match()[0], 0)
                self.assertEqual(len(fixture.fills()), 1)
                self.assertEqual(fixture.session.calls, [])
            finally:
                fixture.runtime.close()

    def test_fill_equals_workspace_streamed_path(self):
        results = []
        for workspace_symbol in ("ONGUSDT", SYMBOL):
            with tempfile.TemporaryDirectory() as temp:
                fixture = _Fixture(temp, workspace_symbol=workspace_symbol)
                try:
                    _stream(fixture.coverage, bid="64249.5", ask="64250.5")
                    self.assertEqual(fixture.match()[0], 1)
                    order = fixture.runtime.store.get_paper_limit(fixture.order_id, ACCOUNT)
                    results.append((fixture.fills(), order.status, order.filled_quantity))
                    self.assertEqual(fixture.session.calls, [])
                finally:
                    fixture.runtime.close()
        self.assertEqual(results[0], results[1])

    def test_missing_streamed_book_matches_nothing_and_never_calls_rest(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, hub=False)
            try:
                applied, owner_ms = fixture.match()
                self.assertEqual(applied, 0)
                self.assertEqual(fixture.session.calls, [])
                self.assertLess(owner_ms, 1000)
                self.assertEqual(fixture.fills(), [])
                order = fixture.runtime.store.get_paper_limit(fixture.order_id, ACCOUNT)
                self.assertEqual((order.status, order.filled_quantity), ("open", Decimal("0")))
            finally:
                fixture.runtime.close()


class RobotMarketBookDispatchTests(unittest.TestCase):
    def test_market_book_read_runs_on_caller_thread_not_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, hub=False, rest_delay_s=0.0)
            dispatched = []
            fixture.runtime._robot_command_dispatcher = (
                lambda operation: dispatched.append(operation) or operation(fixture.runtime)
            )
            try:
                # On the owner (store-owning) thread: streamed evidence only.
                self.assertIsNone(fixture.runtime._dispatch_robot_market_book(SYMBOL))
                self.assertEqual(fixture.session.calls, [])

                # From the monitor thread: the provider read (REST fallback
                # included) happens there, and nothing is queued to the owner.
                result = {}
                worker = threading.Thread(
                    target=lambda: result.setdefault(
                        "book", fixture.runtime._dispatch_robot_market_book(SYMBOL),
                    ),
                    name="robot-breakout-monitor",
                )
                worker.start()
                worker.join(10)
                self.assertEqual(result["book"].asks[0].price.value, Decimal("64241"))
                self.assertEqual(fixture.session.calls, [("robot-breakout-monitor", SYMBOL)])
                self.assertEqual(dispatched, [])
            finally:
                fixture.runtime.close()


if __name__ == "__main__":
    unittest.main()
