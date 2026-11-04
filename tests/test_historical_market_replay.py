"""Focused contract checks for isolated, no-look-ahead historical trade replay."""
from decimal import Decimal
import unittest

from research.historical_market_replay import Candle, EntryIntent, replay_candles


def candle(index, open_, high, low, close, *, interval=300_000):
    return Candle(index * interval, interval, open_, high, low, close, 100)


class HistoricalMarketReplayTests(unittest.TestCase):
    def test_entry_only_at_next_open_and_stop_first_on_ambiguous_bar(self):
        bars = (
            candle(0, 100, 101, 99, 100),
            candle(1, 100, 110, 90, 105),  # BOTH 95 STOP and 108 TAKE crossed
        )
        views = []

        def strategy(view):
            views.append((view.signal_time_ms, len(view.closed_history), view.bar.close))
            return EntryIntent("LONG", 1, 95, 108) if len(views) == 1 else None

        result = replay_candles(
            simulation_run_id="fixture-a", candles=bars,
            on_closed_bar=strategy, taker_fee_rate=Decimal("0"),
        )
        self.assertEqual(views, [(300_000, 1, Decimal(100)), (600_000, 2, Decimal(105))])
        self.assertEqual(result.source, "SIMULATION")
        self.assertEqual(result.trades[0].entry_time_ms, 300_000)
        self.assertEqual(result.trades[0].entry_price, Decimal(100))
        self.assertEqual(result.trades[0].exit_reason, "STOP")
        self.assertEqual(result.trades[0].exit_price, Decimal(95))
        self.assertEqual(result.realized_cash, Decimal(4995))
        self.assertTrue(result.trades[0].trade_id.startswith("SIMULATION:fixture-a:"))

    def test_final_bar_signal_never_fills_and_no_external_outputs(self):
        result = replay_candles(
            simulation_run_id="no-fill",
            candles=(candle(0, 100, 101, 99, 100),),
            on_closed_bar=lambda _: EntryIntent("LONG", 1, 95, 108),
        )
        self.assertEqual(result.trades, ())
        self.assertFalse(result.open_position)
        self.assertEqual(result.realized_cash, Decimal(5000))

    def test_entry_gap_skips_stale_trade_and_stop_gap_is_adverse(self):
        views = 0

        def signal(_):
            nonlocal views
            views += 1
            return EntryIntent("LONG", 1, 95, 108) if views == 1 else None

        result = replay_candles(
            simulation_run_id="gap",
            candles=(
                candle(0, 100, 102, 98, 100),
                candle(1, 100, 101, 98, 100),
                candle(2, 90, 92, 88, 90),
            ),
            on_closed_bar=signal, taker_fee_rate=Decimal("0"),
        )
        self.assertEqual(result.trades[0].exit_price, Decimal(90))
        self.assertEqual(result.realized_cash, Decimal(4990))

        skipped = replay_candles(
            simulation_run_id="skip",
            candles=(candle(0, 100, 101, 99, 100),
                     candle(1, 120, 121, 119, 120)),
            on_closed_bar=lambda view: EntryIntent("LONG", 1, 95, 108)
            if len(view.closed_history) == 1 else None,
        )
        self.assertEqual(skipped.trades, ())
        self.assertFalse(skipped.open_position)

    def test_fees_are_debited_once_and_run_ids_are_disjoint(self):
        bars = (
            candle(0, 100, 101, 99, 100),
            candle(1, 100, 110, 99, 109),
        )
        def strategy(view):
            return EntryIntent("LONG", 1, 95, 108) if len(view.closed_history) == 1 else None

        def run(run_id):
            return replay_candles(
                simulation_run_id=run_id, candles=bars,
                on_closed_bar=strategy, taker_fee_rate=Decimal("0.001"),
            )

        first, second = run("one"), run("two")
        self.assertEqual(first.trades[0].fees, Decimal("0.208"))
        self.assertEqual(first.trades[0].net_pnl, Decimal("7.792"))
        self.assertEqual(first.realized_cash, Decimal("5007.792"))
        self.assertNotEqual(first.trades[0].trade_id, second.trades[0].trade_id)
        self.assertEqual(first.trades[0].source, "SIMULATION")

    def test_never_release_future_or_overlapping_bars(self):
        seen = []
        bars = (
            candle(0, 100, 101, 99, 100),
            candle(1, 101, 103, 100, 102),
            candle(2, 102, 104, 101, 103),
        )
        replay_candles(
            simulation_run_id="causal",
            candles=bars,
            on_closed_bar=lambda view: seen.append(
                (view.signal_time_ms, len(view.closed_history),
                 max(x.high for x in view.closed_history))
            ),
        )
        self.assertEqual(seen, [
            (300_000, 1, Decimal(101)),
            (600_000, 2, Decimal(103)),
            (900_000, 3, Decimal(104)),
        ])
        with self.assertRaises(ValueError):
            replay_candles(
                simulation_run_id="bad", candles=(bars[1], bars[0]),
                on_closed_bar=lambda _: None,
            )
        with self.assertRaises(ValueError):
            replay_candles(
                simulation_run_id="../paper", candles=bars,
                on_closed_bar=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()
