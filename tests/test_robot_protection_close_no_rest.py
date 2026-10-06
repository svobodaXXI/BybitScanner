"""P0 Robot protection latency (Slice 2B): no network I/O in owner-thread
PAPER protection closes.

Before: _dispatch_paper_protection_obligation -> PaperMarketExecutor.execute
-> LiveOrderBookProvider.get_book(symbol). When the Workspace was not
streaming that symbol, get_book fell back to a synchronous Bybit REST request
(10 s timeout) on the single owner thread, which could hold the owner long
enough to overflow the 64-slot protection ingress.

After: owner-thread protection closes execute only against an already-
streamed in-memory book (Workspace buffer or Robot coverage hub context), or,
for continuity recovery only, the authoritative REST snapshot the coverage
manager fetched off the owner thread. Otherwise nothing executes and the
durable obligation resumes on a later quote.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import tempfile
import threading
import time
import unittest

from terminal.domain.models import (
    ExecutionId, OrderId, OrderSide, Quantity, Symbol, TradingAccountId,
)
from terminal.paper.executor import PaperMarketExecutor
from terminal.runtime.paper_http_server import LiveOrderBookProvider, PublicOrderBookBuffer
from tests.test_terminal_paper_runtime import (
    _crossing_book,
    _instrument,
    _open_robot_position_with_confirmed_protection,
    _set_admission,
)
from terminal.runtime.paper_runtime import PaperRuntime
from dataclasses import replace


SYMBOL = "BTCUSDT"
ACCOUNT = TradingAccountId("paper")
_sequence = iter(range(1, 1_000_000))


class _Response:
    def __init__(self, symbol: str, bid: str, ask: str) -> None:
        self._payload = {
            "retCode": 0,
            "result": {"s": symbol, "b": [[bid, "10"]], "a": [[ask, "10"]]},
        }

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _SlowRestSession:
    """Deterministic stand-in for a slow Bybit REST/proxy round trip."""

    def __init__(self, *, delay_s: float = 0.0, bid: str = "63990", ask: str = "63995") -> None:
        self.delay_s = delay_s
        self.bid = bid
        self.ask = ask
        self.calls: list[tuple[str, str]] = []

    def get(self, url, *, params, timeout):
        self.calls.append((threading.current_thread().name, params["symbol"]))
        if self.delay_s:
            time.sleep(self.delay_s)
        return _Response(params["symbol"], self.bid, self.ask)


@dataclass
class _Context:
    symbol: str
    public_orderbook: PublicOrderBookBuffer
    reconnect_count: int = 0


class _Hub:
    def __init__(self, *contexts: _Context) -> None:
        self._contexts = contexts

    def list_contexts(self):
        return self._contexts


def _stream(buffer: PublicOrderBookBuffer, *, bid: str, ask: str) -> None:
    sequence = next(_sequence)
    assert buffer.apply_message({
        "topic": f"orderbook.{buffer.depth}.{buffer.symbol}",
        "type": "snapshot",
        "ts": int(time.time() * 1000),
        "data": {"s": buffer.symbol, "b": [[bid, "10"]], "a": [[ask, "10"]],
                 "u": sequence, "seq": sequence},
    }) == "APPLIED"


class _Fixture:
    """Robot LONG BTCUSDT (entry 64250.5, STOP 64000, TAKE 64600) opened while
    the Workspace streamed BTCUSDT; the Workspace then switched to ONGUSDT --
    exactly the incident shape where protection lost its Workspace book."""

    def __init__(self, temp: str, *, hub: bool = True, rest_delay_s: float = 0.0) -> None:
        self.workspace = PublicOrderBookBuffer(SYMBOL)
        _stream(self.workspace, bid="64249.5", ask="64250.5")
        self.coverage = PublicOrderBookBuffer(SYMBOL)
        _stream(self.coverage, bid="64249.5", ask="64250.5")
        self.session = _SlowRestSession()
        self.provider = LiveOrderBookProvider(
            self.workspace, rest_session=self.session,
            hub=_Hub(_Context(SYMBOL, self.coverage)) if hub else None,
        )
        primary = _instrument()
        self.runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3", book_provider=self.provider,
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(primary, symbol=symbol),
        )
        _open_robot_position_with_confirmed_protection(
            self.runtime, symbol=SYMBOL, entry_price=Decimal("64250.5"),
            stop_price=Decimal("64000"), take_price=Decimal("64600"),
            trade_id="trade-no-rest", candidate_id="candidate-no-rest",
        )
        other = PublicOrderBookBuffer("ONGUSDT")
        _stream(other, bid="0.2", ask="0.21")
        self.provider.set_buffer(other)
        self.session.calls.clear()
        self.session.delay_s = rest_delay_s
        self.entry_executions = len(self.runtime.store.load_executions())

    def event(self, *, bid: str, ask: str):
        book = _crossing_book(SYMBOL, bid=bid, ask=ask)
        started = time.perf_counter()
        result = self.runtime.process_robot_market_event(
            SYMBOL, book, event_id=f"{SYMBOL}:{book.source_sequence}:{book.source_update_id}",
            received_at_ms=book.received_at_ms,
        )
        return result, (time.perf_counter() - started) * 1000

    def trade(self):
        return self.runtime.store.get_robot_trade("trade-no-rest")

    def new_executions(self) -> int:
        return len(self.runtime.store.load_executions()) - self.entry_executions


class ProviderFallbackCharacterizationTests(unittest.TestCase):
    def test_get_book_still_blocks_on_rest_but_streamed_lookup_never_does(self):
        session = _SlowRestSession(delay_s=0.05)
        workspace = PublicOrderBookBuffer("ONGUSDT")
        _stream(workspace, bid="0.2", ask="0.21")
        coverage = PublicOrderBookBuffer(SYMBOL)
        _stream(coverage, bid="64000", ask="64001")
        provider = LiveOrderBookProvider(
            workspace, rest_session=session, hub=_Hub(_Context(SYMBOL, coverage)),
        )

        streamed = provider.get_streamed_book(Symbol(SYMBOL))
        self.assertEqual(streamed.bids[0].price.value, Decimal("64000"))
        self.assertEqual(session.calls, [])
        self.assertIsNone(provider.get_streamed_book(Symbol("ETHUSDT")))
        self.assertEqual(session.calls, [])
        coverage.mark_disconnected()
        self.assertIsNone(provider.get_streamed_book(Symbol(SYMBOL)))
        self.assertEqual(session.calls, [])

        # The pre-2B close path: an executor fed by get_book() performs a
        # synchronous REST round trip on the calling (owner) thread.
        started = time.perf_counter()
        PaperMarketExecutor(
            provider, _NoopEngine(), max_book_age_ms=1000,
            clock_ms=lambda: int(time.time() * 1000),
        ).execute(
            trading_account_id=ACCOUNT, symbol=Symbol(SYMBOL), side=OrderSide.SELL,
            quantity=Quantity(Decimal("0.005")), order_link_id="old-path",
            order_id=OrderId("old-path-order"), exec_id=ExecutionId("old-path-exec"),
        )
        self.assertEqual(session.calls, [(threading.current_thread().name, SYMBOL)])
        self.assertGreaterEqual((time.perf_counter() - started) * 1000, 50)


class _NoopEngine:
    def apply_paper_execution(self, event):
        from terminal.persistence.sqlite_store import ExecutionApplyResult
        return ExecutionApplyResult.APPLIED


class OwnerThreadProtectionCloseTests(unittest.TestCase):
    def test_stop_close_uses_streamed_coverage_book_with_zero_network_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_delay_s=2.0)
            try:
                _stream(fixture.coverage, bid="63990", ask="63995")
                (finalized, obligation), owner_ms = fixture.event(bid="63990", ask="63995")

                self.assertEqual(fixture.session.calls, [])
                self.assertLess(owner_ms, 1000)
                self.assertEqual(obligation.winning_leg, "STOP")
                self.assertEqual(obligation.status, "RESOLVED")
                trade = fixture.trade()
                self.assertEqual((trade.exit_reason, trade.exit_price), ("STOP", Decimal("63990")))
                self.assertEqual(fixture.new_executions(), 1)

                # Duplicate/replayed delivery after resolution closes nothing.
                (_, replay), _ = fixture.event(bid="63980", ask="63985")
                self.assertIsNone(replay)
                self.assertEqual(fixture.new_executions(), 1)
                self.assertEqual(fixture.session.calls, [])
            finally:
                fixture.runtime.close()

    def test_take_close_uses_streamed_coverage_book(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_delay_s=2.0)
            try:
                _stream(fixture.coverage, bid="64610", ask="64615")
                (_, obligation), _ = fixture.event(bid="64610", ask="64615")
                self.assertEqual((obligation.winning_leg, obligation.status), ("TAKE", "RESOLVED"))
                trade = fixture.trade()
                self.assertEqual((trade.exit_reason, trade.exit_price), ("TAKE", Decimal("64610")))
                self.assertEqual(fixture.session.calls, [])
            finally:
                fixture.runtime.close()

    def test_missing_streamed_book_fails_closed_without_rest_or_fill_then_resumes_once(self):
        with tempfile.TemporaryDirectory() as temp:
            # No coverage context and Workspace on another symbol: the only way
            # to a book would be REST, which would happily return a fill price.
            fixture = _Fixture(temp, hub=False, rest_delay_s=2.0)
            try:
                (_, latched), owner_ms = fixture.event(bid="63990", ask="63995")
                self.assertEqual(fixture.session.calls, [])
                self.assertLess(owner_ms, 1000)
                self.assertEqual((latched.winning_leg, latched.status), ("STOP", "DISPATCHING"))
                self.assertEqual(fixture.new_executions(), 0)
                self.assertIsNone(fixture.trade().exit_time_ms)

                # A retreat must not erase the latch; still nothing to execute on.
                (_, retreated), _ = fixture.event(bid="64300", ask="64305")
                self.assertEqual(retreated, latched)
                self.assertEqual(fixture.new_executions(), 0)

                # The Workspace streams the symbol again: resume exactly once.
                fixture.provider.set_buffer(fixture.coverage)
                _stream(fixture.coverage, bid="63970", ask="63975")
                (_, resolved), _ = fixture.event(bid="63960", ask="63965")
                self.assertEqual(resolved.status, "RESOLVED")
                self.assertEqual(resolved.obligation_id, latched.obligation_id)
                self.assertEqual(fixture.trade().exit_price, Decimal("63970"))
                (_, replay), _ = fixture.event(bid="63960", ask="63965")
                self.assertIsNone(replay)
                self.assertEqual(fixture.new_executions(), 1)
                self.assertEqual(fixture.session.calls, [])
            finally:
                fixture.runtime.close()


class ContinuityRecoveryCloseTests(unittest.TestCase):
    def _recover(self, fixture: _Fixture, book):
        return fixture.runtime.recover_robot_protection_continuity_loss(
            SYMBOL, book, event_id=f"{SYMBOL}:rest-recovery:{book.source_sequence}",
            received_at_ms=book.received_at_ms, reason="ingress_overflow",
        )

    def test_stream_down_emergency_close_uses_off_thread_recovery_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_delay_s=2.0)
            try:
                _set_admission(fixture.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
                fixture.coverage.mark_disconnected()
                started = time.perf_counter()
                recovered = self._recover(fixture, _crossing_book(SYMBOL, bid="64100", ask="64101"))
                owner_ms = (time.perf_counter() - started) * 1000

                self.assertTrue(recovered)
                self.assertEqual(fixture.session.calls, [])
                self.assertLess(owner_ms, 1000)
                trade = fixture.trade()
                self.assertEqual(
                    (trade.exit_reason, trade.exit_price), ("EMERGENCY_CLOSE", Decimal("64100")),
                )
                self.assertEqual(fixture.new_executions(), 1)
            finally:
                fixture.runtime.close()

    def test_stale_recovery_snapshot_without_stream_stays_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_delay_s=2.0)
            try:
                _set_admission(fixture.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
                fixture.coverage.mark_disconnected()
                stale = replace(
                    _crossing_book(SYMBOL, bid="64100", ask="64101"),
                    received_at_ms=int(time.time() * 1000) - 5000,
                )
                self.assertFalse(self._recover(fixture, stale))
                self.assertEqual(fixture.session.calls, [])
                self.assertEqual(fixture.new_executions(), 0)
                self.assertIsNone(fixture.trade().exit_time_ms)
                state = fixture.runtime.store.get_robot_runtime_state(ACCOUNT)
                self.assertEqual(state.recovery_status, "RECONCILIATION_REQUIRED")
            finally:
                fixture.runtime.close()


if __name__ == "__main__":
    unittest.main()
