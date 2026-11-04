"""Keep the local 64-candle DEMO DMI fixture equal to the existing Wilder engine.

No network, no orders and no Robot imports. This is intentionally a test of a
versioned display fixture, NOT a second indicator implementation in TypeScript.
"""
from decimal import Decimal
import json
from pathlib import Path
import unittest

from research.historical_market_replay import Candle
from research.wilder_dmi import WilderDmi

PRICES = [
    100, 101, 99, 102, 103, 104, 106, 107, 105, 104, 102, 101, 103, 105, 106, 105,
    103, 102, 100, 99, 101, 103, 105, 107, 109, 108, 107, 104, 101, 100, 99, 101,
    104, 107, 110, 112, 111, 109, 107, 105, 103, 106, 109, 112, 114, 113, 111, 108,
    106, 104, 103, 105, 108, 111, 115, 118, 116, 113, 110, 107, 108, 111, 114, 117,
]
INTERVAL = 300_000


class SyntheticDmiFixtureTests(unittest.TestCase):
    def test_demo_is_wilder_engine_output_and_has_28_bar_warmup(self):
        path = Path(__file__).resolve().parents[1] / (
            "terminal/frontend/src/replay/syntheticDmiFixture.json"
        )
        fixture = json.loads(path.read_text("utf-8"))
        self.assertEqual((fixture["di_length"], fixture["adx_smoothing"]), (14, 14))
        self.assertEqual(len(fixture["values"]), len(PRICES))
        indicator = WilderDmi(timeframe_ms=INTERVAL)
        for i, close in enumerate(PRICES):
            prev_close = PRICES[i - 1] if i else close
            opened = Decimal(prev_close)
            closing = Decimal(close)
            bar = Candle(
                i * INTERVAL, INTERVAL, opened,
                max(opened, closing) + 1, min(opened, closing) - 1, closing, 100 + 3*i,
            )
            result = indicator.observe_closed(bar)
            expected = fixture["values"][i]
            self.assertEqual([value is None for value in expected], [
                result.plus_di is None, result.minus_di is None, result.adx is None,
            ], f"warmup at candle {i}")
            for field, output in zip(expected, [result.plus_di, result.minus_di, result.adx]):
                if field is not None:
                    self.assertLess(
                        abs(Decimal(field) - output), Decimal("0.000001"),
                        f"mismatched Wilder DMI on candle {i}",
                    )
        self.assertIsNone(fixture["values"][26][2])
        self.assertIsNotNone(fixture["values"][27][2])


if __name__ == "__main__":
    unittest.main()
