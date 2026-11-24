"""Pure tick-sequence controls; no live stream or complete revision claim."""
import unittest
from dataclasses import asdict
import json

from geometry.control_anchor import (
    ConfirmedAnchor, ControlAnchorState, initialize_control_anchor, observe_trade,
)


class DynamicControlAnchorTest(unittest.TestCase):
    def tick(self, state, i, price, anchors=(), *, broken=False, valid=True,
             sequence=None, trade_id=None, timestamp=None):
        return observe_trade(
            state, trade_id=trade_id or f"t{i}",
            timestamp_ms=timestamp if timestamp is not None else i*1000,
            sequence=sequence if sequence is not None else i,
            price=price, breakout_observed=broken,
            confirmed_anchors=anchors, source_valid=valid,
        )

    def test_falling_waits_for_new_low_even_after_breakout(self):
        s = initialize_control_anchor("episode", "falling", "100.00")
        a = ConfirmedAnchor(8, "112", 8000, 9000)
        s, request = self.tick(s, 10, "115", [a], broken=True)
        self.assertIsNone(request)
        self.assertTrue(s.breakout_seen)
        s, request = self.tick(s, 11, "100.00", [a])
        self.assertIsNone(request)
        s, request = self.tick(s, 12, "99.99", [a])
        self.assertEqual(request.new_extreme, "99.99")
        self.assertEqual(request.old_extreme, "100.00")
        self.assertEqual(request.control_anchor, a)
        self.assertEqual(request.timestamp_ms, 12000)
        self.assertEqual(request.episode_id, "episode")
        self.assertEqual(s.extreme, "99.99")

    def test_rising_mirror_uses_latest_known_low(self):
        s = initialize_control_anchor("episode", "rising", "100.00")
        old = ConfirmedAnchor(2, "90", 2000, 3000)
        latest = ConfirmedAnchor(4, "93", 4000, 5000)
        future = ConfirmedAnchor(5, "94", 5000, 11000)
        s, request = self.tick(s, 9, "89", [old], broken=True)
        self.assertIsNone(request)
        s, request = self.tick(s, 10, "100.01", [future, old, latest])
        self.assertEqual(request.control_anchor, latest)
        self.assertEqual(request.new_extreme, "100.01")

    def test_prebreak_extreme_and_later_equal_price(self):
        s = initialize_control_anchor("episode", "falling", "100")
        s, r = self.tick(s, 1, "99")
        self.assertIsNone(r)
        s, r = self.tick(s, 2, "110", broken=True)
        self.assertIsNone(r)
        s, r = self.tick(s, 3, "99")
        self.assertIsNone(r)
        s, r = self.tick(s, 4, "98.99")
        self.assertIsNone(r.control_anchor)
        self.assertEqual(r.old_extreme, "99")
        self.assertEqual(s.extreme, "98.99")

    def test_same_sequence_distinct_trades_and_restart_duplicate(self):
        s = initialize_control_anchor("episode", "falling", "100")
        s, _ = self.tick(s, 1, "110", broken=True)
        s, r = self.tick(s, 2, "99.99", sequence=2)
        self.assertIsNotNone(r)
        payload = json.loads(json.dumps(asdict(s)))
        payload["trade_ids"] = tuple(payload["trade_ids"])
        restored = ControlAnchorState(**payload)
        again, r = self.tick(restored, 2, "99.99", sequence=2)
        self.assertEqual(again, restored)
        self.assertIsNone(r)
        s, r = self.tick(restored, 3, "99.98", sequence=2, timestamp=2000)
        self.assertIsNotNone(r)
        self.assertEqual(r.new_extreme, "99.98")
        again, r = self.tick(s, 2, "99.99", sequence=2)
        self.assertEqual(again, s)
        self.assertIsNone(r)
        again, r = self.tick(s, 1, "98", sequence=1)
        self.assertEqual(again, s)
        self.assertIsNone(r)

    def test_gap_and_missing_pivot_do_not_create_geometry(self):
        s = initialize_control_anchor("episode", "falling", "100")
        unchanged, r = self.tick(s, 1, "99", broken=True, valid=False)
        self.assertEqual(unchanged, s)
        self.assertIsNone(r)
        s, _ = self.tick(s, 2, "110", broken=True)
        future = ConfirmedAnchor(1, "110", 1000, 3000)
        s, r = self.tick(s, 3, "99", [future])
        self.assertIsNotNone(r)
        self.assertIsNone(r.control_anchor)
        # Missing evidence is a failed-build diagnostic, not a new line.
        self.assertFalse(hasattr(r, "geometry"))
        s, r = self.tick(s, 4, "99")
        self.assertIsNone(r)


