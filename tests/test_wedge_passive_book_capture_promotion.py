"""Regression tests for same-symbol passive Wedge book capture promotion.

Research-only WebSocket subscribe behavior; no Robot admission or trading.
"""
import json
from types import SimpleNamespace
import unittest

from terminal.market_data.hub import MarketDataHub


class _Registry:
    def get(self, symbol):
        return SimpleNamespace(symbol=symbol)


class _WebSocket:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send(self, raw):
        if self.fail:
            raise OSError("simulated unavailable socket")
        self.messages.append(json.loads(raw))


def _hub(socket=None):
    hub = MarketDataHub(_Registry(), lambda *_: None)
    hub._ws = socket
    return hub


class PassiveBookCapturePromotionTests(unittest.TestCase):
    def test_promote_same_symbol_without_restarting_trade_source(self):
        socket = _WebSocket()
        hub = _hub(socket)
        passive = hub.subscribe_flow_only("BTCUSDT")
        source = passive.impulse_observation
        self.assertFalse(passive.capture_book)
        self.assertEqual(socket.messages[0]["args"], ["publicTrade.BTCUSDT"])

        upgraded = hub.subscribe_flow_only("BTCUSDT", capture_book=True)
        self.assertIs(upgraded, passive)
        self.assertIs(upgraded.impulse_observation, source)
        self.assertTrue(upgraded.capture_book)
        self.assertEqual(len(socket.messages), 2)
        self.assertEqual(socket.messages[1]["op"], "subscribe")
        self.assertEqual(socket.messages[1]["args"], ["orderbook.200.BTCUSDT"])
        self.assertTrue(socket.messages[1]["req_id"].startswith("flowbook:"))

        frame = {"topic": "orderbook.200.BTCUSDT", "type": "snapshot", "data": {"u": 1}}
        hub._dispatch(frame)
        self.assertEqual([entry[1] for entry in passive.book_frames], [frame])
        self.assertIs(hub.subscribe_flow_only("BTCUSDT", capture_book=True), passive)
        self.assertEqual(len(socket.messages), 2, "repeat must not duplicate L2 subscribe")

    def test_failed_upgrade_does_not_claim_book_capture_and_can_retry(self):
        socket = _WebSocket()
        hub = _hub(socket)
        passive = hub.subscribe_flow_only("BTCUSDT")
        socket.fail = True
        self.assertIs(hub.subscribe_flow_only("BTCUSDT", capture_book=True), passive)
        self.assertFalse(passive.capture_book)
        self.assertEqual(len(socket.messages), 1)
        socket.fail = False
        hub.subscribe_flow_only("BTCUSDT", capture_book=True)
        self.assertTrue(passive.capture_book)
        self.assertEqual(socket.messages[-1]["args"], ["orderbook.200.BTCUSDT"])

    def test_disconnected_upgrade_is_used_by_next_full_reconnect_subscribe(self):
        hub = _hub()
        passive = hub.subscribe_flow_only("BTCUSDT")
        self.assertIs(hub.subscribe_flow_only("BTCUSDT", capture_book=True), passive)
        self.assertTrue(passive.capture_book)
        self.assertEqual(passive.topics(), [
            "publicTrade.BTCUSDT", "orderbook.200.BTCUSDT",
        ])

    def test_existing_protected_context_is_never_replaced(self):
        socket = _WebSocket()
        hub = _hub(socket)
        protected = object()
        hub._contexts["BTCUSDT"] = protected
        self.assertIs(hub.subscribe_flow_only("BTCUSDT", capture_book=True), protected)
        self.assertEqual(socket.messages, [])
        self.assertEqual(hub._flow_only, {})


if __name__ == "__main__":
    unittest.main()
