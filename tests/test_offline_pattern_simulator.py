"""Focused invariants for offline SIMULATION; no network or PAPER dependencies."""
import unittest
from decimal import Decimal

from research.offline_pattern_simulator import Candle, Signal, simulate, candles_from_rows


D = Decimal


class OfflinePatternSimulatorTests(unittest.TestCase):
    def bars(self):
        return (
            Candle(1000, D("100"), D("101"), D("99"), D("100")),
            Candle(2000, D("100"), D("103"), D("99"), D("102")),
            Candle(3000, D("102"), D("106"), D("101"), D("105")),
            Candle(4000, D("105"), D("106"), D("104"), D("105")),
        )

    def test_signal_enters_only_on_next_bar_and_pays_costs(self):
        result = simulate(self.bars(), [Signal(0, "WEDGE", "LONG", D("98"), D("104"))],
                          simulation_run_id="case-1")
        self.assertEqual(result.namespace, "SIMULATION")
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.entry_time_ms, 2000)
        self.assertEqual(trade.exit_time_ms, 3000)
        self.assertEqual(trade.exit_reason, "TAKE")
        self.assertLess(trade.net_pnl, trade.gross_pnl)
        self.assertEqual(result.final_equity, result.initial_equity + trade.net_pnl)

    def test_ambiguous_intrabar_stop_take_is_stop(self):
        bars = (self.bars()[0], Candle(2000, D("100"), D("120"), D("80"), D("100")))
        result = simulate(bars, [Signal(0, "TRIANGLE", "LONG", D("95"), D("105"))],
                          simulation_run_id="case-2", fee_rate=D("0"), slippage_rate=D("0"))
        self.assertEqual(result.trades[0].exit_reason, "STOP")
        self.assertEqual(result.trades[0].exit, D("95"))

    def test_last_bar_decision_does_not_trade(self):
        result = simulate(self.bars(), [Signal(3, "BOX", "SHORT", D("110"), D("90"))],
                          simulation_run_id="case-3")
        self.assertEqual(result.trades, ())

    def test_multiple_simultaneous_patterns_need_explicit_selection(self):
        with self.assertRaises(ValueError):
            simulate(self.bars(), [Signal(0, "WEDGE", "LONG", D("95"), D("110")),
                                   Signal(0, "BOX", "LONG", D("95"), D("110"))],
                     simulation_run_id="case-4")

    def test_invalid_timestamps_and_run_path_fail_closed(self):
        with self.assertRaises(ValueError):
            simulate([self.bars()[0], self.bars()[0]], [], simulation_run_id="case-5")
        with self.assertRaises(ValueError):
            simulate(self.bars(), [], simulation_run_id="../paper")

    def test_replay_adapter_and_reproducibility(self):
        rows = [{"time": str(b.time_ms), "open": str(b.open), "high": str(b.high),
                 "low": str(b.low), "close": str(b.close)} for b in self.bars()]
        bars = candles_from_rows(rows)
        signals = [Signal(0, "DOUBLE_TOP", "LONG", D("98"), D("104"))]
        first = simulate(bars, signals, simulation_run_id="repro")
        second = simulate(bars, signals, simulation_run_id="repro")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
