"""Virtual-only next-M1-open execution: no external trading endpoints."""
import unittest
from decimal import Decimal

from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MINUTE_MS
from research.simulator_v2.virtual_account import VirtualAccount
from research.simulator_v2.virtual_exchange import (
    MarketRequest,
    RobotStopRequest,
    VirtualExchange,
)

D = Decimal


def bar(index, opening="100", highest="110", lowest="90", closing="105"):
    return Candle(
        start_ms=index * MINUTE_MS, interval_ms=MINUTE_MS,
        open=D(opening), high=D(highest), low=D(lowest),
        close=D(closing), volume=D("10"),
    )


class VirtualExchangeTests(unittest.TestCase):
    def setup_exchange(self, initial=D("1000"), fee=D("0.001")):
        account = VirtualAccount(
            simulation_run_id="sim-1", symbol="BTCUSDT",
            initial_balance=initial,
        )
        return VirtualExchange(account=account, taker_fee_rate=fee)

    def test_order_only_fills_at_following_open_and_account_receives_receipt(self):
        exchange = self.setup_exchange()
        self.assertIsNone(exchange.on_closed_minute(bar(0)))
        self.assertEqual(exchange.virtual_time_ms, MINUTE_MS)
        order = MarketRequest(order_id="order-1", side="BUY", quantity=D("2"))
        exchange.submit(order, submitted_at_ms=MINUTE_MS)
        self.assertEqual(exchange.account.fills, ())
        self.assertEqual(exchange.pending, order)
        fill = exchange.on_closed_minute(bar(1, opening="102", highest="108", lowest="97"))
        self.assertEqual(fill.virtual_time_ms, 2 * MINUTE_MS)
        self.assertEqual(fill.price, D("102"))
        self.assertEqual(fill.fee, D("0.204"))
        self.assertEqual(fill.fill_id, "order-1_fill")
        self.assertEqual(exchange.account.fills, (fill,))
        self.assertIsNone(exchange.pending)
        account = exchange.account.snapshot(as_of_ms=2 * MINUTE_MS, mark_price=D("105"))
        self.assertEqual(account.position_quantity, D("2"))
        self.assertEqual(account.average_entry, D("102"))
        self.assertEqual(account.balance, D("999.796"))
        self.assertEqual(account.unrealized_pnl, D("6"))
        self.assertEqual([e.kind for e in exchange.events], ["SUBMITTED", "FILLED"])

    def test_closed_position_and_net_pnl_reuse_existing_account(self):
        exchange = self.setup_exchange(fee=D("0"))
        exchange.on_closed_minute(bar(0))
        exchange.submit(MarketRequest("entry", "SELL", D("1")), submitted_at_ms=MINUTE_MS)
        exchange.on_closed_minute(bar(1, opening="100"))
        exchange.submit(MarketRequest("exit", "BUY", D("1")), submitted_at_ms=2 * MINUTE_MS)
        exchange.on_closed_minute(bar(2, opening="90"))
        report = exchange.account.snapshot(as_of_ms=3 * MINUTE_MS)
        self.assertEqual(report.position_quantity, D("0"))
        self.assertEqual(report.realized_gross_pnl, D("10"))
        self.assertEqual(report.balance, D("1010"))

    def test_no_holes_duplicates_or_same_candle_lookahead(self):
        exchange = self.setup_exchange()
        with self.assertRaises(ValueError):
            exchange.submit(MarketRequest("id1", "BUY", D("1")), submitted_at_ms=0)
        exchange.on_closed_minute(bar(0))
        exchange.submit(MarketRequest("id1", "BUY", D("1")), submitted_at_ms=MINUTE_MS)
        with self.assertRaises(ValueError):
            exchange.submit(MarketRequest("id2", "BUY", D("1")), submitted_at_ms=MINUTE_MS)
        with self.assertRaises(ValueError):
            exchange.on_closed_minute(bar(0))
        with self.assertRaises(ValueError):
            exchange.on_closed_minute(bar(2))
        self.assertEqual(exchange.account.fills, ())
        self.assertEqual(exchange.virtual_time_ms, MINUTE_MS)
        exchange.on_closed_minute(bar(1))
        with self.assertRaises(ValueError):
            exchange.submit(MarketRequest("id1", "BUY", D("1")), submitted_at_ms=2 * MINUTE_MS)

    def test_cancellation_and_idempotent_order_identity(self):
        exchange = self.setup_exchange()
        exchange.on_closed_minute(bar(0))
        exchange.submit(MarketRequest("cancel1", "BUY", D("1")), submitted_at_ms=MINUTE_MS)
        exchange.cancel_pending("cancel1", cancelled_at_ms=MINUTE_MS)
        self.assertIsNone(exchange.on_closed_minute(bar(1)))
        self.assertEqual(exchange.account.fills, ())
        with self.assertRaises(ValueError):
            exchange.submit(MarketRequest("cancel1", "BUY", D("1")), submitted_at_ms=2 * MINUTE_MS)
        self.assertEqual([e.kind for e in exchange.events], ["SUBMITTED", "CANCELLED"])

    def test_failed_fill_stops_clock_preserves_pending_and_can_cancel(self):
        exchange = self.setup_exchange(initial=D("1"), fee=D("0.1"))
        exchange.on_closed_minute(bar(0))
        request = MarketRequest("too-expensive", "BUY", D("1"))
        exchange.submit(request, submitted_at_ms=MINUTE_MS)
        with self.assertRaises(ValueError):
            exchange.on_closed_minute(bar(1, opening="100"))
        self.assertEqual(exchange.virtual_time_ms, MINUTE_MS)
        self.assertEqual(exchange.pending, request)
        self.assertEqual(exchange.account.fills, ())
        exchange.cancel_pending("too-expensive", cancelled_at_ms=MINUTE_MS)
        self.assertIsNone(exchange.on_closed_minute(bar(1)))

    def test_only_internal_virtual_decimal_orders_are_accepted(self):
        for args in (
            ("one", "BUY", D("0"), "SIMULATION"),
            ("two", "SELL", D("NaN"), "SIMULATION"),
            ("three", "BUY", D("1"), "PAPER"),
            ("four", "LONG", D("1"), "SIMULATION"),
            ("bad/order", "BUY", D("1"), "SIMULATION"),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                MarketRequest(*args)
        exchange = self.setup_exchange()
        self.assertFalse(hasattr(exchange, "api"))
        self.assertFalse(hasattr(exchange, "client"))
        with self.assertRaises(ValueError):
            VirtualExchange(account=exchange.account, taker_fee_rate=D("-0.01"))

    def test_native_robot_markets_fill_one_per_minute_and_stop_has_priority(self):
        exchange = self.setup_exchange(initial=D("10000"), fee=D("0.001"))
        exchange.on_closed_minute(bar(0))
        first = MarketRequest("robot-market-1", "BUY", D("1"))
        second = MarketRequest("robot-market-2", "BUY", D("1"))
        exchange.submit_robot_market(first, submitted_at_ms=MINUTE_MS)
        exchange.submit_robot_market(second, submitted_at_ms=MINUTE_MS)

        exchange.on_closed_minute(bar(
            1, opening="100", highest="104", lowest="99", closing="101",
        ))
        self.assertEqual([fill.fill_id for fill in exchange.last_minute_fills], [
            "robot-market-1_fill",
        ])
        self.assertEqual(exchange.robot_markets, (second,))
        exchange.synchronize_robot_stop(
            RobotStopRequest("robot-stop-1", "LONG", D("95")),
            synchronized_at_ms=2 * MINUTE_MS,
        )

        exchange.on_closed_minute(bar(
            2, opening="94", highest="96", lowest="90", closing="93",
        ))
        self.assertEqual([fill.fill_id for fill in exchange.last_minute_fills], [
            "robot-stop-1_fill",
        ])
        self.assertEqual(exchange.robot_markets, ())
        self.assertIsNone(exchange.robot_stop)
        snapshot = exchange.account.snapshot(as_of_ms=3 * MINUTE_MS, mark_price=D("94"))
        self.assertEqual(snapshot.position_quantity, D("0"))
        self.assertEqual(
            [(event.order_id, event.kind) for event in exchange.events],
            [
                ("robot-market-1", "SUBMITTED"),
                ("robot-market-2", "SUBMITTED"),
                ("robot-market-1", "FILLED"),
                ("robot-stop-1", "STOP_FILLED"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
