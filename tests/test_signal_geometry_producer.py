import unittest
from types import SimpleNamespace

from signal_geometry_producer import build_wedge_geometry_snapshot


class Candles:
    def itertuples(self, index=False):
        return iter([
            SimpleNamespace(time=1000, open=10, high=12, low=8, close=11),
            SimpleNamespace(time=301000, open=11, high=14, low=9, close=13),
        ])


GEOMETRY = {
    "upper_line": {"model": "anchor", "anchor_index": 0, "second_index": 1,
                   "anchor_price": 12, "second_price": 14},
    "lower_line": {"model": "anchor", "anchor_index": 0, "second_index": 1,
                   "anchor_price": 8, "second_price": 9},
}


class GeometryProducerTests(unittest.TestCase):
    def build(self, geometry=GEOMETRY, now=602000):
        return build_wedge_geometry_snapshot("id-1", "BTCUSDT", "5", geometry, Candles(), now_ms=now)

    def test_anchor_prices_and_times_are_exact_not_refitted(self):
        value = self.build()
        self.assertIsNotNone(value)
        self.assertEqual(value["boundaries"][0]["anchors"], [
            {"bar_open_time_ms": 1000, "price": 12},
            {"bar_open_time_ms": 301000, "price": 14},
        ])
        self.assertEqual(value["signal_id"], "id-1")

    def test_open_candle_rejected(self):
        self.assertIsNone(self.build(now=601000))

    def test_regression_line_without_explicit_anchors_rejected(self):
        self.assertIsNone(self.build({"upper_line": {"slope": 1}, "lower_line": GEOMETRY["lower_line"]}))

    def test_out_of_window_anchor_rejected(self):
        broken = {**GEOMETRY, "lower_line": {**GEOMETRY["lower_line"], "second_index": 2}}
        self.assertIsNone(self.build(broken))


if __name__ == "__main__":
    unittest.main()
