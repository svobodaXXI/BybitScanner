"""Deterministic SIMULATION-only GTC LIMIT matching; no Robot policy, no network."""
import unittest
from decimal import Decimal as D

from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_account import VirtualAccount
from research.simulator_v2.virtual_exchange import (
    LimitRequest, MarketRequest, VirtualExchange,
)


def bar(i, opening="100", high="110", low="90", closing="100"):
    return Candle(
        start_ms=i * MINUTE_MS, interval_ms=MINUTE_MS,
        open=D(opening), high=D(high), low=D(low),
        close=D(closing), volume=D("10"),
    )


def exchange(balance="1000", maker_fee="0.0002", taker_fee="0.0006"):
    return VirtualExchange(
        account=VirtualAccount(
            simulation_run_id="limtest", symbol="BTCUSDT",
            initial_balance=D(balance),
        ),
        maker_fee_rate=D(maker_fee), taker_fee_rate=D(taker_fee),
    )


class SimGtcLimitTests(unittest.TestCase):
    def test_buy_remains_gtc_until_strict_trade_through_then_maker_fill(self):
        ex = exchange()
        ex.on_closed_minute(bar(0))
        request = LimitRequest("buy1", "BUY", D("2"), D("95"))
        ex.submit_limit(request, submitted_at_ms=MINUTE_MS)
        self.assertEqual(ex.account.fills, ())
        self.assertIsNone(ex.on_closed_minute(bar(1, high="100", low="95")))
        self.assertEqual(ex.pending, request)
        self.assertIsNone(ex.on_closed_minute(bar(2, high="101", low="96")))
        self.assertEqual(ex.pending, request)
        fill = ex.on_closed_minute(bar(3, high="101", low="94"))
        self.assertEqual(fill.price, D("95"))
        self.assertEqual(fill.quantity, D("2"))
        self.assertEqual(fill.fee, D("0.038"))
        self.assertEqual(fill.virtual_time_ms, 4 * MINUTE_MS)
        self.assertEqual(ex.account.fills, (fill,))
        self.assertIsNone(ex.pending)
        self.assertEqual(
            [(e.kind, e.order_type) for e in ex.events],
            [("SUBMITTED", "LIMIT"), ("FILLED", "LIMIT")],
        )

    def test_sell_limit_requires_strict_high_past_price(self):
        ex = exchange()
        ex.on_closed_minute(bar(0))
        ex.submit_limit(LimitRequest("sell1", "SELL", D("1"), D("105")),
                        submitted_at_ms=MINUTE_MS)
        self.assertIsNone(ex.on_closed_minute(bar(1, high="105", low="99")))
        fill = ex.on_closed_minute(bar(2, high="106", low="98"))
        self.assertEqual(fill.side, "SELL")
        self.assertEqual(fill.price, D("105"))
        self.assertEqual(fill.fee, D("0.021"))
        snap = ex.account.snapshot(as_of_ms=3 * MINUTE_MS, mark_price=D("100"))
        self.assertEqual(snap.position_quantity, D("-1"))

    def test_marketable_open_does_not_invent_price_improvement(self):
        for side, open_price, limit in (("BUY", "94", "95"), ("SELL", "106", "105")):
            with self.subTest(side=side):
                ex = exchange()
                ex.on_closed_minute(bar(0))
                ex.submit_limit(LimitRequest("open1", side, D("1"), D(limit)),
                                submitted_at_ms=MINUTE_MS)
                fill = ex.on_closed_minute(bar(
                    1, opening=open_price, high="110", low="90", closing="100",
                ))
                self.assertEqual(fill.price, D(limit))
                self.assertEqual(fill.fee, D(limit) * D("0.0006"))

    def test_amend_and_cancel_preserve_one_order_identity(self):
        ex = exchange()
        ex.on_closed_minute(bar(0))
        original = LimitRequest("change1", "BUY", D("1"), D("95"))
        ex.submit_limit(original, submitted_at_ms=MINUTE_MS)
        ex.on_closed_minute(bar(1, low="96"))
        updated = LimitRequest("change1", "BUY", D("1"), D("97"))
        with self.assertRaises(ValueError):
            ex.amend_limit(LimitRequest("foreign", "BUY", D("1"), D("97")),
                           amended_at_ms=2 * MINUTE_MS)
        with self.assertRaises(ValueError):
            ex.amend_limit(LimitRequest("change1", "SELL", D("1"), D("97")),
                           amended_at_ms=2 * MINUTE_MS)
        with self.assertRaises(ValueError):
            ex.amend_limit(updated, amended_at_ms=MINUTE_MS)
        ex.amend_limit(updated, amended_at_ms=2 * MINUTE_MS)
        self.assertEqual(ex.pending, updated)
        self.assertEqual([v.kind for v in ex.events], ["SUBMITTED", "AMENDED"])
        fill = ex.on_closed_minute(bar(2, low="96"))
        self.assertEqual(fill.price, D("97"))
        with self.assertRaises(ValueError):
            ex.submit_limit(original, submitted_at_ms=3 * MINUTE_MS)
        self.assertEqual(len(ex.account.fills), 1)
        ex.submit_limit(LimitRequest("cancel2", "SELL", D("1"), D("150")),
                        submitted_at_ms=3 * MINUTE_MS)
        ex.cancel_pending("cancel2", cancelled_at_ms=3 * MINUTE_MS)
        ex.on_closed_minute(bar(3))
        self.assertEqual(len(ex.account.fills), 1)
        self.assertEqual(ex.events[-1].order_type, "LIMIT")
        with self.assertRaises(ValueError):
            ex.submit_limit(LimitRequest("cancel2", "SELL", D("1"), D("150")),
                            submitted_at_ms=4 * MINUTE_MS)

    def test_failed_virtual_fee_does_not_advance_limit_or_clock(self):
        ex = exchange(balance="0.01")
        ex.on_closed_minute(bar(0))
        order = LimitRequest("blocked", "BUY", D("1"), D("95"))
        ex.submit_limit(order, submitted_at_ms=MINUTE_MS)
        events = ex.events
        with self.assertRaises(ValueError):
            ex.on_closed_minute(bar(1, low="94"))
        self.assertEqual(ex.events, events)
        self.assertEqual(ex.pending, order)
        self.assertEqual(ex.virtual_time_ms, MINUTE_MS)
        self.assertEqual(ex.account.fills, ())
        ex.cancel_pending("blocked", cancelled_at_ms=MINUTE_MS)
        self.assertIsNone(ex.on_closed_minute(bar(1, low="94")))

    def test_cross_market_and_limit_duplicates_are_rejected(self):
        ex = exchange()
        ex.on_closed_minute(bar(0))
        ex.submit_limit(LimitRequest("once", "BUY", D("1"), D("50")),
                        submitted_at_ms=MINUTE_MS)
        with self.assertRaises(ValueError):
            ex.submit(MarketRequest("other", "BUY", D("1")),
                      submitted_at_ms=MINUTE_MS)
        ex.cancel_pending("once", cancelled_at_ms=MINUTE_MS)
        with self.assertRaises(ValueError):
            ex.submit(MarketRequest("once", "SELL", D("1")),
                      submitted_at_ms=MINUTE_MS)
        with self.assertRaises(ValueError):
            LimitRequest("x", "BUY", D("1"), D("-1"))
        with self.assertRaises(ValueError):
            LimitRequest("x", "BUY", D("1"), D("NaN"))
        with self.assertRaises(ValueError):
            LimitRequest("x", "BUY", D("1"), D("Infinity"))
        with self.assertRaises(ValueError):
            LimitRequest("x", "BUY", D("1"), D("0"))

    def test_session_limit_fill_and_rewind_are_distinct_from_market(self):
        session = VirtualReplaySession(
            simulation_run_id="sessionlim", symbol="BTCUSDT",
            initial_balance=D("1000"), maker_fee_rate=D("0.001"),
        )
        with self.assertRaises(ValueError):
            session.submit_limit(LimitRequest("l", "BUY", D("1"), D("95")))
        session.step(bar(0))
        session.submit_limit(LimitRequest("limit1", "BUY", D("1"), D("95")))
        session.step(bar(1, low="95"))
        self.assertEqual(session.account.fills, ())
        state = session.step(bar(2, low="94"))
        self.assertEqual(state.position_quantity, D("1"))
        self.assertEqual(state.average_entry, D("95"))
        self.assertEqual(state.fees, D("0.095"))
        events = [e for e in session.events if e.source == "EXCHANGE"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "VIRTUAL_LIMIT_FILLED")
        self.assertEqual(dict(events[0].details)["price"], "95")
        self.assertEqual(
            session.account.snapshot(as_of_ms=2 * MINUTE_MS).applied_fills, 0,
        )
        self.assertEqual(
            session.account.snapshot(as_of_ms=3 * MINUTE_MS, mark_price=D("100")).applied_fills, 1,
        )

    def test_session_failed_limit_rolls_back_exact_m1_without_fake_fill(self):
        session = VirtualReplaySession(
            simulation_run_id="limfail", symbol="BTCUSDT",
            initial_balance=D("0.01"),
        )
        session.step(bar(0))
        session.submit_limit(LimitRequest("blocked", "BUY", D("1"), D("95")))
        old_events = session.events
        with self.assertRaises(StepBlocked):
            session.step(bar(1, low="94"))
        self.assertEqual(session.events, old_events)
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.exchange.pending.order_id, "blocked")
        self.assertEqual(session.virtual_time_ms, MINUTE_MS)
        session.cancel_pending("blocked")
        session.resume()
        session.step(bar(1, low="94"))
        self.assertEqual(session.account.fills, ())


if __name__ == "__main__":
    unittest.main()
