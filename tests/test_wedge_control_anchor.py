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
