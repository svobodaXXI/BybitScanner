"""Read-only MIRROR ambiguity diagnostics never choose a trade."""
import unittest

from research.simulator_v2.mirror_real_archive_probe import (
    audit_simultaneous_mirror_evidence,
)


class MirrorAmbiguityAuditTests(unittest.TestCase):
    def source(self, *, second_breakout: int = 300_000):
        levels = []
        entries = []
        for i, breakout in enumerate((300_000, second_breakout)):
            level_id = f"lvl-test-{i}"
            levels.append({
                "level_id": level_id, "confirmed_at_ms": 0,
                "boundary": {"anchor_price": 0.3 + i * 0.02,
                             "slope_per_ms": 0.0},
            })
            entries.append({
                "entry_id": f"{level_id}@1@600000",
                "terms": {
                    "level_id": level_id,
                    "level_source": "swing_zone", "level_pattern": None,
                    "level_side": "lower",
                    "level_breakout_close_ms": breakout,
                    "level_breakout_direction": "DOWN",
                    "direction": "LONG",
                    "reference": "0.3", "stop": "0.29", "target": "0.34",
                    "confirmation": {"kind": "ENGULFING",
                                     "close_time_ms": 600_000},
                },
            })
        state = {"registry": {"levels": levels},
                 "standalone_entries": entries}
        conflict = ((600_000, tuple(x["entry_id"] for x in entries)),)
        return state, conflict

    def test_same_breakout_group_is_descriptive_not_an_order_priority(self):
        state, conflict = self.source()
        result = audit_simultaneous_mirror_evidence(state, conflict)
        self.assertEqual(result["same_breakout_minutes"], 1)
        self.assertEqual(result["distinct_breakout_minutes"], 0)
        self.assertEqual(result["ambiguous_minutes"], 1)
        self.assertTrue(result["no_priority_rule_inferred"])
        self.assertEqual(result["unproven_entries"], [])
        self.assertEqual(len(result["source_level_proofs"]), 2)

    def test_different_breakout_is_not_merged_by_confirmation_time(self):
        state, conflict = self.source(second_breakout=360_000)
        result = audit_simultaneous_mirror_evidence(state, conflict)
        self.assertEqual(result["same_breakout_minutes"], 0)
        self.assertEqual(result["distinct_breakout_minutes"], 1)
        self.assertEqual(result["mixed_side_minutes"], 0)

    def test_missing_or_future_proof_stays_unproven(self):
        state, conflict = self.source()
        state["standalone_entries"][1]["terms"]["confirmation"]["close_time_ms"] = 660_000
        result = audit_simultaneous_mirror_evidence(state, conflict)
        self.assertEqual(len(result["unproven_entries"]), 1)
        self.assertIsNone(result["group_evidence"][0]["same_breakout"])
        self.assertEqual(result["same_breakout_minutes"], 0)
        self.assertEqual(result["distinct_breakout_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
