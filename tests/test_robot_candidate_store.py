import tempfile
from pathlib import Path
import unittest

from robot_candidate_store import (
    STATUS_APPROVED,
    STATUS_AVAILABLE,
    approve_candidate,
    create_signal_snapshot,
    load_candidate,
)


class RobotCandidateStoreTests(unittest.TestCase):
    def test_snapshot_is_detached_and_approval_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store_dir = Path(temp_dir)
            source = {
                "symbol": "ONGUSDT",
                "pattern": "Falling Wedge",
                "potential_percent": 3.25,
                "geometry": {
                    "upper": [1.1, 1.0],
                    "lower": [0.9, 0.95],
                },
            }

            created = create_signal_snapshot(
                source,
                timeframe="1",
                store_dir=store_dir,
                candidate_id="candidate_001",
                created_at="2026-09-08T20:00:00+00:00",
            )

            self.assertEqual(created["status"], STATUS_AVAILABLE)
            self.assertEqual(
                created["signal_snapshot"]["potential_percent"],
                3.25,
            )

            source["potential_percent"] = 99
            source["geometry"]["upper"][0] = 999

            persisted = load_candidate(
                "candidate_001",
                store_dir=store_dir,
            )
            self.assertEqual(
                persisted["signal_snapshot"]["potential_percent"],
                3.25,
            )
            self.assertEqual(
                persisted["signal_snapshot"]["geometry"]["upper"][0],
                1.1,
            )

            approved, changed = approve_candidate(
                "candidate_001",
                approval={"user_id": 123},
                store_dir=store_dir,
                approved_at="2026-09-08T20:01:00+00:00",
            )
            self.assertTrue(changed)
            self.assertEqual(approved["status"], STATUS_APPROVED)
            self.assertEqual(approved["approval"], {"user_id": 123})

            repeated, changed = approve_candidate(
                "candidate_001",
                approval={"user_id": 999},
                store_dir=store_dir,
                approved_at="2026-09-08T20:02:00+00:00",
            )
            self.assertFalse(changed)
            self.assertEqual(repeated["approval"], {"user_id": 123})
            self.assertEqual(
                repeated["approved_at"],
                "2026-09-08T20:01:00+00:00",
            )
            self.assertEqual(
                repeated["signal_snapshot"],
                persisted["signal_snapshot"],
            )


if __name__ == "__main__":
    unittest.main()
