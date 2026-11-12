"""Local publicTrade SHADOW observation uses one shared Robot feature layer."""
import unittest
from unittest.mock import patch

from research.robot_entry_flow_live import LocalRobotFlowShadow, MINUTE_MS


class FakeContext:
    def __init__(self):
        self.symbol = "ICNTUSDT"
        self.reconnect_count = 0
        self.trades_subscription_state = "SUBSCRIBED"
        self.trade_bootstrap_complete = True
        self.trade_listeners = {}
        self.disconnect_listeners = {}

    def add_trade_listener(self, name, callback):
        self.trade_listeners[name] = callback

    def remove_trade_listener(self, name):
        self.trade_listeners.pop(name, None)

    def add_disconnect_listener(self, name, callback):
        self.disconnect_listeners[name] = callback

    def remove_disconnect_listener(self, name):
        self.disconnect_listeners.pop(name, None)

    def emit(self, data, received):
        for callback in tuple(self.trade_listeners.values()):
            callback({"data": data}, received)

    def disconnect(self):
        self.reconnect_count += 1
        self.trades_subscription_state = "DISCONNECTED"
        self.trade_bootstrap_complete = False
        for callback in tuple(self.disconnect_listeners.values()):
            callback(self.reconnect_count, "TEST")

    def ready(self):
        self.trades_subscription_state = "SUBSCRIBED"
        self.trade_bootstrap_complete = True


def print_at(identifier, ms, side, price, size):
    return {
        "s": "ICNTUSDT", "i": identifier, "T": ms,
        "S": side, "p": price, "v": size,
    }


class LocalFlowShadowTests(unittest.TestCase):
    def test_native_trades_emit_only_after_complete_consecutive_windows(self):
        ctx = FakeContext()
        shadow = LocalRobotFlowShadow(ctx, started_at_ms=0)
        ctx.emit([print_at("pre", 10, "Sell", "1", "999")], 20)
        self.assertIsNone(shadow.latest_transition)  # attach-mid-minute quarantined

        ctx.emit([print_at("a", MINUTE_MS+10, "Sell", "1", "200")], MINUTE_MS+20)
        ctx.emit([print_at("b", 2*MINUTE_MS+10, "Buy", "1.0", "300"),
                  print_at("c", 2*MINUTE_MS+20, "Buy", "1.01", "100")],
                 2*MINUTE_MS+30)
        self.assertIsNone(shadow.latest_transition)
        ctx.emit([print_at("d", 3*MINUTE_MS+10, "Buy", "1.02", "1")],
                 3*MINUTE_MS+20)
        transition = shadow.latest_transition
        self.assertTrue(transition.buy_wave_accelerating)
        self.assertEqual(transition.known_at_ms, 3*MINUTE_MS+20)
        self.assertEqual(shadow.observed_windows, 1)
        self.assertEqual(shadow.coverage, "OBSERVED_WS_FRAMES_NOT_COMPLETE_EXCHANGE_TAPE")
        shadow.close()
        self.assertFalse(ctx.trade_listeners)
        self.assertFalse(ctx.disconnect_listeners)

    def test_disconnection_resets_continuity_and_produces_no_stale_signal(self):
        ctx = FakeContext()
        shadow = LocalRobotFlowShadow(ctx, started_at_ms=0)
        ctx.emit([print_at("a", MINUTE_MS+10, "Sell", "1", "100")], MINUTE_MS+20)
        ctx.disconnect()
        ctx.ready()
        ctx.emit([print_at("b", 2*MINUTE_MS+10, "Buy", "1", "200")], 2*MINUTE_MS+20)
        ctx.emit([print_at("c", 3*MINUTE_MS+10, "Buy", "1.01", "100")], 3*MINUTE_MS+20)
        self.assertIsNone(shadow.latest_transition)
        shadow.close()

    def test_long_reconnect_gap_quarantines_first_received_minute(self):
        ctx = FakeContext()
        shadow = LocalRobotFlowShadow(ctx, started_at_ms=0)
        ctx.emit([print_at("a", MINUTE_MS+10, "Sell", "1", "100")], MINUTE_MS+20)
        ctx.disconnect()
        ctx.ready()
        # First received minute after a long break is never trusted.
        ctx.emit([print_at("rejoined", 10*MINUTE_MS+10, "Buy", "1", "1000")],
                 10*MINUTE_MS+20)
        ctx.emit([print_at("b", 11*MINUTE_MS+10, "Sell", "1", "100")],
                 11*MINUTE_MS+20)
        ctx.emit([print_at("c", 12*MINUTE_MS+10, "Buy", "1", "300"),
                  print_at("d", 12*MINUTE_MS+20, "Buy", "1.01", "100")],
                 12*MINUTE_MS+30)
        self.assertIsNone(shadow.latest_transition)
        ctx.emit([print_at("e", 13*MINUTE_MS+10, "Buy", "1", "10")],
                 13*MINUTE_MS+20)
        self.assertTrue(shadow.latest_transition.buy_wave_accelerating)
        self.assertEqual(shadow.observed_windows, 1)
        shadow.close()

    def test_invalid_duplicate_and_big_packet_quarantine_unknown(self):
        ctx = FakeContext()
        shadow = LocalRobotFlowShadow(ctx, started_at_ms=0)
        ctx.emit([print_at("x", MINUTE_MS+10, "Sell", "1", "2")], MINUTE_MS+20)
        ctx.emit([print_at("x", MINUTE_MS+10, "Sell", "1", "2")], MINUTE_MS+30)
        self.assertIsNone(shadow.latest_transition)
        ctx.emit([print_at("bad", 2*MINUTE_MS+10, "Wrong", "1", "2")], 2*MINUTE_MS+20)
        self.assertIsNone(shadow.latest_transition)
        with patch("research.robot_entry_flow_live.MAX_PACKET_PRINTS", 1):
            ctx.emit([print_at("x1", 3*MINUTE_MS+10, "Buy", "1", "2"),
                      print_at("x2", 3*MINUTE_MS+11, "Buy", "1", "2")], 3*MINUTE_MS+20)
        self.assertIsNone(shadow.latest_transition)
        shadow.close()

    def test_missing_market_minute_does_not_invent_continuation(self):
        ctx = FakeContext()
        shadow = LocalRobotFlowShadow(ctx, started_at_ms=0)
        ctx.emit([print_at("a", MINUTE_MS+10, "Sell", "1", "20")], MINUTE_MS+20)
        ctx.emit([print_at("b", 3*MINUTE_MS+10, "Buy", "1", "20")], 3*MINUTE_MS+20)
        self.assertIsNone(shadow.latest_transition)
        ctx.emit([print_at("c", 4*MINUTE_MS+10, "Buy", "1.01", "30")], 4*MINUTE_MS+20)
        self.assertIsNone(shadow.latest_transition)
        shadow.close()

    def test_bad_receive_clock_and_unhealthy_hub_are_ignored(self):
        ctx = FakeContext()
        shadow = LocalRobotFlowShadow(ctx, started_at_ms=0)
        ctx.trade_bootstrap_complete = False
        ctx.emit([print_at("a", MINUTE_MS+10, "Buy", "1", "100")], MINUTE_MS+20)
        ctx.ready()
        ctx.emit([print_at("b", 2*MINUTE_MS+10, "Buy", "1", "100")], 2*MINUTE_MS+20)
        ctx.emit([print_at("future", 4*MINUTE_MS+10, "Buy", "1", "100")],
                 3*MINUTE_MS+20)
        self.assertIsNone(shadow.latest_transition)
        shadow.close()
