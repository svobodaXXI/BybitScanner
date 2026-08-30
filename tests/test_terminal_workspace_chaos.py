"""Deterministic M7 chaos and regression coverage for the Workspace stream."""

from copy import deepcopy
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

from terminal.market_data.client_projection import ClientMarketProjection, StaleProjectionError
from terminal.market_data.hub import SymbolContext
from terminal.market_data.workspace_stream import (
    WorkspaceStreamBackpressure,
    WorkspaceStreamBroker,
    WorkspaceStreamError,
    WorkspaceStreamSession,
)
from terminal.runtime.paper_http_server import PaperHttpHandler


class _Book:
    def __init__(self):
        self.data = {
            "state": "READY", "version": 1, "updateId": 10, "sequence": 20,
            "receivedAt": 1000, "bids": [{"price": "100", "size": "2"}],
            "asks": [{"price": "101", "size": "3"}],
        }

    def snapshot(self):
        return deepcopy(self.data)


class _Trades:
    def __init__(self):
        self.items = []

    def snapshot_after(self, after):
        return deepcopy([item for item in self.items if item["ended_at_ms"] > after])


class _Candles:
    def __init__(self):
        self.data = {
            "state": "READY", "version": 1, "receivedAt": 1000,
            "candles": [{"startTime": 1, "open": "1", "high": "1", "low": "1", "close": "1"}],
        }

    def snapshot(self):
        return deepcopy(self.data)


def _instrument(symbol):
    return {"symbol": symbol, "tick_size": "0.5", "quantity_step": "0.001"}


class WorkspaceChaosTests(unittest.TestCase):
    def setUp(self):
        self.context = SymbolContext("BTCUSDT", _Book(), _Trades(), {"5": _Candles()})
        self.current = SimpleNamespace(value=True)

        def factory(_symbol="BTCUSDT"):
            return ClientMarketProjection(
                self.context, 7,
                is_current=lambda _context, _generation: self.current.value,
            )

        self.factory = factory

    def test_resume_boundaries_replay_overflow_and_heartbeat_are_monotonic(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument, replay_limit=2)
        first = session.initial_snapshot()
        self.context.public_orderbook.data.update(version=2, updateId=11, sequence=21)
        self.context.public_orderbook.data["bids"] = [{"price": "99", "size": "4"}]
        second = session.poll()[0]
        heartbeat = session.heartbeat()
        self.assertEqual([first["event_sequence"], second["event_sequence"], heartbeat["event_sequence"]], [1, 2, 3])
        self.assertEqual((heartbeat["kind"], heartbeat["component"]), ("health", "stream"))
        self.assertEqual(session.resume_after(3), ())
        self.assertEqual(session.resume_after(2), (heartbeat,))
        gap = session.resume_after(0)[0]
        self.assertEqual((gap["kind"], gap["resync"], gap["resync_reason"]), ("workspace_snapshot", True, "resume_gap"))
        future = session.resume_after(session.latest_sequence + 1)[0]
        self.assertEqual(future["resync_reason"], "invalid_resume_sequence")

    def test_pending_overflow_clears_queue_and_stale_generation_fails_closed(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument, pending_limit=1)
        event = session.initial_snapshot()
        session.enqueue((event,))
        with self.assertRaises(WorkspaceStreamBackpressure):
            session.enqueue((event,))
        self.assertEqual(session.drain(), ())
        self.current.value = False
        with self.assertRaises(StaleProjectionError):
            session.poll()

    def test_component_resnapshot_escalates_to_one_atomic_workspace_snapshot(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument)
        session.initial_snapshot()
        self.context.public_orderbook.data.update(version=3, updateId=12, sequence=22)
        event = session.poll()[0]
        self.assertEqual(event["kind"], "workspace_snapshot")
        self.assertTrue(event["resync"])
        self.assertEqual(event["resync_reason"], "book_resync")
        self.assertEqual(set(event["components"]), {"book", "trades", "candles"})

    def test_broker_rejects_duplicate_foreign_and_burst_attachments(self):
        broker = WorkspaceStreamBroker(self.factory, _instrument, session_limit=2)
        first = broker.open("BTCUSDT", "5")
        with self.assertRaises(WorkspaceStreamError):
            broker.open("BTCUSDT", "5", stream_id=first.session.stream_id, after_sequence=1)
        broker.detach(first.session.stream_id)
        with self.assertRaises(LookupError):
            broker.open("ETHUSDT", "5", stream_id=first.session.stream_id, after_sequence=1)
        resumed = broker.open("BTCUSDT", "5", stream_id=first.session.stream_id, after_sequence=1)
        self.assertTrue(resumed.resumed)
        second = broker.open("BTCUSDT", "5")
        with self.assertRaises(WorkspaceStreamBackpressure):
            broker.open("BTCUSDT", "5")
        broker.drop(resumed.session.stream_id)
        broker.drop(second.session.stream_id)

    def test_socket_write_timeout_drops_resumable_session(self):
        broker = WorkspaceStreamBroker(self.factory, _instrument)
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.market_data = SimpleNamespace(workspace_streams=broker)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        with patch(
            "terminal.runtime.paper_http_server.websocket_text_frame",
            side_effect=TimeoutError("controlled slow writer"),
        ):
            thread.start()
            client = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
            try:
                client.sendall((
                    "GET /api/workspace/stream?symbol=BTCUSDT&interval=5 HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{server.server_port}\r\n"
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    "Sec-WebSocket-Version: 13\r\n"
                    "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
                ).encode("ascii"))
                received = b""
                while b"\r\n\r\n" not in received:
                    received += client.recv(4096)
                self.assertIn(b"101 Switching Protocols", received)
                self.assertEqual(client.recv(1), b"")
                self.assertEqual(broker._sessions, {})
            finally:
                client.close()
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_mixed_book_trade_candle_churn_stays_one_generation(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument)
        snapshot = session.initial_snapshot()
        self.context.public_orderbook.data.update(version=2, updateId=11, sequence=21)
        self.context.public_orderbook.data["bids"] = [{"price": "99", "size": "5"}]
        self.context.public_trades.items.extend([
            {"id": "later", "ended_at_ms": 1200},
            {"id": "earlier", "ended_at_ms": 1100},
            {"id": "later", "ended_at_ms": 1200},
        ])
        self.context.public_klines["5"].data.update(version=2)
        self.context.public_klines["5"].data["candles"] = [
            {"startTime": 1, "open": "1", "high": "2", "low": "1", "close": "2"},
            {"startTime": 2, "open": "2", "high": "2", "low": "2", "close": "2"},
        ]
        events = session.poll()
        self.assertEqual([event["kind"] for event in events], ["book_delta", "trade_batch", "candle_update"])
        self.assertEqual([event["event_sequence"] for event in events], [2, 3, 4])
        self.assertEqual({event["workspace_generation"] for event in (snapshot, *events)}, {7})
        self.assertEqual({event["stream_id"] for event in (snapshot, *events)}, {session.stream_id})


if __name__ == "__main__":
    unittest.main()
