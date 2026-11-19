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
    # Durable event-order watermark. Bounded ID caches alone eventually replay history.
    last_notified_key: tuple[int, int, str] | None = None


@dataclass(frozen=True)
class LifecycleEvent:
    kind: str  # EVENT_OPENED / EVENT_CLOSED
    trade_id: str
    symbol: str
    time_ms: int
    exit_reason: str | None = None


def _event_key(event: LifecycleEvent) -> tuple[int, int, str]:
    # Same order as collect_new_lifecycle_events: OPENED before CLOSED at equal ms.
    return (event.time_ms, int(event.kind != EVENT_OPENED), event.trade_id)


def recover_legacy_lifecycle_cursor(store, state: LifecycleState, now_ms: int) -> bool:
    """Fence old 200-ID states before sending anything else.

    Older versions kept only the last 200 IDs while re-reading all history.
    When a cache is full, derive the newest *confirmed sent* event from the
    durable trade ledger. Older unknown events fail closed (not replayed).
    """
    if (state.last_notified_key is not None
            or (len(state.opened) < REMEMBERED_TRADE_IDS
                and len(state.closed) < REMEMBERED_TRADE_IDS)):
        return False
    opened, closed = set(state.opened), set(state.closed)
    confirmed = []
    for trade in store.load_robot_trades_with_events_since(
            PAPER_ACCOUNT_ID, state.initialized_at_ms):
        if trade.trade_id in opened and trade.entry_time_ms >= state.initialized_at_ms:
            confirmed.append((trade.entry_time_ms, 0, trade.trade_id))
        if (trade.trade_id in closed and trade.exit_time_ms is not None
                and trade.exit_time_ms >= state.initialized_at_ms):
            confirmed.append((trade.exit_time_ms, 1, trade.trade_id))
    # No matching durable evidence: quarantine the historical backlog instead
    # of sending an unbounded batch of potentially already-delivered notices.
    state.last_notified_key = max(confirmed) if confirmed else (now_ms, 1, "\uffff")
    return True


def save_lifecycle_state(path: Path, state: LifecycleState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    payload = {
        "initialized_at_ms": state.initialized_at_ms,
        "opened": state.opened,
        "closed": state.closed,
        "retry_after_ms": state.retry_after_ms,
    }
    # Preserve the historical initial-state format until a delivery is recorded.
    if state.last_notified_key is not None:
        payload["last_notified_key"] = state.last_notified_key
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def load_lifecycle_state(path: Path, now_ms: int) -> LifecycleState:
    """Load dedup state; the first run starts at ``now_ms`` so history is never re-sent."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cursor = raw.get("last_notified_key")
        if cursor is not None:
            if (not isinstance(cursor, list) or len(cursor) != 3
                    or type(cursor[0]) is not int or type(cursor[1]) is not int
                    or cursor[1] not in (0, 1) or not isinstance(cursor[2], str)
                    or not cursor[2]):
                raise ValueError("invalid lifecycle cursor")
            cursor = tuple(cursor)
        return LifecycleState(
            initialized_at_ms=int(raw["initialized_at_ms"]),
            opened=[str(item) for item in raw.get("opened", [])],
            closed=[str(item) for item in raw.get("closed", [])],
            retry_after_ms=max(0, int(raw.get("retry_after_ms", 0))),
            last_notified_key=cursor,
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
    key = _event_key(event)
    if state.last_notified_key is None or key > state.last_notified_key:
        state.last_notified_key = key


def collect_new_lifecycle_events(store, state: LifecycleState) -> list[LifecycleEvent]:
    """Events not yet posted, oldest first; a trade's "opened" precedes its "closed"."""

    since = state.initialized_at_ms
    if state.last_notified_key is not None:
        since = max(since, state.last_notified_key[0])
    events = []
    for trade in store.load_robot_trades_with_events_since(PAPER_ACCOUNT_ID, since):
        symbol = trade.symbol.value
        # An OPENED event is only meaningful while the trade is still open.
        # A trade that entered and exited between polls needs only its CLOSED
        # notification; otherwise a closed snapshot appears under "Сделка открыта".
        if (trade.exit_time_ms is None
                and trade.entry_time_ms >= since
                and trade.trade_id not in state.opened):
            events.append(LifecycleEvent(EVENT_OPENED, trade.trade_id, symbol, trade.entry_time_ms))
        if (
            trade.exit_time_ms is not None
            and trade.exit_time_ms >= since
            and trade.trade_id not in state.closed
        ):
            events.append(LifecycleEvent(
                EVENT_CLOSED, trade.trade_id, symbol, trade.exit_time_ms, trade.exit_reason,
            ))
    events.sort(key=_event_key)
    if state.last_notified_key is not None:
        events = [event for event in events if _event_key(event) > state.last_notified_key]
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
