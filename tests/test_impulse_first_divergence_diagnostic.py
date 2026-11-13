"""A diagnostic signal must share the native runner's exclusive end boundary."""
from __future__ import annotations

from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
import hashlib
import unittest
from unittest.mock import patch

from research.simulator_v2.diagnose_first_divergence import (
    eligible_trace_signal, verify_pinned_code_blobs,
)


class FirstDivergenceDiagnosticBoundaryTests(unittest.TestCase):
    def test_source_blob_preflight_accepts_pinned_content_and_rejects_drift(self):
        # Test exact Git blob hashing without a repository checkout or full replay.
        data = b"def example():\n    return True\n"
        expected = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "robot_entry_flow_evidence.py"
            path.write_bytes(data.replace(b"\n", b"\r\n"))
            with patch(
                "research.simulator_v2.diagnose_first_divergence.CODE_BLOBS",
                {"robot_entry_flow_evidence.py": expected},
            ):
                verify_pinned_code_blobs(
                    root, {"code_blob_proof": {"robot_entry_flow_evidence.py": expected}}
                )
                path.write_bytes(b"def changed():\n    return False\n")
                with self.assertRaisesRegex(SystemExit, "source Git blob mismatch"):
                    verify_pinned_code_blobs(
                        root, {"code_blob_proof": {"robot_entry_flow_evidence.py": expected}}
                    )
                with self.assertRaisesRegex(SystemExit, "saved code blob provenance mismatch"):
                    verify_pinned_code_blobs(root, {"code_blob_proof": {}})

    def test_only_preterminal_signals_are_traced(self):
        end_exclusive_ms = 1794355200000  # 2026-11-11 00:00 UTC
        self.assertFalse(eligible_trace_signal(None, end_exclusive_ms=end_exclusive_ms))
        self.assertTrue(eligible_trace_signal(
            SimpleNamespace(known_at_ms=end_exclusive_ms - 60_000),
            end_exclusive_ms=end_exclusive_ms,
        ))
        self.assertFalse(eligible_trace_signal(
            SimpleNamespace(known_at_ms=end_exclusive_ms),
            end_exclusive_ms=end_exclusive_ms,
        ))
        self.assertFalse(eligible_trace_signal(
            SimpleNamespace(known_at_ms=end_exclusive_ms + 60_000),
            end_exclusive_ms=end_exclusive_ms,
        ))


if __name__ == "__main__":
    unittest.main()
