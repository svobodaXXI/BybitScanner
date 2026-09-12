from types import SimpleNamespace
import unittest
from unittest.mock import patch

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord
import telegram_monitoring as monitoring


class TelegramMonitoringTests(unittest.TestCase):
    def _record(self, *, phase="WAITING_RETEST", execution=None):
        state = {
            "phase": phase,
            "pattern": "Falling Wedge",
            "direction": "LONG",
        }
        if execution is not None:
            state["execution"] = execution
        return RobotCandidateRecord(
            candidate_id="cand-1",
            trading_account_id=TradingAccountId("paper"),
            symbol=Symbol("1000NEIROCTOUSDT"),
            status="APPROVED",
            signal_snapshot={
                "symbol": "1000NEIROCTOUSDT",
                "pattern": "Falling Wedge",
                "quality": "B Setup",
                "potential": {"signed_percent": 0.76},
            },
            snapshot_sha256="abc",
            robot_state=state,
            state_revision=1,
            approved_at_ms=1,
            updated_at_ms=2,
        )

    def test_phase_labels_are_human_readable(self):
        self.assertEqual(monitoring._phase_label(self._record(phase="WAITING_BREAKOUT")), "Ожидание пробоя")
        self.assertEqual(monitoring._phase_label(self._record(phase="WAITING_RETEST")), "Ожидание ретеста")
        self.assertEqual(monitoring._phase_label(self._record(phase="RETEST_DETECTED")), "Ретест обнаружен")

    def test_limit_order_takes_priority_over_retest_label(self):
        record = self._record(
            phase="RETEST_DETECTED",
            execution={"limit_order_id": "paper-limit-1"},
        )
        self.assertEqual(monitoring._phase_label(record), "Лимитный ордер выставлен")

    def test_candidate_keyboard_uses_candidate_id(self):
        keyboard = monitoring.build_candidate_keyboard((self._record(),))
        button = keyboard["inline_keyboard"][0][0]
        self.assertEqual(button["callback_data"], "monitor:candidate:cand-1")
        self.assertIn("1000NEIROCTOUSDT", button["text"])

    def test_parse_monitor_callbacks(self):
        self.assertEqual(monitoring.parse_monitor_callback("monitor:list"), {"action": "list"})
        self.assertEqual(
            monitoring.parse_monitor_callback("monitor:candidate:cand-1"),
            {"action": "candidate", "candidate_id": "cand-1"},
        )
        self.assertIsNone(monitoring.parse_monitor_callback("robot:approve:cand-1"))

    @patch("telegram_monitoring.get_robot_runtime_status")
    def test_candidate_card_contains_required_monitoring_fields(self, status):
        status.return_value = SimpleNamespace(mode="ROBOT_RUNNING", recovery_status="READY")
        card = monitoring.format_candidate_card(self._record(phase="RETEST_DETECTED"))
        self.assertIn("Тикер: 1000NEIROCTOUSDT", card)
        self.assertIn("Паттерн: Falling Wedge", card)
        self.assertIn("Направление: LONG", card)
        self.assertIn("Состояние: Ретест обнаружен", card)
        self.assertIn("Качество: B Setup", card)
        self.assertIn("Потенциал: +0.76%", card)
        self.assertIn("Робот: ROBOT_RUNNING / READY", card)
        self.assertIn("Сделка: не открыта", card)


if __name__ == "__main__":
    unittest.main()
