"""Causal, in-memory regression for the isolated Wedge A/B counterfactual."""
import unittest
from decimal import Decimal as D
from types import SimpleNamespace

from research.historical_market_replay import Candle
from research.simulator_v2.wedge_partial_ab_ci import model_one


def bar(t, o, h, l, c):
    return Candle(t, 60_000, D(o), D(h), D(l), D(c), D("1"))


def entry():
    return SimpleNamespace(
        side="BUY", quantity=D("4"), price=D("100"),
        fee=D("0.24"), virtual_time_ms=60_000,
    )


class WedgePartialCausality(unittest.TestCase):
    def test_take_on_trigger_bar_precedes_next_open_partial(self):
        bars = (
            bar(60_000, "100", "103", "99.9", "102.5"),
            bar(120_000, "102.5", "103", "101", "102"),
        )
        a = model_one(bars, entry(), None, D("99"), D("102.5"), "A")
        b = model_one(bars, entry(), None, D("99"), D("102.5"), "B")
        self.assertEqual(a["net"], b["net"])
        self.assertEqual(a["reason"], "TAKE")
        self.assertEqual(b["partials"], 0)

    def test_partial_is_next_open_and_stop_tightens_only(self):
        bars = (
            bar(60_000, "100", "102.1", "99.9", "101.5"),
            bar(120_000, "102.1", "102.4", "101.5", "102"),
            bar(180_000, "102", "102.1", "98.5", "99.5"),
        )
        a = model_one(bars, entry(), None, D("99"), D("105"), "A")
        b = model_one(bars, entry(), None, D("99"), D("105"), "B")
        self.assertEqual(a["reason"], "STOP")
        self.assertEqual(b["reason"], "STOP")
        self.assertEqual(b["partials"], 1)
        self.assertGreater(D(b["net"]), D(a["net"]))

    def test_rounded_partial_must_leave_remainder(self):
        e = SimpleNamespace(
            side="BUY", quantity=D("2"), price=D("100"),
            fee=D("0.12"), virtual_time_ms=60_000,
        )
        bars = (
            bar(60_000, "100", "102.5", "99.9", "101.5"),
            bar(120_000, "102.2", "102.3", "100.1", "101"),
            bar(180_000, "101", "105", "99.5", "100"),
        )
        b = model_one(bars, e, None, D("99"), D("105"), "B")
        self.assertEqual(b["partials"], 0)


if __name__ == "__main__":
    unittest.main()
