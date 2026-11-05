"""H-017 blue reference: only already-known geometry at M5 OPEN, no fills."""
from dataclasses import replace
from decimal import Decimal
import unittest

from research.causal_trend_geometry import CausalLine, ConfirmedPivot, TrendCandidate
from research.h017_blue_open_preview import blue_open_risk_preview
from research.h017_local_risk import H017LocalRiskPolicy

HOUR = 3_600_000
M5 = 300_000


def pivot(kind, idx, price, span=HOUR):
    return ConfirmedPivot(
        kind=kind, index=idx, at_ms=idx*span,
        confirmed_at_ms=(idx+1)*span, price=Decimal(str(price)),
    )


def fixture(side="BULL"):
    if side == "BULL":
        a, b, c, d = (
            pivot("LOW", 1, 100), pivot("HIGH", 2, 112),
            pivot("LOW", 3, 102), pivot("HIGH", 4, 114),
        )
        p, q = pivot("HIGH", 84, 111, M5), pivot("HIGH", 88, 108, M5)
    else:
        a, b, c, d = (
            pivot("HIGH", 1, 120), pivot("LOW", 2, 108),
            pivot("HIGH", 3, 118), pivot("LOW", 4, 106),
        )
        p, q = pivot("LOW", 84, 109, M5), pivot("LOW", 88, 112, M5)
    # Both blue anchor confirmations must be AFTER the new H1 is known,
    # and BEFORE the candidate M5 opens.
    p = replace(p, at_ms=7*HOUR, confirmed_at_ms=7*HOUR+M5)
    q = replace(q, at_ms=7*HOUR+2*M5, confirmed_at_ms=7*HOUR+3*M5)
    trend = TrendCandidate(side, CausalLine(a,c,6*HOUR),
                           CausalLine(b,d,6*HOUR), (a,b,c,d), 6*HOUR)
    reference = CausalLine(p,q,7*HOUR+3*M5)
    return trend, reference


class OpenOnly:
    """Any access to this candle's high/low/close is an immediate test failure."""
    def __init__(self, start_ms, price):
        self.start_ms = start_ms
        self.end_ms = start_ms + M5
        self.open = Decimal(str(price))

    def __getattr__(self, name):
        raise AssertionError("future M5 OHLC accessed: " + name)


class BlueRiskPreviewTests(unittest.TestCase):
    def setUp(self):
        self.policy = H017LocalRiskPolicy()

    def test_long_and_short_use_actual_open_hourly_target_and_fixed_stop(self):
        for side, price, expected_side in (
            ("BULL", "109", "LONG"), ("BEAR", "110", "SHORT"),
        ):
            with self.subTest(side=side):
                trend, blue = fixture(side)
                result = blue_open_risk_preview(
                    bar=OpenOnly(8*HOUR, price),
                    known_trend=trend, known_blue=blue, policy=self.policy,
                )
                self.assertIsNotNone(result)
                self.assertEqual(result["risk_status"], "RISK_PASS")
                self.assertEqual(result["side"], expected_side)
                self.assertEqual(result["entry_price"], price)
                self.assertEqual(result["stop_price"], str(
                    Decimal(price) * (
                        Decimal("0.993") if side == "BULL" else Decimal("1.007")
                    )
                ))
                self.assertEqual(result["quantity"], str(Decimal(10)/Decimal(price)))
                self.assertEqual(result["target_price"],
                                 str(trend.target.value_at(8*HOUR)))
                self.assertEqual(result["classification"], "UNVALIDATED_GEOMETRY_ONLY")
                self.assertEqual(result["source"], "SIMULATION")
                self.assertNotIn("trade_id", result)

    def test_insufficient_one_to_one_is_preview_only_not_a_fill(self):
        trend, blue = fixture()
        poor = blue_open_risk_preview(
            bar=OpenOnly(8*HOUR, "117.9"),
            known_trend=trend, known_blue=blue, policy=self.policy,
        )
        self.assertIsNotNone(poor)
        self.assertEqual(poor["risk_status"], "RISK_BELOW_1R")
        self.assertNotIn("stop_price", poor)
        self.assertNotIn("quantity", poor)
        self.assertNotIn("trade_id", poor)

    def test_missing_unconfirmed_wrong_sided_or_stale_geometry_is_ignored(self):
        trend, blue = fixture()
        known = OpenOnly(8*HOUR, "109")
        self.assertIsNone(blue_open_risk_preview(
            bar=known, known_trend=None, known_blue=blue, policy=self.policy))
        self.assertIsNone(blue_open_risk_preview(
            bar=known, known_trend=trend, known_blue=None, policy=self.policy))
        self.assertIsNone(blue_open_risk_preview(
            bar=OpenOnly(7*HOUR, "109"),
            known_trend=trend, known_blue=blue, policy=self.policy))
        self.assertIsNone(blue_open_risk_preview(
            bar=OpenOnly(8*HOUR, "90"),
            known_trend=trend, known_blue=blue, policy=self.policy))
        older = replace(blue, available_at_ms=trend.available_at_ms-M5)
        self.assertIsNone(blue_open_risk_preview(
            bar=known, known_trend=trend, known_blue=older, policy=self.policy))
        bad_side = replace(blue, first=pivot("LOW", 84, 100, M5),
                           second=pivot("LOW", 88, 101, M5))
        self.assertIsNone(blue_open_risk_preview(
            bar=known, known_trend=trend, known_blue=bad_side, policy=self.policy))


if __name__ == "__main__":
    unittest.main()
