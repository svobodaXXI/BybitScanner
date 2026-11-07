"""Offline regression for exact replay-helper routing in the protected verifier."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_dev_workflow import FakeGit
from tools.dev.verify import _run_check, verify


class ReplayRoutingTests(unittest.TestCase):
    def run_verifier(self, *, failing=False, helper="runtime_replay.py"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            tests.mkdir()
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / helper).write_text("VALUE = 1\n", encoding="utf-8")
            (tests / "test_runtime_replay.py").write_text(
                "import unittest\nclass ReplayTests(unittest.TestCase):\n"
                f"    def test_replay(self): self.assertTrue({not failing!r})\n",
                encoding="utf-8",
            )
            (tests / "test_other.py").write_text(
                "import unittest\nclass OtherTests(unittest.TestCase):\n"
                "    def test_other(self): pass\n", encoding="utf-8",
            )
            git = FakeGit(root)
            with patch("tools.dev.verify.Git", return_value=git), patch(
                "tools.dev.verify._run_check", wraps=_run_check,
            ) as check:
                passed, output = verify([f"tests/{helper}", "tests/test_other.py"], git=git)
            modules = [call.args[2][-1] for call in check.call_args_list
                       if call.args[2][:3] == (sys.executable, "-m", "unittest")]
            receipt = (root / ".git" / "bybitscanner" / "latest-pass.json").exists()
            return passed, output, modules, receipt

    def test_helper_runs_sibling_tests_and_preserves_other_routing(self):
        passed, output, modules, _ = self.run_verifier()
        self.assertTrue(passed, output)
        self.assertEqual(modules, ["tests.test_runtime_replay", "tests.test_other"])
        self.assertNotIn("NO TESTS RAN", output)
        # The actual repository target also contains discoverable replay tests.
        self.assertGreater(unittest.defaultTestLoader.loadTestsFromName(
            "tests.test_runtime_replay").countTestCases(), 0)

    def test_replay_failure_still_blocks_receipt(self):
        passed, output, modules, receipt = self.run_verifier(failing=True)
        self.assertFalse(passed)
        self.assertIn("focused-test:runtime_replay.py", output)
        self.assertIn("tests.test_runtime_replay", modules)
        self.assertFalse(receipt)

    def test_unmapped_helper_keeps_existing_fail_closed_behavior(self):
        passed, output, modules, receipt = self.run_verifier(helper="other_helper.py")
        self.assertFalse(passed, output)
        self.assertEqual(modules, ["tests.other_helper", "tests.test_other"])
        self.assertIn("NO TESTS RAN", output)
        self.assertFalse(receipt)
