"""Minimal Telegram presentation layer for Robot v0.1.

This module is presentation-only. It formats already-authoritative Robot
lifecycle/trade projections into Telegram text and inline-keyboard payloads.
It performs no trading decisions, execution, persistence, or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

VIEW_FEED = "feed"
VIEW_POSITIONS = "positions"
VIEW_WATCHING = "watching"

EVENT_OBSERVATION = "OBSERVATION"
EVENT_OPENED = "OPENED"
EVENT_CLOSED = "CLOSED"


class RobotTelegramProjectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RobotFeedCard:
    event_type: str
    title: str
    text: str
    chart: Mapping[str, Any] | None
    reply_markup: Mapping[str, Any]


def build_main_menu_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [{"text": "Терминал", "callback_data": "menu:terminal"}],
            [{"text": "🤖 Робот", "callback_data": "robot:view:feed"}],
            [{"text": "Запуск сканера", "callback_data": "menu:scanner"}],
            [{"text": "Статистика", "callback_data": "menu:statistics"}],
        ]
    }


def build_robot_tab_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [
                {"text": "Все позиции", "callback_data": "robot:view:positions"},
                {"text": "Под наблюдением", "callback_data": "robot:view:watching"},
            ],
            [{"text": "Обновить", "callback_data": "robot:view:feed"}],
        ]
    }


def parse_robot_view_callback(data: Any) -> str | None:
    parts = str(data).split(":")
    if len(parts) != 3 or parts[:2] != ["robot", "view"]:
        return None
    view = parts[2]
    return view if view in {VIEW_FEED, VIEW_POSITIONS, VIEW_WATCHING} else None


CONTROL_START = "start"
CONTROL_PAUSE = "pause"
CONTROL_RESUME = "resume"
CONTROL_STOP = "stop"
CONTROL_CLOSE_ALL = "close_all"
CONTROL_CLOSE_ALL_CONFIRM = "close_all_confirm"
CONTROL_CLOSE_ALL_CANCEL = "close_all_cancel"
ROBOT_CONTROL_COMMANDS = {
    CONTROL_START, CONTROL_PAUSE, CONTROL_RESUME, CONTROL_STOP,
    CONTROL_CLOSE_ALL, CONTROL_CLOSE_ALL_CONFIRM, CONTROL_CLOSE_ALL_CANCEL,
}


def parse_robot_control_callback(data: Any) -> str | None:
    parts = str(data).split(":")
    if len(parts) != 3 or parts[:2] != ["robot", "cmd"]:
        return None
    command = parts[2]
    return command if command in ROBOT_CONTROL_COMMANDS else None


def build_robot_control_keyboard(
    mode: str, recovery_status: str,
) -> dict[str, list[list[dict[str, str]]]]:
    """Render the operator control panel from live durable admission state.

    Exactly one button ever occupies the pause/resume slot (its label and
    callback_data flip with current state, per
    AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 Rationale) so a
    rejected transition is structurally unreachable from this keyboard.
    RECONCILIATION_REQUIRED offers no buttons: recovering out of it is a
    separate, unresolved problem this control surface does not attempt.
    """
    if recovery_status == "RECONCILIATION_REQUIRED":
        return {"inline_keyboard": []}
    if mode == "ROBOT_STOPPED":
        return {
            "inline_keyboard": [
                [{"text": "▶ Старт", "callback_data": f"robot:cmd:{CONTROL_START}"}],
            ]
        }
    toggle = (
        {"text": "▶ Старт", "callback_data": f"robot:cmd:{CONTROL_RESUME}"}
        if recovery_status == "PAUSED"
        else {"text": "⏸ Пауза", "callback_data": f"robot:cmd:{CONTROL_PAUSE}"}
    )
    return {
        "inline_keyboard": [
            [toggle],
            [
                {"text": "❌ Закрыть всё", "callback_data": f"robot:cmd:{CONTROL_CLOSE_ALL}"},
                {"text": "⏹ Стоп", "callback_data": f"robot:cmd:{CONTROL_STOP}"},
            ],
        ]
    }


def build_robot_close_all_confirmation_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    """One lightweight confirmation tap before close_all_now() executes.

    close_all_now() is the one command in this set that forces an immediate
    Market close of a live (PAPER) position, so — unlike start/pause/resume/
    stop — it is never fired directly from the control panel button.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Подтвердить", "callback_data": f"robot:cmd:{CONTROL_CLOSE_ALL_CONFIRM}"},
                {"text": "Отмена", "callback_data": f"robot:cmd:{CONTROL_CLOSE_ALL_CANCEL}"},
            ],
        ]
    }


def _required_text(source: Mapping[str, Any], key: str) -> str:
    value = str(source.get(key, "")).strip()
    if not value:
        raise RobotTelegramProjectionError(f"{key} is required")
    return value


