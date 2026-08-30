import json
import socket
import threading
import unittest
from copy import deepcopy
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from terminal.market_data.client_projection import ClientMarketProjection, StaleProjectionError
from terminal.market_data.hub import SymbolContext
from terminal.market_data.workspace_stream import (
    WorkspaceStreamBackpressure, WorkspaceStreamBroker, WorkspaceStreamError,
    WorkspaceStreamSession,
    websocket_accept, websocket_text_frame,
)
from terminal.runtime.paper_http_server import PaperHttpHandler


class _Book:
    def __init__(self):
        self.data = {
            "state": "READY", "version": 1, "updateId": 10, "sequence": 20,
            "receivedAt": 1000,
            "bids": [{"price": "100", "size": "1"}],
            "asks": [{"price": "101", "size": "1"}],
        }

    def snapshot(self):
        return deepcopy(self.data)


class _Trades:
    def __init__(self):
        self.items = []

    def snapshot_after(self, _after):
        return deepcopy(self.items)


class _Candles:
    def __init__(self):
        self.data = {"state": "READY", "version": 1, "receivedAt": 1000, "candles": [
            {"startTime": 1, "open": "1", "high": "1", "low": "1", "close": "1"},
        ]}

    def snapshot(self):
        return deepcopy(self.data)


def _context():
    return SymbolContext("BTCUSDT", _Book(), _Trades(), {"5": _Candles()})


def _instrument(_symbol):
    return {"symbol": "BTCUSDT", "tick_size": "0.5", "quantity_step": "0.001"}


class WorkspaceStreamTests(unittest.TestCase):
    def setUp(self):
        self.context = _context()
        self.current = True
        self.factory = lambda _symbol="BTCUSDT": ClientMarketProjection(
            self.context, 7, is_current=lambda _context, _generation: self.current,
        )

    def test_atomic_snapshot_and_multiplexed_incremental_sequence(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument)
        snapshot = session.initial_snapshot()
        self.assertEqual(snapshot["kind"], "workspace_snapshot")
        self.assertEqual(snapshot["state"], "READY")
        self.assertEqual(snapshot["event_sequence"], 1)
        self.assertEqual(snapshot["workspace_generation"], 7)
        self.assertIn("book_sequence", snapshot["health"])
        self.assertEqual(snapshot["book"]["kind"], "book_snapshot")
        self.assertEqual(snapshot["trades"]["kind"], "trade_bootstrap")
        self.assertEqual(snapshot["candles"]["kind"], "candle_bootstrap")

        self.context.public_orderbook.data["bids"][0]["size"] = "2"
        self.context.public_orderbook.data["version"] += 1
        self.context.public_orderbook.data["updateId"] += 1
        self.context.public_orderbook.data["sequence"] += 1
        self.context.public_trades.items.append({"id": "t1", "ended_at_ms": 1100})
        self.context.public_klines["5"].data["candles"][0]["close"] = "2"
        events = session.poll()
        self.assertEqual([event["kind"] for event in events], [
            "book_delta", "trade_batch", "candle_update",
        ])
        self.assertEqual([event["event_sequence"] for event in events], [2, 3, 4])
        self.assertTrue(all(event["symbol"] == "BTCUSDT" for event in events))

    def test_resume_replays_available_events_and_gap_resnapshots(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument, replay_limit=2)
        first = session.initial_snapshot()
        self.context.public_orderbook.data["bids"][0]["size"] = "2"
        self.context.public_orderbook.data["version"] += 1
        self.context.public_orderbook.data["updateId"] += 1
        self.context.public_orderbook.data["sequence"] += 1
        second = session.poll()[0]
        self.context.public_trades.items.append({"id": "t1", "ended_at_ms": 1100})
        third = session.poll()[0]
        self.assertEqual(session.resume_after(second["event_sequence"]), (third,))
        resnapshot = session.resume_after(0)[0]
        self.assertEqual(resnapshot["kind"], "workspace_snapshot")
        self.assertTrue(resnapshot["resync"])
        self.assertEqual(resnapshot["resync_reason"], "resume_gap")

    def test_wrong_generation_fails_closed_and_backpressure_is_bounded(self):
        session = WorkspaceStreamSession(lambda: self.factory(), _instrument, pending_limit=1)
        event = session.initial_snapshot()
        session.enqueue((event,))
        with self.assertRaises(WorkspaceStreamBackpressure):
            session.enqueue((event,))
        self.current = False
        with self.assertRaises(StaleProjectionError):
            session.poll()

    def test_broker_resume_identity_and_session_bound(self):
        broker = WorkspaceStreamBroker(self.factory, _instrument, session_limit=1)
        opened = broker.open("btcusdt", "5")
        with self.assertRaises(WorkspaceStreamError):
            broker.open(
                "BTCUSDT", "5", stream_id=opened.session.stream_id,
                after_sequence=opened.events[0]["event_sequence"],
            )
        broker.detach(opened.session.stream_id)
        resumed = broker.open(
            "BTCUSDT", "5", stream_id=opened.session.stream_id,
            after_sequence=opened.events[0]["event_sequence"],
        )
        self.assertTrue(resumed.resumed)
        self.assertEqual(resumed.events, ())
        broker.detach(opened.session.stream_id)
        replacement = broker.open("BTCUSDT", "5")
        with self.assertRaises(LookupError):
            broker.open("BTCUSDT", "5", stream_id=opened.session.stream_id, after_sequence=0)
        self.assertNotEqual(opened.session.stream_id, replacement.session.stream_id)

    def test_websocket_handshake_and_large_text_frame(self):
        self.assertEqual(
            websocket_accept("dGhlIHNhbXBsZSBub25jZQ=="),
            "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        )
        payload = {"value": "x" * 200}
        frame = websocket_text_frame(payload)
        self.assertEqual(frame[:2], bytes((0x81, 126)))
        size = int.from_bytes(frame[2:4], "big")
        self.assertEqual(json.loads(frame[4:4 + size]), payload)

    def test_http_endpoint_upgrades_and_sends_workspace_snapshot_frame(self):
        broker = WorkspaceStreamBroker(self.factory, _instrument)
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.market_data = SimpleNamespace(workspace_streams=broker)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
        try:
            request = (
                "GET /api/workspace/stream?symbol=BTCUSDT&interval=5 HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{server.server_port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
            )
            client.sendall(request.encode("ascii"))
            received = b""
            while b"\r\n\r\n" not in received:
                received += client.recv(4096)
            headers, frame = received.split(b"\r\n\r\n", 1)
            self.assertIn(b"101 Switching Protocols", headers)
            while len(frame) < 4:
                frame += client.recv(4096)
            marker = frame[1] & 0x7F
            if marker == 126:
                size = int.from_bytes(frame[2:4], "big")
                offset = 4
            elif marker == 127:
                while len(frame) < 10:
                    frame += client.recv(4096)
                size = int.from_bytes(frame[2:10], "big")
                offset = 10
            else:
                size = marker
                offset = 2
            while len(frame) < offset + size:
                frame += client.recv(4096)
            payload = json.loads(frame[offset:offset + size])
            self.assertEqual(payload["kind"], "workspace_snapshot")
            self.assertEqual(payload["workspace_generation"], 7)
        finally:
            client.close()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
