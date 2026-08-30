"""Multiplexed snapshot-first Workspace client stream."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from terminal.market_data.client_projection import ClientMarketProjection


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_REPLAY_LIMIT = 256
DEFAULT_PENDING_LIMIT = 64
DEFAULT_SESSION_LIMIT = 32


class WorkspaceStreamError(RuntimeError):
    """The requested stream cannot safely serve the active Workspace."""


class WorkspaceStreamBackpressure(WorkspaceStreamError):
    """A slow client exceeded the bounded pending-event contract."""


def websocket_accept(key: str) -> str:
    digest = hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def websocket_text_frame(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    size = len(body)
    if size < 126:
        header = bytes((0x81, size))
    elif size <= 0xFFFF:
        header = bytes((0x81, 126)) + size.to_bytes(2, "big")
    else:
        header = bytes((0x81, 127)) + size.to_bytes(8, "big")
    return header + body


@dataclass(frozen=True, slots=True)
class WorkspaceStreamOpen:
    session: "WorkspaceStreamSession"
    events: tuple[dict, ...]
    resumed: bool


class WorkspaceStreamSession:
    """One generation-scoped multiplexed projection with bounded replay."""

    def __init__(
        self,
        projection_factory: Callable[[], ClientMarketProjection],
        instrument_factory: Callable[[str], dict[str, str]],
        *,
        interval: str = "5",
        replay_limit: int = DEFAULT_REPLAY_LIMIT,
        pending_limit: int = DEFAULT_PENDING_LIMIT,
    ) -> None:
        if replay_limit <= 0 or pending_limit <= 0:
            raise ValueError("Workspace stream bounds must be positive")
        self.stream_id = uuid4().hex
        self.interval = interval
        self.replay_limit = replay_limit
        self.pending_limit = pending_limit
        self._projection_factory = projection_factory
        self._instrument_factory = instrument_factory
        self._projection = projection_factory()
        self.symbol = self._projection.symbol
        self.workspace_generation = self._projection.workspace_generation
        self._sequence = 0
        self._replay: deque[dict] = deque(maxlen=replay_limit)
        self._pending: deque[dict] = deque()
        self._lock = threading.RLock()
        self.last_access = time.monotonic()

    @property
    def latest_sequence(self) -> int:
        with self._lock:
            return self._sequence

    def initial_snapshot(self, *, reason: str | None = None) -> dict:
        with self._lock:
            self._projection = self._projection_factory()
            self.symbol = self._projection.symbol
            self.workspace_generation = self._projection.workspace_generation
            book = self._projection.book_event()
            trades = self._projection.trades_event()
            candles = self._projection.candles_event(self.interval)
            if (
                book is None or book.get("kind") != "book_snapshot"
                or trades is None or trades.get("kind") != "trade_bootstrap"
                or candles is None or candles.get("kind") != "candle_bootstrap"
            ):
                raise WorkspaceStreamError("active Workspace is not snapshot-ready")
            self._projection.assert_current()
            components = {
                "book": book.get("state", "NOT_READY"),
                "trades": trades.get("state", "NOT_READY"),
                "candles": candles.get("state", "NOT_READY"),
            }
            state = "READY" if set(components.values()) == {"READY"} else "DEGRADED"
            return self._emit(
                "workspace_snapshot", state=state,
                instrument=self._instrument_factory(self.symbol),
                components=components,
                health=self._projection.context.health_snapshot(),
                book=book, trades=trades, candles=candles,
                resync=reason is not None, resync_reason=reason,
            )

    def poll(self) -> tuple[dict, ...]:
        with self._lock:
            events: list[dict] = []
            for component, event in (
                ("book", self._projection.book_event()),
                ("trades", self._projection.trades_event()),
                ("candles", self._projection.candles_event(self.interval)),
            ):
                if event is None:
                    continue
                kind = str(event["kind"])
                if kind in {"book_snapshot", "trade_bootstrap", "candle_bootstrap"}:
                    return (self.initial_snapshot(reason=f"{component}_resync"),)
                if kind in {"book_health", "candle_health"}:
                    kind = "health"
                events.append(self._emit(
                    kind, state=str(event.get("state") or "READY"),
                    component=component, payload=event,
                ))
            self.last_access = time.monotonic()
            return tuple(events)

    def heartbeat(self) -> dict:
        with self._lock:
            self.last_access = time.monotonic()
            return self._emit("health", state="READY", component="stream", payload={
                "service_alive": True,
            })

    def resume_after(self, sequence: int) -> tuple[dict, ...]:
        with self._lock:
            if sequence < 0 or sequence > self._sequence:
                return (self.initial_snapshot(reason="invalid_resume_sequence"),)
            if sequence == self._sequence:
                return ()
            oldest = self._replay[0]["event_sequence"] if self._replay else self._sequence + 1
            if sequence < oldest - 1:
                return (self.initial_snapshot(reason="resume_gap"),)
            self.last_access = time.monotonic()
            return tuple(event for event in self._replay if event["event_sequence"] > sequence)

    def enqueue(self, events: tuple[dict, ...]) -> None:
        with self._lock:
            if len(self._pending) + len(events) > self.pending_limit:
                self._pending.clear()
                raise WorkspaceStreamBackpressure("slow client exceeded pending event limit")
            self._pending.extend(events)

    def drain(self) -> tuple[dict, ...]:
        with self._lock:
            events = tuple(self._pending)
            self._pending.clear()
            return events

    def _emit(self, kind: str, *, state: str, **payload: object) -> dict:
        self._sequence += 1
        event = {
            "stream_id": self.stream_id,
            "event_sequence": self._sequence,
            "event_timestamp": int(time.time() * 1000),
            "symbol": self.symbol,
            "workspace_generation": self.workspace_generation,
            "kind": kind,
            "state": state,
            **payload,
        }
        self._replay.append(event)
        return event


class WorkspaceStreamBroker:
    """Bound the resumable stream sessions owned by the HTTP runtime."""

    def __init__(
        self,
        projection_factory: Callable[[str], ClientMarketProjection],
        instrument_factory: Callable[[str], dict[str, str]],
        *,
        session_limit: int = DEFAULT_SESSION_LIMIT,
    ) -> None:
        if session_limit <= 0:
            raise ValueError("Workspace stream session limit must be positive")
        self._projection_factory = projection_factory
        self._instrument_factory = instrument_factory
        self._session_limit = session_limit
        self._sessions: dict[str, WorkspaceStreamSession] = {}
        self._attached: set[str] = set()
        self._lock = threading.RLock()

    def open(
        self, symbol: str, interval: str, *,
        stream_id: str | None = None, after_sequence: int | None = None,
    ) -> WorkspaceStreamOpen:
        normalized = symbol.strip().upper()
        with self._lock:
            if stream_id is not None:
                session = self._sessions.get(stream_id)
                if session is None or session.symbol != normalized or session.interval != interval:
                    raise LookupError("unknown Workspace stream")
                if stream_id in self._attached:
                    raise WorkspaceStreamError("Workspace stream is already attached")
                self._attached.add(stream_id)
                events = session.resume_after(after_sequence if after_sequence is not None else -1)
                return WorkspaceStreamOpen(session, events, True)
            self._make_room_locked()
            session = WorkspaceStreamSession(
                lambda: self._projection_factory(normalized), self._instrument_factory,
                interval=interval,
            )
            self._sessions[session.stream_id] = session
            self._attached.add(session.stream_id)
            return WorkspaceStreamOpen(session, (session.initial_snapshot(),), False)

    def detach(self, stream_id: str) -> None:
        with self._lock:
            self._attached.discard(stream_id)

    def drop(self, stream_id: str) -> None:
        with self._lock:
            self._sessions.pop(stream_id, None)
            self._attached.discard(stream_id)

    def _make_room_locked(self) -> None:
        if len(self._sessions) < self._session_limit:
            return
        detached = [
            session for session in self._sessions.values()
            if session.stream_id not in self._attached
        ]
        if not detached:
            raise WorkspaceStreamBackpressure("Workspace stream session limit reached")
        oldest = min(detached, key=lambda item: item.last_access)
        self._sessions.pop(oldest.stream_id, None)
