"""Scoped, pure decision-time ICNT research diagnostic regressions."""
from decimal import Decimal as D
import unittest

from research.simulator_v2.audit_icnt_impulse_entries import (
    _book_features, decision_features,
)
from research.simulator_v2.historical_orderbook import BookState
from robot_entry_flow_evidence import (
    TakerPrint, aggregate_taker_prints, compare_flow_windows,
    plan_impulse_protected_entry, recognize_impulse_signal,
)


def print_(identity, at, side, price, size):
    return TakerPrint("ICNTUSDT", identity, at, side, D(price), D(size))


def original_plan_and_tape():
    before = (
        print_("older_sell", 61000, "Sell", ".290", "3000"),
        print_("older_buy", 119000, "Buy", ".289", "1000"),
    )
    current = (
        print_("latest_sell", 121000, "Sell", ".2885", "2000"),
        print_("latest_buy", 179000, "Buy", ".291", "4000"),
    )
    a = aggregate_taker_prints(before, symbol="ICNTUSDT",
                               start_ms=60000, end_ms=120000)
    b = aggregate_taker_prints(current, symbol="ICNTUSDT",
                               start_ms=120000, end_ms=180000)
    transition = compare_flow_windows(a, b, decision_ms=180000)
    signal = recognize_impulse_signal(
        transition, closed_at_ms=180000,
        candle_open=b.start_price, candle_close=b.end_price,
        candle_low=D(".2885"), candle_high=D(".291"),
    )
    plan = plan_impulse_protected_entry(
        signal, tick_size=D(".0001"), quantity=D("1000"),
        max_notional_usdt=D("1000"), max_risk_usdt=D("50"),
        entry_fee_rate=D(".0006"), exit_fee_rate=D(".0006"),
        quantity_step=D("1"), minimum_quantity=D("1"),
    )
    row = {
        "signal_ms": 180000, "entry_ms": 180050, "direction": "LONG",
        "order_id": "IMPULSE_180000", "exit_reason": "STOP",
        "net_pnl_usdt": "-2", "evidence_flags": ["ENTRY_DEPTH_UNPROVEN"],
        "entry_price": str(plan.entry_price),
        "signal_structural_extreme": str(signal.structural_extreme),
        "planned_stop_price": str(plan.stop_price),
        "planned_take_price": str(plan.take_price),
        "quantity": str(plan.quantity),
    }
    return row, {60000: before, 120000: current}


def quote(at):
    return BookState(
        "ICNTUSDT", at, at, 1, 1,
        ((D(".2909"), D("100")), (D(".2908"), D("200"))),
        ((D(".2910"), D("300")), (D(".2911"), D("250"))),
    )


class ICNTEntryEvidenceTests(unittest.TestCase):
    def test_reconstruct_original_causal_long_admission(self):
        row, tape = original_plan_and_tape()
        result = decision_features(row, tape, quote(179999))
        self.assertEqual(result["direction"], "LONG")
        self.assertTrue(result["buy_wave_accelerating"])
        self.assertEqual(result["oi_gate"], "OFF")
        self.assertEqual(result["l2_predecision_status"],
                         "OBSERVED_QUOTE_NOT_QUEUE_PROOF")
        self.assertEqual(result["book_age_ms"], 1)
        self.assertEqual(result["signal_to_model_entry_ms"], 50)
        self.assertIsNone(result["absorption_observed"])
        self.assertEqual(result["execution_flags"], ["ENTRY_DEPTH_UNPROVEN"])

    def test_no_equal_time_or_future_book_is_used(self):
        self.assertEqual(_book_features(quote(180000), 180000),
                         {"l2_predecision_status": "UNKNOWN"})
        self.assertEqual(_book_features(quote(180010), 180000),
                         {"l2_predecision_status": "UNKNOWN"})
        self.assertEqual(_book_features(quote(179700), 180000),
                         {"l2_predecision_status": "STALE", "book_age_ms": 300})

    def test_original_signal_drift_refuses_diagnostic(self):
        row, tape = original_plan_and_tape()
        row["direction"] = "SHORT"
        with self.assertRaisesRegex(ValueError, "cannot be reproduced"):
            decision_features(row, tape, None)
        row["direction"] = "LONG"
        row["planned_stop_price"] = "0.1"
        with self.assertRaisesRegex(ValueError, "risk plan"):
            decision_features(row, tape, None)


if __name__ == "__main__":
    unittest.main()
