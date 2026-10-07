"""P0-B slice 4: read-side / one-shot owner-thread paths never do network I/O.

open_positions() valued every open position with
LiveOrderBookProvider.get_book(): a synchronous Bybit REST request (10 s
timeout) per position whose symbol the Workspace was not streaming, run
serially on the serialized PAPER owner. It now values only from an
already-streamed book; without a fresh one the position is returned without
a mark (the existing current_price/unrealized_pnl None semantics).

Owner-thread one-shot monitors (event fill finalization, continuity
recovery, the _match_symbol Box branch) read closed candles through
CachedClosedCandleProvider, which fetched in place on an owner cache miss.
They now use the cache's non-fetching peek; only the background monitor
thread keeps the fetching provider.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import inspect
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from terminal.api.models import (
    ClientActionId, CommandResultStatus, MarketCommandRequest, VolumeRequest, VolumeUnit,
)
from terminal.domain.models import OrderSide
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.paper_http_server import LiveOrderBookProvider, PublicOrderBookBuffer
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_robot_protection_close_no_rest import _Context, _Hub, _SlowRestSession, _stream
from tests.test_terminal_paper_runtime import _crossing_book, _instrument


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


class _Fixture:
    """Three manual PAPER LONG positions. Afterwards the Workspace shows
    ONGUSDT and only BTCUSDT has a streamed (coverage) book; REST is slow."""

    def __init__(self, temp: str, *, rest_delay_s: float = 2.0, candle_fetch=None) -> None:
        self.session = _SlowRestSession(bid="64249.5", ask="64250.5")
        self.coverage = PublicOrderBookBuffer("BTCUSDT")
        workspace = PublicOrderBookBuffer("ONGUSDT")
        _stream(workspace, bid="0.2", ask="0.21")
        self.provider = LiveOrderBookProvider(
            workspace, rest_session=self.session,
            hub=_Hub(_Context("BTCUSDT", self.coverage)),
        )
        primary = _instrument()
        self.candle_fetches: list[str] = []
        self.runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3", book_provider=self.provider,
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(primary, symbol=symbol),
            robot_closed_candle_provider=CachedClosedCandleProvider(
                candle_fetch or (lambda symbol: self.candle_fetches.append(symbol) or None)
            ),
        )
        for symbol in SYMBOLS:  # manual entries (provider path, fast REST in setup)
            result = self.runtime.api.market(MarketCommandRequest(
                ClientActionId(f"manual-{symbol}"), symbol, OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            assert result.status is CommandResultStatus.COMPLETED, result
        self.session.calls.clear()
        self.session.delay_s = rest_delay_s

    def open_positions(self):
        started = time.perf_counter()
        response = self.runtime.open_positions()
        return response, (time.perf_counter() - started) * 1000


class OpenPositionsOwnerIoTests(unittest.TestCase):
    def test_owner_makes_zero_network_calls_and_does_not_serialize_rest(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                _stream(fixture.coverage, bid="64299.5", ask="64300.5")
                response, owner_ms = fixture.open_positions()
                self.assertEqual(fixture.session.calls, [])
                # Three positions, 2 s REST each before: now no wait at all.
                self.assertLess(owner_ms, 1000)
                self.assertEqual(
                    [item.symbol for item in response.positions], sorted(SYMBOLS),
                )
            finally:
                fixture.runtime.close()

    def test_streamed_book_valuation_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                _stream(fixture.coverage, bid="64299.5", ask="64300.5")
                response, _ = fixture.open_positions()
                btc = next(item for item in response.positions if item.symbol == "BTCUSDT")
                mid = (Decimal("64299.5") + Decimal("64300.5")) / Decimal("2")
                self.assertEqual(btc.current_price, mid)
                self.assertEqual(
                    btc.unrealized_pnl,
                    (mid - btc.average_entry) * btc.position_quantity,
                )
            finally:
                fixture.runtime.close()

    def test_missing_or_stale_book_returns_position_without_mark(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                # Coverage book exists but is stale (> 1 s); ETH/SOL are not streamed.
                _stream(fixture.coverage, bid="64299.5", ask="64300.5")
                time.sleep(1.1)
                response, _ = fixture.open_positions()
                self.assertEqual(fixture.session.calls, [])
                for item in response.positions:
                    self.assertIsNone(item.current_price)
                    self.assertIsNone(item.unrealized_pnl)
                    self.assertGreater(item.position_quantity, 0)
                    self.assertIsNotNone(item.average_entry)
                    self.assertGreater(item.engaged_notional_usdt, 0)
            finally:
                fixture.runtime.close()


class OwnerOneShotClosedCandleTests(unittest.TestCase):
    def test_only_background_monitor_keeps_fetching_candle_provider(self):
        source = inspect.getsource(PaperRuntime)
        self.assertEqual(source.count("get_closed_candle=self._robot_closed_candle_provider"), 1)
        self.assertEqual(source.count("get_closed_candle=self._owner_closed_candle"), 4)

    def test_continuity_recovery_monitor_never_fetches_candles_on_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_delay_s=0.0)
            runtime = fixture.runtime
            captured = []
            real_monitor = __import__(
                "terminal.runtime.paper_runtime", fromlist=["RobotBreakoutMonitor"],
            ).RobotBreakoutMonitor

            def recording_monitor(*args, **kwargs):
                captured.append(kwargs["get_closed_candle"])
                return real_monitor(*args, **kwargs)

            try:
                self.assertEqual(runtime._owner_closed_candle, runtime.robot_closed_candle_cache.peek)
                with patch("terminal.runtime.paper_runtime.RobotBreakoutMonitor", recording_monitor):
                    book = _crossing_book("ETHUSDT", bid="64100", ask="64101")
                    runtime.recover_robot_protection_continuity_loss(
                        "ETHUSDT", book, event_id="ETHUSDT:rest-recovery:1",
                        received_at_ms=book.received_at_ms, reason="ingress_overflow",
                    )
                self.assertEqual(len(captured), 1)
                # Cold cache on the owner: "no candle yet", zero fetches.
                self.assertIsNone(captured[0]("ETHUSDT"))
                self.assertEqual(fixture.candle_fetches, [])
                # Off the owner the cache still fetches (background monitor).
                worker = threading.Thread(
                    target=lambda: runtime.robot_closed_candle_cache("ETHUSDT"),
                )
                worker.start()
                worker.join(5)
                self.assertEqual(fixture.candle_fetches, ["ETHUSDT"])
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
