"""Telegram owner menu for read-only Robot candidate monitoring.

This listener extends the existing Telegram review/Robot callback surface without
changing Robot state. It reads authoritative candidate state from the Terminal
SQLite store and delegates all non-monitoring callbacks to ``telegram_review``.

Run this listener instead of ``telegram_review.py``; two long-polling getUpdates
consumers must not be run for the same bot token.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

import config
import telegram_bot
from robot_telegram_feed import format_robot_status_text
from terminal.application.robot_control import get_robot_runtime_status
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord, SQLiteStore


PROJECT_ROOT = Path(__file__).resolve().parent
OFFSET_FILE = PROJECT_ROOT / "review_queue" / ".telegram_offset"
PAPER_ACCOUNT_ID = TradingAccountId("paper")
DB_PATH = Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))

SCANNER_ACTIONS = {
    "SCANNER_RUNNING": ("Остановить сканер", "pause"),
    "SCANNER_PAUSED": ("Запустить сканер", "resume"),
    "SCANNER_STOPPED": ("Запустить сканер", "start"),
}


@contextmanager
def _robot_store():
    # Read Robot projections without creating or migrating a database.
    connection = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("BEGIN")
    store = SQLiteStore(connection, DB_PATH, 5000)
    try:
        yield store
    finally:
        store.close()


def _scanner_request(action=None):
    base = os.environ.get("BYBITSCANNER_PAPER_BACKEND_URL", "http://127.0.0.1:8765").rstrip("/")
    url = base + "/api/scanner/" + (action or "status")
    response = (
        requests.post(url, json={}, timeout=10, allow_redirects=False)
        if action
        else requests.get(url, timeout=10, allow_redirects=False)
    )
    response.raise_for_status()
    result = response.json()
    if result.get("ok") is not True or result.get("mode") not in SCANNER_ACTIONS:
        raise ValueError("Scanner authority unavailable")
    return result


def _send_text(chat_id, text, **kwargs):
    telegram_bot.send_message(config.TELEGRAM_TOKEN, chat_id, text, **kwargs)


def _send_scanner_control(chat_id):
    try:
        state = _scanner_request()
        # One dispatch only. Never retry a mutation after an ambiguous response.
        _scanner_request(SCANNER_ACTIONS[state["mode"]][1])
    except Exception:
        _send_text(
            chat_id,
            "Команда сканера не подтверждена. Состояние будет проверено; автоматического повтора нет.",
        )
    try:
        state = _scanner_request()
        _send_text(
            chat_id,
            "Сканер: "
            + {
                "SCANNER_RUNNING": "запущен",
                "SCANNER_PAUSED": "на паузе",
                "SCANNER_STOPPED": "остановлен",
            }[state["mode"]],
        )
    except Exception:
        _send_text(chat_id, "Состояние сканера недоступно.")
    refresh_command_menu()


def _send_robot_status(chat_id):
    try:
        with _robot_store() as store:
            runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
            candidates = store.load_robot_candidates(PAPER_ACCOUNT_ID)
        opened = sum(item.status == "OPEN" for item in candidates)
        watching = sum(item.status == "APPROVED" for item in candidates)
        _send_text(
            chat_id,
            f"Робот: {_robot_status_text(runtime)}\n"
            f"Статус робота: Наблюдение: {watching} кандидатов\n"
            f"Открытых позиций: {opened}",
        )
    except Exception:
        _send_text(chat_id, "Состояние робота и число открытых позиций недоступны.")


def _send_workspace(chat_id, *, positions=False):
    url = os.environ.get("BYBITSCANNER_WORKSPACE_URL", "").strip()
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        _send_text(chat_id, "HTTPS-адрес терминала не настроен (BYBITSCANNER_WORKSPACE_URL).")
        return
    if positions:
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "view"
        ]
        query.append(("view", "positions"))
        url = urlunsplit(parts._replace(query=urlencode(query)))
    label = "Все открытые позиции" if positions else "Терминал"
    _send_text(
        chat_id,
        label,
        reply_markup={
            "inline_keyboard": [[{"text": label, "web_app": {"url": url}}]],
        },
    )


PHASE_LABELS = {
    "WAITING_BREAKOUT": "Ожидание пробоя",
    "WAITING_RETEST": "Ожидание ретеста",
    "RETEST_DETECTED": "Ретест обнаружен",
    "EXPIRED_AT_APEX": "Истёк у апекса",
}


def _telegram_request(method: str, **params):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/{method}"
    response = requests.get(url, params=params, timeout=40)
    return response.json()


def _owner_id() -> str:
    return str(getattr(config, "TELEGRAM_CHAT_ID", "")).strip()


def _is_owner(user_id) -> bool:
    owner = _owner_id()
    return bool(owner) and str(user_id).strip() == owner


def _load_offset():
    if not OFFSET_FILE.exists():
        return None
    try:
        return int(OFFSET_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(int(offset)), encoding="utf-8")


def _load_active_candidates() -> tuple[RobotCandidateRecord, ...]:
    with SQLiteStore.open(DB_PATH) as store:
        records = store.load_robot_candidates(PAPER_ACCOUNT_ID)
    active = [record for record in records if record.status == "APPROVED"]
    active.sort(key=lambda record: (record.updated_at_ms, record.candidate_id), reverse=True)
    return tuple(active)


def _phase_label(record: RobotCandidateRecord) -> str:
    state = record.robot_state or {}
    execution = state.get("execution") if isinstance(state, Mapping) else None
    if isinstance(execution, Mapping) and execution.get("limit_order_id"):
        return "Лимитный ордер выставлен"
    phase = str(state.get("phase", "")).strip() if isinstance(state, Mapping) else ""
    if not phase:
        return "Паттерн формируется"
    return PHASE_LABELS.get(phase, phase)


def _candidate_button_label(record: RobotCandidateRecord) -> str:
    label = _phase_label(record)
    marker = "🟢" if label in {"Ретест обнаружен", "Лимитный ордер выставлен"} else "🟡"
    return f"{marker} {record.symbol.value} · {label}"


def build_candidate_keyboard(records: tuple[RobotCandidateRecord, ...]):
    rows = [
        [
            {
                "text": _candidate_button_label(record),
                "callback_data": f"monitor:candidate:{record.candidate_id}",
            }
        ]
        for record in records
    ]
    rows.append([{"text": "🔄 Обновить", "callback_data": "monitor:list"}])
    return {"inline_keyboard": rows}


def _quality_text(snapshot: Mapping[str, object]) -> str:
    quality = snapshot.get("quality")
    if isinstance(quality, Mapping):
        for key in ("tier", "label", "quality"):
            value = quality.get(key)
            if value:
                return str(value)
    return str(quality or "—")


def _potential_text(snapshot: Mapping[str, object]) -> str:
    potential = snapshot.get("potential")
    if isinstance(potential, Mapping):
        value = potential.get("signed_percent", potential.get("percent"))
        if value is not None:
            try:
                number = float(value)
                return f"{number:+.2f}%"
            except (TypeError, ValueError):
                return str(value)
    return "—"


def _robot_status_text(runtime) -> str:
    if runtime is None:
        return format_robot_status_text("ROBOT_STOPPED", "ROBOT_STOPPED")
    return format_robot_status_text(runtime.mode, runtime.recovery_status)


def format_candidate_card(record: RobotCandidateRecord) -> str:
    snapshot = record.signal_snapshot
    state = record.robot_state or {}
    direction = state.get("direction") or snapshot.get("direction") or "—"
    pattern = snapshot.get("pattern") or state.get("pattern") or "—"
    try:
        robot_status = _robot_status_text(get_robot_runtime_status())
    except Exception:
        robot_status = "Неизвестно"

    return (
        "🤖 Мониторинг кандидата\n\n"
        f"Тикер: {record.symbol.value}\n"
        f"Паттерн: {pattern}\n"
        f"Направление: {direction}\n"
        f"Состояние: {_phase_label(record)}\n"
        f"Качество: {_quality_text(snapshot)}\n"
        f"Потенциал: {_potential_text(snapshot)}\n\n"
        f"Робот: {robot_status}\n"
        "Сделка: не открыта"
    )


def parse_monitor_callback(data: str):
    parts = str(data).split(":")
    if parts == ["monitor", "list"]:
        return {"action": "list"}
    if len(parts) == 3 and parts[0] == "monitor" and parts[1] == "candidate" and parts[2]:
        return {"action": "candidate", "candidate_id": parts[2]}
    return None


def _send_candidate_list(chat_id) -> None:
    records = _load_active_candidates()
    if not records:
        telegram_bot.send_message(
            config.TELEGRAM_TOKEN,
            chat_id,
            "🤖 Мониторинг\n\nАктивных кандидатов сейчас нет.",
        )
        return
    telegram_bot.send_message(
        config.TELEGRAM_TOKEN,
        chat_id,
        f"🤖 Мониторинг\n\nАктивных кандидатов: {len(records)}\nВыберите тикер:",
        reply_markup=build_candidate_keyboard(records),
    )


def _send_candidate_card(chat_id, candidate_id: str) -> None:
    with SQLiteStore.open(DB_PATH) as store:
        record = store.get_robot_candidate(candidate_id)
    if record is None or record.status != "APPROVED":
        telegram_bot.send_message(
            config.TELEGRAM_TOKEN,
            chat_id,
            "Кандидат больше не активен. Обновите список мониторинга.",
            reply_markup={
                "inline_keyboard": [[{"text": "🔄 Мониторинг", "callback_data": "monitor:list"}]]
            },
        )
        return
    telegram_bot.send_message(
        config.TELEGRAM_TOKEN,
        chat_id,
        format_candidate_card(record),
        reply_markup={
            "inline_keyboard": [[{"text": "⬅️ К кандидатам", "callback_data": "monitor:list"}]]
        },
    )


def _answer_callback(callback_id, text: str = "") -> None:
    if callback_id:
        try:
            _telegram_request("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except Exception as exc:
            print("[MONITORING CALLBACK ERROR]", exc)


def _process_monitor_callback(callback_query) -> bool:
    parsed = parse_monitor_callback(callback_query.get("data", ""))
    if parsed is None:
        return False
    user = callback_query.get("from") or {}
    if not _is_owner(user.get("id")):
        _answer_callback(callback_query.get("id"), "Недостаточно прав")
        return True
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        _answer_callback(callback_query.get("id"), "Чат не найден")
        return True
    _answer_callback(callback_query.get("id"))
    if parsed["action"] == "list":
        _send_candidate_list(chat_id)
    else:
        _send_candidate_card(chat_id, parsed["candidate_id"])
    return True


def _process_message(message) -> bool:
    from_user = message.get("from") or {}
    if not _is_owner(from_user.get("id")):
        return False
    text = str(message.get("text", "")).strip()
    command = text.split("@", 1)[0]
    handlers = {
        "/terminal": _send_workspace,
        "/scanner": _send_scanner_control,
        "/robot": _send_robot_status,
        "/positions": lambda chat_id: _send_workspace(chat_id, positions=True),
        "/monitoring": _send_candidate_list,
        "Мониторинг": _send_candidate_list,
    }
    handler = handlers.get(command)
    if handler is None:
        return False
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    # Web App navigation and runtime controls belong to the owner's private chat.
    if chat_id is not None and str(chat_id) == _owner_id():
        handler(chat_id)
    return True


_published_commands = None


def refresh_command_menu() -> None:
    global _published_commands
    try:
        state = _scanner_request()
        scanner_label = SCANNER_ACTIONS[state["mode"]][0]
    except Exception:
        scanner_label = "Сканер: состояние недоступно"
    commands = json.dumps(
        [
            {"command": "terminal", "description": "Терминал"},
            {"command": "scanner", "description": scanner_label},
            {"command": "robot", "description": "Робот"},
            {"command": "positions", "description": "Все открытые позиции"},
            {"command": "monitoring", "description": "Мониторинг кандидатов"},
        ],
        ensure_ascii=False,
    )
    # Cache only successful Telegram publication, never runtime truth.
    if commands != _published_commands:
        response = _telegram_request("setMyCommands", commands=commands)
        if not response.get("ok"):
            raise RuntimeError("setMyCommands failed")
        _published_commands = commands


def configure_monitoring_menu() -> None:
    refresh_command_menu()

    owner = _owner_id()
    if owner:
        response = _telegram_request(
            "setChatMenuButton",
            chat_id=owner,
            menu_button=json.dumps({"type": "commands"}),
        )
        if not response.get("ok"):
            raise RuntimeError(f"setChatMenuButton failed: {response}")


def run() -> None:
    print("=" * 60)
    print("BybitScanner Telegram Monitoring Listener")
    print(f"DB: {DB_PATH}")
    print("=" * 60)
    configure_monitoring_menu()
    offset = _load_offset()

    while True:
        try:
            refresh_command_menu()
            params = {
                "timeout": 30,
                "allowed_updates": json.dumps(["callback_query", "message"]),
            }
            if offset is not None:
                params["offset"] = offset
            result = _telegram_request("getUpdates", **params)
            if not result.get("ok"):
                print("[MONITORING TELEGRAM ERROR]", result)
                time.sleep(3)
                continue

            for update in result.get("result", []):
                update_id = update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1
                    _save_offset(offset)

                callback_query = update.get("callback_query")
                if callback_query:
                    if not _process_monitor_callback(callback_query):
                        import telegram_review

                        telegram_review._process_callback(callback_query)
                    continue

                message = update.get("message")
                if message:
                    _process_message(message)

        except KeyboardInterrupt:
            print()
            print("Monitoring listener stopped.")
            break
        except Exception as exc:
            print("[MONITORING LOOP ERROR]", exc)
            time.sleep(3)


if __name__ == "__main__":
    run()
