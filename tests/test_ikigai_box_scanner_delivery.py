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
from tests.test_ikigai_box_detector import _two_impulses, _terminal_wick_two_impulses
from geometry.ikigai_box import detect_ikigai_box, detect_ikigai_box_watches
from geometry.ikigai_box_chart import ikigai_box_signal_text


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
        send_order = []

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
            side_effect=lambda symbol, *, timeframe: {"symbol": symbol, "result": None, "data": source if timeframe == "5" else None},
        ) as scan, patch.object(
            main, "send_message", return_value=True,
        ), patch.object(
            box, "render_ikigai_box_chart", side_effect=fake_render,
        ), patch.object(
            box, "send_message",
            side_effect=lambda *args: (send_order.append("text"), {"ok": True})[1],
        ) as text, patch.object(
            box, "send_photo",
            side_effect=lambda *args, **kwargs: (
                send_order.append("photo"), {"ok": True}
            )[1],
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

        self.assertEqual(scan.call_count, 4)
        self.assertEqual(photo.call_count, 1)
        text.assert_called_once()
        self.assertEqual(send_order, ["text", "photo"])
        self.assertEqual(len(plotted), 1)
        received_frame, formation, path = plotted[0]
        self.assertEqual(len(received_frame), len(source) - 1)
        self.assertLess(received_frame["high"].max(), 100_000)
        self.assertNotIn("_analysis.png", path)
        self.assertIn("ikigai_box", path)
        self.assertEqual(formation.direction, "SHORT")
        potential = (
            abs(formation.fibonacci_1_618 - formation.fibonacci_1_0)
            / formation.fibonacci_1_0 * 100
        )
        self.assertEqual(
            text.call_args.args[2],
            f"📡 Сканер: TESTUSDT\n"
            f"↑ Коробка Икигаи (+{potential:.2f}%)\n"
            "5м",
        )
        self.assertEqual(photo.call_args.kwargs["caption"], "")
        buttons = [
            button["text"]
            for row in photo.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertNotIn("🤖 Робот", buttons)
        robot.assert_not_called()
        self.assertEqual(len(history), 1)
        pd.testing.assert_frame_equal(source, original)

    def test_watch_ready_photo_is_distinct_and_never_creates_robot_candidate(self):
        history = {}
        frames, end = _terminal_wick_two_impulses(second=False)
        frames["time"] = [
            1_790_000_000_000 + i * 3_600_000
            for i in range(len(frames))
        ]
        watch = next(
            w for w in detect_ikigai_box_watches(frames)
            if w.anchor_identity == ("SHORT", 20, 23)
        )
        self.assertEqual(watch.phase, "BOX_READY")
        # Bybit returns one still-forming newest candle. Its extreme must
        # never alter WATCH's current frame, frozen anchor or chart.
        live = pd.concat([frames, pd.DataFrame([{
            "time": int(frames.iloc[-1]["time"]) + 3_600_000,
            "open": 1000, "high": 1001, "low": 999, "close": 1000,
        }])], ignore_index=True)
        with tempfile.TemporaryDirectory() as root, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(
            box, "send_message", return_value={"ok": True},
        ) as text, patch.object(
            box, "send_photo", return_value={"ok": True},
        ) as photo, patch.object(
            box, "load_memory", side_effect=lambda: dict(history),
        ), patch.object(
            box, "save_memory", side_effect=lambda v: history.update(v),
        ), patch("notification.create_signal_snapshot") as robot:
            self.assertTrue(box.send_ikigai_box_watch_observation(
                "HEIUSDT", live, watch, timeframe="60", chart_dir=root,
            ))
            self.assertFalse(box.send_ikigai_box_watch_observation(
                "HEIUSDT", live, watch, timeframe="60", chart_dir=root,
            ))
        photo.assert_called_once()
        sent = photo.call_args
        text.assert_called_once()
        self.assertEqual(
            text.call_args.args[2],
            ikigai_box_signal_text("HEIUSDT", "60", watch),
        )
        self.assertEqual(sent.kwargs["caption"], "")
        self.assertNotIn("_analysis.png", sent.args[2])
        self.assertIn("_WATCH_", sent.args[2])
        self.assertEqual(len(history), 1)
        robot.assert_not_called()

    def test_watch_invalid_or_zone_touched_is_not_telegram_signal(self):
        from dataclasses import replace
        frames, _ = _terminal_wick_two_impulses(second=False)
        frames["time"] = [
            1_790_000_000_000 + i * 3_600_000
            for i in range(len(frames))
        ]
        watch = next(
            w for w in detect_ikigai_box_watches(frames)
            if w.anchor_identity == ("SHORT", 20, 23)
        )
        live = pd.concat([frames, pd.DataFrame([{
            "time": int(frames.iloc[-1]["time"]) + 3_600_000,
            "open": 0.1400, "high": 0.1700,
            "low": 0.1398, "close": 0.1680,
        }])], ignore_index=True)
        with patch.object(box, "send_photo") as photo, patch.object(
            box, "render_ikigai_box_chart",
        ) as render, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ):
            self.assertFalse(box.send_ikigai_box_watch_observation(
                "HEIUSDT", live, replace(watch, anchor_end_price=0.150),
                timeframe="60",
            ))
            # Real data now includes an already touched extension, but caller
            # may still carry the earlier frozen WATCH: fail closed.
            touched = pd.concat([live, pd.DataFrame([{
                "time": int(live.iloc[-1]["time"]) + 3_600_000,
                "open": 0.168, "high": 0.170,
                "low": 0.167, "close": 0.169,
            }])], ignore_index=True)
            current_watch = replace(watch, as_of_index=len(touched)-2)
            self.assertFalse(box.send_ikigai_box_watch_observation(
                "HEIUSDT", touched, current_watch, timeframe="60",
            ))
        photo.assert_not_called()
        render.assert_not_called()

    def test_shared_review_buttons_are_owner_only_for_confirmed_and_watch(self):
        from contextlib import ExitStack
        frames, _ = _terminal_wick_two_impulses(second=False)
        frames["time"] = [1_790_000_000_000 + i * 300_000 for i in range(len(frames))]
        watch = next(w for w in detect_ikigai_box_watches(frames)
                     if w.anchor_identity == ("SHORT", 20, 23))
        live = pd.concat([frames, frames.iloc[[-1]]], ignore_index=True)
        for early in (False, True):
            with self.subTest(watch=early), ExitStack() as stack:
                stack.enter_context(patch.object(box, "get_telegram_chat_ids", return_value=("owner", "guest")))
                stack.enter_context(patch.object(box, "get_telegram_owner_chat_id", return_value="owner"))
                stack.enter_context(patch.object(box, "load_memory", return_value={}))
                saved = stack.enter_context(patch.object(box, "save_memory"))
                stack.enter_context(patch.object(box, "render_ikigai_box_chart"))
                text = stack.enter_context(patch.object(box, "send_message", return_value={"ok": True}))
                photo = stack.enter_context(patch.object(box, "send_photo", return_value={"ok": True}))
                robot = stack.enter_context(patch("notification.create_signal_snapshot"))
                if early:
                    result = box.send_ikigai_box_watch_observation(
                        "TESTUSDT", live, watch, timeframe="5", test_mode=True)
                else:
                    result = box.send_ikigai_box_observation(
                        "TESTUSDT", _candles(), timeframe="5", test_mode=True)
                self.assertTrue(result)
                expected_text = ikigai_box_signal_text(
                    "TESTUSDT", "5",
                    watch if early else detect_ikigai_box(_candles().iloc[:-1]),
                )
                self.assertEqual(text.call_count, 2)
                for index, call in enumerate(photo.call_args_list):
                    self.assertEqual(text.call_args_list[index].args[2], expected_text)
                    self.assertEqual(call.kwargs["caption"], "")
                    buttons = [b for row in call.kwargs["reply_markup"]["inline_keyboard"] for b in row]
                    callbacks = [b["callback_data"] for b in buttons if "callback_data" in b]
                    self.assertEqual(callbacks, [f"review:{action}:TESTUSDT:5" for action in
                                               ("queue", "good", "geometry", "anchor")] if index == 0 else [])
                    self.assertTrue(any("url" in b for b in buttons))
                saved.assert_not_called()
                robot.assert_not_called()

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

    def test_failed_text_does_not_send_photo_or_mark_delivery(self):
        with patch.object(box, "render_ikigai_box_chart"), patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(
            box, "send_message", return_value={"ok": False},
        ) as text, patch.object(
            box, "send_photo",
        ) as photo, patch.object(
            box, "load_memory", return_value={},
        ), patch.object(
            box, "save_memory",
        ) as save:
            self.assertFalse(box.send_ikigai_box_observation(
                "TESTUSDT", _candles(), timeframe="5",
            ))
        text.assert_called_once()
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
            box, "send_message", return_value={"ok": True},
        ) as text, patch.object(
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
        self.assertEqual(text.call_count, 2)
        self.assertEqual(
            photo.call_args_list[0].args[2],
            photo.call_args_list[1].args[2],
        )


if __name__ == "__main__":
    unittest.main()
