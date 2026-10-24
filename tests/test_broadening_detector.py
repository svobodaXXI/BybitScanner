"""HORN-2: offline Broadening Formation detector (DOCUMENTS/SCANNER_BROADENING_FORMATION_HORN_1.md).

Synthetic megaphones prove PRELIMINARY (4 pivots, not None), MATURE (5+), the
mirror, local START, invalidation without anchor substitution and no look-ahead.
Owner-labeled Triangle/Wedge/no-geometry Gold windows are negatives at their
decision bar. No exchange, Scanner, Telegram or Robot calls.
"""
import unittest

import numpy as np
import pandas as pd

from geometry.broadening import (
    STAGE_MATURE,
    STAGE_PRELIMINARY,
    _expanding_run,
    _line,
    _positive_width,
    _value,
    detect_broadening,
)
from tests.geometry_gold import ROOT, _load_frame, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
HORN_GEOMETRY = ROOT / "tests" / "fixtures" / "horn_geometry"


def zigzag(points, length):
    """Candles whose closes interpolate the turning points; each turn is a strict 3/3 pivot."""
    index, price = zip(*points)
    close = np.interp(np.arange(length), index, price)
    previous = np.r_[close[0], close[:-1]]
    open_ = close - 0.3 * (close - previous)
    return pd.DataFrame({
        "time": np.arange(length) * 300000,
        "open": open_,
        "high": np.maximum(open_, close) + 0.05,
        "low": np.minimum(open_, close) - 0.05,
        "close": close,
        "volume": 1.0,
    })


LEAD = [(0, 100.0), (60, 100.2)]
FOUR = LEAD + [(72, 101.0), (84, 99.0), (96, 102.0), (108, 97.5), (120, 99.0)]
FIVE = LEAD + [(72, 101.0), (84, 99.0), (96, 102.0), (108, 97.5), (120, 103.5), (132, 101.0)]


def anchors(formation):
    return [(index, side) for index, side, _ in formation.anchors]


class PreliminaryAndMatureTest(unittest.TestCase):
    def test_four_pivots_give_preliminary_with_projected_boundaries(self):
        frame = zigzag(FOUR, 121)
        # LOW108 is confirmed at 111 (3 right bars): detected immediately, not None.
        self.assertIsNone(detect_broadening(frame, 110))
        formation = detect_broadening(frame, 111)
        self.assertIsNotNone(formation)
        self.assertEqual(formation.stage, STAGE_PRELIMINARY)
        self.assertEqual(anchors(formation), [(72, "H"), (84, "L"), (96, "H"), (108, "L")])
        self.assertEqual(formation.start_index, 72)
        self.assertEqual(formation.waves, 3)
        self.assertEqual((formation.upper_line["anchor_index"], formation.upper_line["second_index"]), (72, 96))
        self.assertEqual((formation.lower_line["anchor_index"], formation.lower_line["second_index"]), (84, 108))
        self.assertGreater(formation.upper_line["slope"], 0)
        self.assertLess(formation.lower_line["slope"], 0)
        upper_now, lower_now = formation.project(111)
        upper_later, lower_later = formation.project(140)
        self.assertGreater(upper_later - lower_later, upper_now - lower_now)
        self.assertGreater(formation.diagnostics["width_end"], formation.diagnostics["width_start"])

    def test_fifth_pivot_raises_stage_to_mature(self):
        formation = detect_broadening(zigzag(FIVE, 133))
        self.assertEqual(formation.stage, STAGE_MATURE)
        self.assertEqual(
            anchors(formation), [(72, "H"), (84, "L"), (96, "H"), (108, "L"), (120, "H")]
        )
        self.assertEqual((formation.upper_line["anchor_index"], formation.upper_line["second_index"]), (72, 120))
        self.assertEqual(formation.waves, 4)

    def test_mirror_is_detected_symmetrically(self):
        formation = detect_broadening(zigzag([(i, 200.0 - p) for i, p in FIVE], 133))
        self.assertEqual(formation.stage, STAGE_MATURE)
        self.assertEqual(
            anchors(formation), [(72, "L"), (84, "H"), (96, "L"), (108, "H"), (120, "L")]
        )

    def test_no_direction_is_assigned(self):
        formation = detect_broadening(zigzag(FIVE, 133))
        fields = set(vars(formation)) | set(formation.diagnostics)
        self.assertFalse({"direction", "side", "bias", "long", "short"} & {f.lower() for f in fields})


class LocalStartTest(unittest.TestCase):
    def test_start_comes_from_local_wave_structure(self):
        # HIGH5 / LOW14 extend the same expanding sequence but lie beyond the
        # existing locality bound at the decision bar: START is the local HIGH72.
        points = [(0, 100.0), (5, 100.3), (14, 99.8)] + FIVE[2:]
        formation = detect_broadening(zigzag(points, 136), 135)
        self.assertEqual(formation.start_index, 72)
        self.assertEqual(anchors(formation)[0], (72, "H"))
        self.assertEqual(formation.stage, STAGE_MATURE)


