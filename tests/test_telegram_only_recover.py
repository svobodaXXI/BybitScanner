"""Regression tests for the isolated Telegram-only lifecycle boundary."""
import unittest
from unittest.mock import patch, MagicMock

from tools import telegram_only_recover as recovery


class TelegramOnlyRecoveryTests(unittest.TestCase):
    def test_missing_or_mismatched_guard_never_starts(self):
        with patch.object(recovery, "_proof", side_effect=recovery.TelegramRecoveryBlocked("position_protection_unproven")):
            with patch.object(recovery.subprocess, "run") as run:
                with self.assertRaises(recovery.TelegramRecoveryBlocked):
                    recovery.recover("a" * 40)
                run.assert_not_called()

    def test_active_telegram_is_not_restarted(self):
        with patch.object(recovery, "_proof", return_value=4242), patch.object(
            recovery, "_systemd", return_value={"ActiveState": "active", "MainPID": "123"}
        ), patch.object(recovery.subprocess, "run") as run:
            with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "worker_not_absent"):
                recovery.recover("a" * 40)
            run.assert_not_called()

    def test_occupied_listener_is_not_started(self):
        with patch.object(recovery, "_proof", return_value=4242), patch.object(
            recovery, "_systemd", return_value={"ActiveState": "failed", "MainPID": "0"}
        ), patch("tools.legacy_runtime_process.probe_listener_pids", return_value=(99,)), patch.object(
            recovery.subprocess, "run"
        ) as run:
            with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "listener_not_absent"):
                recovery.recover("a" * 40)
            run.assert_not_called()

    def test_telegram_409_failure_is_single_attempt(self):
        with patch.object(recovery, "_proof", return_value=4242), patch.object(
            recovery, "_systemd", return_value={"ActiveState": "failed", "MainPID": "0"}
        ), patch("tools.legacy_runtime_process.probe_listener_pids", return_value=()), patch.object(
            recovery.subprocess, "run", return_value=MagicMock(returncode=1)
        ) as run:
            with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "no_retry"):
                recovery.recover("a" * 40)
            run.assert_called_once_with(
                ["systemctl", "start", recovery.UNIT], cwd=recovery.ROOT,
                capture_output=True, text=True, check=False, timeout=180,
            )

    def test_backend_changed_before_start_never_starts(self):
        with patch.object(recovery, "_proof", side_effect=[
            4242, recovery.TelegramRecoveryBlocked("backend_pid_changed")
        ]), patch.object(recovery, "_systemd", return_value={
            "ActiveState": "failed", "MainPID": "0"
        }), patch("tools.legacy_runtime_process.probe_listener_pids", return_value=()), patch.object(
            recovery.subprocess, "run"
        ) as run:
            with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "backend_pid_changed"):
                recovery.recover("a" * 40)
            run.assert_not_called()

    def test_success_requires_ready_telegram_and_same_backend(self):
        ready = MagicMock(status=200)
        ready.json.return_value = {
            "component": "telegram_monitoring", "status": "ready", "database_identity": "db"
        }
        with patch.object(recovery, "_proof", return_value=4242) as proof, patch.object(
            recovery, "_systemd", return_value={"ActiveState": "failed", "MainPID": "0"}
        ), patch("tools.legacy_runtime_process.probe_listener_pids", return_value=()), patch.object(
            recovery.subprocess, "run", return_value=MagicMock(returncode=0)
        ) as run, patch("tools.runtime_intent.http_get", return_value=ready), patch.object(
            recovery, "_read_json", return_value={"database_identity": "db"}
        ):
            self.assertEqual(recovery.recover("a" * 40), "TELEGRAM_ONLY_RECOVERED")
            self.assertEqual(proof.call_count, 3)
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
