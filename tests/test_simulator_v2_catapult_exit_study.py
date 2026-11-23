"""Focused synthetic mechanics for the research-only exit-policy proposal.

These cases are NOT historical Bybit trades, paper fills or profitability tests.
"""
import unittest
from dataclasses import replace
from decimal import Decimal as D

from research.simulator_v2.catapult_exit_study import (
    FrozenTrade, MarketReceipt, StudySettings, evaluate_exit,
)


def trade(direction="LONG", **overrides):
    vals = dict(
        trade_id="fixture-trade-1", direction=direction, regime="PROBE",
        filled_at_ms=1000, entry_price=D("100"),
        protective_stop=D("99") if direction == "LONG" else D("101"),
        remaining_qty=D("2"), entry_fee_for_remaining=D("0.12"),
        protection_confirmed=True,
    )
    vals.update(overrides)
    return FrozenTrade(**vals)


def receipt(direction="LONG", **overrides):
    vals = dict(
        trade_id="fixture-trade-1", decision_at_ms=11000,
        book_event_ms=10800, book_received_ms=10900,
        print_event_ms=10850, print_received_ms=10950,
        book_snapshot_delta_continuous=True, prints_covered=True,
        mark_price=D("99.80") if direction == "LONG" else D("100.20"),
        best_price_since_fill=D("100"),
        directional_print_delta_usdt=D("0"),
        structure_invalidated=False,
    )
    vals.update(overrides)
    return MarketReceipt(**vals)


def settings(**overrides):
    vals = dict(
        timeouts_by_regime_ms=(
            ("PROBE", 5000), ("TREND_RETEST", 20000), ("EXHAUSTION", 7000),
        ),
        minimum_followthrough_r=D("0.3"),
        opposition_notional_usdt=D("200"),
        start_trailing_at_r=D("1"),
        trailing_gap_r=D("0.5"),
        partial_fraction=D("0.25"),
        exit_fee_rate=D("0.0006"),
        adverse_slippage_rate=D("0.001"),
        max_data_age_ms=500,
    )
    vals.update(overrides)
    return StudySettings(**vals)


