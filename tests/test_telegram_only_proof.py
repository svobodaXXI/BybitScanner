"""Isolated source-level protection gates for Telegram-only restart."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import telegram_only_recover as recovery


SHA = "a" * 40
IDENTITY = "b" * 64


class TelegramProtectionProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "release"
        self.unit_dir = Path(self.temp.name) / "units"
        (self.root / "deploy" / "systemd").mkdir(parents=True)
        self.unit_dir.mkdir()
        (self.root / "deploy" / "systemd" / recovery.UNIT).write_text("unit", encoding="utf-8")
        (self.unit_dir / recovery.UNIT).write_text("unit", encoding="utf-8")
        for name, value in (("ROOT", self.root), ("UNIT_DIR", self.unit_dir)):
            p = patch.object(recovery, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.responses = {
            "/api/health": {
                "ok": True, "component": "paper_backend", "mode": "paper",
                "build_sha": SHA, "database_identity": IDENTITY,
                "paper_live_safe": True, "robot_admission_ready": False,
            },
            "/api/scanner/status": {"ok": True, "mode": "SCANNER_STOPPED",
                                    "worker_quiescent": True},
            "/api/robot/autopilot": {"ok": True, "mode": "OFF"},
            "/api/open-positions": {"ok": True, "account_id": "paper", "positions": [
                {"symbol": "SOONUSDT", "position_side": "Short",
                 "position_quantity": "990"}
            ]},
            "/api/paper-state?symbol=SOONUSDT": {
                "ok": True, "account_id": "paper", "symbol": "SOONUSDT",
                "position_side": "Short", "position_quantity": "990",
                "active_limit_orders": [],
                "protection": {
                    "status": "confirmed_active", "stop_loss": "0.25570",
                    "take_profit": "0.24670", "effective_quantity": "990",
                    "warning": None, "pending_command_id": None,
                },
            },
            "/api/robot/protection-health": {
                "ok": True, "healthy": True, "unhealthy_symbols": {},
                "covered_symbols": [], "armed_symbols": [], "coverage_roles": {},
            },
        }

    def prove(self):
        with patch("tools.vps_release_identity.verify_release", return_value=SHA), patch(
            "tools.paper_maintenance._durable_editor_freeze", return_value=IDENTITY
        ), patch.object(
            recovery, "_systemd", return_value={"ActiveState": "active", "MainPID": "461792"}
        ), patch.object(recovery, "_read_json", side_effect=self.responses.__getitem__):
            return recovery._proof(SHA)

    def test_full_position_confirmed_active_is_sufficient_for_telegram_only(self):
        self.assertEqual(self.prove(), 461792)

    def test_missing_stop_blocks(self):
        self.responses["/api/paper-state?symbol=SOONUSDT"]["protection"]["stop_loss"] = None
        with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "position_protection_unproven"):
            self.prove()

    def test_partial_coverage_blocks(self):
        self.responses["/api/paper-state?symbol=SOONUSDT"]["protection"]["effective_quantity"] = "500"
        with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "position_protection_unproven"):
            self.prove()

    def test_mismatched_position_inventory_blocks(self):
        self.responses["/api/paper-state?symbol=SOONUSDT"]["position_quantity"] = "500"
        with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "position_protection_unproven"):
            self.prove()

    def test_pending_protection_command_blocks(self):
        self.responses["/api/paper-state?symbol=SOONUSDT"]["protection"]["pending_command_id"] = "pending"
        with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "position_protection_unproven"):
            self.prove()

    def test_unhealthy_monitor_blocks(self):
        self.responses["/api/robot/protection-health"]["unhealthy_symbols"] = {"SOONUSDT": "lost"}
        with self.assertRaisesRegex(recovery.TelegramRecoveryBlocked, "protection_health_unproven"):
            self.prove()


if __name__ == "__main__":
    unittest.main()
