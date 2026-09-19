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
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

import config
import telegram_bot
from telegram_labels import SCANNER_EMOJI, ROBOT_EMOJI
from robot_lifecycle_posts import (
    build_lifecycle_keyboard, collect_new_lifecycle_events, format_lifecycle_caption,
    load_lifecycle_state, mark_notified, save_lifecycle_state,
)
from robot_position_chart import render_position_chart
from robot_position_view import (
    chart_candle_limit, format_position_card, load_position_view, with_last_price,
)
from robot_telegram_feed import (
    VIEW_POSITIONS, build_robot_control_keyboard,
    format_paper_positions_view,
    format_robot_status_text, parse_robot_view_callback,
)
from terminal.application.robot_control import get_robot_runtime_status
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord, SQLiteStore


PROJECT_ROOT = Path(__file__).resolve().parent
OFFSET_FILE = PROJECT_ROOT / "review_queue" / ".telegram_offset"
LIFECYCLE_STATE_FILE = PROJECT_ROOT / "review_queue" / ".robot_lifecycle_notified"
LIFECYCLE_POLL_SECONDS = 10
_CHART_LOCK = threading.Lock()
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
    return telegram_bot.send_message(config.TELEGRAM_TOKEN, chat_id, text, **kwargs)


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
            f"{SCANNER_EMOJI} Сканер: "
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
        mode = runtime.mode if runtime is not None else "ROBOT_STOPPED"
        recovery_status = runtime.recovery_status if runtime is not None else "ROBOT_STOPPED"
        _send_text(
            chat_id,
            f"{ROBOT_EMOJI} Робот: {_robot_status_text(runtime)}\n"
            f"Статус робота: Наблюдение: {watching} кандидатов\n"
            f"Открытых позиций: {opened}",
            reply_markup=build_robot_control_keyboard(mode, recovery_status),
        )
    except Exception:
        _send_text(chat_id, "Состояние робота и число открытых позиций недоступны.")


def _workspace_url(*, positions=False):
    url = os.environ.get("BYBITSCANNER_WORKSPACE_URL", "").strip()
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username
                or parts.password or any(char.isspace() for char in url)):
            return None
        # Accessing port rejects malformed/out-of-range URL ports.
        parts.port
    except ValueError:
        return None
    if positions:
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "view"
        ]
        query.append(("view", "positions"))
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


def _send_paper_positions(chat_id):
    try:
        with _robot_store() as store:
            if store.get_paper_account(PAPER_ACCOUNT_ID) is None:
                raise ValueError("PAPER account is not initialized")

            positions = store.load_open_position_projections(PAPER_ACCOUNT_ID)

            unfinished_commands = tuple(
                record
                for record in store.load_unfinished_commands()
                if record.trading_account_id == PAPER_ACCOUNT_ID
            )
            unfinished_reconciliation = tuple(
                checkpoint
                for checkpoint in store.load_reconciliation_checkpoints()
                if (
                    checkpoint.position_key.trading_account_id == PAPER_ACCOUNT_ID
                    and checkpoint.completed_at_ms is None
                )
            )

        uncertain = bool(unfinished_commands or unfinished_reconciliation)
        position_rows = build_position_buttons(positions)

        if not positions and uncertain:
            messages = (
                "\u26a0 PAPER \u00b7 \u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e"
                "\n\n\u041e\u0442\u043a\u0440\u044b\u0442\u044b\u0445 \u043f\u043e\u0437\u0438\u0446\u0438\u0439 \u0432 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u043e\u0439 \u043f\u0440\u043e\u0435\u043a\u0446\u0438\u0438 \u043d\u0435\u0442, "
                "\u043d\u043e \u0435\u0441\u0442\u044c \u043d\u0435\u0437\u0430\u0432\u0435\u0440\u0448\u0451\u043d\u043d\u0430\u044f PAPER-\u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044f \u0438\u043b\u0438 \u0441\u0432\u0435\u0440\u043a\u0430. "
                "\u041e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0438\u0435 \u044d\u043a\u0441\u043f\u043e\u0437\u0438\u0446\u0438\u0438 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e.",
            )
        else:
            messages = format_paper_positions_view(positions)
            if uncertain:
                messages = tuple(messages) + (
                    "\u26a0 \u0415\u0441\u0442\u044c \u043d\u0435\u0437\u0430\u0432\u0435\u0440\u0448\u0451\u043d\u043d\u0430\u044f PAPER-\u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044f \u0438\u043b\u0438 \u0441\u0432\u0435\u0440\u043a\u0430. "
                    "\u0421\u043f\u0438\u0441\u043e\u043a \u0432\u044b\u0448\u0435 \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0443\u044e \u044d\u043a\u0441\u043f\u043e\u0437\u0438\u0446\u0438\u044e, \u043d\u043e \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043d\u0435\u043f\u043e\u043b\u043d\u044b\u043c.",
                )
    except Exception:
        _send_text(chat_id, "Данные позиций недоступны.")
        return
    url = _workspace_url(positions=True)
    rows = list(position_rows)
    if url:
        rows.append([{"text": "Открыть в терминале", "web_app": {"url": url}}])
    markup = {"inline_keyboard": rows} if rows else None
    for index, text in enumerate(messages):
        _send_text(chat_id, text, reply_markup=markup if index == len(messages) - 1 else None)


