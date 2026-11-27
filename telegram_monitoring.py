"""Telegram owner menu for read-only Robot candidate monitoring.

This listener extends the existing Telegram review/Robot callback surface without
changing Robot state. It reads authoritative candidate state from the Terminal
SQLite store and delegates all non-monitoring callbacks to ``telegram_review``.

Run this listener instead of ``telegram_review.py``; two long-polling getUpdates
consumers must not be run for the same bot token. A localhost-only health
listener (default port 8766) doubles as the per-host singleton: a second worker
cannot bind it and never enters getUpdates. ``GET /health`` answers 200 only
after a getUpdates response proved this worker owns the update stream.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

import config
import metascalp_bridge
import signal_archive
import telegram_bot
from telegram_gateway_client import TelegramGatewayError
import telegram_runtime_intent
from telegram_labels import SCANNER_EMOJI, ROBOT_EMOJI
from tools import stop_robot_runtime
from robot_lifecycle_posts import (
    EVENT_OPENED, build_lifecycle_keyboard, collect_new_lifecycle_events,
    format_lifecycle_caption, load_lifecycle_state, mark_notified, save_lifecycle_state,
)
from robot_position_chart import render_position_chart
from robot_position_view import (
    PositionView, chart_candle_limit, format_position_card, load_position_view,
    signal_chart_candle_minutes, with_last_price,
)
from robot_telegram_feed import (
    VIEW_POSITIONS, build_robot_control_keyboard,
    format_paper_positions_view,
    format_robot_status_text, robot_control_status_note, parse_robot_view_callback,
)
from terminal.application.robot_admission import box_plan_admission_handle
from terminal.application.robot_control import get_robot_runtime_status
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord, SQLiteStore
from tradingview_bridge import create_tradingview_url
from notification import build_tradingview_keyboard
from telegram_market import MarketRadar, RADAR_INTERVAL_SECONDS


PROJECT_ROOT = Path(__file__).resolve().parent
OFFSET_FILE = PROJECT_ROOT / "review_queue" / ".telegram_offset"
LIFECYCLE_STATE_FILE = PROJECT_ROOT / "review_queue" / ".robot_lifecycle_notified"
LIFECYCLE_POLL_SECONDS = 10
LIFECYCLE_RETRY_COOLDOWN_MS = 300_000  # Durable five-minute backoff.
_CHART_LOCK = threading.Lock()
PAPER_ACCOUNT_ID = TradingAccountId("paper")
DB_PATH = Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))

SCANNER_ACTIONS = {
    "SCANNER_RUNNING": ("⏸ Пауза сканера", "pause"),
    "SCANNER_PAUSED": ("▶ Продолжить сканер", "resume"),
    "SCANNER_STOPPED": ("▶ Запустить сканер", "start"),
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


_MARKET_REQUEST_LOCK = threading.Lock()
_MARKET_RADAR = MarketRadar()


def _send_market(chat_id):
    """Read the prepared card; the Telegram poller stays responsive."""
    if not _MARKET_REQUEST_LOCK.acquire(blocking=False):
        return
    try:
        threading.Thread(target=_market_worker, args=(chat_id,),
                         name="telegram-market-request", daemon=True).start()
    except Exception:
        _MARKET_REQUEST_LOCK.release()
        raise


def _market_worker(chat_id):
    try:
        if not _SHUTDOWN_REQUESTED.is_set():
            _send_text(chat_id, _MARKET_RADAR.card(int(time.time() * 1000)))
    finally:
        _MARKET_REQUEST_LOCK.release()


def _run_market_radar(stop):
    """Existing Telegram worker only; follow Scanner state read-only.

    No scanner/robot lifecycle commands. On pause, stop or unavailable
    authority, clear the radar rather than advertise an old live ranking.
    """
    source = None
    running = False
    next_probe = 0.0
    try:
        while not stop.is_set() and not _SHUTDOWN_REQUESTED.is_set():
            started = time.monotonic()
            if started >= next_probe:
                try:
                    running = (_scanner_request()["mode"] == "SCANNER_RUNNING")
                except Exception:
                    running = False
                next_probe = time.monotonic() + 5
            if not running:
                _MARKET_RADAR.clear()
                stop.wait(1)
                continue
            try:
                if source is None:
                    from bybit_api import PublicRadarSource
                    source = PublicRadarSource()
                _MARKET_RADAR.step(source.symbols, source.candles, source.recent_trades,
                                   now_ms=int(time.time() * 1000),
                                   monotonic_now=time.monotonic())
            except Exception:
                # A public-data failure never exits the Telegram/Scanner loop.
                stop.wait(5)
            stop.wait(max(0, RADAR_INTERVAL_SECONDS - (time.monotonic() - started)))
    finally:
        _MARKET_RADAR.clear()
        if source is not None:
            source.close()


def start_market_thread(stop):
    worker = threading.Thread(target=_run_market_radar, args=(stop,),
                              name="telegram-market-radar", daemon=True)
    worker.start()
    return worker


def _send_scanner_control(chat_id):
    """RUNNING pauses the live pass; anything else is the SCANNER runtime intent."""
    try:
        state = _scanner_request()
    except Exception:
        state = None
    if state is not None and state["mode"] == "SCANNER_RUNNING":
        try:
            # One dispatch only. Never retry a mutation after an ambiguous response.
            _scanner_request("pause")
        except Exception:
            _send_text(
                chat_id,
                "Команда сканера не подтверждена. Состояние будет проверено; автоматического повтора нет.",
            )
    else:
        # STOPPED/PAUSED, or an absent backend: the shared bootstrap prepares and routes.
        result = telegram_runtime_intent.execute("SCANNER")
        if not result.ok:
            _send_text(chat_id, telegram_runtime_intent.failure_text(result))
            refresh_command_menu()
            return
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


def _send_scanner_stop(chat_id):
    """Canonical SCANNER-scope shutdown; the independent helper may close this worker."""
    _send_text(chat_id, "⏹ Останавливаю сканер…")
    try:
        stop_robot_runtime.launch_detached(stop_robot_runtime.SCOPE_SCANNER, notify_chat=chat_id)
    except Exception as exc:
        print("[SCANNER STOP LAUNCH ERROR]", type(exc).__name__)
        _send_text(chat_id, "⚠ Остановка сканера не запущена.")


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
            f"Открытых позиций: {opened}"
            f"{robot_control_status_note(mode, recovery_status)}",
            reply_markup=build_robot_control_keyboard(mode, recovery_status),
        )
    except Exception:
        _send_text(chat_id, "Состояние робота и число открытых позиций недоступны.")


def _send_robot_start(chat_id):
    result = telegram_runtime_intent.execute("ROBOT")
    if result.ok:
        _send_robot_status(chat_id)
    else:
        _send_text(chat_id, telegram_runtime_intent.failure_text(result))


def _send_all(chat_id):
    result = telegram_runtime_intent.execute("ALL")
    if result.ok:
        _send_text(
            chat_id,
            f"✅ Всё готово · Робот {result.final.get('robot', '?')} "
            f"· Сканер {result.final.get('scanner', '?')}",
        )
    else:
        _send_text(chat_id, telegram_runtime_intent.failure_text(result))


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


def build_position_card_markup(view) -> dict[str, list[list[dict[str, str]]]]:
    """Read-only navigation for one position; invalid symbols fail closed to Back only."""
    symbol = str(getattr(view, "symbol", "")).strip().upper()
    timeframe = str(getattr(view, "chart_candle_minutes", "")).strip()
    if not (symbol and symbol.isalnum() and timeframe.isdigit()):
        return POSITIONS_BACK_MARKUP
    rows: list[list[dict[str, str]]] = []
    if symbol and symbol.isalnum() and timeframe.isdigit():
        rows.append([{
            "text": "📈 Open TradingView",
            "url": create_tradingview_url(symbol, timeframe),
        }])
    rows.append([{"text": "⬅️ К позициям", "callback_data": "robot:view:positions"}])
    return _with_signal_button({"inline_keyboard": rows}, getattr(getattr(view, "trade", None), "candidate_id", None))


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
    reply_markup = build_position_card_markup(view)
    if not view.is_robot:
        _send_text(chat_id, caption, reply_markup=reply_markup)
        return
    _send_chart_card(chat_id, view, candles, caption, reply_markup)


def _with_candles(view, now_ms: int | None = None):
    """One candle request per chart, shared by the position card and lifecycle posts."""

    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    # Closed lifecycle cards are historical: do not show the market movement
    # after execution as if it belonged to this trade.
    exit_ms = view.exit_time_ms if not view.is_open else None
    as_of_ms = min(now_ms, exit_ms) if exit_ms is not None else now_ms
    minutes = view.chart_candle_minutes
    # Include older same-campaign filled executions when the exchange candle
    # window can reach them; never fetch future or unrelated-symbol history.
    earliest = view.entry_time_ms
    if view.mirror_campaign:
        historical = [m.time_ms for m in view.markers
                      if m.filled and (earliest is None or m.time_ms < earliest)]
        if historical:
            earliest = min(historical)
    limit, entry_before_chart = chart_candle_limit(earliest, as_of_ms, minutes)
    candles = None
    try:
        import bybit_api

        if exit_ms is None:
            candles = bybit_api.get_candles(view.symbol, str(minutes), limit)
        else:
            candles = bybit_api.get_candles(
                view.symbol, str(minutes), limit, end_ms=as_of_ms,
            )
            # Do not trust a provider returning post-exit candles despite the
            # historical end bound; never silently redraw later price action.
            if candles is not None and "time" in candles.columns:
                candles = candles.loc[candles["time"] <= as_of_ms].copy()
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


def _send_chart_card(chat_id, view, candles, caption, reply_markup, *, require_chart=False) -> bool:
    """For MIRROR lifecycle, an absent PNG is NOT successful delivery."""

    # pyplot is not thread-safe and the chart path is per symbol: one render+send at a time.
    with _CHART_LOCK:
        try:
            chart_path = render_position_chart(view, candles)
        except Exception as exc:
            print("[POSITION CHART ERROR]", view.symbol, exc)
            if require_chart:
                return False
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
        except TelegramGatewayError:
            # An unknown delivery or rejection is not grounds for a second
            # immediate text send. The lifecycle cooldown owns retries.
            print("[POSITION CARD PHOTO GATEWAY ERROR]")
            return False
        except Exception as exc:
            print("[POSITION CARD PHOTO ERROR]", view.symbol, type(exc).__name__)
    if require_chart:
        return False
    return _delivered(_send_text(chat_id, caption, reply_markup=reply_markup))


def _send_lifecycle_post(chat_id, event, view) -> bool:
    view, candles = _with_candles(view)
    caption = format_lifecycle_caption(event, view)
    return _send_chart_card(
        chat_id, view, candles, caption,
        _with_signal_button(build_lifecycle_keyboard(), getattr(getattr(view, "trade", None), "candidate_id", None)),
        require_chart=view.mirror_campaign,
    )


def poll_lifecycle_once(now_ms: int | None = None) -> None:
    chat_id = _owner_id()
    if not chat_id:
        return
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    state = load_lifecycle_state(LIFECYCLE_STATE_FILE, now_ms)
    if now_ms < state.retry_after_ms:
        return  # Durable suppression after restart; no replay during cooldown.
    before_floors = (state.opened_floor, state.closed_floor)
    with _robot_store() as store:
        events = collect_new_lifecycle_events(store, state)
        pending = [
            (event, load_position_view(store, event.symbol, trade_id=event.trade_id))
            for event in events
        ]
    if before_floors != (state.opened_floor, state.closed_floor):
        # Persist the validated cursor before any further notifications.
        save_lifecycle_state(LIFECYCLE_STATE_FILE, state)
    blocked = set()
    for event, view in pending:
        # The trade may close between event selection and this read. Never
        # render a durable CLOSED view under a stale OPENED notification.
        # Mark only that obsolete OPENED notification; the CLOSED event remains
        # eligible (including on the next poll after a concurrent close).
        if event.kind == EVENT_OPENED and view is not None and not view.is_open:
            mark_notified(state, event)
            save_lifecycle_state(LIFECYCLE_STATE_FILE, state)
            continue
        # "закрыта" never goes out before a failed "открыта" of the same trade.
        if event.trade_id in blocked:
            continue
        try:
            sent = view is not None and _send_lifecycle_post(chat_id, event, view)
        except Exception as exc:
            print("[LIFECYCLE SEND ERROR]", event.kind, event.trade_id, exc)
            sent = False
        if not sent:
            state.retry_after_ms = now_ms + LIFECYCLE_RETRY_COOLDOWN_MS
            save_lifecycle_state(LIFECYCLE_STATE_FILE, state)
            print("[LIFECYCLE] delivery deferred; cooldown_seconds=300")
            return  # Stop the batch on first failure; preserve pending IDs.
        state.retry_after_ms = 0
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


_TELEGRAM_METHOD_ERROR_COUNTS: dict[tuple[str, str], int] = {}
_TELEGRAM_METHOD_NEXT_REPORT = 0.0


def _record_telegram_method_error(method: str, code) -> None:
    """Bounded per-method status counters; never log payloads or identities."""
    global _TELEGRAM_METHOD_NEXT_REPORT
    status = str(code) if type(code) is int and 400 <= code <= 599 else "unknown"
    key = (method, status)
    _TELEGRAM_METHOD_ERROR_COUNTS[key] = _TELEGRAM_METHOD_ERROR_COUNTS.get(key, 0) + 1
    now = time.monotonic()
    if now >= _TELEGRAM_METHOD_NEXT_REPORT:
        summary = ", ".join(
            f"{name}:{status}={count}"
            for (name, status), count in sorted(_TELEGRAM_METHOD_ERROR_COUNTS.items())
        )
        print("[TELEGRAM METHOD ERRORS]", summary)
        _TELEGRAM_METHOD_ERROR_COUNTS.clear()
        _TELEGRAM_METHOD_NEXT_REPORT = now + 60


def _telegram_request(method: str, **params):
    import telegram_gateway_client
    try:
        if telegram_gateway_client.configured():
            if method == "getUpdates":
                result = telegram_gateway_client.get_updates(**params)
            else:
                result = telegram_gateway_client.bot_method(method, **params)
        else:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/{method}"
            response = requests.get(url, params=params, timeout=40)
            result = response.json()
    except Exception:
        _record_telegram_method_error(method, None)
        raise
    if isinstance(result, dict) and result.get("ok") is False:
        _record_telegram_method_error(method, result.get("error_code"))
    return result


def _telegram_backoff_seconds(result, *, default=3) -> int:
    """Bound an API retry_after; no request/data retry of any trading command."""
    if not isinstance(result, dict) or result.get("error_code") != 429:
        return default
    params = result.get("parameters")
    retry = params.get("retry_after") if isinstance(params, dict) else None
    if type(retry) is int and retry > 0:
        return min(max(default, retry), 300)
    return default


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


MONITOR_CANDIDATE_PREFIX = "monitor:c:"
SOURCE_SIGNAL_PREFIX = "monitor:s:"
MONITOR_TOKEN_HEX_LENGTH = 16


def _candidate_callback_token(candidate_id: str) -> str:
    import hashlib

    return hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:MONITOR_TOKEN_HEX_LENGTH]


def _resolve_candidate_callback_token(
    token: str, records: tuple[RobotCandidateRecord, ...],
) -> RobotCandidateRecord | None:
    matches = [record for record in records if _candidate_callback_token(record.candidate_id) == token]
    return matches[0] if len(matches) == 1 else None


def build_candidate_keyboard(records: tuple[RobotCandidateRecord, ...]):
    rows = [
        [
            {
                "text": _candidate_button_label(record),
                "callback_data": MONITOR_CANDIDATE_PREFIX + _candidate_callback_token(record.candidate_id),
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


def _signal_button(candidate_id: str | None) -> dict[str, str] | None:
    """Opaque, bounded callback. The candidate id stays outside Telegram payloads."""
    if not candidate_id:
        return None
    return {
        "text": "↩️ К сигналу",
        "callback_data": SOURCE_SIGNAL_PREFIX + _candidate_callback_token(str(candidate_id)),
    }


def _with_signal_button(markup: dict, candidate_id: str | None) -> dict:
    rows = list(markup.get("inline_keyboard", []))
    button = _signal_button(candidate_id)
    if button:
        rows.insert(0, [button])
    return {"inline_keyboard": rows}


def _candidate_view(record: RobotCandidateRecord) -> PositionView:
    snapshot = record.signal_snapshot
    state = record.robot_state or {}
    return PositionView(
        symbol=record.symbol.value,
        direction=str(state.get("direction") or snapshot.get("direction") or "—"),
        is_open=False, quantity=None, average_entry=None, stop_price=None,
        take_price=None,
        pattern=str(snapshot.get("pattern") or state.get("pattern") or "—"),
        signal_snapshot=snapshot,
        chart_candle_minutes=signal_chart_candle_minutes(snapshot),
    )


def _load_candidate_candles(record: RobotCandidateRecord, *, source: bool = False):
    """One read-only Bybit request. Historical source chart never contains future candles."""
    import bybit_api

    view = _candidate_view(record)
    interval = view.chart_candle_minutes
    if source:
        try:
            as_of = int(record.signal_snapshot["decision_time_ms"])
        except (KeyError, TypeError, ValueError):
            return view, None, "Исходный график: время сигнала не сохранено"
        if as_of <= 0:
            return view, None, "Исходный график: время сигнала недостоверно"
        df = bybit_api.get_candles(view.symbol, str(interval), 120, end_ms=as_of)
        if df is None or df.empty:
            return view, None, "Исторические свечи сигнала недоступны"
        # Source-time invariant: a bar is drawable only if it closed by decision_time.
        df = df.loc[df["time"] + interval * 60_000 <= as_of].copy()
        if df.empty:
            return view, None, "Свечи на момент сигнала не подтверждены"
        return view, df, ("Сохранённая геометрия сигнала · "
                           + datetime.fromtimestamp(as_of / 1000, timezone.utc).strftime("%d.%m %H:%M UTC"))
    df = bybit_api.get_candles(view.symbol, str(interval), 120 if interval != 1 else 300)
    if df is None or df.empty:
        return view, None, "Актуальные свечи недоступны"
    last_open = int(df["time"].iloc[-1])
    now = int(time.time() * 1000)
    last_close = last_open + interval * 60_000
    stale = last_open > now + 60_000 or now - last_close > interval * 2 * 60_000
    close = float(df["close"].iloc[-1])
    checked_at = datetime.fromtimestamp(last_open / 1000, timezone.utc).strftime("%d.%m %H:%M UTC")
    return view, df, (f"Цена: {close:.8g} · свеча {checked_at}" + (" · ДАННЫЕ УСТАРЕЛИ" if stale else ""))


SIGNAL_REPOST_MARK = "🔁 ДУБЛИРОВАНИЕ"
RESTORED_SIGNAL_MARK = "♻️ ВОССТАНОВЛЕННЫЙ СИГНАЛ (не оригинал)"
TELEGRAM_CAPTION_LIMIT = 1024


def _signal_archive_ids(record: RobotCandidateRecord) -> list[str]:
    """Exact ids under which the Scanner stored this candidate's original signal.

    The Robot candidate id, or the Box plan id it was handed off from. Never a ticker.
    """
    ids = [record.candidate_id]
    source_id = record.signal_snapshot.get("source_box_candidate_id")
    if source_id:
        ids.append(str(source_id))
        try:
            # The Box scanner archives under the callback-safe handle of its plan.
            ids.append(box_plan_admission_handle(str(source_id)))
        except ValueError:
            pass
    return ids


def _load_archived_candidate_source(record: RobotCandidateRecord) -> dict | None:
    """Exact candidate archive first, then the Scanner's same-formation origin.

    A Scanner writes origin:<symbol>:<timeframe>:<formation_id> alongside
    source-original.  Older/partially archived candidates may lack their own
    copy.  Never search by ticker alone or accept another pattern's origin.
    """
    original = signal_archive.load_original_signal(_signal_archive_ids(record))
    if original is not None:
        return original
    snapshot = record.signal_snapshot
    formation_id = snapshot.get("scanner_formation_id")
    timeframe = snapshot.get("timeframe")
    pattern = snapshot.get("pattern")
    if (not isinstance(formation_id, str) or not formation_id
            or len(formation_id) > 256
            or not isinstance(pattern, str) or not pattern
            or str(snapshot.get("symbol", "")) != record.symbol.value
            or str(timeframe or "") not in {"1", "5"}):
        return None
    origin_id = f"origin:{record.symbol.value}:{timeframe}:{formation_id}"
    original = signal_archive.load_original_signal([origin_id])
    if (original is None
            or original.get("candidate_id") != origin_id
            or original.get("symbol") != record.symbol.value
            or str(original.get("timeframe")) != str(timeframe)
            or original.get("pattern") != pattern):
        return None
    return original


def _format_signal_time(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")


def _repost_keyboard(symbol: str, timeframe: str, signal_id: str | None = None) -> dict:
    """Repost the exact source, without inventing an Editor route for a PNG-only archive."""
    # _repost_editor_source_id resolves lineage but can intentionally fall back
    # to an image-only candidate/archive ID. A link must carry validated frozen
    # geometry of this specific symbol/timeframe, never just a ticker.
    frozen = (signal_archive.load_frozen_signal_geometry(signal_id)
              if isinstance(signal_id, str) and signal_id else None)
    exact_source = bool(
        isinstance(frozen, Mapping)
        and frozen.get("signal_id") == signal_id
        and frozen.get("symbol") == symbol
        and str(frozen.get("timeframe")) == str(timeframe)
    )
    try:
        rows = build_tradingview_keyboard(
            symbol, timeframe, include_review_actions=True,
            robot_candidate_id=None, robot_status_button=False,
            signal_id=signal_id if exact_source else None,
            editor_available=exact_source,
        )["inline_keyboard"]
    except Exception as exc:
        print("[SIGNAL REPOST NAV ERROR]", symbol, exc)
        rows = []
    rows.append([{"text": "⬅️ К кандидатам", "callback_data": "monitor:list"}])
    return {"inline_keyboard": rows}


def _repost_editor_source_id(original: Mapping) -> str | None:
    """Prefer the original immutable Editor history, never a ticker match.

    The live Scanner card and the later Robot candidate repost have different
    archive IDs. Direct Scanner-recorded lineage, or a unique integrity-checked
    legacy frozen source with identical image/text/pattern and near send time,
    may point to the original Editor history. Pre-lineage candidate archives
    with their own validated frozen geometry retain their own identity.
    If neither exists, retain the archive identity for provenance; the
    keyboard independently hides Editor unless the exact geometry validates.
    """
    own_id = str(original.get("candidate_id") or "").strip() or None
    linked = original.get("source_formation_ids")
    if isinstance(linked, list):
        for source_id in linked:
            if not (isinstance(source_id, str)
                    and source_id.startswith("source-original:")
                    and len(source_id) == len("source-original:") + 24
                    and all(ch in "0123456789abcdef" for ch in source_id[16:])):
                continue
            source = signal_archive.load_original_signal([source_id])
            if source is None:
                continue
            match_fields = ("symbol", "timeframe", "pattern", "text", "image_sha256")
            if any(source.get(field) != original.get(field) for field in match_fields):
                continue
            frozen = signal_archive.load_frozen_signal_geometry(source_id)
            if (frozen is not None and frozen.get("signal_id") == source_id
                    and frozen.get("symbol") == original.get("symbol")
                    and str(frozen.get("timeframe")) == str(original.get("timeframe"))):
                return source_id
    # Pre-lineage archives can be unlinked despite containing an intact
    # source-original from the same immutable Telegram signal. Search only
    # when no lineage was recorded and this record lacks its own frozen rays.
    if (not linked and own_id and not own_id.startswith("source-original:")
            and signal_archive.load_frozen_signal_geometry(own_id) is None):
        unique = signal_archive.find_unique_legacy_frozen_source_id(original)
        if unique is not None:
            return unique
    if own_id:
        return own_id
    return None


def _repost_caption(original: Mapping) -> str:
    head = f"{SIGNAL_REPOST_MARK}\nОригинал отправлен: {_format_signal_time(original['sent_at_ms'])}\n\n"
    body = str(original.get("text") or "").strip()
    room = TELEGRAM_CAPTION_LIMIT - len(head)
    if len(body) > room:
        body = body[: max(room - 1, 0)] + "…"
    return head + body


def _repost_original_signal(chat_id, original: Mapping) -> bool:
    """New message at the end of the feed with the archived original image and text.

    Reuses the Telegram file_id when it still works, otherwise the archived PNG bytes.
    The original message is never edited or deleted.
    """
    caption = _repost_caption(original)
    markup = _repost_keyboard(
        str(original.get("symbol", "")), str(original.get("timeframe", "")),
        _repost_editor_source_id(original),
    )
    file_id = original.get("photo_file_id")
    if file_id:
        try:
            if _delivered(telegram_bot.send_photo_by_file_id(
                    config.TELEGRAM_TOKEN, chat_id, file_id, caption=caption, reply_markup=markup)):
                return True
        except Exception as exc:
            print("[SIGNAL REPOST FILE_ID ERROR]", original.get("symbol"), exc)
    try:
        if _delivered(telegram_bot.send_photo(
                config.TELEGRAM_TOKEN, chat_id, original["image_path"],
                caption=caption, reply_markup=markup)):
            return True
    except Exception as exc:
        print("[SIGNAL REPOST PHOTO ERROR]", original.get("symbol"), exc)
    return False


def _send_source_signal_card(chat_id, token: str) -> None:
    # Closed candidates are also needed for OPENED/CLOSED trade posts.
    with _robot_store() as store:
        record = _resolve_candidate_callback_token(
            token, store.load_robot_candidates(PAPER_ACCOUNT_ID)
        )
    if record is None:
        _send_text(chat_id, "Исходный сигнал не найден или ссылка неоднозначна.")
        return
    symbol = record.symbol.value
    original = _load_archived_candidate_source(record)
    if original is not None:
        if _repost_original_signal(chat_id, original):
            return
        # The archived record is intact but Telegram would not take the image.
        _send_text(
            chat_id,
            f"{SIGNAL_REPOST_MARK}\nОригинал отправлен: {_format_signal_time(original['sent_at_ms'])}\n\n"
            f"{original.get('text', '')}\n\n"
            "⚠️ Изображение оригинала не удалось отправить повторно.",
            reply_markup=_repost_keyboard(
                symbol, str(original.get("timeframe", "")), _repost_editor_source_id(original),
            ),
        )
        return
    # No archived original (a candidate created before the archive existed, or it was
    # lost). Reconstruct from the immutable snapshot only when its signal time is
    # proven; never substitute the current market and never present it as the original.
    unavailable = (
        f"ℹ️ Оригинал сигнала по {symbol} не сохранён: кандидат создан до включения архива "
        "сигналов или запись недоступна. Показать его точную копию нельзя, "
        "график текущего рынка не подставляю."
    )
    try:
        view, candles, context = _load_candidate_candles(record, source=True)
    except Exception as exc:
        print("[SOURCE SIGNAL ERROR]", symbol, exc)
        _send_text(chat_id, unavailable)
        return
    if candles is None:
        _send_text(chat_id, unavailable + "\n" + context)
        return
    caption = (f"{RESTORED_SIGNAL_MARK}\n{symbol} · {record.signal_snapshot.get('pattern', '—')}\n"
               f"{context}\nТочная копия исходного сообщения не сохранена: "
               "график воссоздан из сохранённого снимка, только закрытые свечи на момент сигнала.")
    _send_chart_card(
        chat_id, view, candles, caption,
        {"inline_keyboard": [[{"text": "⬅️ К кандидатам", "callback_data": "monitor:list"}]]},
    )


def _process_mirror_source_callback(callback_query) -> bool:
    """Repost the exact source-pattern archive or the frozen MIRROR origin.

    Never reconstruct a historic pattern from current candles. The fallback is
    explicitly labelled as a MIRROR level chart, not the missing original.
    """
    data = str(callback_query.get("data") or "")
    mirror_prefix, signal_prefix = "mirror:source:", "signal:source:"
    is_mirror = data.startswith(mirror_prefix)
    if not (is_mirror or data.startswith(signal_prefix)):
        return False
    token = data[len(mirror_prefix if is_mirror else signal_prefix):]
    if len(token) != 24 or any(char not in "0123456789abcdef" for char in token):
        return False
    callback_id = callback_query.get("id")
    if not _is_owner((callback_query.get("from") or {}).get("id")):
        _answer_callback(callback_id, "Недостаточно прав")
        return True
    chat_id = (((callback_query.get("message") or {}).get("chat") or {}).get("id"))
    if chat_id is None or str(chat_id) != _owner_id():
        _answer_callback(callback_id, "Только личный чат владельца")
        return True
    _answer_callback(callback_id)
    if not is_mirror:
        original = signal_archive.load_original_signal([f"source-original:{token}"])
        if original is None:
            _send_text(chat_id, "Исходная карточка сигнала недоступна: архив не найден.")
        elif not _repost_original_signal(chat_id, original):
            _send_text(chat_id, "Не удалось отправить сохранённый график исходного сигнала.")
        return True
    mirror = signal_archive.load_original_signal([f"mirror-origin:{token}"])
    if mirror is None:
        _send_text(chat_id, "Исходная MIRROR-карточка недоступна: архив не найден.")
        return True
    parent_ids = mirror.get("source_formation_ids") or []
    original = signal_archive.load_original_signal(parent_ids)
    if original is not None:
        if _repost_original_signal(chat_id, original):
            return True
        _send_text(chat_id, "Исходный паттерн найден, но его график не удалось отправить.")
        return True
    if parent_ids:
        # An established parent lineage is not an archived parent signal.
        # Never silently present the MIRROR campaign as that missing pattern.
        _send_text(
            chat_id,
            "⚠️ Исходная карточка паттерна не сохранена. "
            "Ниже доступна только архивная MIRROR-карточка этой кампании, "
            "не оригинал паттерна.",
        )
    # A bare level has no source pattern. With an unavailable parent,
    # the following first-card fallback is explicitly disclosed above.
    # Never substitute a newer same-ticker observation.
    first_id = mirror.get("source_campaign_first_id")
    first = signal_archive.load_original_signal([first_id]) if first_id else None
    if first is not None:
        if _repost_original_signal(chat_id, first):
            return True
        _send_text(chat_id, "Первую карточку MIRROR-кампании не удалось отправить.")
        return True
    if not parent_ids:
        _send_text(chat_id, "Первая карточка MIRROR-кампании не сохранена. "
                            "Показываю архивный график этого события без подмены источника.")
    if not _repost_original_signal(chat_id, mirror):
        _send_text(chat_id, "Не удалось отправить архивный MIRROR-график.")
    return True


def parse_monitor_callback(data: str):
    text = str(data)
    if text == "monitor:list":
        return {"action": "list"}
    if text.startswith(SOURCE_SIGNAL_PREFIX):
        token = text[len(SOURCE_SIGNAL_PREFIX):]
        if len(token) == MONITOR_TOKEN_HEX_LENGTH and all(c in "0123456789abcdef" for c in token):
            return {"action": "source", "token": token}
    if text.startswith(MONITOR_CANDIDATE_PREFIX):
        token = text[len(MONITOR_CANDIDATE_PREFIX):]
        if len(token) == MONITOR_TOKEN_HEX_LENGTH and all(char in "0123456789abcdef" for char in token):
            return {"action": "candidate", "token": token}
    legacy_prefix = "monitor:candidate:"
    if text.startswith(legacy_prefix):
        candidate_id = text[len(legacy_prefix):]
        if candidate_id:
            return {"action": "candidate", "candidate_id": candidate_id}
    return None


def _require_monitoring_delivery(response, operation: str) -> None:
    if not isinstance(response, Mapping) or response.get("ok") is not True:
        raise RuntimeError(f"{operation} failed: {response}")


def _send_candidate_list(chat_id) -> None:
    records = _load_active_candidates()
    if not records:
        response = telegram_bot.send_message(
            config.TELEGRAM_TOKEN,
            chat_id,
            "🤖 Мониторинг\n\nАктивных кандидатов сейчас нет.",
        )
        _require_monitoring_delivery(response, "candidate list sendMessage")
        return
    response = telegram_bot.send_message(
        config.TELEGRAM_TOKEN,
        chat_id,
        f"🤖 Мониторинг\n\nАктивных кандидатов: {len(records)}\nВыберите тикер:",
        reply_markup=build_candidate_keyboard(records),
    )
    _require_monitoring_delivery(response, "candidate list sendMessage")


def _send_candidate_card(chat_id, candidate_id: str) -> None:
    with SQLiteStore.open(DB_PATH) as store:
        record = store.get_robot_candidate(candidate_id)
    if record is None or record.status != "APPROVED":
        response = telegram_bot.send_message(
            config.TELEGRAM_TOKEN,
            chat_id,
            "Кандидат больше не активен. Обновите список мониторинга.",
            reply_markup={
                "inline_keyboard": [[{"text": "🔄 Мониторинг", "callback_data": "monitor:list"}]]
            },
        )
        _require_monitoring_delivery(response, "candidate stale sendMessage")
        return
    markup = {"inline_keyboard": [
        [{"text": "🔄 Обновить график",
          "callback_data": MONITOR_CANDIDATE_PREFIX + _candidate_callback_token(record.candidate_id)}],
        [{"text": "⬅️ К кандидатам", "callback_data": "monitor:list"}],
    ]}
    markup = _with_signal_button(markup, record.candidate_id)
    caption = format_candidate_card(record)
    try:
        view, candles, context = _load_candidate_candles(record)
        caption += "\n" + context
        if candles is not None:
            if _send_chart_card(chat_id, view, candles, caption, markup):
                return
            raise RuntimeError("candidate card delivery failed")
    except Exception as exc:
        print("[CANDIDATE CHART ERROR]", record.symbol.value, exc)
        caption += "\nГрафик недоступен"
    response = telegram_bot.send_message(
        config.TELEGRAM_TOKEN, chat_id, caption, reply_markup=markup,
    )
    _require_monitoring_delivery(response, "candidate card sendMessage")


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
    if str(chat_id) != _owner_id():
        _answer_callback(callback_query.get("id"), "Только личный чат владельца")
        return True
    _answer_callback(callback_query.get("id"))
    if parsed["action"] == "list":
        _send_candidate_list(chat_id)
    elif parsed["action"] == "source":
        _send_source_signal_card(chat_id, parsed["token"])
    elif "candidate_id" in parsed:
        _send_candidate_card(chat_id, parsed["candidate_id"])
    else:
        records = _load_active_candidates()
        record = _resolve_candidate_callback_token(parsed["token"], records)
        if record is None:
            _send_candidate_list(chat_id)
        else:
            _send_candidate_card(chat_id, record.candidate_id)
    return True


def _process_message(message) -> bool:
    from_user = message.get("from") or {}
    if not _is_owner(from_user.get("id")):
        return False
    text = str(message.get("text", "")).strip()
    command = text.split("@", 1)[0]
    handlers = {
        "/market": _send_market,
        "Рынок": _send_market,
        "/terminal": _send_workspace,
        "/scanner": _send_scanner_control,
        "/scanner_stop": _send_scanner_stop,
        "/robot": _send_robot_status,
        "/robot_start": _send_robot_start,
        "/all": _send_all,
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


def _signal_has_button(message, data: str) -> bool:
    markup = (message or {}).get("reply_markup") or {}
    return any(
        isinstance(button, dict) and button.get("callback_data") == data
        for row in markup.get("inline_keyboard") or []
        for button in row or []
    )


def _process_metascalp_callback(callback_query) -> bool:
    """TG-METASCALP-2: owner tap opens a new MetaScalp order book (no retry)."""
    data = callback_query.get("data", "")
    symbol = metascalp_bridge.parse_callback(data)
    if symbol is None:
        return False
    callback_id = callback_query.get("id")
    if not _is_owner((callback_query.get("from") or {}).get("id")):
        _answer_callback(callback_id, "Недостаточно прав")
        return True
    # The symbol must come from the signal card's own button.
    if not symbol or not _signal_has_button(callback_query.get("message"), data):
        _answer_callback(callback_id, "Некорректный тикер сигнала")
        return True
    try:
        text = metascalp_bridge.open_order_book(symbol)
    except metascalp_bridge.MetaScalpError as exc:
        text = str(exc)
    except Exception as exc:
        print("[METASCALP ERROR]", exc)
        text = "MetaScalp: внутренняя ошибка"
    _answer_callback(callback_id, text)
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
_menu_commands_retry_after = 0.0
_menu_button_check_after = 0.0
MENU_BUTTON_CHECK_INTERVAL_SECONDS = 300


def refresh_command_menu() -> None:
    global _published_commands, _menu_commands_retry_after
    if time.monotonic() < _menu_commands_retry_after:
        return
    try:
        state = _scanner_request()
        scanner_label = SCANNER_ACTIONS[state["mode"]][0]
    except Exception:
        scanner_label = f"{SCANNER_EMOJI} Сканер: состояние недоступно"
    commands = json.dumps(
        [
            {"command": "positions", "description": "Все открытые позиции"},
            {"command": "monitoring", "description": "Мониторинг кандидатов"},
            {"command": "robot", "description": "Робот"},
            {"command": "robot_start", "description": "▶ Запустить робота"},
            {"command": "all", "description": "▶ Запустить всё"},
            {"command": "scanner", "description": scanner_label},
            {"command": "scanner_stop", "description": "⏹ Остановить сканер"},
            {"command": "terminal", "description": "Терминал"},
            {"command": "market", "description": "Рынок"},
        ],
        ensure_ascii=False,
    )
    # Cache only successful publication; a failed menu must not starve polling.
    if commands != _published_commands:
        try:
            response = _telegram_request("setMyCommands", commands=commands)
        except Exception:
            _menu_commands_retry_after = time.monotonic() + 60
            return
        if not response.get("ok"):
            _menu_commands_retry_after = time.monotonic() + _telegram_backoff_seconds(
                response, default=60
            )
            return
        _published_commands = commands


def _ensure_commands_menu_button(*, force: bool = False) -> None:
    global _menu_button_check_after
    owner = _owner_id()
    if not owner:
        return
    now = time.monotonic()
    if not force and now < _menu_button_check_after:
        return
    # Schedule the next check before a call that might fail or return 429.
    _menu_button_check_after = now + MENU_BUTTON_CHECK_INTERVAL_SECONDS
    if not force:
        try:
            current = _telegram_request("getChatMenuButton", chat_id=owner)
        except Exception:
            return
        if not current.get("ok"):
            _menu_button_check_after = max(
                _menu_button_check_after,
                now + _telegram_backoff_seconds(current, default=60),
            )
            return
        if (current.get("result") or {}).get("type") == "commands":
            return
    try:
        response = _telegram_request(
            "setChatMenuButton",
            chat_id=owner,
            menu_button=json.dumps({"type": "commands"}),
        )
    except Exception:
        return
    if not response.get("ok"):
        _menu_button_check_after = max(
            _menu_button_check_after,
            now + _telegram_backoff_seconds(response, default=60),
        )


def _refresh_owner_menu_surface() -> None:
    """Republish changed commands; verify button only on the throttled cadence."""
    refresh_command_menu()
    _ensure_commands_menu_button()


def configure_monitoring_menu() -> None:
    refresh_command_menu()
    _ensure_commands_menu_button()


HEALTH_COMPONENT = "telegram_monitoring"
HEALTH_PORT_ENV = "BYBITSCANNER_TELEGRAM_MONITORING_PORT"
DEFAULT_HEALTH_PORT = 8766
INITIAL_POLL_TIMEOUT = 0
LONG_POLL_TIMEOUT = 30
_POLLING_READY = threading.Event()
_SHUTDOWN_REQUESTED = threading.Event()
_DATABASE_IDENTITY: str | None = None


class TelegramUpdateConflict(RuntimeError):
    """getUpdates 409: another consumer owns this bot's update stream."""


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        if self.path.split("?", 1)[0] != "/health":
            self.send_error(404)
            return
        ready = _POLLING_READY.is_set()
        body = json.dumps({"component": HEALTH_COMPONENT,
                           "status": "ready" if ready else "not_ready",
                           "database_identity": _DATABASE_IDENTITY}).encode("ascii")
        self.send_response(200 if ready else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - http.server API
        """Identity-checked graceful exit request from the canonical shutdown helper."""
        if self.path.split("?", 1)[0] != "/shutdown":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else None
            if not isinstance(payload, dict) or set(payload) != {"database_identity"}:
                raise ValueError("invalid shutdown payload")
            claimed = payload["database_identity"]
            if not isinstance(claimed, str) or not claimed:
                raise ValueError("invalid shutdown identity")
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"ok": False, "error": "invalid_shutdown"})
            return
        if not isinstance(_DATABASE_IDENTITY, str) or claimed != _DATABASE_IDENTITY:
            self._json(409, {"ok": False, "error": "database_identity_mismatch"})
            return
        self._json(200, {"ok": True, "shutdown": "scheduled"})
        _SHUTDOWN_REQUESTED.set()

    def _json(self, status, payload):
        body = json.dumps(payload).encode("ascii")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - keep the console quiet
        pass


