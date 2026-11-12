"""Offline integration of the existing M1 timeline, virtual executor and account."""
import unittest
from decimal import Decimal

from research.historical_market_replay import Candle
from robot_entry_flow_evidence import TakerPrint
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_exchange import MarketRequest

D = Decimal


def bar(index, opening="100", close="105"):
    return Candle(
        start_ms=index * MINUTE_MS, interval_ms=MINUTE_MS,
        open=D(opening), high=D("110"), low=D("90"),
        close=D(close), volume=D("10"),
    )


class VirtualReplaySessionTests(unittest.TestCase):
    def test_full_market_step_fill_equity_and_journal(self):
        session = VirtualReplaySession(
            simulation_run_id="s1", symbol="BTCUSDT",
            initial_balance=D("1000"), taker_fee_rate=D("0.001"),
        )
        first = session.step(bar(0))
        self.assertEqual(first.balance, D("1000"))
        session.submit(MarketRequest("order1", "BUY", D("2")))
        self.assertEqual(session.account.fills, ())
        next_account = session.step(bar(1, opening="102"))
        fill = session.account.fills[0]
        self.assertEqual(fill.price, D("102"))
        self.assertEqual(fill.virtual_time_ms, 2 * MINUTE_MS)
        self.assertEqual(next_account.position_quantity, D("2"))
        self.assertEqual(next_account.balance, D("999.796"))
        self.assertEqual(next_account.unrealized_pnl, D("6"))
        self.assertEqual(next_account.equity, D("1005.796"))
        self.assertEqual([event.kind for event in session.events],
                         ["M1_CLOSED", "M1_CLOSED", "VIRTUAL_MARKET_FILLED"])
        last = session.events[-1]
        self.assertEqual(last.source, "EXCHANGE")
        self.assertEqual(last.entity_id, fill.fill_id)
        self.assertEqual(dict(last.details)["fee"], str(fill.fee))
        self.assertTrue(all(event.source in {"EXCHANGE", "MARKET"}
                            for event in session.events))
        self.assertEqual(session.timeline.virtual_time_ms,
                         session.exchange.virtual_time_ms)

    def test_short_close_and_historical_projection(self):
        session = VirtualReplaySession(
            simulation_run_id="short", symbol="BTCUSDT",
            initial_balance=D("1000"), taker_fee_rate=D("0"),
        )
        session.step(bar(0))
        session.submit(MarketRequest("short1", "SELL", D("1")))
        session.step(bar(1, opening="100"))
        session.submit(MarketRequest("cover1", "BUY", D("1")))
        last = session.step(bar(2, opening="90"))
        self.assertEqual(last.balance, D("1010"))
        self.assertEqual(last.position_quantity, D("0"))
        self.assertEqual(session.account.snapshot(
            as_of_ms=2*MINUTE_MS, mark_price=D("105"),
        ).position_quantity, D("-1"))
        self.assertEqual(session.timeline.events_at(MINUTE_MS), session.events[:1])

    def test_rejects_failed_virtual_fill_without_advanced_clock_or_journal(self):
        session = VirtualReplaySession(
            simulation_run_id="bad", symbol="BTCUSDT",
            initial_balance=D("1"), taker_fee_rate=D("0.1"),
        )
        session.step(bar(0))
        session.submit(MarketRequest("too-much", "BUY", D("1")))
        old_events = session.events
        with self.assertRaises(StepBlocked):
            session.step(bar(1))
        self.assertEqual(session.events, old_events)
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.virtual_time_ms, MINUTE_MS)
        self.assertEqual(session.exchange.virtual_time_ms, MINUTE_MS)
        with self.assertRaises(StepBlocked):
            session.submit(MarketRequest("other", "BUY", D("1")))
        session.cancel_pending("too-much")
        session.resume()
        final = session.step(bar(1))
        self.assertEqual(final.balance, D("1"))
        self.assertEqual([event.kind for event in session.events],
                         ["M1_CLOSED", "M1_CLOSED"])

    def test_cannot_submit_before_any_close_or_skip_bars(self):
        session = VirtualReplaySession(
            simulation_run_id="idle", symbol="BTCUSDT", initial_balance=D("1000"),
        )
        with self.assertRaises(ValueError):
            session.submit(MarketRequest("x", "BUY", D("1")))
        session.step(bar(0))
        with self.assertRaises(ValueError):
            session.step(bar(2))
        self.assertEqual(session.virtual_time_ms, MINUTE_MS)
        self.assertEqual(session.account.fills, ())

    def test_reuses_robot_flow_evidence_without_virtual_orders(self):
        session = VirtualReplaySession(
            simulation_run_id="flow", symbol="ICNTUSDT", initial_balance=D("1000"),
        )
        session.step(bar(0))
        first = (TakerPrint("ICNTUSDT", "a", 50, "Sell", D("100"), D("1")),)
        journal = session.events
        self.assertIsNone(session.observe_committed_taker_prints(first, source_id="archive-sha"))
        self.assertEqual(session.events, journal)
        self.assertIsNone(session.latest_entry_flow)
        session.step(bar(1))
        second = (
            TakerPrint("ICNTUSDT", "b", 60010, "Buy", D("100"), D("3")),
            TakerPrint("ICNTUSDT", "c", 60020, "Buy", D("101"), D("2")),
        )
        result = session.observe_committed_taker_prints(second, source_id="archive-sha")
        self.assertTrue(result.buy_wave_accelerating)
        self.assertEqual(result.known_at_ms, 2 * MINUTE_MS)
        self.assertEqual(session.latest_entry_flow, result)
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.events, journal + session.events[len(journal):])
        self.assertTrue(all(event.source == "MARKET" for event in session.events))

    def test_flow_observation_refuses_uncommitted_or_duplicate_minute(self):
        session = VirtualReplaySession(
            simulation_run_id="flow-gap", symbol="ICNTUSDT", initial_balance=D("1000"),
        )
        one = (TakerPrint("ICNTUSDT", "a", 50, "Buy", D("100"), D("1")),)
        with self.assertRaises(StepBlocked):
            session.observe_committed_taker_prints(one, source_id="raw")
        session.step(bar(0))
        self.assertIsNone(session.observe_committed_taker_prints(one, source_id="raw"))
        with self.assertRaises(ValueError):
            session.observe_committed_taker_prints(one, source_id="raw")
        session.step(bar(1))
        self.assertIsNone(session.observe_committed_taker_prints((), source_id="raw"))
        session.step(bar(2))
        next_print = (TakerPrint("ICNTUSDT", "b", 120010, "Buy", D("100"), D("1")),)
        self.assertIsNone(session.observe_committed_taker_prints(next_print, source_id="raw"))

    def test_no_robot_strategy_or_network_client(self):
        session = VirtualReplaySession(
            simulation_run_id="offline", symbol="ETHUSDT", initial_balance=D("100"),
        )
        self.assertFalse(hasattr(session, "api"))
        self.assertFalse(hasattr(session, "client"))
        self.assertEqual(session.timeline._stages[0][1], None)
        self.assertEqual(session.timeline._stages[1][1], None)
        self.assertIsNotNone(session.timeline._stages[2][1])


if __name__ == "__main__":
    unittest.main()