POSITION_CARD_PREFIX = "pos:card:"
POSITIONS_BACK_MARKUP = {
    "inline_keyboard": [[{"text": "⬅️ К позициям", "callback_data": "robot:view:positions"}]],
}


def build_position_buttons(positions) -> list[list[dict[str, str]]]:
    # Numbering and order match format_paper_positions_view's list.
    return [
        [{
            "text": f"{index}. {record.position_key.symbol.value} · {record.side.value}",
            "callback_data": POSITION_CARD_PREFIX + record.position_key.symbol.value,
        }]
        for index, record in enumerate(positions, start=1)
    ]


def parse_position_card_callback(data) -> str | None:
    text = str(data)
    if not text.startswith(POSITION_CARD_PREFIX):
        return None
    symbol = text[len(POSITION_CARD_PREFIX):].strip().upper()
    return symbol if symbol and symbol.isalnum() else None


def _send_position_card(chat_id, symbol: str) -> None:
    try:
        with _robot_store() as store:
            view = load_position_view(store, symbol)
    except Exception as exc:
        print("[POSITION CARD ERROR]", symbol, exc)
        _send_text(chat_id, "Данные позиции недоступны.", reply_markup=POSITIONS_BACK_MARKUP)
        return
    if view is None:
        _send_text(
            chat_id,
            f"{symbol}: открытой позиции нет. Обновите список позиций.",
            reply_markup=POSITIONS_BACK_MARKUP,
        )
        return

    view, candles = _with_candles(view)
    caption = format_position_card(view)
    if not view.is_robot:
        _send_text(chat_id, caption, reply_markup=POSITIONS_BACK_MARKUP)
        return
    _send_chart_card(chat_id, view, candles, caption, POSITIONS_BACK_MARKUP)


def _with_candles(view, now_ms: int | None = None):
    """One candle request per chart, shared by the position card and lifecycle posts."""

    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    minutes = view.chart_candle_minutes
    limit, entry_before_chart = chart_candle_limit(view.entry_time_ms, now_ms, minutes)
    candles = None
    try:
        import bybit_api

        candles = bybit_api.get_candles(view.symbol, str(minutes), limit)
        if candles is not None and len(candles):
            view = replace(
                with_last_price(view, candles["close"].iloc[-1]),
                entry_before_chart=entry_before_chart,
            )
    except Exception as exc:
        print("[POSITION CARD CANDLES ERROR]", view.symbol, exc)
    return view, candles


def _delivered(response) -> bool:
    return isinstance(response, Mapping) and bool(response.get("ok"))


