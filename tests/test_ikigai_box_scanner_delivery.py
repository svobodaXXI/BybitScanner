"""End-to-end opt-in Scanner/Telegram observation tests (no network or PAPER DB)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

# Reuse existing import-time config/bybit stubs rather than reading local secrets.
import tests.test_telegram_delivery  # noqa: F401
import main
import ikigai_box_scanner as box
from tests.test_ikigai_box_detector import _two_impulses


def _candles():
    frame, _, _ = _two_impulses(second_steps=7)
    frame["time"] = [
        1_790_000_000_000 + n * 300_000 for n in range(len(frame))
    ]
    # Simulate Bybit's current, still-open candle: extreme high must never
    # change the first impulse anchor or be sent to the detector/renderer.
    frame.loc[len(frame)] = dict(
        time=int(frame.iloc[-1]["time"]) + 300_000,
        open=100_000, high=100_001, low=99_999, close=100_000,
    )
    return frame


class IkigaiBoxTelegramBridgeTests(unittest.TestCase):
    def test_actual_scanner_without_wedge_sends_photo_once_and_no_robot(self):
        source = _candles()
        original = source.copy(deep=True)
        history = {}
        plotted = []

        def fake_render(frame, formation, path, **kwargs):
            plotted.append((frame.copy(), formation, path))
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fresh-ikigai-image")
            return target

        real_sender = box.send_ikigai_box_observation
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"BYBITSCANNER_IKIGAI_BOX_SIGNALS": "1"}
        ), patch.object(main, "get_symbols", return_value=["TESTUSDT"]), patch.object(
            main, "analyze_symbol",
            return_value={"symbol": "TESTUSDT", "result": None, "data": source},
        ) as scan, patch.object(
            main, "send_message", return_value=True,
        ), patch.object(
            box, "render_ikigai_box_chart", side_effect=fake_render,
        ), patch.object(
            box, "send_photo", return_value={"ok": True},
        ) as photo, patch.object(
            box, "load_memory", side_effect=lambda: dict(history),
        ), patch.object(
            box, "save_memory", side_effect=lambda record: history.update(record),
        ), patch.object(box, "get_telegram_chat_ids", return_value=("owner",)), patch(
            "notification.create_signal_snapshot",
        ) as robot:
            # Actual Scanner integration; temporary chart root can be passed by
            # patching the module's default function call below.
            def send_under_test(symbol, candles, *, timeframe, test_mode=False):
                return real_sender(
                    symbol, candles, timeframe=timeframe,
                    test_mode=test_mode, chart_dir=folder,
                )

            with patch.object(box, "send_ikigai_box_observation", side_effect=send_under_test):
                main.run_scan_pass()
                main.run_scan_pass()

        self.assertEqual(scan.call_count, 2)
        self.assertEqual(photo.call_count, 1)
        self.assertEqual(len(plotted), 1)
        received_frame, formation, path = plotted[0]
        self.assertEqual(len(received_frame), len(source) - 1)
        self.assertLess(received_frame["high"].max(), 100_000)
        self.assertNotIn("_analysis.png", path)
        self.assertIn("ikigai_box", path)
        self.assertEqual(formation.direction, "SHORT")
        self.assertIn("1.618", photo.call_args.kwargs["caption"])
        self.assertIn("Наблюдение", photo.call_args.kwargs["caption"])
        buttons = [
            button["text"]
            for row in photo.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertNotIn("🤖 Робот", buttons)
        robot.assert_not_called()
        self.assertEqual(len(history), 1)
        pd.testing.assert_frame_equal(source, original)

    def test_opt_in_off_preserves_old_scanner_behavior(self):
        with patch.dict(os.environ, {"BYBITSCANNER_IKIGAI_BOX_SIGNALS": "0"}), patch.object(
            main, "get_symbols", return_value=["TESTUSDT"],
        ), patch.object(
            main, "analyze_symbol",
            return_value={"symbol": "TESTUSDT", "result": None, "data": _candles()},
        ), patch.object(main, "send_message", return_value=True), patch.object(
            box, "send_ikigai_box_observation",
        ) as sending:
            main.run_scan_pass()
        sending.assert_not_called()

    def test_render_failure_never_sends_stale_file(self):
        source = _candles()
        with patch.object(box, "render_ikigai_box_chart",
                          side_effect=RuntimeError("render failed")), patch.object(
            box, "send_photo",
        ) as photo, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(box, "load_memory", return_value={}), patch.object(
            box, "save_memory",
        ) as save:
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                box.send_ikigai_box_observation(
                    "TESTUSDT", source, timeframe="5",
                )
        photo.assert_not_called()
        save.assert_not_called()

    def test_failed_delivery_does_not_mark_candidate_as_delivered(self):
        source = _candles()
        seen = {}
        def fake_render(frame, formation, path, **kwargs):
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fresh")
            return target

        with tempfile.TemporaryDirectory() as directory, patch.object(
            box, "render_ikigai_box_chart", side_effect=fake_render,
        ), patch.object(box, "get_telegram_chat_ids", return_value=("owner",)), patch.object(
            box, "send_photo", side_effect=[{"ok": False}, {"ok": True}],
        ) as photo, patch.object(box, "load_memory",
                               side_effect=lambda: dict(seen)), patch.object(
            box, "save_memory", side_effect=lambda row: seen.update(row),
        ):
            for expected in (False, True):
                result = box.send_ikigai_box_observation(
                    "TESTUSDT", source, timeframe="5",
                    chart_dir=directory,
                )
                self.assertEqual(result, expected)
                self.assertEqual(bool(seen), expected)
        self.assertEqual(photo.call_count, 2)
        self.assertEqual(
            photo.call_args_list[0].args[2],
            photo.call_args_list[1].args[2],
        )


if __name__ == "__main__":
    unittest.main()
