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