def _send_chart_card(chat_id, view, candles, caption, reply_markup) -> bool:
    """Photo card; a chart or sendPhoto failure falls back to text. True if delivered."""

    # pyplot is not thread-safe and the chart path is per symbol: one render+send at a time.
    with _CHART_LOCK:
        try:
            chart_path = render_position_chart(view, candles)
        except Exception as exc:
            print("[POSITION CHART ERROR]", view.symbol, exc)
            return _delivered(
                _send_text(chat_id, caption + "\nГрафик недоступен", reply_markup=reply_markup)
            )
        try:
            response = telegram_bot.send_photo(
                config.TELEGRAM_TOKEN, chat_id, str(chart_path),
                caption=caption, reply_markup=reply_markup,
            )
            if _delivered(response):
                return True
            raise RuntimeError(f"sendPhoto failed: {response}")
        except Exception as exc:
            print("[POSITION CARD PHOTO ERROR]", view.symbol, exc)
    return _delivered(_send_text(chat_id, caption, reply_markup=reply_markup))


def _send_lifecycle_post(chat_id, event, view) -> bool:
    view, candles = _with_candles(view)
    caption = format_lifecycle_caption(event, view)
    return _send_chart_card(chat_id, view, candles, caption, build_lifecycle_keyboard())


def poll_lifecycle_once(now_ms: int | None = None) -> None:
    chat_id = _owner_id()
    if not chat_id:
        return
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    state = load_lifecycle_state(LIFECYCLE_STATE_FILE, now_ms)
    with _robot_store() as store:
        events = collect_new_lifecycle_events(store, state)
        pending = [
            (event, load_position_view(store, event.symbol, trade_id=event.trade_id))
            for event in events
        ]
    blocked = set()
    for event, view in pending:
        # "закрыта" never goes out before a failed "открыта" of the same trade.
        if event.trade_id in blocked:
            continue
        try:
            sent = view is not None and _send_lifecycle_post(chat_id, event, view)
        except Exception as exc:
            print("[LIFECYCLE SEND ERROR]", event.kind, event.trade_id, exc)
            sent = False
        if not sent:
            print("[LIFECYCLE] not delivered, will retry:", event.kind, event.trade_id)
            blocked.add(event.trade_id)
            continue
        mark_notified(state, event)
        save_lifecycle_state(LIFECYCLE_STATE_FILE, state)
        print("[LIFECYCLE]", event.kind, event.symbol, event.trade_id)


def _lifecycle_loop() -> None:
    while True:
        try:
            poll_lifecycle_once()
        except Exception as exc:
            print("[LIFECYCLE LOOP ERROR]", exc)
        time.sleep(LIFECYCLE_POLL_SECONDS)


def start_lifecycle_thread() -> threading.Thread:
    thread = threading.Thread(target=_lifecycle_loop, name="robot-lifecycle-posts", daemon=True)
    thread.start()
    return thread


def _send_workspace(chat_id, *, positions=False):
    url = _workspace_url(positions=positions)
    if url is None:
        _send_text(chat_id, "HTTPS-адрес терминала не настроен (BYBITSCANNER_WORKSPACE_URL).")
        return
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
        f"{ROBOT_EMOJI} Робот: {robot_status}\n"
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
        "/positions": _send_paper_positions,
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


def _process_positions_callback(callback_query) -> bool:
    data = callback_query.get("data", "")
    card_symbol = parse_position_card_callback(data)
    if card_symbol is None and parse_robot_view_callback(data) != VIEW_POSITIONS:
        return False
    user_id = (callback_query.get("from") or {}).get("id")
    chat_id = ((callback_query.get("message") or {}).get("chat") or {}).get("id")
    if not _is_owner(user_id) or str(chat_id) != _owner_id():
        _answer_callback(callback_query.get("id"), "Недостаточно прав")
        return True
    _answer_callback(callback_query.get("id"))
    if card_symbol is not None:
        _send_position_card(chat_id, card_symbol)
    else:
        _send_paper_positions(chat_id)
    return True


_published_commands = None


def refresh_command_menu() -> None:
    global _published_commands
    try:
        state = _scanner_request()
        scanner_label = SCANNER_ACTIONS[state["mode"]][0]
    except Exception:
        scanner_label = f"{SCANNER_EMOJI} Сканер: состояние недоступно"
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
    start_lifecycle_thread()
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
                    if not (_process_positions_callback(callback_query)
                            or _process_monitor_callback(callback_query)):
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
