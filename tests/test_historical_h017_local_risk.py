"""Opt-in H-017 risk model: deposit, structural stop, minimum 1R and 20 slots."""
from decimal import Decimal
import unittest

from research.h017_local_risk import H017LocalRiskPolicy
from research.historical_market_replay import Candle


def candle(index, *, opened="100", high="100.2", low="99.8", closed="100"):
    return Candle(
        index * 300_000, 300_000, Decimal(opened), Decimal(high),
        Decimal(low), Decimal(closed), Decimal("1"),
    )


class H017RiskPolicyTests(unittest.TestCase):
    def test_fixed_200_usdt_deposit_and_twenty_ten_usdt_slots(self):
        policy = H017LocalRiskPolicy()
        self.assertEqual(policy.initial_cash, Decimal("200"))
        self.assertEqual(policy.max_open_positions, 20)
        self.assertEqual(policy.slot_budget, Decimal("10"))
        self.assertEqual(policy.max_stop_fraction, Decimal("0.007"))
        self.assertEqual(policy.minimum_reward_risk, Decimal("1"))

    def test_long_short_stops_use_one_known_tick_beyond_extreme_if_under_07_percent(self):
        policy = H017LocalRiskPolicy()
        long = policy.proposal(
            side="LONG", expected_entry="100", confirmed_extreme="99.7",
            tick_size="0.01", target="100.31",
        )
        self.assertIsNotNone(long)
        self.assertEqual(long.stop, Decimal("99.69"))
        self.assertEqual(long.take, Decimal("100.31"))
        self.assertEqual(long.quantity, Decimal("0.1"))

        short = policy.proposal(
            side="SHORT", expected_entry="100", confirmed_extreme="100.2",
            tick_size="0.01", target="99.79",
        )
        self.assertIsNotNone(short)
        self.assertEqual(short.stop, Decimal("100.21"))
        self.assertEqual(short.take, Decimal("99.79"))

    def test_distant_missing_and_boundary_extremes_use_fixed_07_percent(self):
        policy = H017LocalRiskPolicy()
        for kwargs in (
            {"confirmed_extreme": "98", "tick_size": "0.01"},
            {"confirmed_extreme": "99.31", "tick_size": "0.01"},
            {"confirmed_extreme": "99.6"},
            {},
        ):
            with self.subTest(kwargs=kwargs):
                proposal = policy.proposal(
                    side="LONG", expected_entry="100", target="100.7", **kwargs,
                )
                self.assertIsNotNone(proposal)
                self.assertEqual(proposal.stop, Decimal("99.300"))
        short = policy.proposal(
            side="SHORT", expected_entry="100", target="99.3",
            confirmed_extreme="105", tick_size="0.01",
        )
        self.assertIsNotNone(short)
        self.assertEqual(short.stop, Decimal("100.700"))
        with self.assertRaises(ValueError):
            policy.proposal(side="LONG", expected_entry="100", target="101",
                            confirmed_extreme="99.8", tick_size="0")

    def test_rejects_less_than_one_to_one_and_missing_real_target(self):
        policy = H017LocalRiskPolicy()
        self.assertIsNone(policy.proposal(
            side="LONG", expected_entry="100", target="100.30",
            confirmed_extreme="99.7", tick_size="0.01",
        ))
        self.assertIsNone(policy.proposal(
            side="SHORT", expected_entry="100", target="99.4",
        ))
        with self.assertRaises(ValueError):
            policy.proposal(side="LONG", expected_entry="100", target=None)

    def test_replay_opens_twenty_concurrent_budgeted_positions_never_twenty_one(self):
        policy = H017LocalRiskPolicy()
        bars = tuple(candle(i) for i in range(26))
        views = []
        events = []

        def signal(view):
            views.append((view.signal_time_ms, view.open_positions_count))
            return policy.proposal(side="LONG", expected_entry="100", target="101")

        result = policy.replay(
            simulation_run_id="h017-twenty", candles=bars,
            on_closed_bar=signal, on_visual_event=events.append,
        )
        fills = [e for e in events if e.kind == "ENTRY_FILLED"]
        self.assertEqual(result.initial_cash, Decimal("200"))
        self.assertEqual(result.peak_open_positions, 20)
        self.assertTrue(result.open_position)
        self.assertEqual(len(fills), 20)
        self.assertEqual(len({event.trade_id for event in fills}), 20)
        self.assertEqual(len(result.trades), 0)
        self.assertTrue(all(e.source == "SIMULATION" for e in events))
        self.assertTrue(all(e.candle is None for e in fills))
        self.assertEqual(views[-1][1], 20)
        self.assertTrue(all(fill.price == Decimal("100") for fill in fills))
        self.assertTrue(all(fill.stop == Decimal("99.300") for fill in fills))
        self.assertLess(result.final_mark_to_market_equity, Decimal("200"))
        self.assertGreater(result.final_mark_to_market_equity, Decimal("199.8"))
        self.assertEqual(result.final_mark_to_market_equity, result.realized_cash)
        self.assertGreater(result.realized_cash, Decimal("199.8"))

    def test_gap_rechecks_actual_open_and_does_not_fill_worse_than_07_percent(self):
        policy = H017LocalRiskPolicy()
        bars = (
            candle(0),
            candle(1, opened="100.2", high="100.3", low="100.0", closed="100.1"),
        )
        result = policy.replay(
            simulation_run_id="h017-gap", candles=bars,
            on_closed_bar=lambda view: policy.proposal(
                side="LONG", expected_entry="100", target="100.7",
            ) if len(view.closed_history) == 1 else None,
        )
        self.assertEqual(result.peak_open_positions, 0)
        self.assertFalse(result.open_position)
        self.assertEqual(result.realized_cash, Decimal("200"))

    def test_slot_can_be_reused_after_stop_and_cash_losses_remain_truthful(self):
        policy = H017LocalRiskPolicy()
        bars = (
            candle(0),
            candle(1, high="100.2", low="99.2", closed="99.5"),
            candle(2),
            candle(3, high="100.2", low="99.2", closed="99.5"),
        )
        seen = []
        def signal(view):
            if len(view.closed_history) in (1, 3):
                return policy.proposal(
                    side="LONG", expected_entry="100", target="101",
                )
            return None
        result = policy.replay(
            simulation_run_id="h017-repeat", candles=bars,
            on_closed_bar=signal, on_visual_event=seen.append,
        )
        self.assertEqual(len(result.trades), 2)
        self.assertEqual(result.peak_open_positions, 1)
        self.assertEqual([t.exit_reason for t in result.trades], ["STOP", "STOP"])
        self.assertLess(result.realized_cash, Decimal("200"))
        self.assertFalse(result.open_position)
        self.assertEqual(len({t.trade_id for t in result.trades}), 2)
        # Decimal intermediate rounding may differ by one far-sub-cent ULP
        # when independently accumulating fills versus reported net PnL.
        expected = Decimal("200") + sum((t.net_pnl for t in result.trades), Decimal(0))
        self.assertEqual(result.realized_cash.quantize(Decimal("1e-18")),
                         expected.quantize(Decimal("1e-18")))


if __name__ == "__main__":
    unittest.main()
