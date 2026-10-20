"""Editor deep link: signal_id through Telegram -> launcher, and frozen geometry conversion."""
import copy
import os
import sys
import types
import unittest
from unittest import mock

try:  # config.py is a local, untracked secrets file: tests never read it
    import config  # noqa: F401
except ImportError:
    sys.modules["config"] = types.SimpleNamespace(
        TELEGRAM_ENABLED=False, TELEGRAM_TOKEN="", TELEGRAM_CHAT_IDS=[], TELEGRAM_TEST_MODE=True,
        MAX_SYMBOLS=None,
    )

import signal_geometry_view as view
import workspace_owner_launcher
from tools import workspace_ready_delivery as delivery

SOURCE_TIME = 1_792_499_700_000
STEP = 5 * 60_000


def snapshot():
    """Same shape as a stored Scanner wedge snapshot (indices of a 200-candle window)."""
    current = 199
    return {
        "symbol": "AVAUSDT", "pattern": "Falling Wedge",
        "scanner_source_timeframe": "5",
        "scanner_source_candle_time_ms": SOURCE_TIME,
        "scanner_formation_id": f"{SOURCE_TIME - (current - 117) * STEP}:{SOURCE_TIME - (current - 123) * STEP}",
        "geometry": {
            "current_index": current,
            "upper_line": {"anchor_index": 117, "anchor_price": 0.2295, "second_index": 188,
                           "second_price": 0.2259, "slope": (0.2259 - 0.2295) / 71,
                           "intercept": 0.2295 - 117 * (0.2259 - 0.2295) / 71},
            "lower_line": {"anchor_index": 123, "anchor_price": 0.2265, "second_index": 176,
                           "second_price": 0.2247, "slope": (0.2247 - 0.2265) / 53,
                           "intercept": 0.2265 - 123 * (0.2247 - 0.2265) / 53},
        },
    }


class GeometryConversionTests(unittest.TestCase):
    def test_both_boundaries_get_proven_candle_open_times(self):
        result = view.build_signal_geometry("cid1", snapshot(), "a" * 64)
        upper, lower = result["boundaries"]
        self.assertEqual(upper["boundary_id"], "cid1:upper")
        self.assertEqual([a["bar_open_time_ms"] for a in upper["anchors"]],
                         [SOURCE_TIME - 82 * STEP, SOURCE_TIME - 11 * STEP])
        self.assertEqual([a["price"] for a in upper["anchors"]], [0.2295, 0.2259])
        self.assertEqual([a["bar_open_time_ms"] for a in lower["anchors"]],
                         [SOURCE_TIME - 76 * STEP, SOURCE_TIME - 23 * STEP])
        self.assertEqual(result["snapshot_revision"], "a" * 64)
        self.assertEqual(result["timeframe"], "5")

    def test_unproven_time_mapping_is_unavailable_not_approximated(self):
        broken = snapshot()
        broken["scanner_formation_id"] = "1:2"
        with self.assertRaises(view.SignalGeometryUnavailable) as caught:
            view.build_signal_geometry("cid1", broken, "a" * 64)
        self.assertEqual(caught.exception.reason, "index_time_mapping_unproven")

    def test_missing_identity_geometry_and_bad_pivot_fail_closed(self):
        for mutate, reason in (
            (lambda s: s.pop("scanner_formation_id"), "formation_identity_absent"),
            (lambda s: s.pop("geometry"), "geometry_absent"),
            (lambda s: s.__setitem__("scanner_source_timeframe", "1h"), "source_timeframe_unsupported"),
            (lambda s: s["geometry"]["upper_line"].__setitem__("second_price", 0.5), "upper_line_pivot_off_line"),
            (lambda s: s["geometry"]["lower_line"].pop("second_index"), "lower_line.second_index_invalid"),
        ):
            data = copy.deepcopy(snapshot())
            mutate(data)
            with self.assertRaises(view.SignalGeometryUnavailable) as caught:
                view.build_signal_geometry("cid1", data, "a" * 64)
            self.assertEqual(caught.exception.reason, reason)