class ControlBoundaryConstructionTest(unittest.TestCase):
    def fixture(self, highs, *, mirror=False, current=70, opposite=None, post_slope=.5):
        import pandas as pd
        from geometry.control_anchor import RebuildRequest
        anchors = tuple(ConfirmedAnchor(i, str(p), i*1000, i*1000+1)
                        for i,p in highs)
        # Piecewise-linear high path between real contact points.
        # Triggering candle is open and already contains the new low.
        prices = []
        for i in range(current+1):
            before = max((a for a in anchors if a.index <= i), key=lambda a:a.index)
            after = next((a for a in anchors if a.index > i), None)
            if after:
                high = float(before.price)+(float(after.price)-float(before.price))*(i-before.index)/(after.index-before.index)
            else:
                high = float(before.price)-post_slope*(i-before.index)
            prices.append(high)
        opposite = opposite or {"slope":-.1, "intercept":102.5}
        frame = pd.DataFrame({"high": prices, "low": [min(h-.1, 90.) for h in prices]})
        family = "falling"
        if mirror:
            frame = pd.DataFrame({"high": 250.-frame.low, "low": 250.-frame.high})
            anchors = tuple(ConfirmedAnchor(a.index, str(250.-float(a.price)), a.pivot_at_ms, a.known_at_ms)
                            for a in anchors)
            opposite = {"slope":-opposite["slope"], "intercept":250.-opposite["intercept"]}
            family = "rising"
        request = RebuildRequest("episode", family, "159" if mirror else "91",
                                 "160" if mirror else "90", "trade", current*1000, current, anchors[-1])
        return request, anchors, frame, opposite

    def select(self, request, anchors, frame, opposite):
        from geometry.control_boundary import select_strict_boundary
        return select_strict_boundary(request, anchors, frame, episode_start=0,
                                      current_index=len(frame)-1, opposite_line=opposite)

    def test_clean_contact_mandatory_and_mirrored(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                q, a, f, o = self.fixture([(0,130),(30,115),(60,100)], mirror=mirror,
                                           opposite={"slope":-.1,"intercept":100.})
                result = self.select(q,a,f,o)
                self.assertEqual(result.status, "CONTROL_CONTACT")
                self.assertTrue(result.candidates)
                self.assertTrue(all(c["second_index"] == 60 for c in result.candidates))

    def test_preceding_highs_force_outer_line_and_mirror(self):
        for mirror in (False, True):
            with self.subTest(mirror=mirror):
                q,a,f,o = self.fixture([(0,120),(15,117),(30,114),(60,100)], mirror=mirror, post_slope=.4)
                result = self.select(q,a,f,o)
                self.assertEqual(result.status, "EARLIER_ENVELOPE")
                self.assertTrue(result.candidates)
                self.assertTrue(all(c["second_index"] < 60 for c in result.candidates))

    def test_no_fallback_for_clean_unsupported_contact(self):
        q,a,f,o = self.fixture([(0,130),(60,100)], opposite={"slope":-.1,"intercept":100.})
        result = self.select(q,a,f,o)
        self.assertEqual(result.status, "CONTACT_UNSUPPORTED")
        self.assertEqual(result.candidates, ())

    def test_no_fabricated_line_when_current_extreme_missing(self):
        q,a,f,o = self.fixture([(0,130),(30,115),(60,100)],
                               opposite={"slope":-.1,"intercept":100.})
        f.loc[70,"low"] = 91.
        self.assertEqual(self.select(q,a,f,o).status, "EVIDENCE_UNAVAILABLE")


class ExistingTradeSourceAdapterTest(unittest.TestCase):
    def fixture(self):
        import pandas as pd
        from decimal import Decimal
        from terminal.market_data.impulse_observation import ObservedPrint
        interval = 300000
        times = [i*interval for i in range(16)]
        highs = [110,111,112,120,113,112,111,110,116,111,110,109,108,107,106,105]
        lows = [v-2 for v in highs]
        lows[-1] = 99.
        frame = pd.DataFrame({"time":times,"high":highs,"low":lows,
                              "open":[v-1 for v in highs],"close":[v-1 for v in highs]})
        frame.loc[15,"close"] = 99.
        at = times[-1]+1000
        trade = ObservedPrint("exact-print", at, 8, "Sell", Decimal("99"), Decimal("1"), at+1)
        state = initialize_control_anchor("episode", "falling", "100")
        state,_ = observe_trade(state, trade_id="breakout", timestamp_ms=times[-1]+100,
                                sequence=7, price="121", breakout_observed=True,
                                confirmed_anchors=[], source_valid=True)
        known = [i+interval for i in times[:-1]]
        return state,trade,frame,known

    def test_existing_print_and_closed_pivot_confirmation(self):
        from terminal.market_data.wedge_control_source import observe_wedge_print
        state,trade,frame,known = self.fixture()
        result = observe_wedge_print(state,trade,frame,timeframe="5",episode_start=0,
                                     opposite_line={"slope":-.1,"intercept":100.},
                                     closed_known_at_ms=known,prefix_as_of_trade_id=trade.trade_id,
                                     breakout_observed=False,source_valid=True)
        self.assertIsNotNone(result.request)
        self.assertEqual(result.request.control_anchor.index, 8)
        self.assertEqual(result.request.control_anchor.known_at_ms, 12*300000)
        self.assertEqual(result.request.timestamp_ms, trade.timestamp_ms)
        self.assertEqual(result.state.extreme, "99")
        # A request is not successful revision/trading authority.
        self.assertIsNotNone(result.boundary)

    def test_reject_later_frame_gap_and_unproved_visibility(self):
        from terminal.market_data.wedge_control_source import observe_wedge_print
        state,trade,frame,known = self.fixture()
        args = dict(timeframe="5",episode_start=0,
                    opposite_line={"slope":-.1,"intercept":100.},
                    closed_known_at_ms=known,prefix_as_of_trade_id=trade.trade_id,
                    breakout_observed=False,source_valid=True)
        for overrides in ({"prefix_as_of_trade_id":"later"},
                          {"source_valid":False},
                          {"closed_known_at_ms":known[:-1]+[trade.received_at_ms+1]}):
            result = observe_wedge_print(state,trade,frame,**{**args,**overrides})
            self.assertEqual(result.status,"EVIDENCE_UNAVAILABLE")
            self.assertEqual(result.state,state)
            self.assertIsNone(result.request)
        gapped = frame.drop(index=4).reset_index(drop=True)
        result = observe_wedge_print(state,trade,gapped,**{**args,"closed_known_at_ms":known[:-1]})
        self.assertEqual(result.status,"EVIDENCE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
