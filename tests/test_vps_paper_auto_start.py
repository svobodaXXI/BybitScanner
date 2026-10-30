"""No real runtime, DB, or trading transitions: isolated VPS launch policy checks."""
import unittest
from unittest.mock import patch

from tools import vps_paper_auto_start as launch


TOKEN = "x" * 40
ENV = {
    "BYBITSCANNER_VPS_PAPER_AUTO_ON_START": "1",
    "BYBITSCANNER_AUTOPILOT_OWNER_TOKEN": TOKEN,
}


def replies(mode="OFF", healthy=True, scanner="SCANNER_RUNNING", account="paper"):
    return {
        "/api/health": {
            "ok": True, "component": "paper_backend", "mode": "paper",
            "paper_live_safe": True, "robot_admission_ready": True,
            "scanner_acceptance_ready": True, "database_identity": "db",
        },
        "/api/scanner/status": {"ok": True, "mode": scanner},
        "/api/robot/protection-health": {"ok": True, "healthy": healthy},
        "/api/robot/autopilot": {
            "ok": True, "mode": mode,
            "trading_account_id": {"value": account},
        },
    }


class UnifiedPaperStartTests(unittest.TestCase):
    def test_missing_owner_opt_in_never_calls_backend(self):
        with patch.object(launch, "request") as call:
            with self.assertRaises(launch.StartupBlocked):
                launch.enable_from_authorized_start({})
            call.assert_not_called()

    def test_token_required_before_any_backend_mutation(self):
        with patch.object(launch, "request") as call:
            with self.assertRaises(launch.StartupBlocked):
                launch.enable_from_authorized_start({
                    "BYBITSCANNER_VPS_PAPER_AUTO_ON_START": "1",
                })
            call.assert_not_called()

    def test_ready_runtime_confirmed_then_authorized_mode_change(self):
        responses = replies()
        calls = []

        def fake(path, *, data=None, token=None):
            calls.append((path, data, token))
            if data is not None:
                self.assertEqual(path, "/api/robot/autopilot")
                self.assertEqual(data, {"mode": "PAPER_AUTO", "confirm_paper_auto": True})
                self.assertEqual(token, TOKEN)
                responses[path] = {**responses[path], "mode": "PAPER_AUTO"}
            return responses[path]

        with patch.object(launch, "request", side_effect=fake):
            launch.enable_from_authorized_start(ENV)
        self.assertEqual(sum(data is not None for _, data, _ in calls), 1)
        self.assertEqual(calls[-1][0], "/api/robot/autopilot")
        self.assertIsNone(calls[-1][1])

    def test_already_enabled_is_idempotent(self):
        responses = replies(mode="PAPER_AUTO")
        with patch.object(launch, "request", side_effect=lambda path, **_: responses[path]) as call:
            launch.enable_from_authorized_start(ENV)
        self.assertEqual(call.call_count, 5)

    def test_fail_closed_on_unproven_gates(self):
        for name, payload in (
            ("scanner", replies(scanner="SCANNER_STOPPED")),
            ("protection", replies(healthy=False)),
            ("live", {**replies(), "/api/health": {
                **replies()["/api/health"], "paper_live_safe": False,
            }}),
            ("account", replies(account="live")),
            ("shadow", replies(mode="SHADOW")),
        ):
            with self.subTest(name=name):
                with patch.object(launch, "request", side_effect=lambda path, **_: payload[path]) as call:
                    with self.assertRaises(launch.StartupBlocked):
                        launch.enable_from_authorized_start(ENV)
                    self.assertFalse(any(c.kwargs.get("data") for c in call.call_args_list))

    def test_failed_post_never_reports_success(self):
        responses = replies()

        def fake(path, *, data=None, token=None):
            if data:
                raise launch.StartupBlocked("HTTP 403")
            return responses[path]

        with patch.object(launch, "request", side_effect=fake):
            with self.assertRaises(launch.StartupBlocked):
                launch.enable_from_authorized_start(ENV)


if __name__ == "__main__":
    unittest.main()
