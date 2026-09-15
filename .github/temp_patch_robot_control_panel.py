from pathlib import Path

monitoring_path = Path("telegram_monitoring.py")
text = monitoring_path.read_text(encoding="utf-8")

old = "from robot_telegram_feed import format_robot_status_text\n"
new = "from robot_telegram_feed import build_robot_control_keyboard, format_robot_status_text\n"
if text.count(old) != 1:
    raise SystemExit(f"monitoring import marker count={text.count(old)}")
text = text.replace(old, new, 1)

old = '''def _send_robot_status(chat_id):
    try:
        with _robot_store() as store:
            runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
            candidates = store.load_robot_candidates(PAPER_ACCOUNT_ID)
        opened = sum(item.status == "OPEN" for item in candidates)
        watching = sum(item.status == "APPROVED" for item in candidates)
        _send_text(
            chat_id,
            f"Робот: {_robot_status_text(runtime)}\\n"
            f"Статус робота: Наблюдение: {watching} кандидатов\\n"
            f"Открытых позиций: {opened}",
        )
    except Exception:
        _send_text(chat_id, "Состояние робота и число открытых позиций недоступны.")
'''
new = '''def _send_robot_status(chat_id):
    try:
        with _robot_store() as store:
            runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
            candidates = store.load_robot_candidates(PAPER_ACCOUNT_ID)
        opened = sum(item.status == "OPEN" for item in candidates)
        watching = sum(item.status == "APPROVED" for item in candidates)
        mode = runtime.mode if runtime is not None else "ROBOT_STOPPED"
        recovery_status = runtime.recovery_status if runtime is not None else "ROBOT_STOPPED"
        _send_text(
            chat_id,
            f"Робот: {_robot_status_text(runtime)}\\n"
            f"Статус робота: Наблюдение: {watching} кандидатов\\n"
            f"Открытых позиций: {opened}",
            reply_markup=build_robot_control_keyboard(mode, recovery_status),
        )
    except Exception:
        _send_text(chat_id, "Состояние робота и число открытых позиций недоступны.")
'''
if text.count(old) != 1:
    raise SystemExit(f"robot status marker count={text.count(old)}")
text = text.replace(old, new, 1)
monitoring_path.write_text(text, encoding="utf-8")

test_path = Path("tests/test_telegram_monitoring.py")
test_text = test_path.read_text(encoding="utf-8")
old = '''        monitoring._send_robot_status(123)
        self.assertIn("Запущен / Готов", send.call_args.args[1])
        self.assertIn("Открытых позиций: 1", send.call_args.args[1])
'''
new = '''        monitoring._send_robot_status(123)
        self.assertIn("Запущен / Готов", send.call_args.args[1])
        self.assertIn("Открытых позиций: 1", send.call_args.args[1])
        keyboard = send.call_args.kwargs["reply_markup"]
        self.assertEqual(
            keyboard["inline_keyboard"][0][0]["callback_data"],
            "robot:cmd:pause",
        )
        self.assertEqual(
            keyboard["inline_keyboard"][1][0]["callback_data"],
            "robot:cmd:close_all",
        )
        self.assertEqual(
            keyboard["inline_keyboard"][1][1]["callback_data"],
            "robot:cmd:stop",
        )
'''
if test_text.count(old) != 1:
    raise SystemExit(f"monitoring test marker count={test_text.count(old)}")
test_text = test_text.replace(old, new, 1)

test_path.write_text(test_text, encoding="utf-8")
