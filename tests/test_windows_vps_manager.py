"""Safety regression tests for standalone Windows VPS Manager commands."""
from __future__ import annotations

import queue
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.windows_vps_manager import ACTIONS, VPSManager, parse_args, ssh_command


class TestWindowsVpsManager(unittest.TestCase):
    def test_all_actions_use_strict_ssh_and_no_interactive_passwords(self) -> None:
        for action in ACTIONS:
            with self.subTest(action=action):
                command = ssh_command("vps.example.org", "bybitscanner", action)
                self.assertEqual(command[0], "ssh")
                self.assertIn("StrictHostKeyChecking=yes", command)
                self.assertIn("BatchMode=yes", command)
                self.assertEqual(command[-2], "bybitscanner@vps.example.org")
                self.assertEqual(command[-1], ACTIONS[action])

    def test_no_write_actions_or_arbitrary_shell(self) -> None:
        for action, remote in ACTIONS.items():
            with self.subTest(action=action):
                self.assertNotIn("systemctl stop", remote)
                self.assertNotIn("systemctl start", remote)
                self.assertNotIn("git pull", remote)
                self.assertNotIn("git reset", remote)
                self.assertNotIn("rm -", remote)
        with self.assertRaises(ValueError):
            ssh_command("vps.example.org", "bybitscanner", "rm -rf /")

    def test_status_action_fails_on_first_unavailable_service(self) -> None:
        # Even if the last service exists, a failure from an earlier
        # systemctl call must propagate to SSH and the GUI status indicator.
        command = ssh_command("vps.example.org", "bybitscanner", "Состояние")
        remote = command[-1]
        self.assertTrue(remote.startswith("set -e; "), remote)
        self.assertEqual(remote, ACTIONS["Состояние"])
        self.assertEqual(remote.count("systemctl show "), 3)
        self.assertNotIn("systemctl start", remote)
        self.assertNotIn("systemctl stop", remote)

    def test_paper_diagnostics_and_update_preflight_fail_on_early_errors(self) -> None:
        # A failed Git inspection or systemctl query must not be masked by
        # a later successful health response in the same SSH command.
        for action in ("Диагностика PAPER", "Предпроверка обновления"):
            with self.subTest(action=action):
                remote = ssh_command("vps.example.org", "bybitscanner", action)[-1]
                self.assertTrue(remote.startswith("set -e; "), remote)
                self.assertEqual(remote, ACTIONS[action])
                self.assertNotIn("systemctl start", remote)
                self.assertNotIn("systemctl stop", remote)

    def test_failed_ssh_and_timeout_are_not_reported_as_success(self) -> None:
        for result, expected in (
            (subprocess.CompletedProcess(["ssh"], 0, stdout="healthy", stderr=""), "success"),
            (subprocess.CompletedProcess(["ssh"], 255, stdout="", stderr="denied"), "failure"),
        ):
            with self.subTest(exit_code=result.returncode):
                state = SimpleNamespace(events=queue.Queue())
                with patch("tools.windows_vps_manager.subprocess.run", return_value=result):
                    VPSManager.worker(state, ["ssh", "example"])
                kind, output = state.events.get_nowait()
                self.assertEqual(kind, expected)
                self.assertIn(f"Exit code: {result.returncode}", output)

        state = SimpleNamespace(events=queue.Queue())
        with patch("tools.windows_vps_manager.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("ssh", 45)):
            VPSManager.worker(state, ["ssh", "example"])
        kind, output = state.events.get_nowait()
        self.assertEqual(kind, "failure")
        self.assertIn("TimeoutExpired", output)

    def test_status_bar_distinguishes_failures_from_success(self) -> None:
        for kind, expected in (("failure", "Ошибка"), ("success", "Успешно")):
            with self.subTest(kind=kind):
                status = Mock()
                button = Mock()
                fake = SimpleNamespace(
                    events=queue.Queue(), write=Mock(), status=status,
                    buttons=[button], after=Mock(), drain=Mock(), busy=True,
                )
                fake.events.put((kind, "diagnostic output"))
                VPSManager.drain(fake)
                self.assertFalse(fake.busy)
                self.assertTrue(status.set.call_args.args[0].startswith(expected))
                button.state.assert_called_with(["!disabled"])
                fake.write.assert_called_once_with("diagnostic output")

    def test_git_actions_are_safe_directory_scoped(self) -> None:
        for action, remote in ACTIONS.items():
            if "git " in remote:
                with self.subTest(action=action):
                    self.assertNotIn("git -C", remote)
                    self.assertIn("git -c safe.directory=/opt/BybitScanner -C /opt/BybitScanner", remote)
                    self.assertNotIn("config --global", remote)

    def test_gitless_installed_release_is_observable_without_false_clean_claim(self) -> None:
        for name in ("Git / локальные изменения", "Предпроверка обновления"):
            with self.subTest(name=name):
                remote = ACTIONS[name]
                self.assertTrue(remote.startswith("set -e; "))
                self.assertIn("test -e /opt/BybitScanner/.git", remote)
                self.assertIn("GIT_WORKTREE=ABSENT", remote)
                self.assertIn("GIT_STATUS=UNKNOWN", remote)
                self.assertIn("/api/health", remote)
                self.assertNotIn("git pull", remote)
                self.assertNotIn("git reset", remote)
        self.assertIn("DEPLOY_PREFLIGHT=NOT_PROVEN", ACTIONS["Предпроверка обновления"])

    def test_explicit_key_is_offered_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "bybitscanner_laptop"
            key.write_text("", encoding="utf-8")
            command = ssh_command("vps.example.org", "bybitscanner", "Состояние", str(key))
            self.assertEqual(command[command.index("-i") + 1], str(key))
            self.assertIn("IdentitiesOnly=yes", command)
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertEqual(command[-2], "bybitscanner@vps.example.org")
            self.assertEqual(command[-1], ACTIONS["Состояние"])

    def test_without_key_command_is_unchanged(self) -> None:
        self.assertEqual(
            ssh_command("vps.example.org", "bybitscanner", "Состояние"),
            ssh_command("vps.example.org", "bybitscanner", "Состояние", "   "),
        )
        self.assertNotIn("-i", ssh_command("vps.example.org", "bybitscanner", "Состояние"))

    def test_missing_key_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                ssh_command(
                    "vps.example.org", "bybitscanner", "Состояние",
                    str(Path(folder) / "absent_key"),
                )

    def test_shortcut_arguments_prefill_fields(self) -> None:
        args = parse_args(["--host", "vps.example.org", "--user", "vpsmanager", "--key", "C:/k"])
        self.assertEqual((args.host, args.user, args.key), ("vps.example.org", "vpsmanager", "C:/k"))
        defaults = parse_args([])
        self.assertEqual((defaults.host, defaults.user, defaults.key), ("", "bybitscanner", None))
        # Unknown switches must not crash a windowed executable.
        self.assertEqual(parse_args(["--bogus", "x"]).host, "")

    def test_invalid_remote_targets_rejected(self) -> None:
        for hostname, user in [
            ("-oProxyCommand=evil", "bybitscanner"),
            ("hostname;id", "bybitscanner"),
            ("host with spaces", "bybitscanner"),
            ("host", "root;id"),
            ("", "bybitscanner"),
            ("host", "-root"),
        ]:
            with self.subTest(hostname=hostname, user=user):
                with self.assertRaises(ValueError):
                    ssh_command(hostname, user, "Состояние")


if __name__ == "__main__":
    unittest.main()
