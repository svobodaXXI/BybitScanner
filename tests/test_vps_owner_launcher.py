"""Offline tests only; no VPS, SSH, market connection or runtime mutation."""
import unittest
from types import SimpleNamespace
from unittest import mock

from tools import vps_owner_launcher as launcher


class VpsOwnerLauncherTests(unittest.TestCase):
    def test_ssh_command_is_batch_only_and_trusted_host_only(self):
        argv = launcher.ssh_argv("root@vps.example", "C:/keys/vps")
        self.assertEqual(argv[0], "ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("PasswordAuthentication=no", argv)
        self.assertIn("bybitscanner-paper-start.service", argv[-1])
        self.assertNotIn("PAPER_AUTO", argv[-1])

    def test_bad_target_fails_without_ssh(self):
        with mock.patch.object(launcher.subprocess, "run") as run:
            self.assertEqual(launcher.launch({}), 2)
            run.assert_not_called()
        for value in ("root@host;rm", "root@", "a b@host"):
            with self.assertRaises(ValueError):
                launcher.ssh_argv(value, "key")

    def test_unreachable_vps_never_runs_local_fallback(self):
        calls = []
        def fail(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=255, stdout="", stderr="secret URL")
        result = launcher.launch({"BYBITSCANNER_VPS_SSH_TARGET": "root@vps.example",
                                  "BYBITSCANNER_VPS_SSH_KEY": "key"}, run=fail)
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 1)

    def test_paper_core_does_not_imply_autopilot(self):
        env = {"BYBITSCANNER_VPS_SSH_TARGET": "root@vps.example", "BYBITSCANNER_VPS_SSH_KEY": "key"}
        def off(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout='PAPER_CORE {"autopilot": "OFF"}', stderr="")
        def on(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout='PAPER_CORE {"autopilot": "PAPER_AUTO"}', stderr="")
        self.assertEqual(launcher.launch(env, run=off), 3)
        self.assertEqual(launcher.launch(env, run=on), 0)

    def test_no_proof_of_core_is_failure(self):
        env = {"BYBITSCANNER_VPS_SSH_TARGET": "root@vps.example", "BYBITSCANNER_VPS_SSH_KEY": "key"}
        with mock.patch.object(launcher, "print") as print_mock:
            def wrong(*args, **kwargs):
                return SimpleNamespace(returncode=0, stdout="Finished successfully", stderr="")
            self.assertEqual(launcher.launch(env, run=wrong), 1)


if __name__ == "__main__":
    unittest.main()
