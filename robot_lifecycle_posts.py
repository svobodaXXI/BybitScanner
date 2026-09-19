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
        }),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_lifecycle_state(path: Path, now_ms: int) -> LifecycleState:
    """Load dedup state; the first run starts at ``now_ms`` so history is never re-sent."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return LifecycleState(
            initialized_at_ms=int(raw["initialized_at_ms"]),
            opened=[str(item) for item in raw.get("opened", [])],
            closed=[str(item) for item in raw.get("closed", [])],
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
    events = []
    for trade in store.load_robot_trades_with_events_since(PAPER_ACCOUNT_ID, since):
        symbol = trade.symbol.value
        if trade.entry_time_ms >= since and trade.trade_id not in state.opened:
            events.append(LifecycleEvent(EVENT_OPENED, trade.trade_id, symbol, trade.entry_time_ms))
        if (
            trade.exit_time_ms is not None
            and trade.exit_time_ms >= since
            and trade.trade_id not in state.closed
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
        header = f"{ROBOT_EMOJI} Сделка открыта"
    else:
        header = f"{ROBOT_EMOJI} Сделка закрыта · {exit_reason_label(event.exit_reason)}"
    return f"{header}\n\n{format_position_card(view)}"[:CAPTION_LIMIT]
