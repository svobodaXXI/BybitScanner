import unittest
import pandas as pd
from geometry.wedge_control_anchor import propose_control_boundary


def data(highs):
    return pd.DataFrame({"high": highs, "low": [70.]*(len(highs)-1)+[69.99]})


def pivots(highs):
    return [{"index": i, "price": highs[i], "known_at_ms": (i+1)*100}
            for i in (0,2,4)]


class WedgeControlAnchorTest(unittest.TestCase):
    def evaluate(self, highs, **overrides):
        args = dict(family="falling", episode_start=0, first_strict_index=0,
                    previous_extreme="70", trade_price="69.99",
                    event_index=5, event_time_ms=600,
                    established_pivots=pivots(highs), candles=data(highs))
        return propose_control_boundary(**dict(args, **overrides))

    def test_new_tick_and_contact(self):
        highs=[100.,98.,96.,94.,92.,90.]
        for price in ("101", "70", "70.01"):
            self.assertEqual(self.evaluate(highs,trade_price=price)["status"],"UNCHANGED")
        r=self.evaluate(highs)
        self.assertEqual(r["status"],"CONTROL_CONTACT")
        self.assertEqual(r["control_anchor"]["index"],4)
        self.assertEqual(r["lines"][0]["second_index"],4)
        self.assertEqual(r["episode_start"],0)

    def test_earlier_extremum_forces_outer_line(self):
        highs=[100.,98.,96.,91.,86.,85.]
        r=self.evaluate(highs)
        self.assertEqual(r["status"],"OUTER_ENVELOPE")
        self.assertEqual(r["control_anchor"]["index"],4)
        self.assertEqual(r["lines"][0]["second_index"],2)

    def test_mirror(self):
        highs=[100.,98.,96.,91.,86.,85.]
        # Build mirror from the exact decimal event price; avoid binary
        # subtraction changing the event's tick identity.
        b=data(highs)
        m=pd.DataFrame({"high":[130.]*5+[130.01], "low":200-b.high})
        r=self.evaluate(highs,family="rising",previous_extreme="130",
                        trade_price="130.01",candles=m,
                        established_pivots=pivots(list(m.low)))
        self.assertEqual(r["status"],"OUTER_ENVELOPE")
        self.assertGreater(r["lines"][0]["slope"],0)

    def test_later_wick_not_a_structural_fallback(self):
        self.assertEqual(self.evaluate([100.,98.,96.,94.,92.,99.])["status"],
                         "REBUILD_UNAVAILABLE")

    def test_unavailable_or_future_evidence(self):
        highs=[100.,98.,96.,94.,92.,90.]
        self.assertEqual(self.evaluate(highs,candles=None)["status"],"REBUILD_UNAVAILABLE")
        self.assertEqual(self.evaluate(highs,trade_price="69.98")["status"],"REBUILD_UNAVAILABLE")
        p=pivots(highs)
        p[-1]["known_at_ms"]=601
        r=self.evaluate(highs,established_pivots=p)
        self.assertEqual(r["control_anchor"]["index"],2)

    def test_future_rows_do_not_change_revision_proposal(self):
        highs=[100.,98.,96.,94.,92.,90.]
        b=pd.concat([data(highs),pd.DataFrame({"high":[999.],"low":[1.]})],ignore_index=True)
        self.assertEqual(self.evaluate(highs),self.evaluate(highs,candles=b))

    def test_native_print_prefix_same_bar_and_first_print(self):
        from decimal import Decimal
        from terminal.market_data.impulse_observation import ObservedPrint
        from geometry.wedge_control_anchor import propose_control_boundary_from_print

        highs = [100., 98., 96., 94., 92.]
        prefix = pd.DataFrame({
            "open_time_ms": [60_000*i for i in range(1, 6)],
            "open": [75.]*5, "high": highs, "low": [70.]*5, "close": [75.]*5,
        })
        known = [{"index": i, "price": highs[i], "known_at_ms": (i+2)*60_000}
                 for i in (0, 2, 4)]

        def evaluate(frame, price, timestamp, cutoff):
            return propose_control_boundary_from_print(
                family="falling", episode_start=0, first_strict_index=0,
                established_pivots=known, candles=frame, timeframe_ms=60_000,
                prefix_as_of_ms=cutoff,
                observed_print=ObservedPrint("tick", timestamp, 1, "Sell",
                                             Decimal(price), Decimal("1"), timestamp+1),
            )

        first = evaluate(prefix, "69.99", 360001, 359999)
        self.assertEqual(first["status"], "CONTROL_CONTACT")
        self.assertEqual(first["source_trade_id"], "tick")
        self.assertEqual(first["control_anchor"]["index"], 4)
        self.assertEqual(len(prefix), 5)
        active = pd.concat([prefix, pd.DataFrame([{
            "open_time_ms": 360000, "open": 69.99, "high": 69.99,
            "low": 69.99, "close": 69.99,
        }])], ignore_index=True)
        self.assertEqual(evaluate(active, "69.99", 360002, 360001)["status"], "UNCHANGED")
        second = evaluate(active, "69.98", 360002, 360001)
        self.assertEqual(second["status"], "CONTROL_CONTACT")
        self.assertEqual(second["previous_extreme"], "69.99")
        self.assertEqual(second["source_bar_open_ms"], 360000)
        self.assertEqual(active.iloc[-1]["low"], 69.99)
        self.assertEqual(evaluate(active, "69.98", 360000, 360001)["status"],
                         "REBUILD_UNAVAILABLE")
        self.assertEqual(evaluate(prefix, "69.99", 420001, 359999)["status"],
                         "REBUILD_UNAVAILABLE")
        self.assertEqual(evaluate(active, "69.98", 360002, 359999)["status"],
                         "REBUILD_UNAVAILABLE")

    def test_seed_uses_exact_archived_native_geometry(self):
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from signal_archive import record_original_signal
        from geometry.wedge_control_anchor import load_control_anchor_seed
        from geometry.trendline import fit_anchor_trendline

        highs = [90,92,94,100,92,90,91,96,88,86,87,92,84,82,81,80]
        bars = [{"open_time_ms": (i+1)*300000, "open": h-10,
                 "high": h, "low": h-20, "close": h-10}
                for i,h in enumerate(highs)]
        upper = fit_anchor_trendline([{"index": i, "price": highs[i]}
                                      for i in (3,7)])
        lower = fit_anchor_trendline([{"index": i, "price": highs[i]-20}
                                      for i in (5,9)])
        geometry = {"upper_line": upper, "lower_line": lower,
                    "start_index": 3, "end_index": 11, "current_index": 15}
        source = {"schema_version": 1, "signal_id": "seed", "symbol": "TESTUSDT",
                  "timeframe": "5", "bars": bars, "boundaries": []}
        for side, indices, column in (("upper",(3,7),"high"),("lower",(5,9),"low")):
            source["boundaries"].append({
                "boundary_id": side, "kind": "ray",
                "anchors": [{"bar_open_time_ms": bars[i]["open_time_ms"],
                             "price": bars[i][column]} for i in indices],
            })
        record = SimpleNamespace(candidate_id="seed", symbol=SimpleNamespace(value="TESTUSDT"),
            signal_snapshot={"symbol": "TESTUSDT", "timeframe": "5",
                             "pattern": "Falling Wedge", "geometry": geometry})
        with TemporaryDirectory() as directory:
            self.assertTrue(record_original_signal(
                "seed", symbol="TESTUSDT", timeframe="5", pattern="Falling Wedge",
                text="test", image_bytes=b"test", geometry_snapshot=source, directory=directory,
            ))
            seed = load_control_anchor_seed(record, directory=directory)
            self.assertIsNotNone(seed)
            self.assertEqual(seed["episode_start"], 3)
            self.assertEqual(seed["first_strict_index"], 3)
            self.assertEqual(seed["established_pivots"][-1]["index"], 11)
            self.assertEqual(seed["prefix_as_of_ms"], 5100000)
            self.assertEqual(len(seed["candles"]), 16)
            record.signal_snapshot["geometry"] = dict(geometry, current_index=16)
            self.assertIsNone(load_control_anchor_seed(record, directory=directory))
            record.signal_snapshot["geometry"] = dict(geometry, start_index=4)
            self.assertIsNone(load_control_anchor_seed(record, directory=directory))
            record.signal_snapshot["geometry"] = geometry
            record.candidate_id = "another"
            self.assertIsNone(load_control_anchor_seed(record, directory=directory))

    def test_inbox_observation_breakout_then_new_extreme_and_gap(self):
        from queue import Queue
        from terminal.market_data.impulse_observation import PublicTradeObservation
        from geometry.wedge_control_anchor import ControlAnchorObservation
        from geometry.trendline import fit_anchor_trendline

        highs = [100., 97., 94., 91., 92.]
        frame = pd.DataFrame({
            "open_time_ms": [60_000*i for i in range(1, 6)],
            "open": [75.]*5, "high": highs, "low": [70.]*5, "close": [75.]*5,
        })
        points = [{"index": i, "price": highs[i], "known_at_ms": 360000}
                  for i in (0,2,4)]
        line = fit_anchor_trendline(points[:2])
        seed = {"candidate_id": "host", "family": "falling", "episode_start": 0,
                "first_strict_index": 0, "prefix_as_of_ms": 360000,
                "timeframe_ms": 60000, "candles": frame,
                "established_pivots": points, "original_strict_line": line}
        source = PublicTradeObservation("TESTUSDT")
        inbox = Queue(maxsize=4)
        track = ControlAnchorObservation(seed, source, inbox, source.attach_print_inbox(inbox))

        def push(identity, time, price):
            self.assertTrue(source.observe({
                "topic": "publicTrade.TESTUSDT", "data": [{
                    "s": "TESTUSDT", "i": identity, "T": time,
                    "S": "Sell", "p": price, "v": "1", "seq": time,
                }],
            }, received_at_ms=time+1))
            return track.consume()

        self.assertEqual(push("before",360001,"69.99"), ())
        self.assertEqual(push("break",360002,"88"), ())
        self.assertEqual(push("equal",360003,"69.99"), ())
        result, = push("new",360004,"69.98")
        self.assertEqual(result["status"], "CONTROL_CONTACT")
        self.assertEqual(result["previous_extreme"], "69.99")
        self.assertEqual(result["source_trade_id"], "new")
        self.assertEqual(result["previous_strict_line"], line)
        self.assertEqual(result["validated_pairs"], [])  # no proven opposite ray
        self.assertEqual(len(frame), 5)
        self.assertEqual(push("new",360004,"69.98"), ())
        source.mark_gap()
        self.assertEqual(push("gap",360005,"69.97"), ())
        self.assertFalse(track.valid)



    def test_pair_gate_preserves_native_start_and_opposite_ray(self):
        import json
        from pathlib import Path
        from geometry.wedge_control_anchor import validate_revision_pairs
        from geometry.candidate import build_candidate_lines
        from geometry.wedge_boundaries import build_strict_wedge_support_lines
        from pivots import find_pivots

        fixture = Path(__file__).parent / "fixtures/geometry_formation_fit/historical_cases.json"
        case = json.loads(fixture.read_text(encoding="utf-8"))["cases"]["PONS"]
        frame = pd.DataFrame(case["candles"], columns=["time","open","high","low","close","volume"])
        # Treat the last row as partial; no confirmation uses its OHLC.
        closed = frame.iloc[:-1].copy()
        highs, lows = find_pivots(closed.copy())
        upper, lower = build_candidate_lines(highs), build_candidate_lines(lows)
        extra, _ = build_strict_wedge_support_lines(highs, lows, upper, lower, closed, len(closed)-1)
        line = next(c["line"] for c in upper+extra
                    if (c["anchor_index"], c["second_index"]) == (143,167))
        opposite = next(c["line"] for c in lower
                        if (c["anchor_index"], c["second_index"]) == (145,186))
        kwargs = dict(family="falling", episode_start=143,
                      original_opposite_line=opposite, proposed_lines=[line], candles=frame)
        # This historical control may already be beyond the live revision
        # boundary; never promote it just because native historical fit exists.
        self.assertEqual(validate_revision_pairs(**dict(kwargs, episode_start=144)), [])
        self.assertEqual(validate_revision_pairs(**dict(kwargs, original_opposite_line=None)), [])
        self.assertEqual(validate_revision_pairs(**dict(kwargs, family="rising")), [])
        self.assertEqual(validate_revision_pairs(**dict(kwargs, proposed_lines=[])), [])
        for geometry in validate_revision_pairs(**kwargs):
            self.assertEqual(geometry["start_index"], 143)
            self.assertEqual(geometry["lower_line"]["anchor_index"], 145)
            self.assertGreater(geometry["apex"]["index"], len(frame)-1)

    def test_positive_native_revision_at_new_tick_before_apex(self):
        """Frozen PONS prefix plus one synthetic trade, NOT historical replay."""
        import json
        from pathlib import Path
        from geometry.wedge_control_anchor import validate_revision_pairs
        from geometry.trendline import fit_anchor_trendline
        from geometry.triangle_boundaries import local_alternation_pivots
        from pivots import find_pivots

        fixture = Path(__file__).parent / "fixtures/geometry_formation_fit/historical_cases.json"
        case = json.loads(fixture.read_text(encoding="utf-8"))["cases"]["PONS"]
        closed = pd.DataFrame(case["candles"][:190],
                              columns=["time","open","high","low","close","volume"])
        self.assertEqual(float(closed.low.iloc[143:].min()), 0.5811)
        # Only source bars <=189 and a new synthetic trade are visible.
        price = 0.5810
        event_ms = int(closed.iloc[-1]["time"]) + 300000
        event = pd.DataFrame([dict(time=event_ms, open=price, high=price,
                                   low=price, close=price, volume=1)])
        frame = pd.concat([closed, event], ignore_index=True)
        highs, _ = find_pivots(closed.copy())
        local_highs, _ = local_alternation_pivots(closed, len(closed)-1)
        points = {p["index"]: {"index": p["index"], "price": float(p["price"]),
                                "known_at_ms": event_ms}
                  for p in highs+local_highs if p["index"] >= 143}
        proposal = propose_control_boundary(
            family="falling", episode_start=143, first_strict_index=143,
            previous_extreme="0.5811", trade_price="0.5810", event_index=190,
            event_time_ms=event_ms, established_pivots=list(points.values()), candles=frame,
        )
        self.assertEqual(proposal["control_anchor"]["index"], 178)
        self.assertEqual(proposal["status"], "OUTER_ENVELOPE")
        opposite = fit_anchor_trendline([
            {"index": i, "price": float(closed.low.iloc[i])} for i in (145,186)
        ])
        pairs = validate_revision_pairs(
            family="falling", episode_start=143, original_opposite_line=opposite,
            proposed_lines=proposal["lines"], candles=frame,
        )
        matches = [g for g in pairs if g["upper_line"]["second_index"] == 167]
        self.assertTrue(matches, "clean outer-envelope revision must pass native pair gates")
        g = matches[0]
        self.assertEqual(g["start_index"], 143)
        self.assertEqual(g["lower_line"]["anchor_index"], 145)
        self.assertEqual(g["lower_line"]["second_index"], 186)
        self.assertGreater(g["apex"]["index"], 190)
        self.assertTrue(g["validation"]["valid"])
        self.assertTrue(g["pair_metrics"]["true_converging"])

        # Persist the actual accepted pair, without changing the frozen source.
        from tempfile import TemporaryDirectory
        from geometry.wedge_revision_journal import append_revision, load_revisions

        original = fit_anchor_trendline([
            {"index": i, "price": float(closed.high.iloc[i])} for i in (143,178)
        ])
        seed = {"candidate_id": "pons-control", "source_geometry_sha256": "a"*64,
                "symbol": "PONSUSDT", "timeframe_ms": 300000, "family": "falling",
                "episode_start": 143, "original_strict_line": original,
                "original_opposite_line": opposite,
                "candles": closed.rename(columns={"time":"open_time_ms"})}
        proposal.update(validated_pairs=pairs, source_trade_id="synthetic-190",
                        candidate_id="pons-control", received_at_ms=event_ms+1,
                        previous_extreme="0.5811")
        old_control = dict(points[178])
        with TemporaryDirectory() as directory:
            db = Path(directory)/"paper.sqlite3"
            self.assertEqual(load_revisions(db, seed), [])
            args = dict(previous_control_anchor=old_control, previous_strict_line=original)
            record, created = append_revision(db, seed, proposal, g, **args)
            self.assertTrue(created)
            self.assertEqual(record["revision"], 1)
            self.assertEqual(record["event"], "Паттерн перестроен")
            self.assertEqual(record["strict_line"]["second_index"], 167)
            self.assertEqual(load_revisions(db, seed), [record])
            self.assertEqual(append_revision(db, seed, proposal, g, **args), (record, False))
            with self.assertRaises(ValueError):
                append_revision(db, seed, dict(proposal, received_at_ms=event_ms+2), g, **args)
            self.assertFalse(db.exists())  # PAPER DB never opened by this writer.
            self.assertEqual(seed["original_strict_line"]["second_index"], 178)
            self.assertEqual(load_revisions(db, seed), [record])
