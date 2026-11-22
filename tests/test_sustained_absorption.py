from dataclasses import replace
from decimal import Decimal as D
import unittest

from robot_entry_flow_evidence import TakerPrint
from terminal.market_data.sustained_absorption import (
    AvailablePrint, ReconstructedBook, observe_sustained_absorption,
)


def fixture(direction="LONG"):
    def book(uid, t, size, *, broken=False):
        side = ((D("100" if direction == "LONG" else "102"), D(size)),)
        if broken:
            side = ((D("99" if direction == "LONG" else "103"), D(size)),)
        other = ((D("102" if direction == "LONG" else "100"), D("10")),)
        bids, asks = (side, other) if direction == "LONG" else (other, side)
        return ReconstructedBook("BTCUSDT", 1, uid, t, t, bids, asks)
    times = (999, 1002, 1003, 1009, 1012, 1013, 1019)
    books = tuple(book(i, t, q) for i,(t,q) in enumerate(
        zip(times, ("10","6","10","10","6","10","10"))
    ))
    prints = tuple(AvailablePrint(TakerPrint(
        "BTCUSDT", str(i), t, "Sell" if direction == "LONG" else "Buy",
        D("100" if direction == "LONG" else "102"), D("4")
    ), 1, t) for i,t in enumerate((1001,1011)))
    return books, prints


def observe(books, prints, **kwargs):
    return observe_sustained_absorption(books, prints, **(
        dict(symbol="BTCUSDT", direction="LONG", generation=1, start_ms=1000,
             end_ms=1020, decision_ms=1020, window_ms=10, max_quote_age_ms=10,
             level_count=1) | kwargs
    ))


class SustainedAbsorptionTests(unittest.TestCase):
    def test_mirrored_recovery_never_grants_authority(self):
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                result = observe(*fixture(direction), direction=direction)
                self.assertIsNotNone(result)
                self.assertTrue(result.repeated_recovery_observed)
                self.assertEqual(result.minimum_depth_fraction, D("0.6"))
                self.assertEqual([w.recovery_fraction for w in result.windows], [D(1),D(1)])
                self.assertFalse(result.adverse_quote_break)
                self.assertFalse(result.source_complete)
                self.assertFalse(result.trading_authorized)

    def test_churn_without_prints_is_not_recovery(self):
        books, _ = fixture()
        result = observe(books, ())
        self.assertFalse(result.repeated_recovery_observed)
        self.assertTrue(all(w.recovery_fraction is None for w in result.windows))

    def test_credit_not_reused_by_more_quote_revisions(self):
        books, prints = fixture()
        result = observe(books, prints[:1])
        self.assertEqual(result.windows[0].compatible_recovery_notional, D(400))
        self.assertEqual(result.windows[1].compatible_recovery_notional, D(0))
        self.assertFalse(result.repeated_recovery_observed)

    def test_quote_collapse_is_visible_even_after_recovery(self):
        books, prints = fixture()
        bad = replace(books[3], bids=((D(99),D(10)),))
        result = observe(books[:3]+(bad,)+books[4:], prints)
        self.assertTrue(result.adverse_quote_break)
        self.assertEqual(result.minimum_depth_notional, D(0))

    def test_equal_timestamp_preserves_pressure_but_no_credit(self):
        books, prints = fixture()
        tied = replace(prints[0], print=replace(prints[0].print,event_ms=1002),
                       available_at_ms=1002)
        result = observe(books, (tied, prints[1]))
        self.assertEqual(result.windows[0].opposing_notional, D(400))
        self.assertEqual(result.windows[0].compatible_recovery_notional, D(0))

    def test_reject_gap_future_mixed_generation_or_duplicate(self):
        books, prints = fixture()
        for bad in (
            replace(books[2], update_id=9),
            replace(books[2], generation=2),
            replace(books[2], available_at_ms=1021),
            replace(books[2], bids=((D(103),D(10)),)),
        ):
            self.assertIsNone(observe(books[:2]+(bad,)+books[3:], prints))
        self.assertIsNone(observe(books, (prints[0],prints[0])))
        self.assertIsNone(observe(books, (replace(prints[0], generation=2),)))
        self.assertIsNone(observe(books, prints, max_quote_age_ms=1))
        self.assertIsNone(observe(books, prints, decision_ms=1019))


if __name__ == "__main__":
    unittest.main()
