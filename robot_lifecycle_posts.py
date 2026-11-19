"""Robot trade lifecycle posts ("открыта" / "закрыта"): event selection and dedup state.

Read-only with respect to trading state. ``collect_new_lifecycle_events`` only
reads the store; the Telegram listener thread sends the posts and records a
trade_id in the dedup file only after a successful send.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from robot_position_view import (
    CAPTION_LIMIT, PAPER_ACCOUNT_ID, PositionView, exit_reason_label, format_position_card,
)
from robot_telegram_feed import VIEW_POSITIONS
from telegram_labels import ROBOT_EMOJI


EVENT_OPENED = "OPENED"
EVENT_CLOSED = "CLOSED"
REMEMBERED_TRADE_IDS = 200


@dataclass
class LifecycleState:
    initialized_at_ms: int
    opened: list[str] = field(default_factory=list)
    closed: list[str] = field(default_factory=list)
    retry_after_ms: int = 0
    # Inclusive lower bounds for the compact exact-ID caches; monotone.
    opened_floor: tuple[int, str] | None = None
    closed_floor: tuple[int, str] | None = None


@dataclass(frozen=True)
class LifecycleEvent:
    kind: str  # EVENT_OPENED / EVENT_CLOSED
    trade_id: str
    symbol: str
    time_ms: int
    exit_reason: str | None = None


def save_lifecycle_state(path: Path, state: LifecycleState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps({
            "initialized_at_ms": state.initialized_at_ms,
            "opened": state.opened,
            "closed": state.closed,
            "retry_after_ms": state.retry_after_ms,
            "opened_floor": list(state.opened_floor) if state.opened_floor else None,
            "closed_floor": list(state.closed_floor) if state.closed_floor else None,
        }),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_floor(value) -> tuple[int, str] | None:
    if value is None:
        return None  # Backward-compatible with legacy dedup JSON.
    if (not isinstance(value, list) or len(value) != 2
            or type(value[0]) is not int or value[0] < 0
            or not isinstance(value[1], str) or not value[1]):
        raise ValueError("invalid lifecycle watermark")
    return value[0], value[1]


def load_lifecycle_state(path: Path, now_ms: int) -> LifecycleState:
    """Load dedup state; the first run starts at ``now_ms`` so history is never re-sent."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return LifecycleState(
            initialized_at_ms=int(raw["initialized_at_ms"]),
            opened=[str(item) for item in raw.get("opened", [])],
            closed=[str(item) for item in raw.get("closed", [])],
            retry_after_ms=max(0, int(raw.get("retry_after_ms", 0))),
            opened_floor=_read_floor(raw.get("opened_floor")),
            closed_floor=_read_floor(raw.get("closed_floor")),
        )
    except FileNotFoundError:
        pass
    except (ValueError, KeyError, TypeError) as exc:
        # A damaged file restarts from now: missing a post is safer than a flood.
        print("[LIFECYCLE STATE ERROR] reinitializing:", exc)
    state = LifecycleState(initialized_at_ms=now_ms)
    save_lifecycle_state(path, state)
    return state


def mark_notified(state: LifecycleState, event: LifecycleEvent) -> None:
    sent = state.opened if event.kind == EVENT_OPENED else state.closed
    if event.trade_id not in sent:
        sent.append(event.trade_id)
    del sent[:-REMEMBERED_TRADE_IDS]


def collect_new_lifecycle_events(store, state: LifecycleState) -> list[LifecycleEvent]:
    """Events not yet posted, oldest first; a trade's "opened" precedes its "closed"."""

    since = state.initialized_at_ms
    trades = store.load_robot_trades_with_events_since(PAPER_ACCOUNT_ID, since)
    # The 200 stored IDs are the latest successful sends in source-time
    # order. When older IDs are evicted, suppress everything before the
    # oldest still-retained exact successful event, not the entire history.
    # This is a one-way durable watermark: late records never rewind it.
    by_id = {trade.trade_id: trade for trade in trades}
    for sent, time_field, floor_field in (
        (state.opened, "entry_time_ms", "opened_floor"),
        (state.closed, "exit_time_ms", "closed_floor"),
    ):
        if len(sent) < REMEMBERED_TRADE_IDS:
            continue
        known = []
        for trade_id in sent:
            trade = by_id.get(trade_id)
            ms = getattr(trade, time_field, None)
            if type(ms) is not int or ms < since:
                # An uncertain boundary cannot authorize replay of old posts.
                raise ValueError("lifecycle watermark cannot be verified")
            known.append((ms, trade_id))
        candidate = min(known)
        prior = getattr(state, floor_field)
        if prior is None or candidate > prior:
            setattr(state, floor_field, candidate)

    events = []
    for trade in trades:
        symbol = trade.symbol.value
        # An OPENED event is only meaningful while the trade is still open.
        # A trade that entered and exited between polls needs only its CLOSED
        # notification; otherwise a closed snapshot appears under "Сделка открыта".
        if (trade.exit_time_ms is None
                and trade.entry_time_ms >= since
                and trade.trade_id not in state.opened
                and (state.opened_floor is None
                     or (trade.entry_time_ms, trade.trade_id) >= state.opened_floor)):
            events.append(LifecycleEvent(EVENT_OPENED, trade.trade_id, symbol, trade.entry_time_ms))
        if (
            trade.exit_time_ms is not None
            and trade.exit_time_ms >= since
            and trade.trade_id not in state.closed
            and (state.closed_floor is None
                 or (trade.exit_time_ms, trade.trade_id) >= state.closed_floor)
        ):
            events.append(LifecycleEvent(
                EVENT_CLOSED, trade.trade_id, symbol, trade.exit_time_ms, trade.exit_reason,
            ))
    events.sort(key=lambda event: (event.time_ms, event.kind != EVENT_OPENED, event.trade_id))
    return events


def build_lifecycle_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    # Only the button with a working handler; the Robot tab's other buttons have none yet.
    return {"inline_keyboard": [
        [{"text": "Все позиции", "callback_data": f"robot:view:{VIEW_POSITIONS}"}],
    ]}


def format_lifecycle_caption(event: LifecycleEvent, view: PositionView) -> str:
    if event.kind == EVENT_OPENED:
        attempt = view.reentry_attempt_index
        phase = (f"Повторный перезаход №{attempt - 1}"
                 if attempt in (2, 3) else "Сделка открыта")
    else:
        phase = f"Сделка закрыта · {exit_reason_label(event.exit_reason)}"

    if view.mirror_campaign:
        # Trade events originate in durable Robot trades, not candidate admission.
        from mirror_scanner import mirror_subtype
        subtype = mirror_subtype(
            view.mirror_level_source, view.mirror_pattern, "first_retest",
            retest_confirmed=view.mirror_retest_confirmed,
        )
        if event.kind == EVENT_OPENED:
            timeframe = view.mirror_timeframe or str(view.chart_candle_minutes)
            return f"🪞 MIRROR · {view.symbol} · {timeframe}m\n{subtype}\n{phase}"[:CAPTION_LIMIT]
        # A closed MIRROR trade has the same exact host pattern / net economics
        # layout as other closed trades; preserve subtype as ancillary context.
        return f"🪞 {phase}\n\n{format_position_card(view)}\n{subtype}"[:CAPTION_LIMIT]
    return f"{ROBOT_EMOJI} {phase}\n\n{format_position_card(view)}"[:CAPTION_LIMIT]
