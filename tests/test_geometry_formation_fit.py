"""Frozen eleven-case selection, reference disposition and sensitivity evidence.

No exchange, Scanner, Telegram or Robot calls. Original disputed line equations
and candle runs remain alongside new expectations; no ignored-fixture skips.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import geometry.engine as engine
from geometry.envelope_metrics import evaluate_formation_body_fit, evaluate_body_zone_breaches, evaluate_strict_wedge_wicks, line_value
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
                # Pinned pre-change baseline 8cd852a / CI 45374861702:
                # INJ and XRP already returned None; their archived triangle
                # lines are historical evidence, not current admitted pairs.
                if name in ("INJ", "XRP"):
                    if geometry is not None:
                        frame = self.frames[name]
                        highs, lows = find_pivots(frame.copy())
                        with patch.object(engine, "build_wedge_hull_support_lines", return_value=([], [])), contextlib.redirect_stdout(io.StringIO()):
                            baseline = engine.analyze_geometry(highs, lows, len(frame)-1, frame, _freshness_predicate)
                        seq = geometry.pair_metrics["anchor_sequence"]
                        fit = geometry.envelope_metrics["formation_body_fit"]
                        result = detect_structure(geometry, candles=frame)
                        print("HULL_REGRESSION", json.dumps(dict(
                            symbol=name, baseline=identity(baseline),
                            selected=identity(geometry),
                            anchors=seq,
                            slopes=[geometry.upper_line["slope"], geometry.lower_line["slope"]],
                            contacts=[geometry.upper_line["confirmations"], geometry.lower_line["confirmations"]],
                            strict_wicks={side:evaluate_strict_wedge_wicks(
                                getattr(geometry, side+"_line"),frame,side,geometry.end_index,len(frame)-1)
                                for side in ("upper","lower")},
                            fit={side:fit[side]["body_breach_indices"] for side in ("upper","lower")},
                            fresh=_freshness_predicate(geometry.start_index,geometry.end_index,
                                geometry.apex["index"],geometry.current_index),
                            apex=geometry.apex, compression=geometry.compression,
                            detected=result.get("detected"), detection=result,
                            historical_reference=case["disputed_reference"]["geometry"]["anchors"],
                            highs=[(p["index"],p["price"]) for p in highs],
                            lows=[(p["index"],p["price"]) for p in lows]
                        ),default=str,sort_keys=True))
                    self.assertIsNone(geometry)
                    continue
                if name in ("WLD", "AAVE"):
                    # Explicit dispositions measured in the same baseline/PR
                    # comparison, not automatic refresh of archived winners.
                    frame = self.frames[name]
                    if name == "WLD":
                        # The preceding baseline rising wedge U80/165 L89/177
                        # violates its strict lower side at seven candles.
                        # LOW147 is even below LOW89: no rising line through
                        # the structural lower anchor can enclose this episode.
                        a, b = 89, 177
                        pa, pb = float(frame.iloc[a].low), float(frame.iloc[b].low)
                        slope = (pb-pa)/(b-a)
                        old_lower = {"anchor_index": a, "slope": slope,
                                     "intercept": pa-slope*a}
                        self.assertEqual(evaluate_strict_wedge_wicks(
                            old_lower, frame, "lower", 190, len(frame)-1
                        ), [145,146,147,148,149,153,154])
                        self.assertLess(frame.iloc[147].low, pa)
                        expected = [39,117,43,89,39,117]
                        lower_breaches = [61,62,63]
                    else:
                        # No selected baseline geometry. The new local support
                        # yields a stale falling diagnostic, not a signal.
                        expected = [38,79,40,91,38,91]
                        lower_breaches = [44,45,46,47,48,49,52,53,54,55]
                    self.assertEqual(identity(geometry), expected)
                    sequence = geometry.pair_metrics["anchor_sequence"]
                    self.assertEqual(sequence["family"], "falling")
                    self.assertTrue(sequence["valid"])
                    for side, a, b in (("upper", expected[0], expected[1]),
                                       ("lower", expected[2], expected[3])):
                        line = getattr(geometry, side + "_line")
                        column = "high" if side == "upper" else "low"
                        self.assertAlmostEqual(line_value(line, a), frame.iloc[a][column], places=12)
                        self.assertAlmostEqual(line_value(line, b), frame.iloc[b][column], places=12)
                    self.assertEqual(evaluate_strict_wedge_wicks(
                        geometry.upper_line, frame, "upper", geometry.end_index,
                        len(frame)-1
                    ), [])
                    fit = geometry.envelope_metrics["formation_body_fit"]
                    self.assertEqual(fit["upper"]["body_breach_indices"], [])
                    self.assertEqual(fit["lower"]["body_breach_indices"], lower_breaches)
                    self.assertLess(fit["lower"]["max_consecutive_breaches"], 7)
                    self.assertFalse(_freshness_predicate(
                        geometry.start_index, geometry.end_index,
                        geometry.apex["index"], geometry.current_index
                    ))
                    self.assertFalse(detect_structure(geometry, candles=frame)["detected"])
                    continue
                if name == "PONS":
                    # Explicit owner strict-boundary revision, not a rewrite
                    # of the archived historical fixture. The old upper ray
                    # crosses three highs, including two candle bodies.
                    frame = self.frames[name]
                    old = want["geometry"]
                    self.assertEqual(evaluate_strict_wedge_wicks(
                        old["lines"][0], frame, "upper", old["end"], len(frame)-1
                    ), [158, 167, 168])
                    want = copy.deepcopy(want)
                    g = want["geometry"]
                    upper = g["lines"][0]
                    first, second = 143, 167
                    a, b = float(frame.iloc[first].high), float(frame.iloc[second].high)
                    slope = (b-a)/(second-first)
                    upper.update(anchor_index=first, second_index=second,
                                 anchor_price=a, second_price=b,
                                 slope=slope, intercept=a-slope*first)
                    g["anchors"][1] = second
                    g["widths"] = [line_value(upper, i)-line_value(g["lines"][1], i)
                                   for i in (g["start"], g["end"])]
                    want["fit"][0] = {"indices": [], "runs": [], "max_run": 0}
                    self.assertEqual(evaluate_strict_wedge_wicks(
                        upper, frame, "upper", g["end"], len(frame)-1
                    ), [])
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
                    # AAVE's measured six-bar non-strict body run is
                    # admitted only under the existing cutoff 7 or above.
                    # Below that, the historical comparison proved no winner.
                    # All other PR winners remain stable across this range.
                    expected = None if name == "AAVE" and cutoff <= 6 else identity(self.winners[name])
                    self.assertEqual(identity(winner), expected)


if __name__ == "__main__":
    unittest.main()