class CatapultHypothesisMechanics(unittest.TestCase):
    def test_probe_no_followthrough_previews_full_exit_both_directions(self):
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                result = evaluate_exit(trade(direction), receipt(direction), settings())
                self.assertEqual(result.action, "FULL_EXIT_PREVIEW")
                self.assertLess(result.estimated_net_if_exited, 0)
                self.assertEqual(result.namespace, "SIMULATION_RESEARCH_ONLY")
                self.assertFalse(result.trading_authorized)

    def test_trend_retest_has_own_timeout_not_a_universal_seconds_rule(self):
        e = receipt()
        self.assertEqual(evaluate_exit(trade(), e, settings()).action,
                         "FULL_EXIT_PREVIEW")
        result = evaluate_exit(trade(regime="TREND_RETEST"), e, settings())
        self.assertEqual(result.action, "HOLD")

    def test_profitable_fade_reduces_only_part_with_costs_both_directions(self):
        for direction, price, best in (
            ("LONG", "101", "101.5"), ("SHORT", "99", "98.5"),
        ):
            with self.subTest(direction=direction):
                result = evaluate_exit(
                    trade(direction),
                    receipt(direction, mark_price=D(price),
                            best_price_since_fill=D(best),
                            directional_print_delta_usdt=D("-250")),
                    settings(),
                )
                self.assertEqual(result.action, "PARTIAL_EXIT_PREVIEW")
                self.assertEqual(result.fraction_to_close, D("0.25"))
                self.assertGreater(result.estimated_net_if_exited, 0)
                self.assertIsNone(result.unrounded_stop_preview)

    def test_negative_mark_versus_fees_never_pretends_profitable_partial(self):
        result = evaluate_exit(
            trade(), receipt(mark_price=D("100.01"),
                             best_price_since_fill=D("100.01"),
                             directional_print_delta_usdt=D("-300")),
            settings(),
        )
        self.assertEqual(result.action, "FULL_EXIT_PREVIEW")
        self.assertLess(result.estimated_net_if_exited, 0)

    def test_trailing_preview_tightens_only_long_and_short(self):
        for direction, mark, best in (
            ("LONG", "102", "102"), ("SHORT", "98", "98"),
        ):
            with self.subTest(direction=direction):
                result = evaluate_exit(
                    trade(direction),
                    receipt(direction, mark_price=D(mark),
                            best_price_since_fill=D(best),
                            directional_print_delta_usdt=D("100")),
                    settings(),
                )
                self.assertEqual(result.action, "TRAIL_TIGHTEN_PREVIEW")
                expected = D("101.5") if direction == "LONG" else D("98.5")
                self.assertEqual(result.unrounded_stop_preview, expected)
                self.assertTrue(
                    result.unrounded_stop_preview > trade(direction).protective_stop
                    if direction == "LONG" else
                    result.unrounded_stop_preview < trade(direction).protective_stop
                )
                self.assertFalse(result.trading_authorized)

    def test_no_widening_proposal_when_trailing_gap_too_large(self):
        result = evaluate_exit(
            trade(), receipt(mark_price=D("102"),
                             best_price_since_fill=D("102"),
                             directional_print_delta_usdt=D("500")),
            settings(trailing_gap_r=D("5")),
        )
        self.assertEqual(result.action, "HOLD")
        self.assertIsNone(result.unrounded_stop_preview)

    def test_structure_failure_takes_precedence_even_if_profitable(self):
        result = evaluate_exit(
            trade(), receipt(mark_price=D("101"),
                             best_price_since_fill=D("101"),
                             directional_print_delta_usdt=D("100"),
                             structure_invalidated=True),
            settings(),
        )
        self.assertEqual(result.action, "FULL_EXIT_PREVIEW")

    def test_unverified_host_receipts_and_protection_fail_closed(self):
        source = receipt()
        for e in (
            replace(source, book_snapshot_delta_continuous=False),
            replace(source, prints_covered=False),
            replace(source, trade_id="foreign"),
            replace(source, print_received_ms=11001),
            replace(source, print_received_ms=10849),
            replace(source, book_received_ms=10200),
            replace(source, book_event_ms=999),
            replace(source, decision_at_ms=900),
            replace(source, best_price_since_fill=D("99.9")),
            replace(source, mark_price=D("NaN")),
            replace(source, directional_print_delta_usdt=D("Infinity")),
        ):
            with self.subTest(e=e):
                result = evaluate_exit(trade(), e, settings())
                self.assertEqual(result.action, "INSUFFICIENT")
                self.assertIsNone(result.fraction_to_close)
                self.assertIsNone(result.unrounded_stop_preview)
        result = evaluate_exit(
            trade(protection_confirmed=False), source, settings())
        self.assertEqual(result.action, "INSUFFICIENT")

    def test_source_only_icnt_style_evidence_is_not_host_proof(self):
        # Public Bybit archives have exchange event times, not Robot receipts.
        e = replace(receipt(), book_snapshot_delta_continuous=False,
                    prints_covered=False)
        self.assertEqual(evaluate_exit(trade(), e, settings()).action,
                         "INSUFFICIENT")

    def test_invalid_regime_params_and_trade_risk_are_rejected(self):
        with self.assertRaises(ValueError):
            settings(timeouts_by_regime_ms=(("PROBE", 5000),))
        with self.assertRaises(ValueError):
            settings(partial_fraction=D("1"))
        with self.assertRaises(ValueError):
            settings(exit_fee_rate=D("NaN"))
        with self.assertRaises(ValueError):
            trade(protective_stop=D("101"))
        with self.assertRaises(ValueError):
            trade(regime="UNKNOWN")


if __name__ == "__main__":
    unittest.main()
