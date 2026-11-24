"""Frozen real-price regression; no historical runtime replay claim."""
import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd
from geometry.candidate import build_candidate_lines
from geometry.filter import filter_candidates
from geometry.evaluation import evaluate_candidate_pair
from geometry.engine import analyze_geometry
from pivots import find_pivots
from wedge.analyzer import _freshness_predicate

FIXTURE = Path(__file__).parent / "fixtures" / "geometry_gold" / "XANUSDT_5m_strict_lower_20261124.json"


class StrictWedgeFrozenTest(unittest.TestCase):
    def test_original_rising_wedge_pair_cannot_be_constructed(self):
        case = json.loads(FIXTURE.read_text())
        encoded = json.dumps(case["ohlc_int"], separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), case["ohlc_int_sha256"])
        frame = pd.DataFrame(case["ohlc_int"], columns=["open", "high", "low", "close"]) / case["price_scale"]
        frame["time"] = [case["first_open_ms"] + i * case["step_ms"] for i in range(len(frame))]
        frame["volume"] = 0.
        frame = frame.iloc[:case["as_of_index"] + 1].copy()
        highs, lows = find_pivots(frame.copy())
        a, b, c, d = case["original_anchors"]
        def pick(points, start, second):
            candidates = filter_candidates(build_candidate_lines(points))
            return next((item for item in candidates if (item["anchor_index"], item["second_index"]) == (start, second)), None)
        upper, lower = pick(highs, a, b), pick(lows, c, d)
        self.assertIsNotNone(upper, "archived upper pair not generated on this cutoff")
        self.assertIsNotNone(lower, "archived lower pair not generated on this cutoff")
        end = max(upper["points"][-1]["index"], lower["points"][-1]["index"])
        line = lower["line"]
        protrusions = [i for i in range(c, end + 1) if float(frame.iloc[i]["low"]) < line["slope"] * i + line["intercept"] - 1e-12]
        self.assertIn(178, protrusions)
        self.assertIn(179, protrusions)
        original = evaluate_candidate_pair(upper, lower, highs=highs, lows=lows, current_index=len(frame)-1, candles=frame)
        winner = analyze_geometry(highs, lows, len(frame)-1, frame, _freshness_predicate)
        print("ARCHIVED_PAIR", case["original_anchors"], "END", end, "PROTRUSIONS", protrusions,
              "PAIR_VALIDATION", None if original is None else original.validation,
              "PAIR_ANCHORS", None if original is None else original.pair_metrics.get("anchor_sequence"),
              "NATIVE_WINNER", None if winner is None else [winner.upper_line["anchor_index"], winner.upper_line["second_index"], winner.lower_line["anchor_index"], winner.lower_line["second_index"]])
        self.assertIsNone(original, "strict lower wick protrusions must prevent pair construction")



class EarlyImpulseFrozenTest(unittest.TestCase):
    def test_early_high_and_immediate_low_are_distinct_from_drawn_support(self):
        from geometry.pair_metrics import calculate_pair_metrics
        import geometry.engine as engine
        from unittest.mock import patch
        case = json.loads((FIXTURE.parent / "EIGENUSDT_5m_early_impulse_20261124.json").read_text())
        rows = case["ohlc_int"]
        self.assertEqual(hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest(),
                         case["ohlc_int_sha256"])
        frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"]) / case["price_scale"]
        frame["time"] = [case["first_open_ms"] + i * case["step_ms"] for i in range(len(frame))]
        frame["volume"] = 0.
        frame = frame.iloc[:case["as_of_index"] + 1].copy()
        highs, lows = find_pivots(frame.copy())
        upper = filter_candidates(build_candidate_lines(highs))
        lower = filter_candidates(build_candidate_lines(lows))
        def pick(items, a, b):
            return next(c for c in items if (c["anchor_index"], c["second_index"]) == (a,b))
        def metrics(u,l):
            return calculate_pair_metrics(u,l,len(frame)-1,highs=highs,lows=lows,candles=frame)["anchor_sequence"]
        old_u, old_l = pick(upper,128,161), pick(lower,148,189)
        new_u, new_l = pick(upper,75,128), pick(lower,91,173)
        old_seq, new_seq = metrics(old_u,old_l), metrics(new_u,new_l)
        self.assertEqual(new_seq["expected_secondary_index"],78)
        self.assertEqual(new_seq["secondary_anchor"],91)
        self.assertFalse(new_seq["valid"])
        self.assertTrue(old_seq["valid"])
        def identity(g):
            return None if g is None else [g.upper_line["anchor_index"],g.upper_line["second_index"],
                    g.lower_line["anchor_index"],g.lower_line["second_index"],g.start_index,g.end_index]
        # Read-only native evaluation and exact selection-key components.
        # Keep all existing gates; no alternative selector.
        trace = {}
        native = engine.evaluate_candidate_pair
        def observe(u,l,*args,**kwargs):
            result = native(u,l,*args,**kwargs)
            if result is None:
                return result
            ident = identity(result)
            if ident[0:4] not in ([75,128,78,189], [75,128,78,148],
                                   [128,161,148,189]):
                return result
            pm = result.pair_metrics
            fit = result.envelope_metrics["formation_body_fit"]
            seq = pm["anchor_sequence"]
            origin = seq["impulse_origin_index"]
            start = seq["primary_anchor"]
            terminal = float(frame.iloc[start].high)
            trace[tuple(ident[:4])] = dict(
                geometry=ident,
                validation=result.validation.get("valid"),
                local=engine._is_candidate_local(result,len(frame)-1),
                boundary=engine._is_boundary_structurally_valid(result),
                sequence=engine._is_anchor_sequence_valid(result),
                fresh=engine._is_candidate_fresh(result,_freshness_predicate),
                mode=pm["geometry_mode"],
                wick_exception=pm.get("strict_wick_exception_index"),
                body_breaches=engine._body_zone_breach_count(result),
                body_indices={side:fit[side]["body_breach_indices"] for side in ("upper","lower")},
                score=engine.rank_geometry(result),
                origin=origin,
                first_impulse=terminal-float(frame.iloc[origin].low),
                preceding_context=pm.get("pre_pattern_impulse"),
                first_wave=terminal-float(frame.iloc[seq["secondary_anchor"]].low),
                compression=result.compression)
            return result
        with patch.object(engine, "evaluate_candidate_pair", side_effect=observe):
            winner=engine.analyze_geometry(highs,lows,len(frame)-1,frame,_freshness_predicate)
        # Assert the structural boundary of the reproduced defect rather
        # than force the manually drawn non-adjacent lower anchor.
        for anchors in ((75,128,78,189), (75,128,78,148)):
            record = trace[anchors]
            self.assertTrue(all(record[k] for k in ("validation","local","boundary","sequence","fresh")))
        self.assertIn((128,161,148,189), trace)
        print("EIGEN_SELECTION",json.dumps({"pairs":list(trace.values()),
              "winner":identity(winner)},default=str,sort_keys=True))


if __name__ == "__main__":
    unittest.main()