def _optional_decimal(source: Mapping[str, Any], key: str) -> Decimal | None:
    value = source.get(key)
    if value is None or value == "":
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotTelegramProjectionError(f"{key} must be decimal-compatible") from exc
    if not number.is_finite():
        raise RobotTelegramProjectionError(f"{key} must be finite")
    return number


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return format(value.normalize(), "f")


def build_static_chart_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _required_text(record, "symbol")
    timeframe = str(record.get("timeframe", "1")).strip() or "1"
    geometry = record.get("geometry")
    if geometry is None:
        signal_snapshot = record.get("signal_snapshot")
        if isinstance(signal_snapshot, Mapping):
            geometry = signal_snapshot.get("geometry")
    if not isinstance(geometry, Mapping):
        raise RobotTelegramProjectionError("frozen geometry is required for chart projection")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "geometry": dict(geometry),
        "entry_price": _format_decimal(_optional_decimal(record, "entry_price")),
        "average_entry": _format_decimal(_optional_decimal(record, "average_entry")),
        "stop": _format_decimal(_optional_decimal(record, "stop")),
        "take": _format_decimal(_optional_decimal(record, "take")),
        "entry_marker": record.get("entry_marker"),
        "exit_marker": record.get("exit_marker"),
        "state": str(record.get("state", "")).strip() or "—",
    }


def build_observation_card(record: Mapping[str, Any]) -> RobotFeedCard:
    symbol = _required_text(record, "symbol")
    pattern = _required_text(record, "pattern")
    direction = _required_text(record, "direction")
    state = _required_text(record, "state")
    timeframe = str(record.get("timeframe", "1")).strip() or "1"
    text = (
        f"👀 {symbol} · {pattern}\n"
        f"Направление: {direction}\n"
        f"TF: {timeframe}m\n"
        f"Статус: {state}"
    )
    chart = build_static_chart_projection(record) if record.get("geometry") or record.get("signal_snapshot") else None
    return RobotFeedCard(EVENT_OBSERVATION, "Под наблюдением", text, chart, build_robot_tab_keyboard())


def build_opened_card(record: Mapping[str, Any]) -> RobotFeedCard:
    symbol = _required_text(record, "symbol")
    pattern = _required_text(record, "pattern")
    direction = _required_text(record, "direction")
    volume = _optional_decimal(record, "volume_wv")
    entry = _optional_decimal(record, "average_entry") or _optional_decimal(record, "entry_price")
    stop = _optional_decimal(record, "stop")
    take = _optional_decimal(record, "take")
    text = (
        f"🟢 {symbol} · {pattern}\n"
        f"{direction} открыт\n"
        f"Объём: {_format_decimal(volume)} WV\n"
        f"Вход: {_format_decimal(entry)}\n"
        f"STOP: {_format_decimal(stop)}\n"
        f"TAKE: {_format_decimal(take)}"
    )
    return RobotFeedCard(EVENT_OPENED, "Сделка открыта", text, build_static_chart_projection(record), build_robot_tab_keyboard())


def build_closed_card(record: Mapping[str, Any]) -> RobotFeedCard:
    symbol = _required_text(record, "symbol")
    pattern = _required_text(record, "pattern")
    direction = _required_text(record, "direction")
    reason = _required_text(record, "exit_reason")
    pnl_usdt = _optional_decimal(record, "realized_pnl_usdt")
    pnl_percent = _optional_decimal(record, "realized_pnl_percent")
    text = (
        f"🔴 {symbol} · {pattern}\n"
        f"{direction} закрыт\n"
        f"Причина: {reason}\n"
        f"PnL: {_format_decimal(pnl_usdt)} USDT"
    )
    if pnl_percent is not None:
        text += f" ({_format_decimal(pnl_percent)}%)"
    return RobotFeedCard(EVENT_CLOSED, "Сделка закрыта", text, build_static_chart_projection(record), build_robot_tab_keyboard())


def format_positions_view(records: Sequence[Mapping[str, Any]]) -> str:
    if not records:
        return "🤖 Робот\n\nОткрытых позиций нет."
    lines = ["🤖 Робот · Все позиции", ""]
    for index, record in enumerate(records, start=1):
        symbol = _required_text(record, "symbol")
        direction = _required_text(record, "direction")
        volume = _optional_decimal(record, "volume_wv")
        pnl = _optional_decimal(record, "unrealized_pnl_usdt")
        lines.append(
            f"{index}. {symbol} · {direction} · {_format_decimal(volume)} WV · PnL {_format_decimal(pnl)} USDT"
        )
    return "\n".join(lines)


def format_watching_view(records: Sequence[Mapping[str, Any]]) -> str:
    if not records:
        return "🤖 Робот\n\nПод наблюдением сейчас ничего нет."
    lines = ["🤖 Робот · Под наблюдением", ""]
    for index, record in enumerate(records, start=1):
        symbol = _required_text(record, "symbol")
        pattern = _required_text(record, "pattern")
        state = _required_text(record, "state")
        lines.append(f"{index}. {symbol} · {pattern} · {state}")
    return "\n".join(lines)
