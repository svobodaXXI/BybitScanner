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
        from geometry.triangle_boundaries import build_closed_wick_triangle_pairs
        from geometry.evaluation import evaluate_candidate_pair
        from wedge.detector import detect_structure
        from unittest.mock import patch
        pairs=build_closed_wick_triangle_pairs(highs,lows,frame,len(frame)-1,max_span=round(len(frame)*engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO))
        anchors=lambda u,l:[u["anchor_index"],u["second_index"],l["anchor_index"],l["second_index"]]
        correct=[(u,l) for u,l in pairs if anchors(u,l)==f["corrected_anchors"]]
        self.assertEqual(len(correct),1)
        u,l=correct[0]
        self.assertEqual(u["points"][-1]["contact_kind"],"CLOSED_WICK_NOT_CONFIRMED_PIVOT")
        self.assertEqual(l["points"][-1]["contact_kind"],"CLOSED_WICK_NOT_CONFIRMED_PIVOT")
        direct=evaluate_candidate_pair(u,l,highs=highs,lows=lows,current_index=len(frame)-1,candles=frame)
        self.assertIsNotNone(direct)
        print("PENGSTOCK_WICK_DIRECT",json.dumps(dict(validation=direct.validation,
              sequence=direct.pair_metrics["anchor_sequence"],end=direct.end_index,
              fresh=engine._is_candidate_fresh(direct,_freshness_predicate),
              detection=detect_structure(direct,candles=frame)),default=str))
        self.assertTrue(direct.validation["valid"],direct.validation)
        self.assertTrue(engine._is_anchor_sequence_valid(direct),direct.pair_metrics)
        self.assertTrue(engine._is_candidate_local(direct,len(frame)-1))
        self.assertTrue(engine._is_boundary_structurally_valid(direct))
        self.assertTrue(engine._is_candidate_fresh(direct,_freshness_predicate))
        self.assertTrue(detect_structure(direct,candles=frame)["detected"])
        self.assertEqual(direct.end_index,196)
        future=frame.copy()
        future.loc[len(frame)]={"open":1000,"high":1000,"low":1,"close":1,"time":int(frame.time.iloc[-1])+f["step_ms"],"volume":0}
        self.assertEqual([anchors(u,l) for u,l in pairs],
          [anchors(u,l) for u,l in build_closed_wick_triangle_pairs(highs,lows,future,len(frame)-1,max_span=round(len(frame)*engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO))])
        self.assertFalse(any(anchors(u,l)==f["corrected_anchors"] for u,l in
          build_closed_wick_triangle_pairs(highs,lows,frame,193)))
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
                direct=dict(validation=g.validation,sequence=g.pair_metrics.get("anchor_sequence"),
                    compression=g.compression,mode=g.pair_metrics.get("geometry_mode"),end=g.end_index,
                    fresh=engine._is_candidate_fresh(g,_freshness_predicate),
                    boundary=engine._is_boundary_structurally_valid(g))
        # The candidate is supported by confirmed local pivots but does not
        # satisfy the existing apex-extension limit. Do not tune a threshold
        # or extend END just to reproduce the historical manual drawing.
        self.assertIsNotNone(direct)
        self.assertIn("apex_quality",direct["validation"]["failed_checks"])
        apex_quality=direct["validation"]["checks"]["apex_quality"]
        self.assertEqual(apex_quality["reason"],"Apex extension too large")
        self.assertGreater(apex_quality["details"]["ratio"],3.0)
        self.assertEqual(direct["end"],186)
        self.assertTrue(direct["sequence"]["valid"])
        winner=engine.analyze_geometry(highs,lows,len(frame)-1,frame,_freshness_predicate)
        print("BMT_NATIVE",json.dumps(dict(local_highs=[x["index"] for x in qh],
            local_lows=[x["index"] for x in ql],upper=contacts(upper,148),lower=contacts(lower,146),
            triangle_upper=contacts(tu,148),triangle_lower=contacts(tl,146),
            strict_upper=contacts(wu,148),strict_lower=contacts(wl,146),
            local_upper=contacts(local_u,148),local_lower=contacts(local_l,146),
            direct=direct,winner=None if winner is None else [winner.upper_line["anchor_index"],
                winner.upper_line["second_index"],winner.lower_line["anchor_index"],
                winner.lower_line["second_index"],winner.start_index,winner.end_index]),default=str,sort_keys=True))



