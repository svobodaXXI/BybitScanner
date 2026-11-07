"""Safety regression tests for standalone Windows VPS Manager commands."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.windows_vps_manager import ACTIONS, parse_args, ssh_command


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

    def test_git_actions_are_safe_directory_scoped(self) -> None:
        for action, remote in ACTIONS.items():
            if "git " in remote:
                with self.subTest(action=action):
                    self.assertNotIn("git -C", remote)
                    self.assertIn("git -c safe.directory=/opt/BybitScanner -C /opt/BybitScanner", remote)
                    self.assertNotIn("config --global", remote)

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