class _ExclusiveHealthServer(ThreadingHTTPServer):
    # SO_REUSEADDR on Windows lets a second process bind the same port; the
    # listener is the singleton, so the bind must be exclusive there. On Linux it
    # only permits rebinding over TIME_WAIT leftovers of the previous listener
    # (health probes close from the server side) and never a second live
    # listener; without it a restart within ~60 s of a stop fails with
    # "already owns" although no worker is running.
    allow_reuse_address = sys.platform.startswith("linux")
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def health_port() -> int:
    return int(os.environ.get(HEALTH_PORT_ENV) or DEFAULT_HEALTH_PORT)


def acquire_worker_singleton(port: int | None = None):
    """Bind the localhost health listener; ``None`` means another worker owns the host."""
    try:
        server = _ExclusiveHealthServer(("127.0.0.1", health_port() if port is None else port),
                                        _HealthHandler)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, name="telegram-monitoring-health",
                     daemon=True).start()
    return server


def poll_updates_once(offset):
    """One getUpdates round; readiness follows proven update-stream ownership."""
    params = {
        "timeout": LONG_POLL_TIMEOUT if _POLLING_READY.is_set() else INITIAL_POLL_TIMEOUT,
        "allowed_updates": json.dumps(["callback_query", "message"]),
    }
    if offset is not None:
        params["offset"] = offset
    try:
        result = _telegram_request("getUpdates", **params)
    except Exception:
        _POLLING_READY.clear()
        raise
    if not result.get("ok"):
        _POLLING_READY.clear()
        if result.get("error_code") == 409:
            raise TelegramUpdateConflict(result.get("description") or "getUpdates conflict")
        delay = _telegram_backoff_seconds(result)
        print("[MONITORING TELEGRAM POLL] status=",
              result.get("error_code") if type(result.get("error_code")) is int else "unknown",
              "retry_seconds=", delay)
        time.sleep(delay)
        return offset
    _POLLING_READY.set()

    for update in result.get("result", []):
        # The ordinary worker is only an untrusted courier. It cannot sign
        # approval grants or invoke the owner monolith.
        from tools.telegram_release_inbox import relay
        release_relay = relay(update)
        update_id = update.get("update_id")
        if update_id is not None:
            offset = update_id + 1
            _save_offset(offset)
        if release_relay is not None:
            callback_id = (update.get("callback_query") or {}).get("id")
            _answer_callback(callback_id, "Передано на проверку" if release_relay
                             else "Подтверждение не доказано")
            continue

        callback_query = update.get("callback_query")
        if callback_query:
            # Private metadata for a non-sensitive PAPER close audit trail.
            # The immutable callback id is used only for backend idempotence;
            # never print it, chat/user IDs or the full update payload.
            if str(callback_query.get("data") or "") in (
                "robot:cmd:paper_close_all",
                "robot:cmd:paper_close_all_confirm",
            ):
                callback_query = dict(callback_query)
                callback_query["_paper_monitor_update_id"] = update_id
            if not (_process_metascalp_callback(callback_query)
                    or _process_positions_callback(callback_query)
                    or _process_mirror_source_callback(callback_query)
                    or _process_monitor_callback(callback_query)):
                import telegram_review

                telegram_review._process_callback(callback_query)
            callback_user_id = (callback_query.get("from") or {}).get("id")
            callback_chat_id = (
                ((callback_query.get("message") or {}).get("chat") or {}).get("id")
            )
            if _is_owner(callback_user_id) and str(callback_chat_id) == _owner_id():
                _refresh_owner_menu_surface()
            continue

        message = update.get("message")
        if message:
            _process_message(message)
            message_user_id = (message.get("from") or {}).get("id")
            message_chat_id = (message.get("chat") or {}).get("id")
            if _is_owner(message_user_id) and str(message_chat_id) == _owner_id():
                _refresh_owner_menu_surface()
    return offset


