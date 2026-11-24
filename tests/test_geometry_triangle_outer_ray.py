"""PENGSTOCKUSDT owner upper-ray evidence; no historical decision claim."""
import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd
import geometry.engine as engine
from geometry.candidate import build_candidate_lines
from geometry.filter import filter_candidates
from geometry.triangle_boundaries import build_triangle_only_lines, local_alternation_pivots
from pivots import find_pivots
from wedge.analyzer import _freshness_predicate

FIXTURE = Path(__file__).parent / "fixtures/geometry_gold/PENGSTOCKUSDT_5m_upper_ray_20261125.json"


class TriangleOuterRayEvidence(unittest.TestCase):
    def test_owner_upper_contact_and_native_candidates(self):
        f = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = f["ohlc_int"]
        self.assertEqual(hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest(),
                         f["ohlc_int_sha256"])
        self.assertEqual(len(rows),199)
        frame = pd.DataFrame(rows,columns=["open","high","low","close"])/f["price_scale"]
        frame["time"] = [f["first_open_ms"]+i*f["step_ms"] for i in range(len(frame))]
        frame["volume"] = 0.
        frame = frame.iloc[:f["as_of_index"]+1].copy()
        def breaches(a,b,end):
            x,y = frame.iloc[a].high,frame.iloc[b].high
            return [i for i in range(a,end+1)
                    if frame.iloc[i].high > x+(y-x)*(i-a)/(b-a)+1e-10]
        self.assertEqual(breaches(157,190,196),[191,194])
        self.assertEqual(breaches(157,194,196),[])
        raw_highs,raw_lows = find_pivots(frame.copy(),min_change=0)
        highs,lows = find_pivots(frame.copy())
        qh,ql = local_alternation_pivots(frame,len(frame)-1)
        self.assertIn(157,[p["index"] for p in highs])
        self.assertIn(190,[p["index"] for p in raw_highs])
        self.assertNotIn(194,[p["index"] for p in raw_highs])
        self.assertNotIn(196,[p["index"] for p in raw_lows])
        upper,lower = filter_candidates(build_candidate_lines(highs)),filter_candidates(build_candidate_lines(lows))
        tu,tl = build_triangle_only_lines(highs,lows,upper,lower,len(frame)-1,candles=frame,
                                           max_span=round(len(frame)*engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO))
        def starts(pool,anchor):
            return sorted({(p["anchor_index"],p["second_index"],p["points"][-1]["index"])
                           for p in pool if p["anchor_index"]==anchor})
        winner = engine.analyze_geometry(highs,lows,len(frame)-1,frame,_freshness_predicate)
        observed = None
        if winner is not None:
            observed = dict(anchors=[winner.upper_line["anchor_index"],winner.upper_line["second_index"],
                                     winner.lower_line["anchor_index"],winner.lower_line["second_index"]],
                            start=winner.start_index,end=winner.end_index,
                            sequence=winner.pair_metrics.get("anchor_sequence"),
                            validation=winner.validation,
                            mode=winner.pair_metrics.get("geometry_mode"))
        print("PENGSTOCK_NATIVE",json.dumps(dict(raw_highs=[p["index"] for p in raw_highs],
              raw_lows=[p["index"] for p in raw_lows], local_highs=[p["index"] for p in qh],
              local_lows=[p["index"] for p in ql], upper=starts(upper,157),lower=starts(lower,155),
              triangle_upper=starts(tu,157),triangle_lower=starts(tl,155),winner=observed),
              default=str,sort_keys=True))



class ConfirmedBoundaryEvidence(unittest.TestCase):
    def test_bmt_confirmed_short_outer_contact(self):
        from geometry.wedge_boundaries import build_strict_wedge_support_lines
        from geometry.evaluation import evaluate_candidate_pair
        f = json.loads((FIXTURE.parent / "BMTUSDT_1m_confirmed_boundary_20261125.json").read_text())
        rows = f["ohlc_int"]
        self.assertEqual(hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest(),
                         f["ohlc_int_sha256"])
        frame = pd.DataFrame(rows,columns=["open","high","low","close"])/f["price_scale"]
        frame["time"] = [f["first_open_ms"]+i*f["step_ms"] for i in range(len(frame))]
        frame["volume"] = 0.
        frame = frame.iloc[:f["as_of_index"]+1].copy()
        rh,rl = find_pivots(frame.copy(),min_change=0)
        highs,lows = find_pivots(frame.copy())
        qh,ql = local_alternation_pivots(frame,len(frame)-1)
        for ix in (148,162,184):
            self.assertIn(ix,[x["index"] for x in rh])
        for ix in (146,179):
            self.assertIn(ix,[x["index"] for x in rl])
        def breaches(a,b,side,end):
            x,y = frame.iloc[a][side],frame.iloc[b][side]
            sign=1 if side=="high" else -1
            return [i for i in range(a,end+1)
                    if sign*(frame.iloc[i][side]-x-(y-x)*(i-a)/(b-a))>1e-12]
        self.assertEqual(breaches(148,184,"high",184),[161,162,163,165])
        self.assertEqual(breaches(148,162,"high",179),[])
        self.assertEqual(breaches(146,179,"low",179),[])
        upper,lower = filter_candidates(build_candidate_lines(highs)),filter_candidates(build_candidate_lines(lows))
        tu,tl = build_triangle_only_lines(highs,lows,upper,lower,len(frame)-1,candles=frame,
                                           max_span=round(len(frame)*engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO))
        wu,wl = build_strict_wedge_support_lines(highs,lows,upper,lower,frame,len(frame)-1)
        def contacts(pool,a):
            return sorted({(p["anchor_index"],p["second_index"],p["points"][-1]["index"]) for p in pool if p["anchor_index"]==a})
        local_u=build_candidate_lines(qh,min_line_span=1)
        local_l=build_candidate_lines(ql,min_line_span=1)
        pick=lambda pool,a,b:next((x for x in pool if (x["anchor_index"],x["second_index"])==(a,b)),None)
        u,v=pick(local_u,148,162),pick(local_l,146,179)
        direct=None
        if u is not None and v is not None:
            g=evaluate_candidate_pair(u,v,highs=highs,lows=lows,current_index=len(frame)-1,candles=frame)
            if g is not None:
                direct=dict(validation=g.validation.get("valid"),sequence=g.pair_metrics.get("anchor_sequence"),
                    compression=g.compression,mode=g.pair_metrics.get("geometry_mode"),end=g.end_index,
                    fresh=engine._is_candidate_fresh(g,_freshness_predicate),
                    boundary=engine._is_boundary_structurally_valid(g))
        winner=engine.analyze_geometry(highs,lows,len(frame)-1,frame,_freshness_predicate)
        print("BMT_NATIVE",json.dumps(dict(local_highs=[x["index"] for x in qh],
            local_lows=[x["index"] for x in ql],upper=contacts(upper,148),lower=contacts(lower,146),
            triangle_upper=contacts(tu,148),triangle_lower=contacts(tl,146),
            strict_upper=contacts(wu,148),strict_lower=contacts(wl,146),
            local_upper=contacts(local_u,148),local_lower=contacts(local_l,146),
            direct=direct,winner=None if winner is None else [winner.upper_line["anchor_index"],
                winner.upper_line["second_index"],winner.lower_line["anchor_index"],
                winner.lower_line["second_index"],winner.start_index,winner.end_index]),default=str,sort_keys=True))


if __name__=="__main__":
    unittest.main()
