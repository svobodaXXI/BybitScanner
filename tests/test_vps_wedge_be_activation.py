"""Bounded offline checks for the immutable Wedge BE owner configuration change."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from tools.vps_wedge_be_activation import (
    FLAG, WedgeBEBlocked, _no_be_key, _read_env, _unchanged, _write_once,
    enable_wedge_be,
)


@unittest.skipUnless(os.name == "posix", "Linux root-owned config semantics")
class WedgeBEConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.env"
        self.path.write_bytes(b"BYBITSCANNER_PAPER_MODE=paper\n")
        self.uid = os.geteuid()
        self.original, self.info = _read_env(self.path, required=True, uid=self.uid)

    def test_create_once_preserves_original_backup(self):
        _write_once(self.path, self.original, self.info, uid=self.uid)
        self.assertEqual(
            self.path.read_bytes(),
            self.original + FLAG + b"=1\n",
        )
        backups = list(self.path.parent.glob("paper.env.before-wedge-be-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertFalse(_no_be_key(self.path.read_bytes()))

    def test_conflicting_flag_refuses_without_write(self):
        self.path.write_bytes(self.original + FLAG + b"=0\n")
        with self.assertRaises(WedgeBEBlocked):
            _write_once(self.path, self.original, self.info, uid=self.uid)
        self.assertEqual(list(self.path.parent.glob("paper.env.before-wedge-be-*")), [])
        self.assertIn(FLAG + b"=0", self.path.read_bytes())

    def test_inode_change_refuses(self):
        swapped = self.path.parent / "swapped.env"
        swapped.write_bytes(self.original)
        os.replace(swapped, self.path)
        self.assertFalse(_unchanged(self.path, self.original, self.info, self.uid))
        with self.assertRaises(WedgeBEBlocked):
            _write_once(self.path, self.original, self.info, uid=self.uid)

    def test_symlink_refused(self):
        self.path.unlink()
        self.path.symlink_to(self.path.parent / "missing.env")
        with self.assertRaises(WedgeBEBlocked):
            _read_env(self.path, required=True, uid=self.uid)

    def test_duplicate_or_commented_key_refused(self):
        self.assertFalse(_no_be_key(b"# " + FLAG + b"=1\n"))
        self.assertFalse(_no_be_key(FLAG + b"=0\n"))
        self.assertTrue(_no_be_key(b"BYBITSCANNER_PAPER_MODE=paper\n"))

    def test_conflicting_effective_configuration_never_attempts_stop(self):
        self.path.write_bytes(self.original + FLAG + b"=0\\n")
        with ExitStack() as stack:
            stack.enter_context(patch("tools.vps_release_identity.verify_release",
                                      return_value="a" * 40))
            stop = stack.enter_context(patch(
                "tools.paper_maintenance._stop_exact_installed_paper_once"))
            status = enable_wedge_be(
                "a" * 40, root=self.path.parent, env_file=self.path,
                owner_env=self.path.parent / "owner.env",
                simulator_env=self.path.parent / "simulator.env", uid=self.uid)
        self.assertIn("BLOCKED:", status)
        stop.assert_not_called()
        self.assertIn(FLAG + b"=0", self.path.read_bytes())

    def test_success_requires_actual_backend_env_attestation(self):
        target = "a" * 40
        with ExitStack() as stack:
            stack.enter_context(patch("tools.vps_release_identity.verify_release",
                                      return_value=target))
            stack.enter_context(patch(
                "tools.paper_maintenance._durable_editor_freeze", return_value="b" * 64))
            stack.enter_context(patch(
                "tools.paper_maintenance._editor_runtime_ready", return_value=True))
            stack.enter_context(patch(
                "tools.paper_maintenance._paper_start_quiescent", return_value=True))
            stack.enter_context(patch(
                "tools.vps_simulator_device_provision._robot_stopped", return_value=True))
            stop = stack.enter_context(patch(
                "tools.paper_maintenance._stop_exact_installed_paper_once",
                return_value="READY: canonical STOP"))
            stack.enter_context(patch("tools.vps_release_resume.check_resume",
                                      return_value="RESUME_READY: stopped"))
            resume = stack.enter_context(patch(
                "tools.paper_maintenance.resume_installed_release",
                return_value="READY: editor resumed"))
            stack.enter_context(patch(
                "tools.vps_simulator_device_provision._runtime_env",
                side_effect=[{}, {FLAG.decode("ascii"): "1"}]))
            status = enable_wedge_be(
                target, root=self.path.parent, env_file=self.path,
                owner_env=self.path.parent / "owner.env",
                simulator_env=self.path.parent / "simulator.env", uid=self.uid)
        self.assertTrue(status.startswith("READY:"), status)
        stop.assert_called_once()
        resume.assert_called_once()
        self.assertEqual(self.path.read_bytes(), self.original + FLAG + b"=1\\n")

    def test_missing_backend_attestation_blocks_even_after_resuming(self):
        target = "a" * 40
        with ExitStack() as stack:
            stack.enter_context(patch("tools.vps_release_identity.verify_release",
                                      return_value=target))
            stack.enter_context(patch(
                "tools.paper_maintenance._durable_editor_freeze", return_value="b" * 64))
            stack.enter_context(patch(
                "tools.paper_maintenance._editor_runtime_ready", return_value=True))
            stack.enter_context(patch(
                "tools.paper_maintenance._paper_start_quiescent", return_value=True))
            stack.enter_context(patch(
                "tools.vps_simulator_device_provision._robot_stopped", return_value=True))
            stack.enter_context(patch(
                "tools.paper_maintenance._stop_exact_installed_paper_once",
                return_value="READY: canonical STOP"))
            stack.enter_context(patch("tools.vps_release_resume.check_resume",
                                      return_value="RESUME_READY: stopped"))
            stack.enter_context(patch(
                "tools.paper_maintenance.resume_installed_release",
                return_value="READY: editor resumed"))
            stack.enter_context(patch(
                "tools.vps_simulator_device_provision._runtime_env",
                side_effect=[{}, {}]))
            status = enable_wedge_be(
                target, root=self.path.parent, env_file=self.path,
                owner_env=self.path.parent / "owner.env",
                simulator_env=self.path.parent / "simulator.env", uid=self.uid)
        self.assertIn("wedge_be_effective_runtime_unproven", status)


if __name__ == "__main__":
    unittest.main()
