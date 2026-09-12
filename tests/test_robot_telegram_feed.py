from decimal import Decimal
import unittest

from robot_telegram_feed import (
    EVENT_CLOSED,
    EVENT_OBSERVATION,
    EVENT_OPENED,
    VIEW_FEED,
    VIEW_POSITIONS,
    VIEW_WATCHING,
    build_closed_card,
    build_main_menu_keyboard,
    build_observation_card,
    build_opened_card,
    build_robot_close_all_confirmation_keyboard,
    build_robot_control_keyboard,
    build_robot_tab_keyboard,
    format_positions_view,
    format_robot_status_text,
    format_watching_view,
    parse_robot_control_callback,
    parse_robot_view_callback,
)


def _geometry():
    return {
        "upper_line": {"slope": -1.0, "intercept": 200.0},
        "lower_line": {"slope": -0.5, "intercept": 145.0},
        "apex": {"index": 110, "price": 90.0, "valid_intersection": True},
        "current_index": 100,
    }


def _base():
    return {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "direction": "LONG",
        "timeframe": "1",
        "state": "WAITING_RETEST",
        "geometry": _geometry(),
        "entry_price": Decimal("96"),
        "average_entry": Decimal("96.1"),
        "stop": Decimal("94.2"),
        "take": Decimal("100.5"),
    }


