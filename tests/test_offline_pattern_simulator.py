"""Focused causal multi-pattern regression tests (offline, no PAPER or HTTP)."""
import unittest
from decimal import Decimal

from research.historical_market_replay import Candle, EntryIntent
from research.offline_pattern_simulator import (
    PatternAdapter, candles_from_rows, simulate_patterns,
)

D = Decimal
STEP = 300_000


def bar(index, *, high="101", low="99", close="100"):
    return Candle(index * STEP, STEP, D("100"), D(high), D(low),
                  D(close), D("10"))


def signal_at_first_close(view):
    if view.five_minute.bar.start_ms == 0:
        return EntryIntent("LONG", D("1"), D("95"), D("104"))
    return None


class OfflinePatternSimulatorTests(unittest.TestCase):
    def test_collision_priority_fill_next_open_and_pattern_attribution(self):
        candles = (
            bar(0), bar(1, high="102"), bar(2, high="106"),
            bar(3),
        )
        result = simulate_patterns(
            simulation_run_id="case-1", candles=candles,
            adapters=[
                PatternAdapter("WEDGE", signal_at_first_close),
                PatternAdapter("TRIANGLE", signal_at_first_close),
            ],
        )
        self.assertEqual(result.replay.source, "SIMULATION")
        self.assertEqual(result.decisions[0].candidates, ("WEDGE", "TRIANGLE"))
        self.assertEqual(result.decisions[0].submitted_pattern, "WEDGE")
        self.assertEqual(len(result.completed_trades), 1)
        labelled = result.completed_trades[0]
        self.assertEqual(labelled.pattern, "WEDGE")
        self.assertEqual(labelled.trade.entry_time_ms, STEP)
        self.assertEqual(labelled.trade.exit_time_ms, 3 * STEP)
        self.assertEqual(labelled.trade.exit_reason, "TAKE")
        self.assertLess(labelled.trade.net_pnl, labelled.trade.gross_pnl)
        self.assertEqual(result.per_pattern[0].completed_trades, 1)
        self.assertEqual(result.per_pattern[1].candidate_signals, 1)
        self.assertEqual(result.per_pattern[1].completed_trades, 0)
        self.assertTrue(all(e.source == "SIMULATION" for e in result.visual_events))

    def test_ambiguous_stop_and_take_resolve_to_stop(self):
        result = simulate_patterns(
            simulation_run_id="case-2",
            candles=(bar(0), bar(1, high="120", low="80")),
            adapters=[PatternAdapter("BOX", signal_at_first_close)],
            taker_fee_rate=D("0"), adverse_slippage_rate=D("0"),
        )
        self.assertEqual(result.completed_trades[0].trade.exit_reason, "STOP")
        self.assertEqual(result.completed_trades[0].trade.exit_price, D("95"))

    def test_last_bar_signal_never_fills(self):
        result = simulate_patterns(
            simulation_run_id="case-3",
            candles=(bar(0),),
            adapters=[PatternAdapter("L_SHAPE", signal_at_first_close)],
        )
        self.assertEqual(result.replay.trades, ())
        self.assertEqual(result.per_pattern[0].completed_trades, 0)

    def test_callback_only_receives_closed_prefix_and_completed_higher_tf(self):
        candles = tuple(bar(i) for i in range(49))
        seen = []

        def inspect(view):
            history = view.five_minute.closed_history
            self.assertEqual(history[-1], view.five_minute.bar)
            self.assertTrue(all(b.end_ms <= view.five_minute.signal_time_ms for b in history))
            for htf in (view.last_closed_1h, view.last_closed_4h):
                if htf is not None:
                    self.assertLessEqual(htf.end_ms, view.five_minute.signal_time_ms)
            seen.append((
                view.five_minute.bar.start_ms,
                view.last_closed_4h is not None,
            ))
            return None

        result = simulate_patterns(
            simulation_run_id="case-4", candles=candles,
            adapters=[PatternAdapter("H1_TREND", inspect)],
        )
        self.assertEqual(len(seen), 49)
        self.assertTrue(all(not closed for _, closed in seen[:47]))
        self.assertTrue(seen[47][1])
        self.assertEqual(result.replay.trades, ())

    def test_rejects_gaps_unsafe_run_ids_and_duplicate_adapters(self):
        with self.assertRaises(ValueError):
            simulate_patterns(
                simulation_run_id="case-5", candles=(bar(0), bar(2)),
                adapters=[PatternAdapter("A", lambda _: None)],
            )
        with self.assertRaises(ValueError):
            simulate_patterns(
                simulation_run_id="../paper", candles=(bar(0),),
                adapters=[PatternAdapter("A", lambda _: None)],
            )
        with self.assertRaises(ValueError):
            simulate_patterns(
                simulation_run_id="case-6", candles=(bar(0),),
                adapters=[
                    PatternAdapter("A", lambda _: None),
                    PatternAdapter("A", lambda _: None),
                ],
            )

    def test_rejects_non_intent_and_does_not_invent_rules(self):
        with self.assertRaises(TypeError):
            simulate_patterns(
                simulation_run_id="case-7", candles=(bar(0),),
                adapters=[PatternAdapter("UNKNOWN", lambda _: True)],
            )

    def test_public_history_adapter_and_reproducibility(self):
        rows = [
            {"time": str(b.start_ms), "open": str(b.open), "high": str(b.high),
             "low": str(b.low), "close": str(b.close), "volume": str(b.volume)}
            for b in (bar(0), bar(1, high="102"), bar(2, high="106"))
        ]
        candles = candles_from_rows(rows)
        adapters = [PatternAdapter("DOUBLE_TOP", signal_at_first_close)]
        first = simulate_patterns(
            simulation_run_id="repro", candles=candles, adapters=adapters,
        )
        second = simulate_patterns(
            simulation_run_id="repro", candles=candles, adapters=adapters,
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
