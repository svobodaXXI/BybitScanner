"""L2 replay output must match immutable event-time receipts, not M1 OHLC."""
from decimal import Decimal as D
import unittest

from research.historical_market_replay import Candle
from research.simulator_v2.historical_orderbook import BookState
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.virtual_exchange import L2PartialTakePolicy
from research.simulator_v2.wedge_visual_replay import WedgeVisualReplay
from robot_entry_flow_evidence import ImpulseProtectedPlan, ImpulseSignal, TakerPrint

M = 60000


def candle(at):
    return Candle(at, M, D("100"), D("200"), D("1"), D("100"), D("1"))


def book(at, bid="99.9", ask="100", bid_size="200", ask_size="200"):
    return BookState(
        "ICNTUSDT", at, at-1, at, at,
        ((D(bid), D(bid_size)),), ((D(ask), D(ask_size)),),
    )


def trade(at, side, price):
    return TakerPrint("ICNTUSDT", f"t{at}", at, side, D(price), D("1"))


def setup(partial=False):
    run_id = "historical_l2_visual_test"
    policy = L2PartialTakePolicy(
        D("0.5"), D("0.25"), D("1"), D("0.1"),
    ) if partial else None
    session = VirtualReplaySession(
        simulation_run_id=run_id, symbol="ICNTUSDT",
        initial_balance=D("1000"), execution_mode="HISTORICAL_L2",
        l2_partial_take_policy=policy,
    )
    plan = ImpulseProtectedPlan(
        ImpulseSignal("LONG", M, D("100"), D("99")),
        D("100"), D("99"), D("104") if partial else D("103"),
        D("100") if partial else D("10"), D("2"), D("100"),
    )
    orders = {f"IMPULSE_{M}": plan}
    recorder = WedgeVisualReplay(
        run_id=run_id, symbol="ICNTUSDT", start_ms=0, end_ms=M*5,
        impulse_plans=orders, historical_l2=True,
    )
    session.step(candle(0))
    session.submit_protected_impulse(plan)
    recorder.record(session, candle(0))
    return session, recorder


def complete(session, recorder):
    for at in (M, M*2, M*3, M*4):
        c = candle(at)
        session.step(c)
        recorder.record(session, c)
    return recorder.document(source_id="verified_trades", expected_fills=len(session.account.fills))


class L2VisualEventTimeTests(unittest.TestCase):
    def test_l2_entry_take_original_time_not_next_m1_close(self):
        session, recorder = setup()
        entry = session.exchange.on_historical_book(book(M+10))
        self.assertEqual(entry.virtual_time_ms, M+10)
        exit_ = session.exchange.on_historical_trade(trade(M+20, "Buy", "103.1"))
        self.assertEqual(exit_.virtual_time_ms, M+20)
        doc = complete(session, recorder)
        fills = [e for e in doc["events"]
                 if e["kind"] in ("ENTRY_FILLED", "EXIT_FILLED")]
        self.assertEqual([e["time_ms"] for e in fills], [M+10, M+20])
        self.assertEqual([e["kind"] for e in fills], ["ENTRY_FILLED", "EXIT_FILLED"])
        self.assertEqual(doc["execution_clock"], "ORIGINAL_EVENT_TIME_NOT_OHLC_M1")
        self.assertEqual(doc["market_data_source"],
                         "PINNED_BYBIT_PUBLIC_TRADES_PLUS_L2_EVENT_TIME_SIMULATION")
        self.assertEqual(D(fills[-1]["net_usdt"]),
                         session.account.snapshot(as_of_ms=M*5).realized_net_pnl)
        self.assertEqual(sum(e["kind"] == "CANDLE_CLOSED" for e in doc["events"]), 1)

    def test_partial_be_stop_marker_and_fee_net_with_exact_receipts(self):
        session, recorder = setup(partial=True)
        exchange = session.exchange
        exchange.on_historical_book(book(M+10))
        exchange.on_historical_book(book(M+20, bid="102.1", ask="102.2"))
        exchange.on_historical_book(book(M+30, bid="102.5", ask="102.6"))
        self.assertEqual(exchange.l2_partial_take_fills, 1)
        self.assertEqual(exchange.l2_be_stop_amendments, 1)
        exchange.on_historical_book(book(M+40, bid="100", ask="100.2"))
        exchange.on_historical_trade(trade(M+50, "Sell", "100"))
        doc = complete(session, recorder)
        events = [e for e in doc["events"]
                  if e["kind"] in (
                      "ENTRY_FILLED", "PARTIAL_FILLED", "STOP_AMENDED", "EXIT_FILLED"
                  )]
        self.assertEqual([e["time_ms"] for e in events],
                         [M+10, M+20, M+30, M+50])
        self.assertEqual(events[1]["quantity"], "25")
        self.assertEqual(D(str(events[2]["stop"])),
                         session.exchange.events[
                             next(i for i, e in enumerate(session.exchange.events)
                                  if e.kind == "STOP_AMENDED_BE")
                         ].stop_price)
        self.assertEqual(events[-1]["quantity"], "75")
        self.assertEqual(events[-1]["reason"], "STOP")
        self.assertEqual(D(events[-1]["net_usdt"]),
                         session.account.snapshot(as_of_ms=M*5).realized_net_pnl)
        self.assertEqual(sum(e["kind"] == "ENTRY_FILLED" for e in events), 1)
        self.assertEqual(doc["execution_certainty"], "CONDITIONAL_L2_NOT_REAL_EXCHANGE_FILLS")

    def test_legacy_visual_rejects_historical_l2_without_explicit_opt_in(self):
        session, _ = setup()
        legacy = WedgeVisualReplay(
            run_id=session.account.simulation_run_id, symbol="ICNTUSDT",
            start_ms=0, end_ms=M*5, impulse_plans={},
        )
        with self.assertRaisesRegex(ValueError, "legacy M1 visual"):
            legacy.record(session, candle(0))


if __name__ == "__main__":
    unittest.main()
