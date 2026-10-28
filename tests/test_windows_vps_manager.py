"""Safety regression tests for standalone Windows VPS Manager commands."""
from __future__ import annotations

import unittest

from tools.windows_vps_manager import ACTIONS, ssh_command


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