class TelegramCallbackTests(unittest.TestCase):
    def test_keyboard_carries_signal_id_when_it_fits_and_drops_it_otherwise(self):
        import notification
        with mock.patch.object(notification, "create_tradingview_url", return_value="https://example.test/x"):
            short = notification.build_tradingview_keyboard("AVAUSDT", "5", robot_candidate_id="214529892adf5024932c8fb8")
            data = [b["callback_data"] for row in short["inline_keyboard"] for b in row if b.get("callback_data", "").startswith("workspace:")]
            self.assertEqual(data, ["workspace:EDITOR:AVAUSDT:5m:214529892adf5024932c8fb8",
                                    "workspace:TERMINAL:AVAUSDT:5m:214529892adf5024932c8fb8"])
            self.assertTrue(all(len(item.encode()) <= 64 for item in data))
            long_symbol = "A" * 28 + "USDT"
            overlong = notification.build_tradingview_keyboard(long_symbol, "5", robot_candidate_id="214529892adf5024932c8fb8")
            data = [b["callback_data"] for row in overlong["inline_keyboard"] for b in row if b.get("callback_data", "").startswith("workspace:")]
            self.assertEqual(data[0], f"workspace:EDITOR:{long_symbol}:5m")
            colon = notification.build_tradingview_keyboard("AVAUSDT", "5", robot_candidate_id="BOX:1")
            data = [b["callback_data"] for row in colon["inline_keyboard"] for b in row if b.get("callback_data", "").startswith("workspace:")]
            self.assertEqual(data[0], "workspace:EDITOR:AVAUSDT:5m")

    def test_callback_parser_accepts_legacy_and_signal_forms_only(self):
        import telegram_review
        parse = telegram_review._parse_workspace_callback
        self.assertEqual(parse("workspace:EDITOR:AVAUSDT:5m")["signal_id"], None)
        self.assertEqual(parse("workspace:EDITOR:AVAUSDT:5m:abc123")["signal_id"], "abc123")
        for bad in ("workspace:EDITOR:AVAUSDT:5m:", "workspace:EDITOR:AVAUSDT:5m:a b",
                    "workspace:EDITOR:AVAUSDT:5m:a:b", "workspace:EDITOR:AVAUSDT:5m:" + "x" * 65,
                    "workspace:SHELL:AVAUSDT:5m:abc"):
            self.assertIsNone(parse(bad), bad)

    def test_launcher_passes_validated_signal_id_to_the_owner_script(self):
        with mock.patch.object(workspace_owner_launcher.os, "name", "nt"), \
                mock.patch.object(workspace_owner_launcher.subprocess, "Popen") as popen:
            workspace_owner_launcher.request_owner_workspace_open("EDITOR", "AVAUSDT", "5m", "abc123")
            argv = popen.call_args.args[0]
            self.assertEqual(argv[-2:], ["-SignalId", "abc123"])
            popen.reset_mock()
            workspace_owner_launcher.request_owner_workspace_open("EDITOR", "AVAUSDT", "5m")
            self.assertNotIn("-SignalId", popen.call_args.args[0])
            with self.assertRaises(ValueError):
                workspace_owner_launcher.request_owner_workspace_open("EDITOR", "AVAUSDT", "5m", "a;b")


class MobileDeliveryContractTests(unittest.TestCase):
    def test_missing_https_infrastructure_is_named_and_creates_no_qr(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIn("BYBITSCANNER_TERMINAL_HTTPS_URL", delivery.missing_requirements())
            self.assertFalse(delivery.deliver_if_verified("EDITOR", "AVAUSDT", "5m", signal_id="abc"))

    def test_localhost_link_is_never_a_mobile_link(self):
        import workspace_ready_link
        with self.assertRaises(ValueError):
            workspace_ready_link.workspace_link("https://localhost", "EDITOR", "AVAUSDT", "5m", "abc")
        with self.assertRaises(ValueError):
            workspace_ready_link.workspace_link("http://127.0.0.1:4173", "EDITOR", "AVAUSDT", "5m", "abc")
        url = workspace_ready_link.workspace_link("https://terminal.example.org", "EDITOR", "AVAUSDT", "5m", "abc")
        self.assertIn("signal_id=abc", url)


if __name__ == "__main__":
    unittest.main()
