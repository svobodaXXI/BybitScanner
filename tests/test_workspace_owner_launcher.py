import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tests.test_telegram_delivery  # installs the established offline config/API stubs
from notification import build_tradingview_keyboard
import signal_archive
import telegram_review
import workspace_owner_launcher as launcher

WINDOWS = {"SystemRoot": r"C:\Windows"}
GEOMETRY_TOKEN = {launcher.GEOMETRY_TOKEN_ENV: "g" * 32}
SIGNAL_ID = "f1c64eb70ca38440d7bc4140"


def rats_snapshot():
    """Shape of the saved 1000RATSUSDT 5m Rising Wedge frozen geometry."""
    return {
        "schema_version": 1, "signal_id": SIGNAL_ID,
        "symbol": "1000RATSUSDT", "timeframe": "5",
        "bars": [
            {"open_time_ms": 1000, "open": 10, "high": 12, "low": 8, "close": 11},
            {"open_time_ms": 2000, "open": 11, "high": 14, "low": 9, "close": 13},
        ],
        "boundaries": [
            {"boundary_id": "upper", "kind": "upper", "anchors": [
                {"bar_open_time_ms": 1000, "price": 12},
                {"bar_open_time_ms": 2000, "price": 14}]},
            {"boundary_id": "lower", "kind": "lower", "anchors": [
                {"bar_open_time_ms": 1000, "price": 8},
                {"bar_open_time_ms": 2000, "price": 9}]},
        ],
    }


class WorkspaceOwnerLauncherTests(unittest.TestCase):
    @patch.object(launcher, "os", SimpleNamespace(name="nt", environ=WINDOWS))
    @patch.object(launcher.subprocess, "Popen")
    @patch.object(launcher.Path, "is_file", return_value=True)
    def test_only_valid_target_reaches_launcher(self, file, popen):
        launcher.request_owner_workspace_open("EDITOR", "BTCUSDT", "5m")
        args = popen.call_args.args[0]
        self.assertIn("-Mode", args)
        self.assertIn("EDITOR", args)
        self.assertIn("BTCUSDT", args)
        self.assertIn("5m", args)

    @patch.object(launcher, "os", SimpleNamespace(name="nt", environ={**WINDOWS, **GEOMETRY_TOKEN}))
    @patch("signal_archive.load_frozen_signal_geometry", return_value={"signal_id": "signal:123"})
    @patch.object(launcher.subprocess, "Popen")
    @patch.object(launcher.Path, "is_file", return_value=True)
    def test_exact_signal_identity_is_forwarded(self, file, popen, frozen):
        launcher.request_owner_workspace_open("EDITOR", "BTCUSDT", "5m", "signal:123")
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("-SignalId") + 1], "signal:123")

    @patch.object(launcher.subprocess, "Popen")
    def test_bad_callback_never_launches(self, popen):
        for mode, symbol, timeframe in (
            ("ROBOT", "BTCUSDT", "5m"), ("EDITOR", "BTC;del", "5m"),
            ("EDITOR", "BTCUSDT", "1w")):
            with self.assertRaises(ValueError):
                launcher.request_owner_workspace_open(mode, symbol, timeframe)
        for signal_id in ("bad/id", "", "a" * 129):
            with self.assertRaises(ValueError):
                launcher.request_owner_workspace_open("EDITOR", "BTCUSDT", "5m", signal_id)
        popen.assert_not_called()


class EditorSignalPreflightTests(unittest.TestCase):
    """Telegram EDITOR for an archived signal must not fail silently on the PC."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {signal_archive.ARCHIVE_ENV: temp.name})
        env.start()
        self.addCleanup(env.stop)
        self.popen = patch.object(launcher.subprocess, "Popen").start()
        patch.object(launcher.Path, "is_file", return_value=True).start()
        self.addCleanup(patch.stopall)

    def press_editor(self, environ):
        callback = build_tradingview_keyboard(
            "1000RATSUSDT", "5", signal_id=SIGNAL_ID,
        )["inline_keyboard"][-1][0]["callback_data"]
        parsed = telegram_review._parse_workspace_callback(callback)
        with patch.object(launcher, "os", SimpleNamespace(name="nt", environ=environ)),                 patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback({"id": "cb"}, parsed)
        return answer.call_args.args

    def record(self, geometry):
        self.assertTrue(signal_archive.record_original_signal(
            SIGNAL_ID, symbol="1000RATSUSDT", timeframe="5", pattern="Rising Wedge",
            text="signal", image_bytes=b"png", geometry_snapshot=geometry,
        ))

    def test_missing_geometry_token_is_reported_instead_of_launching(self):
        self.record(rats_snapshot())
        answer = self.press_editor(dict(WINDOWS))
        self.popen.assert_not_called()
        self.assertEqual(answer, ("cb", telegram_review.WORKSPACE_UNAVAILABLE_TEXT[
            "signal_geometry_token_missing"]))

    def test_signal_without_frozen_geometry_is_reported(self):
        self.record(None)
        answer = self.press_editor({**WINDOWS, **GEOMETRY_TOKEN})
        self.popen.assert_not_called()
        self.assertEqual(answer, ("cb", telegram_review.WORKSPACE_UNAVAILABLE_TEXT[
            "frozen_geometry_missing"]))

    def test_authorized_frozen_signal_launches_system_powershell(self):
        self.record(rats_snapshot())
        answer = self.press_editor({**WINDOWS, **GEOMETRY_TOKEN})
        self.assertEqual(answer, ("cb", "Команда открытия передана на ПК"))
        args = self.popen.call_args.args[0]
        self.assertEqual(args[0], str(launcher.Path(r"C:\Windows") / "System32" /
                                      "WindowsPowerShell" / "v1.0" / "powershell.exe"))
        self.assertEqual(args[args.index("-Timeframe") + 1], "5m")
        self.assertEqual(args[args.index("-SignalId") + 1], SIGNAL_ID)
        self.assertNotIn("g" * 32, " ".join(args))


if __name__ == "__main__":
    unittest.main()