class RobotTelegramFeedTests(unittest.TestCase):
    def test_main_menu_contains_robot_between_terminal_and_scanner(self):
        keyboard = build_main_menu_keyboard()["inline_keyboard"]
        labels = [row[0]["text"] for row in keyboard]
        self.assertEqual(labels, ["Терминал", "🤖 Робот", "Запуск сканера", "Статистика"])
        self.assertEqual(keyboard[1][0]["callback_data"], "robot:view:feed")

    def test_robot_tab_has_positions_and_watching(self):
        keyboard = build_robot_tab_keyboard()["inline_keyboard"]
        self.assertEqual(keyboard[0][0]["callback_data"], "robot:view:positions")
        self.assertEqual(keyboard[0][1]["callback_data"], "robot:view:watching")

    def test_robot_view_callback_parser_is_fail_closed(self):
        self.assertEqual(parse_robot_view_callback("robot:view:feed"), VIEW_FEED)
        self.assertEqual(parse_robot_view_callback("robot:view:positions"), VIEW_POSITIONS)
        self.assertEqual(parse_robot_view_callback("robot:view:watching"), VIEW_WATCHING)
        self.assertIsNone(parse_robot_view_callback("robot:view:unknown"))
        self.assertIsNone(parse_robot_view_callback("robot:approve:candidate"))

    def test_observation_card_uses_existing_state_and_frozen_geometry(self):
        card = build_observation_card(_base())
        self.assertEqual(card.event_type, EVENT_OBSERVATION)
        self.assertIn("TESTUSDT", card.text)
        self.assertIn("WAITING_RETEST", card.text)
        self.assertEqual(card.chart["geometry"], _geometry())

    def test_opened_card_contains_volume_entry_stop_take(self):
        record = _base()
        record["volume_wv"] = Decimal("0.8")
        card = build_opened_card(record)
        self.assertEqual(card.event_type, EVENT_OPENED)
        self.assertIn("0.8 WV", card.text)
        self.assertIn("96.1", card.text)
        self.assertIn("94.2", card.text)
        self.assertIn("100.5", card.text)

    def test_closed_card_contains_reason_and_realized_pnl(self):
        record = _base()
        record.update({
            "exit_reason": "TAKE",
            "realized_pnl_usdt": Decimal("12.5"),
            "realized_pnl_percent": Decimal("2.4"),
            "exit_marker": {"price": "100.5"},
        })
        card = build_closed_card(record)
        self.assertEqual(card.event_type, EVENT_CLOSED)
        self.assertIn("TAKE", card.text)
        self.assertIn("12.5 USDT", card.text)
        self.assertIn("2.4%", card.text)
        self.assertEqual(card.chart["exit_marker"], {"price": "100.5"})

    def test_positions_and_watching_views_are_plain_projections(self):
        positions = format_positions_view([
            {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "volume_wv": Decimal("1"),
                "unrealized_pnl_usdt": Decimal("3.2"),
            }
        ])
        watching = format_watching_view([
            {
                "symbol": "ETHUSDT",
                "pattern": "Falling Wedge",
                "state": "WAITING_BREAKOUT",
            }
        ])
        self.assertIn("BTCUSDT", positions)
        self.assertIn("1 WV", positions)
        self.assertIn("ETHUSDT", watching)
        self.assertIn("WAITING_BREAKOUT", watching)

    def test_empty_views_are_explicit(self):
        self.assertIn("Открытых позиций нет", format_positions_view([]))
        self.assertIn("ничего нет", format_watching_view([]))

    def test_control_callback_parser_accepts_only_known_commands(self):
        self.assertEqual(parse_robot_control_callback("robot:cmd:start"), "start")
        self.assertEqual(parse_robot_control_callback("robot:cmd:pause"), "pause")
        self.assertEqual(parse_robot_control_callback("robot:cmd:resume"), "resume")
        self.assertEqual(parse_robot_control_callback("robot:cmd:stop"), "stop")
        self.assertEqual(parse_robot_control_callback("robot:cmd:close_all"), "close_all")
        self.assertEqual(parse_robot_control_callback("robot:cmd:close_all_confirm"), "close_all_confirm")
        self.assertEqual(parse_robot_control_callback("robot:cmd:close_all_cancel"), "close_all_cancel")
        self.assertIsNone(parse_robot_control_callback("robot:cmd:unknown"))
        self.assertIsNone(parse_robot_control_callback("robot:approve:candidate"))
        self.assertIsNone(parse_robot_control_callback("robot:view:feed"))

    def test_control_keyboard_stopped_offers_only_start(self):
        keyboard = build_robot_control_keyboard("ROBOT_STOPPED", "ROBOT_STOPPED")["inline_keyboard"]
        buttons = [button for row in keyboard for button in row]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]["callback_data"], "robot:cmd:start")

    def test_control_keyboard_running_ready_offers_pause_close_all_and_stop(self):
        keyboard = build_robot_control_keyboard("ROBOT_RUNNING", "READY")["inline_keyboard"]
        buttons = [button for row in keyboard for button in row]
        callbacks = [button["callback_data"] for button in buttons]
        self.assertEqual(callbacks, ["robot:cmd:pause", "robot:cmd:close_all", "robot:cmd:stop"])

    def test_control_keyboard_running_paused_toggles_to_resume(self):
        keyboard = build_robot_control_keyboard("ROBOT_RUNNING", "PAUSED")["inline_keyboard"]
        buttons = [button for row in keyboard for button in row]
        callbacks = [button["callback_data"] for button in buttons]
        self.assertEqual(callbacks, ["robot:cmd:resume", "robot:cmd:close_all", "robot:cmd:stop"])

    def test_control_keyboard_reconciliation_required_offers_no_buttons(self):
        stopped = build_robot_control_keyboard("ROBOT_STOPPED", "RECONCILIATION_REQUIRED")
        running = build_robot_control_keyboard("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")
        self.assertEqual(stopped["inline_keyboard"], [])
        self.assertEqual(running["inline_keyboard"], [])

    def test_close_all_confirmation_keyboard_has_confirm_and_cancel(self):
        keyboard = build_robot_close_all_confirmation_keyboard()["inline_keyboard"]
        buttons = [button for row in keyboard for button in row]
        callbacks = [button["callback_data"] for button in buttons]
        self.assertEqual(callbacks, ["robot:cmd:close_all_confirm", "robot:cmd:close_all_cancel"])


class RobotStatusTextTests(unittest.TestCase):
    """The single shared Russian presentation mapping for durable Robot
    admission (mode, recovery_status), used by both telegram_review.py's
    per-signal status panel and telegram_monitoring.py's candidate card."""

    def test_running_ready(self):
        self.assertEqual(format_robot_status_text("ROBOT_RUNNING", "READY"), "Запущен / Готов")

    def test_running_paused(self):
        self.assertEqual(format_robot_status_text("ROBOT_RUNNING", "PAUSED"), "Запущен / Пауза")

    def test_running_reconciling(self):
        self.assertEqual(format_robot_status_text("ROBOT_RUNNING", "RECONCILING"), "Запущен / Сверка")

    def test_running_reconciliation_required(self):
        self.assertEqual(
            format_robot_status_text("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
            "Запущен / Нужна сверка",
        )

    def test_stopped_collapses_to_a_single_label(self):
        self.assertEqual(format_robot_status_text("ROBOT_STOPPED", "ROBOT_STOPPED"), "Остановлен")

    def test_unknown_values_never_leak_the_raw_internal_string(self):
        self.assertEqual(format_robot_status_text("SOMETHING_NEW", "SOMETHING_NEW"), "Неизвестно")


if __name__ == "__main__":
    unittest.main()
