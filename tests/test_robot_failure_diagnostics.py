import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import robot_failure_diagnostics as diagnostics
from robot_failure_diagnostics import (
    MAX_INCIDENT_RECORDS,
    load_recent_robot_incidents,
    record_robot_incident,
)


class RobotFailureDiagnosticsTests(unittest.TestCase):
    def test_default_directory_is_created_when_missing(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            diagnostics, "__file__", str(Path(temp) / "robot_failure_diagnostics.py"),
        ), patch.dict(os.environ, {
            diagnostics.INCIDENT_DIR_ENV: "",
            diagnostics.PAPER_DB_ENV: "",
        }):
            directory = Path(temp) / "runtime" / "robot_incidents"
            self.assertFalse(directory.exists())
            self.assertTrue(record_robot_incident(
                incident_type="ROBOT_CANDIDATE_FAILURE",
                stage="candidate_persistence",
                reason_code="CANDIDATE_PERSISTENCE_EXCEPTION",
            ))
            self.assertEqual(len(tuple(directory.glob("*.json"))), 1)

    def test_persists_sanitized_candidate_failure_without_raw_exception_text(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "incidents"
            ok = record_robot_incident(
                incident_type="ROBOT_CANDIDATE_FAILURE",
                stage="candidate_persistence",
                reason_code="CANDIDATE_PERSISTENCE_EXCEPTION",
                symbol="B2USDT",
                timeframe="5",
                pattern="IKIGAI_BOX",
                error=RuntimeError("database locked at C:/private/paper.sqlite3"),
                incident_dir=directory,
                timestamp_ms=1234,
            )

            self.assertTrue(ok)
            records = load_recent_robot_incidents(
                incident_dir=directory, limit=10,
            )
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["timestamp_ms"], 1234)
            self.assertEqual(record["symbol"], "B2USDT")
            self.assertEqual(record["timeframe"], "5")
            self.assertEqual(record["pattern"], "IKIGAI_BOX")
            self.assertEqual(record["error_class"], "RuntimeError")
            self.assertEqual(
                record["reason_code"],
                "CANDIDATE_PERSISTENCE_EXCEPTION",
            )
            serialized = next(directory.glob("*.json")).read_text(encoding="utf-8")
            self.assertNotIn("C:/private", serialized)
            self.assertNotIn("database locked", serialized)

    def test_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "incidents"
            for index in range(MAX_INCIDENT_RECORDS + 7):
                self.assertTrue(record_robot_incident(
                    incident_type="TEST",
                    stage="test",
                    reason_code=f"R{index}",
                    incident_dir=directory,
                    timestamp_ms=index,
                ))
            self.assertEqual(
                len(tuple(directory.glob("*.json"))),
                MAX_INCIDENT_RECORDS,
            )

    def test_diagnostic_write_failure_never_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            not_a_directory = Path(temp) / "occupied"
            not_a_directory.write_text("x", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertFalse(record_robot_incident(
                    incident_type="TEST",
                    stage="test",
                    reason_code="WRITE_FAILURE",
                    incident_dir=not_a_directory,
                ))
            self.assertIn("stage=directory_create", output.getvalue())
            self.assertIn("error_class=FileExistsError", output.getvalue())
            self.assertNotIn(str(not_a_directory), output.getvalue())

    def test_writable_directory_with_failed_temp_write_reports_safe_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "incidents"
            with patch.object(
                Path, "write_text", side_effect=OSError("secret at C:/private/log"),
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertFalse(record_robot_incident(
                    incident_type="ROBOT_CANDIDATE_FAILURE",
                    stage="box_plan_preparation",
                    reason_code="BOX_PLAN_PREPARATION_EXCEPTION",
                    incident_dir=directory,
                ))
            self.assertTrue(directory.is_dir())
            self.assertIn("stage=temporary_write", output.getvalue())
            self.assertIn("error_class=OSError", output.getvalue())
            self.assertNotIn("private", output.getvalue())
            self.assertNotIn(str(directory), output.getvalue())


if __name__ == "__main__":
    unittest.main()
