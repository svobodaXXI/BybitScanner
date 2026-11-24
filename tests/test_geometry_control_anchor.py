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


if __name__ == "__main__":
    unittest.main()