class ConfirmedNonStrictHullEvidence(unittest.TestCase):
    def test_usual_owner_adjacent_clean_pair(self):
        from unittest.mock import patch
        from geometry.evaluation import evaluate_candidate_pair
        f = json.loads((FIXTURE.parent / "USUALUSDT_5m_adjacent_boundary_20261125.json").read_text())
        rows = f["ohlc_int"]
        self.assertEqual(hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest(),
                         f["ohlc_int_sha256"])
        frame = pd.DataFrame(rows,columns=["open","high","low","close"])/f["price_scale"]
        frame["time"]=[f["first_open_ms"]+i*f["step_ms"] for i in range(len(frame))]
        frame["volume"]=0.
        frame=frame.iloc[:f["as_of_index"]+1].copy()
        highs,lows=find_pivots(frame.copy())
        for points,indices in ((highs,(120,189)),(lows,(123,167))):
            self.assertTrue(all(i in [p["index"] for p in points] for i in indices))
        for side,a,b,sign in (("high",120,189,1),("low",123,167,-1)):
            x,y=frame.iloc[a][side],frame.iloc[b][side]
            self.assertEqual([i for i in range(a,190)
                if sign*(frame.iloc[i][side]-x-(y-x)*(i-a)/(b-a))>1e-12],[])
        pick=lambda pool,a,b:next((p for p in pool if (p["anchor_index"],p["second_index"])==(a,b)),None)
        upper=pick(filter_candidates(build_candidate_lines(highs)),120,189)
        lower=pick(build_candidate_lines(lows,min_confirmations=1),123,167)
        self.assertIsNotNone(upper)
        self.assertIsNotNone(lower)
        self.assertEqual(lower["confirmations"],1)
        direct=evaluate_candidate_pair(upper,lower,highs=highs,lows=lows,current_index=len(frame)-1,candles=frame)
        observed=None if direct is None else dict(
            validation=direct.validation,sequence=direct.pair_metrics.get("anchor_sequence"),
            boundary=engine._is_boundary_structurally_valid(direct),
            local=engine._is_candidate_local(direct,len(frame)-1),
            fresh=engine._is_candidate_fresh(direct,_freshness_predicate),end=direct.end_index)
        native_calls=[]
        comparison=[]
        compared_models={}
        native=engine.evaluate_candidate_pair
        def trace(u,l,*args,**kwargs):
            anchors=[u["anchor_index"],u["second_index"],l["anchor_index"],l["second_index"]]
            g=native(u,l,*args,**kwargs)
            if anchors==f["corrected_anchors"]:
                native_calls.append(True)
            if g is not None and anchors in (f["corrected_anchors"],f["original_anchors"]):
                from geometry.envelope_metrics import evaluate_strict_wedge_wicks
                compared_models[tuple(anchors)]=g
                seq=g.pair_metrics.get("anchor_sequence")
                comparison.append(dict(anchors=anchors,sequence=seq,
                    mode=g.pair_metrics.get("geometry_mode"),
                    score=engine.rank_geometry(g),body_breaches=engine._body_zone_breach_count(g),
                    strict_wick_exception=g.pair_metrics.get("strict_wick_exception_index"),
                    wicks={side:evaluate_strict_wedge_wicks(getattr(g,side+"_line"),frame,side,
                        g.end_index,len(frame)-1) for side in ("upper","lower")},
                    fresh=engine._is_candidate_fresh(g,_freshness_predicate),
                    validation=g.validation.get("valid"),end=g.end_index))
            return g
        with patch.object(engine,"evaluate_candidate_pair",side_effect=trace):
            winner=engine.analyze_geometry(highs,lows,len(frame)-1,frame,_freshness_predicate)
        print("USUAL_NATIVE",json.dumps(dict(direct=observed,native_calls=len(native_calls),comparison=comparison,
            winner=None if winner is None else [winner.upper_line["anchor_index"],
                winner.upper_line["second_index"],winner.lower_line["anchor_index"],
                winner.lower_line["second_index"],winner.start_index,winner.end_index]),default=str,sort_keys=True))
        # Do not conflate geometric containment with otherwise valid admission.
        self.assertIsNotNone(observed, "Owner pair must survive direct native evaluation before generator change")
        self.assertTrue(observed["validation"]["valid"],observed)
        self.assertTrue(observed["sequence"]["valid"],observed)
        self.assertTrue(all(observed[k] for k in ("boundary","local","fresh")),observed)
        self.assertTrue(native_calls,"Otherwise valid owner pair lost before native evaluation")
        self.assertIsNotNone(winner)
        self.assertEqual([winner.upper_line["anchor_index"],winner.upper_line["second_index"],
                          winner.lower_line["anchor_index"],winner.lower_line["second_index"]],
                         f["corrected_anchors"])
        from geometry.wedge_boundaries import build_wedge_hull_support_lines, wedge_hull_pair_allowed, prefer_recovered_wedge_hulls
        from copy import deepcopy
        from wedge.detector import detect_structure
        def ranked(g):
            return dict(geometry=g,mode_priority=1,fresh=True,strict_wick_exception=False,
                        body_breaches=engine._body_zone_breach_count(g),score=engine.rank_geometry(g))
        previous=ranked(compared_models[tuple(f["original_anchors"])])
        corrected=ranked(compared_models[tuple(f["corrected_anchors"])])
        self.assertEqual(corrected["geometry"].pair_metrics["wedge_hull_support"],"lower")
        self.assertEqual(prefer_recovered_wedge_hulls([previous,corrected],frame),[corrected])
        self.assertEqual(prefer_recovered_wedge_hulls([corrected,previous],frame),[corrected])
        self.assertEqual(prefer_recovered_wedge_hulls([corrected],frame),[])
        self.assertEqual(prefer_recovered_wedge_hulls([previous,corrected],None),[previous])
        for field,value in (("fresh",False),("mode_priority",0),("body_breaches",1)):
            self.assertEqual(prefer_recovered_wedge_hulls([previous,dict(corrected,**{field:value})],frame),[previous])
        different=deepcopy(corrected)
        different["geometry"].pair_metrics["anchor_sequence"]["impulse_origin_index"]=116
        self.assertEqual(prefer_recovered_wedge_hulls([previous,different],frame),[previous])
        detected=detect_structure(winner,candles=frame)
        self.assertTrue(detected["detected"],detected)
        self.assertEqual(detected["pattern"],"Falling Wedge")
        print("USUAL_DETECTION",json.dumps(detected,default=str,sort_keys=True))
        for mirrored in (False,True):
            with self.subTest(mirrored=mirrored):
                if mirrored:
                    # Reflect near the original quote scale: a 0.03 ceiling
                    # increases price enough to turn two additional pivots
                    # into percentage-tolerance confirmations. This fixture
                    # must retain the actual one-forward-contact hull premise.
                    ceiling=0.0212
                    bars=frame.copy()
                    for key,source in (("high","low"),("low","high"),("open","open"),("close","close")):
                        bars[key]=ceiling-frame[source]
                    hs=[dict(p,price=ceiling-p["price"],type="high") for p in lows]
                    ls=[dict(p,price=ceiling-p["price"],type="low") for p in highs]
                else:
                    bars,hs,ls=frame,highs,lows
                strict=pick(build_candidate_lines(ls if mirrored else hs),120,189)
                self.assertIsNotNone(strict)
                self.assertEqual(strict["confirmations"],2)
                reference_hull=pick(build_candidate_lines(hs if mirrored else ls,min_confirmations=1),123,167)
                self.assertIsNotNone(reference_hull)
                self.assertEqual(reference_hull["confirmations"],1)
                hu,hl=build_wedge_hull_support_lines(hs,ls,[] if mirrored else [strict],
                                                   [strict] if mirrored else [],bars,len(bars)-1)
                hull=pick(hu if mirrored else hl,123,167)
                self.assertIsNotNone(hull)
                u,v=(hull,strict) if mirrored else (strict,hull)
                allowed=lambda x,y,b,cut=len(bars)-1: wedge_hull_pair_allowed(x,y,hs,ls,b,cut)
                self.assertTrue(allowed(u,v,bars))
                self.assertFalse(allowed(u,v,None))
                self.assertFalse(allowed(u,v,bars,188))
                other=dict(strict,triangle_only=True)
                self.assertFalse(allowed(hull,other,bars) if mirrored else allowed(other,hull,bars))
                other=dict(strict,strict_wedge_support="lower" if mirrored else "upper")
                self.assertFalse(allowed(hull,other,bars) if mirrored else allowed(other,hull,bars))
                # A real outside wick before END must veto the extra edge;
                # an excursion after END must not change frozen evidence.
                key="high" if mirrored else "low"
                change=1.0 if mirrored else 0.000001
                outside=bars.copy()
                outside.loc[150,key]=change
                self.assertFalse(allowed(u,v,outside))
                outside=bars.copy()
                outside.loc[190,key]=change
                self.assertTrue(allowed(u,v,outside))



if __name__=="__main__":
    unittest.main()
