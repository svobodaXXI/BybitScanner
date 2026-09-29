import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import robot_incident_store


class RobotIncidentStoreTests(unittest.TestCase):
    def test_record_is_sanitized_and_does_not_persist_raw_exception_text(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = "database is locked at C:/secret/paper.sqlite3 token=abc123"
            error = OSError(13, secret)
            record = robot_incident_store.record_robot_incident(
                lifecycle_stage="CANDIDATE_PERSISTENCE",
                reason_code="CANDIDATE_PERSISTENCE_EXCEPTION",
                symbol="BTCUSDT",
                timeframe="5",
                pattern="IKIGAI_BOX",
                candidate_id="candidate-1",
                error=error,
                facts={"SELECTED_RECOVERY_ACTION": "NONE"},
                incident_dir=directory,
                occurred_at_ms=1234,
            )

            files = list(Path(directory).glob("*.json"))
            self.assertEqual(len(files), 1)
            payload = files[0].read_text(encoding="utf-8")
            persisted = json.loads(payload)

        self.assertEqual(persisted, record)
        self.assertEqual(record["reason_code"], "CANDIDATE_PERSISTENCE_EXCEPTION")
        self.assertEqual(record["error_class"], "PermissionError")
        self.assertEqual(record["errno"], 13)
        self.assertNotIn("secret", payload)
        self.assertNotIn("abc123", payload)
        self.assertNotIn("paper.sqlite3", payload)

    def test_retention_keeps_only_newest_bounded_incidents(self):
        with tempfile.TemporaryDirectory() as directory:
            for timestamp in range(1000, 1005):
                robot_incident_store.record_robot_incident(
                    lifecycle_stage="PROTECTION",
                    reason_code="INITIAL_PROTECTION_FAILED",
                    symbol="BTCUSDT",
                    incident_dir=directory,
                    retention=3,
                    occurred_at_ms=timestamp,
                )

            files = sorted(Path(directory).glob("*.json"))
            payloads = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in files
            ]

        self.assertEqual(len(payloads), 3)
        self.assertEqual(
            [item["occurred_at_ms"] for item in payloads],
            [1002, 1003, 1004],
        )

    def test_path_shaped_arbitrary_fact_is_rejected_by_strict_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(robot_incident_store.RobotIncidentError):
                robot_incident_store.record_robot_incident(
                    lifecycle_stage="PROTECTION",
                    reason_code="INITIAL_PROTECTION_FAILED",
                    facts={"DETAIL": "C:/secret/paper.sqlite3"},
                    incident_dir=directory,
                    occurred_at_ms=1000,
                )

    def test_runtime_wrapper_never_raises_when_diagnostic_write_fails(self):
        with patch.object(
            robot_incident_store,
            "record_robot_incident",
            side_effect=OSError("disk unavailable"),
        ):
            self.assertFalse(
                robot_incident_store.try_record_robot_incident(
                    lifecycle_stage="PROTECTION",
                    reason_code="INITIAL_PROTECTION_FAILED",
                )
            )


if __name__ == "__main__":
    unittest.main()
