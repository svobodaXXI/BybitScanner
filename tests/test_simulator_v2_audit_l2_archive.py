"""Small offline fixtures for ICNT Bybit L2 archive structural audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from research.simulator_v2.audit_l2_archive import (
    DAY_BEGIN_MS, DAY_END_MS, inspect,
)


def message(at, *, typ="snapshot", u=10, seq=20, bid="0.2898"):
    return {
        "topic": "orderbook.200.ICNTUSDT", "type": typ,
        "ts": at, "cts": at - 1,
        "data": {
            "s": "ICNTUSDT", "u": u, "seq": seq,
            "b": [[bid, "20"]], "a": [["0.2900", "10"]],
        },
    }


def archive(path: Path, events) -> str:
    payload = "".join(json.dumps(event) + "\n" for event in events).encode()
    with ZipFile(path, mode="w", compression=ZIP_DEFLATED) as z:
        z.writestr("2026-11-10_ICNTUSDT_ob200.data", payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OrderbookArchiveAuditTests(unittest.TestCase):
    def test_full_zip_metadata_no_completeness_claim(self):
        with TemporaryDirectory() as td:
            file = Path(td) / "l2.data.zip"
            checksum = archive(file, [
                message(DAY_BEGIN_MS + 1490),
                message(DAY_BEGIN_MS + 1600, typ="delta", u=11, seq=21),
                message(DAY_END_MS + 1489, u=1, seq=25),
            ])
            report = inspect(file, checksum, expected_records=3)
            self.assertEqual(report["records"], 3)
            self.assertEqual(report["snapshots"], 2)
            self.assertEqual(report["deltas"], 1)
            self.assertEqual(report["start_coverage_gap_ms"], 1490)
            self.assertEqual(report["structural_result"], "METADATA_CONSISTENT")
            self.assertTrue(report["capture_completeness"].startswith("UNPROVEN"))
            self.assertFalse(report["real_l2_simulation_executed"])

    def test_sequence_anomaly_is_not_silently_proven(self):
        with TemporaryDirectory() as td:
            file = Path(td) / "l2.data.zip"
            checksum = archive(file, [
                message(DAY_BEGIN_MS + 1490),
                message(DAY_BEGIN_MS + 1500, typ="delta", u=10, seq=19),
                message(DAY_END_MS + 1489, u=1, seq=25),
            ])
            report = inspect(file, checksum, expected_records=3)
            self.assertEqual(report["structural_result"], "PROVISIONAL")
            self.assertEqual(report["sequence_anomaly_counts"]["nonincreasing_delta_u"], 1)
            self.assertEqual(report["sequence_anomaly_counts"]["nonincreasing_delta_seq"], 1)

    def test_checksum_and_market_identity_fail_closed(self):
        with TemporaryDirectory() as td:
            file = Path(td) / "l2.data.zip"
            events = [
                message(DAY_BEGIN_MS + 1490),
                message(DAY_END_MS + 1489, u=1, seq=25),
            ]
            sha = archive(file, events)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                inspect(file, "0" * 64, expected_records=2)
            events[0]["topic"] = "orderbook.200.ETHUSDT"
            sha = archive(file, events)
            with self.assertRaisesRegex(ValueError, "foreign or malformed"):
                inspect(file, sha, expected_records=2)

    def test_duplicate_prices_and_truncated_day_fail_closed(self):
        with TemporaryDirectory() as td:
            file = Path(td) / "l2.data.zip"
            e = message(DAY_BEGIN_MS + 1490)
            e["data"]["b"] = [["0.2898", "20"], ["0.2898", "10"]]
            sha = archive(file, [e, message(DAY_END_MS + 1489, u=1, seq=25)])
            with self.assertRaisesRegex(ValueError, "duplicate L2 level"):
                inspect(file, sha, expected_records=2)
            sha = archive(file, [message(DAY_BEGIN_MS + 1490)])
            with self.assertRaisesRegex(ValueError, "terminates before"):
                inspect(file, sha, expected_records=1)


if __name__ == "__main__":
    unittest.main()
