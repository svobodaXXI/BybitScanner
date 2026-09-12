"""Telegram owner menu for read-only Robot candidate monitoring.

This listener extends the existing Telegram review/Robot callback surface without
changing Robot state.  It reads authoritative candidate state from the Terminal
SQLite store and delegates all non-monitoring callbacks to ``telegram_review``.

Run this listener instead of ``telegram_review.py``; two long-polling getUpdates
consumers must not be run for the same bot token.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Mapping

import requests

import config
import telegram_bot
import telegram_review
from terminal.application.robot_control import get_robot_runtime_status
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord, SQLiteStore


PROJECT_ROOT = Path(r"C:\BybitScanner")
OFFSET_FILE = PROJECT_ROOT / "review_queue" / ".telegram_offset"
PAPER_ACCOUNT_ID = TradingAccountId("paper")
DB_PATH = Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))

PHASE_LABELS = {
    "WAITING_BREAKOUT": "Ожидание пробоя",
    "WAITING_RETEST": "Ожидание ретеста",
    "RETEST_DETECTED": "Ретест обнаружен",
    "EXPIRED_AT_APEX": "Истёк у апекса",
}

ROBOT_MODE_LABELS = {
    "ROBOT_RUNNING": "Запущен",
    "ROBOT_STOPPED": "Остановлен",
}

ROBOT_RECOVERY_LABELS = {
    "READY": "Готов",
    "PAUSED": "Пауза",
    "RECONCILING": "Сверка",
    "RECONCILIATION_REQUIRED": "Нужна сверка",
    "ROBOT_STOPPED": "Остановлен",
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
        [{
            "text": _candidate_button_label(record),
            "callback_data": f"monitor:candidate:{record.candidate_id}",
        }]
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
        return "Остановлен"
    mode = ROBOT_MODE_LABELS.get(str(runtime.mode), "Неизвестно")
    recovery = ROBOT_RECOVERY_LABELS.get(str(runtime.recovery_status), "Неизвестно")
    if mode == recovery:
        return mode
    return f"{mode} / {recovery}"


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
            reply_markup={"inline_keyboard": [[{"text": "🔄 Мониторинг", "callback_data": "monitor:list"}]]},
        )
        return
    telegram_bot.send_message(
        config.TELEGRAM_TOKEN,
        chat_id,
        format_candidate_card(record),
        reply_markup={"inline_keyboard": [[{"text": "⬅️ К кандидатам", "callback_data": "monitor:list"}]]},
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
    if text not in {"/monitoring", "/monitoring@BybitCleanScannerBot", "Мониторинг"}:
        return False
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is not None:
        _send_candidate_list(chat_id)
    return True


def configure_monitoring_menu() -> None:
    commands = json.dumps([
        {"command": "monitoring", "description": "Мониторинг кандидатов"},
    ], ensure_ascii=False)
    response = _telegram_request("setMyCommands", commands=commands)
    if not response.get("ok"):
        raise RuntimeError(f"setMyCommands failed: {response}")

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