def _release_worker_singleton(server) -> None:
    _POLLING_READY.clear()
    server.shutdown()
    server.server_close()


def database_identity() -> str:
    """This worker's PAPER DB authority, exactly as SQLiteStore defines it."""
    with _robot_store() as store:
        return store.database_identity


def run() -> int:
    global _DATABASE_IDENTITY
    try:
        _DATABASE_IDENTITY = database_identity()
    except Exception as exc:
        print(f"Telegram monitoring cannot attach to PAPER DB {DB_PATH}: {exc}")
        return 1
    server = acquire_worker_singleton()
    if server is None:
        print(f"Telegram monitoring worker already owns 127.0.0.1:{health_port()}; "
              "not starting a second getUpdates consumer.")
        return 1
    print("=" * 60)
    print("BybitScanner Telegram Monitoring Listener")
    print(f"DB: {DB_PATH}")
    print(f"Health: http://127.0.0.1:{server.server_address[1]}/health")
    print("=" * 60)
    offset = _load_offset()
    owned = False
    radar_stop = threading.Event()

    while not _SHUTDOWN_REQUESTED.is_set():
        try:
            if owned:
                # Local scanner state may change outside Telegram. The menu
                # button probe is throttled, and commands publish only on change.
                refresh_command_menu()
                _ensure_commands_menu_button()
            offset = poll_updates_once(offset)
            if not owned and _POLLING_READY.is_set():
                # Menu and lifecycle posts only after getUpdates proved stream ownership.
                owned = True
                start_lifecycle_thread()
                start_market_thread(radar_stop)
                configure_monitoring_menu()
        except TelegramUpdateConflict as exc:
            print("[MONITORING TELEGRAM CONFLICT] another getUpdates consumer is active:", exc)
            radar_stop.set()
            _release_worker_singleton(server)
            return 1
        except KeyboardInterrupt:
            print()
            print("Monitoring listener stopped.")
            break
        except Exception as exc:
            print("[MONITORING LOOP ERROR]", exc)
            _SHUTDOWN_REQUESTED.wait(3)
    if _SHUTDOWN_REQUESTED.is_set():
        print("Monitoring listener stopped by canonical runtime shutdown.")
    radar_stop.set()
    _release_worker_singleton(server)
    return 0

if __name__ == "__main__":
    sys.exit(run())
