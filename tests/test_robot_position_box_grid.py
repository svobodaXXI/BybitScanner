"""Issue #420: frozen Box grid chart tests (no runtime / network)."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import robot_position_chart as chart
from robot_position_chart import PositionChartError, render_position_chart
from tests.test_robot_position_card import _candles, _trade, _view


def box_snapshot(direction="LONG"):
    if direction == "LONG":
        f1, f1618, f2618 = "100", "80", "47.64"
        entries = ["85", "83", "81", "79"]
        take = "98"
    else:
        f1, f1618, f2618 = "100", "120", "152.36"
        entries = ["115", "117", "119", "121"]
        take = "102"
    return {
        "pattern": "IKIGAI_BOX",
        "identity": {"direction": direction},
        "fibonacci": {"f1": f1, "f1618": f1618, "f2618": f2618},
        "plan": {
            "frozen_f1": f1, "frozen_f1618": f1618,
            "limit_prices": entries, "take_price": take,
        },
    }


class FrozenBoxChartTests(unittest.TestCase):
    def test_frozen_levels_are_identical_after_reload(self):
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                snapshot = box_snapshot(direction)
                view = _view(pattern="IKIGAI_BOX", direction=direction,
                             signal_snapshot=snapshot, trade=_trade(pattern="IKIGAI_BOX"))
                actual = chart._frozen_box_levels(view)
                self.assertEqual(
                    actual,
                    tuple(zip(
                        map(Decimal, (snapshot["fibonacci"]["f1"],
                                      snapshot["fibonacci"]["f1618"],
                                      snapshot["fibonacci"]["f2618"], *snapshot["plan"]["limit_prices"])),
                        ("F1.0", "F1.618", "F2.618", "P1", "P2", "P3", "P4"),
                    )),
                )
                self.assertEqual(chart._frozen_box_levels(view), actual)

    def test_open_box_draws_frozen_grid_and_entry_stop_take(self):
        view = _view(pattern="IKIGAI_BOX", signal_snapshot=box_snapshot(),
                     trade=_trade(pattern="IKIGAI_BOX"))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(chart, "_draw_level", wraps=chart._draw_level) as drawn:
                render_position_chart(view, _candles(20), Path(directory) / "box.png")
        labels = [call.args[2] for call in drawn.call_args_list]
        self.assertEqual(labels[:7], ["F1.0", "F1.618", "F2.618", "P1", "P2", "P3", "P4"])
        self.assertEqual(labels[-3:], ["Entry", "SL", "TP"])

    def test_unproven_open_box_never_invents_grid(self):
        view = _view(pattern="IKIGAI_BOX", signal_snapshot={"pattern": "IKIGAI_BOX"},
                     trade=_trade(pattern="IKIGAI_BOX"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PositionChartError):
                render_position_chart(view, _candles(20), Path(directory) / "invalid.png")

    def test_non_box_does_not_draw_box_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(chart, "_draw_level", wraps=chart._draw_level) as drawn:
                render_position_chart(_view(), _candles(20), Path(directory) / "wedge.png")
        self.assertEqual([call.args[2] for call in drawn.call_args_list], ["Entry", "SL", "TP"])


if __name__ == "__main__":
    unittest.main()
