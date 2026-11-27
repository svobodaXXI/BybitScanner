"""Canonical owner action routes Telegram recovery through the same UUID monolith."""
from contextlib import nullcontext
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import patch
import subprocess
import unittest

from tools import paper_maintenance, telegram_only_recover, vps_owner_control


SHA = "a" * 40
REQUEST = "b" * 32


class TelegramOwnerActionTests(unittest.TestCase):
    def test_submit_uses_owner_monolith_and_uuid(self):
        seen = []

        def runner(command, **_kw):
            seen.append(command)
            stdout = "LoadState=not-found\n" if command[0] == "systemctl" else ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with (redirect_stdout(StringIO()),
              patch.object(vps_owner_control, "_owner_request_path"),
              patch.object(vps_owner_control, "_read_request_intent", return_value=None),
              patch.object(vps_owner_control, "_reserve_request_intent")):
            result = vps_owner_control.submit(
                "telegram-recover", SHA, REQUEST, "win-laptop", run=runner, uid=0
            )
        self.assertEqual(result, 0)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1][0], "systemd-run")
        self.assertIn("--unit=" + vps_owner_control.unit_name(REQUEST), seen[1])
        self.assertEqual(
            seen[1][-5:],
            ["-m", "tools.paper_maintenance", SHA, "--action", "telegram-recover"],
        )
        self.assertNotIn("systemctl", seen[1])

    def test_action_dispatch_does_not_resume_full_release(self):
        with patch.object(paper_maintenance, "_owner_action_lifecycle_guard", nullcontext), patch.object(
            telegram_only_recover, "recover", return_value="TELEGRAM_ONLY_RECOVERED"
        ) as recover, patch.object(paper_maintenance, "resume_installed_release") as resume:
            with redirect_stdout(StringIO()) as output:
                result = paper_maintenance.main([SHA, "--action", "telegram-recover"])
            self.assertEqual(result, 0)
            self.assertIn("READY: TELEGRAM_ONLY_RECOVERED", output.getvalue())
            recover.assert_called_once_with(SHA)
            resume.assert_not_called()

    def test_blocked_recovery_never_falls_back_to_resume(self):
        with patch.object(paper_maintenance, "_owner_action_lifecycle_guard", nullcontext), patch.object(
            telegram_only_recover, "recover",
            side_effect=telegram_only_recover.TelegramRecoveryBlocked("position_protection_unproven"),
        ), patch.object(paper_maintenance, "resume_installed_release") as resume:
            with redirect_stdout(StringIO()) as output:
                result = paper_maintenance.main([SHA, "--action", "telegram-recover"])
            self.assertEqual(result, 2)
            self.assertIn("BLOCKED: telegram_only_recovery:", output.getvalue())
            resume.assert_not_called()


if __name__ == "__main__":
    unittest.main()
