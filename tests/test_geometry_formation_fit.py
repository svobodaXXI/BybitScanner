"""Frozen eleven-case selection, reference disposition and sensitivity evidence.

No exchange, Scanner, Telegram or Robot calls. Original disputed line equations
and candle runs remain alongside new expectations; no ignored-fixture skips.
"""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import geometry.engine as engine
from geometry.envelope_metrics import evaluate_formation_body_fit, evaluate_body_zone_breaches, line_value
from confirmation import calculate_atr
from pivots import find_pivots
from wedge.analyzer import _freshness_predicate
from wedge.detector import detect_structure

FIXTURE = Path(__file__).parent / "fixtures" / "geometry_formation_fit" / "historical_cases.json"


def identity(g):
    if g is None:
        return None
    return [g.upper_line["anchor_index"], g.upper_line["second_index"],
            g.lower_line["anchor_index"], g.lower_line["second_index"],
            g.start_index, g.end_index]


def expected_identity(case):
    if case is None:
        return None
    g = case["geometry"]
    return g["anchors"] + [g["start"], g["end"]]


class HistoricalFormationFitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        cls.frames, cls.winners, cls.pools = {}, {}, {}
        original = engine.evaluate_candidate_pair
        for name, case in cls.cases.items():
            frame = pd.DataFrame(case["candles"], columns=["time", "open", "high", "low", "close", "volume"])
            cls.frames[name] = frame
            highs, lows = find_pivots(frame.copy())
            pool = []
            def record_pair(*args, **kwargs):
                geometry = original(*args, **kwargs)
                if geometry is not None:
                    pool.append(geometry)
                return geometry
            with patch.object(engine, "evaluate_candidate_pair", side_effect=record_pair), contextlib.redirect_stdout(io.StringIO()):
                cls.winners[name] = engine.analyze_geometry(highs, lows, len(frame)-1, frame, _freshness_predicate)
            cls.pools[name] = pool

    def test_all_eleven_selected_lines_intervals_and_shape(self):
        self.assertEqual(len(self.cases), 11)
        for name, case in self.cases.items():
            with self.subTest(symbol=name):
                geometry = self.winners[name]
                want = case["expected"]
                self.assertEqual(identity(geometry), expected_identity(want))
                if geometry is None:
                    continue
                self.assertEqual(geometry.pair_metrics["geometry_mode"], want["geometry"]["mode"])
                for side, line in zip(("upper", "lower"), want["geometry"]["lines"]):
                    actual = getattr(geometry, side + "_line")
                    for field in ("slope", "intercept", "anchor_price", "second_price"):
                        self.assertAlmostEqual(actual[field], line[field], places=12)
                    measured = geometry.envelope_metrics["formation_body_fit"][side]
                    old_measurement = want["fit"][0 if side == "upper" else 1]
                    self.assertEqual(measured["body_breach_indices"], old_measurement["indices"])
                    self.assertEqual(measured["breach_runs"], old_measurement["runs"])
                    self.assertLess(measured["max_consecutive_breaches"], 7)
                    self.assertEqual(measured["start_index"], actual["anchor_index"])
                    self.assertEqual(measured["end_index"], geometry.end_index)
                for index, width in zip((geometry.start_index, geometry.end_index), want["geometry"]["widths"]):
                    self.assertAlmostEqual(line_value(geometry.upper_line, index)-line_value(geometry.lower_line, index), width, places=12)
                self.assertEqual(detect_structure(geometry, candles=self.frames[name])["detected"], want["detected"])

    def test_old_boundaries_have_the_recorded_candle_defects_not_just_changed_indices(self):
        expected_runs = {"AZTEC": 16, "HIMS": 10, "QQQ": 45, "CHIP": 8,
                         "AEVO": 19, "INJ": 7, "WLD": 15, "AAVE": 8, "POL": 9,
                         "XRP": 0, "PONS": 2}
        for name, case in self.cases.items():
            with self.subTest(symbol=name):
                ref = case["disputed_reference"]
                g = ref["geometry"]
                frame = self.frames[name]
                fit = evaluate_formation_body_fit(*g["lines"], frame, g["end"])
                self.assertEqual(max(fit[s]["max_consecutive_breaches"] for s in ("upper", "lower")), expected_runs[name])
                atr = calculate_atr(frame)
                for side, line, evidence in zip(("upper", "lower"), g["lines"], ref["fit"]):
                    self.assertEqual(fit[side]["body_breach_indices"], evidence["indices"])
                    # Independently inspect every candle against the stored old
                    # equation, including non-breaches; no pivot requirement.
                    for index in range(line["anchor_index"], g["end"]+1):
                        row = frame.iloc[index]
                        price = line["slope"]*index + line["intercept"]
                        distance = max(row.open, row.close)-price if side == "upper" else price-min(row.open, row.close)
                        self.assertEqual(distance > .15*atr.iloc[index], index in evidence["indices"])
        # These old expectations hid the decisive evidence before common_start.
        for name, side, intervals in [("AEVO", "lower", [(101,111),(128,146)]),
                                       ("INJ", "lower", [(77,83)]),
                                       ("WLD", "upper", [(126,140)])]:
            g = self.cases[name]["disputed_reference"]["geometry"]
            common_start = max(g["anchors"][0],g["anchors"][2])
            fit = evaluate_formation_body_fit(*g["lines"], self.frames[name],g["end"])
            for first,last in intervals:
                self.assertLess(last, common_start)
                self.assertIn([first,last],fit[side]["breach_runs"])

    def test_post_end_price_does_not_change_formation_assessment(self):
        for name, case in self.cases.items():
            with self.subTest(symbol=name):
                g=case["disputed_reference"]["geometry"]
                frame=self.frames[name]
                expected=evaluate_formation_body_fit(*g["lines"],frame,g["end"])
                changed=frame.copy()
                changed.loc[g["end"]+1:, ["open","high","low","close"]] *= 10
                self.assertEqual(evaluate_formation_body_fit(*g["lines"],changed,g["end"]),expected)
        for name in ("AZTEC","HIMS","QQQ","CHIP"):
            case=self.cases[name];g=case["baseline"]["geometry"]
            b=evaluate_body_zone_breaches(*g["lines"],self.frames[name],max(g["anchors"][0],g["anchors"][2]),199)
            ix=b["upper_body_breach_indices"]+b["lower_body_breach_early_indices"]+b["lower_body_breach_late_indices"]
            self.assertEqual(sum(i<=g["end"] for i in ix),case["recorded_body_counts"]["common_to_end"])
            self.assertEqual(sum(i>g["end"] for i in ix),case["recorded_body_counts"]["post_end"])

    def test_selection_stable_for_neighboring_run_cutoffs(self):
        # Reuse real evaluated pairs collected during the full production call.
        # Only evaluation cost is cached: admission/freshness/ranking/selection
        # below execute the real engine again for every cutoff, without a
        # second selection implementation in the test.
        for name,pool in self.pools.items():
            for cutoff in (4,5,6,7,8):
                with self.subTest(symbol=name,cutoff=cutoff):
                    with patch.object(engine,"GEOMETRY_MAX_BODY_BREACH_RUN",cutoff), patch.object(engine,"build_candidate_lines",side_effect=[[None],[None]*len(pool)]), patch.object(engine,"filter_candidates",side_effect=lambda x:x), patch.object(engine,"evaluate_candidate_pair",side_effect=pool), contextlib.redirect_stdout(io.StringIO()):
                        winner=engine.analyze_geometry([{}]*4,[{}]*4,199,freshness_predicate=_freshness_predicate)
                    self.assertEqual(identity(winner),identity(self.winners[name]))


if __name__ == "__main__":
    unittest.main()