class NegativeTest(unittest.TestCase):
    def test_converging_zigzag(self):
        points = LEAD + [(72, 103.0), (84, 98.0), (96, 102.0), (108, 99.0), (120, 101.0), (132, 100.0)]
        self.assertIsNone(detect_broadening(zigzag(points, 136)))

    def test_flat_range_equal_waves(self):
        points = LEAD + [(72, 101.0), (84, 99.0), (96, 101.0), (108, 99.0), (120, 101.0), (132, 99.0)]
        self.assertIsNone(detect_broadening(zigzag(points, 136)))

    def test_single_spike(self):
        self.assertIsNone(detect_broadening(zigzag([(0, 100.0), (80, 100.2), (84, 104.0), (88, 100.2), (130, 100.4)], 131)))

    def test_higher_highs_without_lower_lows(self):
        points = LEAD + [(72, 101.0), (84, 99.5), (96, 102.0), (108, 100.0), (120, 103.0), (132, 100.5)]
        self.assertIsNone(detect_broadening(zigzag(points, 136)))

    def test_split_wave_stops_the_run(self):
        # LOW84 and LOW90 adjacent (no confirmed HIGH between): the wave is split.
        sequence = [(72, "H", 101.0), (84, "L", 99.0), (90, "L", 98.8), (96, "H", 102.0), (108, "L", 97.5)]
        self.assertEqual([p[0] for p in _expanding_run(sequence, 111)], [90, 96, 108])


class InvalidationTest(unittest.TestCase):
    BROKEN = LEAD + [(72, 101.0), (84, 99.0), (96, 102.0), (108, 97.5), (120, 100.5), (132, 99.5)]

    def test_later_confirmed_pivot_invalidates_without_anchor_substitution(self):
        frame = zigzag(self.BROKEN, 136)
        before = detect_broadening(frame, 111)
        self.assertEqual(anchors(before), [(72, "H"), (84, "L"), (96, "H"), (108, "L")])
        # HIGH120 (100.5) is not beyond HIGH96: once confirmed (123) the formation ends.
        self.assertIsNotNone(detect_broadening(frame, 122))
        for as_of in range(123, 136):
            self.assertIsNone(detect_broadening(frame, as_of), as_of)


class NoLookAheadTest(unittest.TestCase):
    def test_verdict_depends_only_on_the_prefix(self):
        frame = zigzag(FIVE, 160)
        for as_of in range(100, 160):
            full = detect_broadening(frame, as_of)
            prefix = detect_broadening(frame.iloc[: as_of + 1].reset_index(drop=True), as_of)
            self.assertEqual(
                None if full is None else (full.stage, full.anchors, full.upper_line, full.lower_line),
                None if prefix is None else (prefix.stage, prefix.anchors, prefix.upper_line, prefix.lower_line),
                as_of,
            )


class GoldNegativeTest(unittest.TestCase):
    """Owner-labeled Triangle (MEGA, RSR), falling Wedge (PONS) and no-geometry (1000XEC)
    windows: no forming broadening at their decision bar."""

    def test_gold_windows_have_no_broadening_at_decision(self):
        cases = {
            case["symbol"]: case
            for name in ("manifest_v1.json", "manifest_g_tri_2.json", "manifest_rsr_anchors.json")
            for case in load_manifest(GOLD / name)["cases"]
        }
        for symbol in ("MEGAUSDT", "RSRUSDT", "PONS", "1000XECUSDT"):
            with self.subTest(symbol=symbol):
                frame = _load_frame(cases[symbol])
                self.assertIsNone(detect_broadening(frame, len(frame) - 1))


class PositiveWidthTest(unittest.TestCase):
    """The channel must be open on the whole formation: upper(t) > lower(t) from START on."""

    def test_uniusdt_5m_crossed_boundaries_are_not_a_formation(self):
        # Exact closed OHLC the live Scanner read (horn_observations/ohlc, decision
        # 1792253400000). The pre-fix detector reported PRELIMINARY H165 L175 H179
        # L194 although the lines cross near index 169.6, between P1 and P2.
        frame = pd.read_csv(HORN_GEOMETRY / "UNIUSDT_5_1792253400000.csv")
        self.assertEqual(len(frame), 199)
        run = _expanding_run(
            sorted([(165, "H", 7.162), (175, "L", 7.154), (179, "H", 7.211), (194, "L", 7.07)]), 198)
        self.assertEqual(len(run), 4)
        upper, lower = _line(run[0], run[2]), _line(run[1], run[3])
        self.assertLess(_value(upper, 165), _value(lower, 165))
        self.assertGreater(_value(upper, 198), _value(lower, 198))
        self.assertFalse(_positive_width(upper, lower, 165, 198))
        self.assertIsNone(detect_broadening(frame))
        self.assertIsNone(detect_broadening(frame, len(frame) - 1))

    def test_synthetic_crossing_between_p1_and_p2_is_rejected(self):
        # Same shape as UNIUSDT: a tiny first wave and a steep lower boundary
        # projected back above HIGH72. Expanding run, HH/LL and width growth all hold.
        frame = zigzag([(0, 99.0), (72, 100.0), (84, 99.9), (96, 100.6), (156, 98.0), (168, 99.0)], 169)
        self.assertIsNone(detect_broadening(frame, 159))

    def test_four_pivot_megaphone_keeps_positive_width(self):
        formation = detect_broadening(zigzag(FOUR, 121), 111)
        self.assertIsNotNone(formation)
        for index in range(formation.start_index, formation.as_of_index + 1):
            upper, lower = formation.project(index)
            self.assertGreater(upper, lower)

    def test_touching_or_rounding_only_width_is_not_positive(self):
        lower = _line((0, "L", 0.3), (10, "L", 0.0))
        touching = _line((0, "H", 0.3), (10, "H", 1.0))
        rounding = _line((0, "H", 0.1 + 0.2), (10, "H", 1.0))  # 0.30000000000000004
        self.assertGreater(_value(rounding, 0) - _value(lower, 0), 0)
        self.assertFalse(_positive_width(touching, lower, 0, 10))
        self.assertFalse(_positive_width(rounding, lower, 0, 10))
        self.assertTrue(_positive_width(_line((0, "H", 0.31), (10, "H", 1.0)), lower, 0, 10))


if __name__ == "__main__":
    unittest.main()
