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
        self.assertNotEqual(socket.messages[0]["req_id"], socket.messages[1]["req_id"])

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

    def test_rejected_book_subscription_ack_disables_capture_and_allows_retry(self):
        socket = _WebSocket()
        hub = _hub(socket)
        passive = hub.subscribe_flow_only("BTCUSDT")
        original_trade_source = passive.impulse_observation
        hub.subscribe_flow_only("BTCUSDT", capture_book=True)
        passive.book_frames.append((1, {"type": "snapshot"}))

        hub._dispatch({
            "op": "subscribe",
            "req_id": socket.messages[1]["req_id"],
            "success": False,
        })
        self.assertFalse(passive.capture_book)
        self.assertEqual(list(passive.book_frames), [])
        self.assertIs(passive.impulse_observation, original_trade_source)

        self.assertIs(hub.subscribe_flow_only("BTCUSDT", capture_book=True), passive)
        self.assertTrue(passive.capture_book)
        self.assertEqual(
            [message["args"] for message in socket.messages],
            [
                ["publicTrade.BTCUSDT"],
                ["orderbook.200.BTCUSDT"],
                ["orderbook.200.BTCUSDT"],
            ],
        )

    def test_disconnected_upgrade_is_used_by_next_full_reconnect_subscribe(self):
        hub = _hub()
        passive = hub.subscribe_flow_only("BTCUSDT")
        self.assertIs(hub.subscribe_flow_only("BTCUSDT", capture_book=True), passive)
        self.assertTrue(passive.capture_book)
        self.assertEqual(passive.topics(), [
            "publicTrade.BTCUSDT", "orderbook.200.BTCUSDT",
        ])

    def test_positive_acks_are_independent_of_data_and_old_request(self):
        socket = _WebSocket()
        hub = _hub(socket)
        passive = hub.subscribe_flow_only("BTCUSDT", capture_book=True)
        old_request = socket.messages[-1]["req_id"]
        hub.release_flow_only("BTCUSDT")
        passive = hub.subscribe_flow_only("BTCUSDT", capture_book=True)
        current_request = socket.messages[-1]["req_id"]
        self.assertNotEqual(old_request, current_request)
        hub._dispatch({"op": "subscribe", "req_id": old_request, "success": True})
        self.assertEqual(hub.private_passive_wedge_snapshot(passive)["subscription_acks"], {})
        hub._dispatch({"topic": "publicTrade.BTCUSDT", "data": [
            {"i": "1", "s": "BTCUSDT", "T": 1000, "seq": 1,
             "S": "Buy", "p": "100", "v": "1"}]})
        self.assertEqual(hub.private_passive_wedge_snapshot(passive)["subscription_acks"], {})
        hub._dispatch({"op": "subscribe", "req_id": current_request, "success": True})
        receipt = hub.private_passive_wedge_snapshot(passive)
        self.assertEqual(set(receipt["subscription_acks"]),
                         {"publicTrade.BTCUSDT", "orderbook.200.BTCUSDT"})
        hub._send_flow_only(socket, passive)
        self.assertEqual(hub.private_passive_wedge_snapshot(passive)["subscription_acks"], {})
        hub._dispatch({"op": "subscribe", "req_id": current_request, "success": True})
        self.assertEqual(hub.private_passive_wedge_snapshot(passive)["subscription_acks"], {})

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
