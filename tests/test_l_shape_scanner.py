"""Offline observer integration checks; all Scanner external effects mocked."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

import tests.test_telegram_delivery  # existing offline config/API stubs
import main
import l_shape_scanner as observer
from geometry.l_shape import detect_l_shape
from tests.test_l_shape_detector import _long_shape, _short_shape, _frame, _flat


def snapshot(closed):
    current = closed.iloc[-1:].copy()
    current["time"] += 300000
    current[["open", "high", "low", "close"]] = 9999.0
    return pd.concat([closed, current], ignore_index=True)


class LShapeObserverTests(unittest.TestCase):
    def test_real_detector_and_preview_use_closed_prefix_without_mutation(self):
        for closed in (_long_shape(), _short_shape()):
            with self.subTest(direction=detect_l_shape(closed).direction):
                candles = snapshot(closed)
                before = candles.copy(deep=True)
                with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as output:
                    result = observer.observe_l_shape("TESTUSDT", candles, timeframe="5", chart_dir=directory)
                    self.assertEqual(result["formation"], detect_l_shape(closed))
                    self.assertEqual(result["source_candle_time_ms"], int(closed.time.iloc[-1]))
                    chart = Path(result["chart_path"])
                    self.assertEqual(chart.parent, Path(directory) / "l_shape")
                    self.assertEqual(chart.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                    self.assertIn("L-SHAPE candidate", output.getvalue())
                assert_frame_equal(candles, before)

    def test_no_candidate_creates_no_chart(self):
        with patch.object(observer, "render_l_shape_preview") as render:
            self.assertIsNone(observer.observe_l_shape("TESTUSDT", snapshot(_frame(_flat(40, 100))), timeframe="5"))
            self.assertIsNone(observer.observe_l_shape("TESTUSDT", None, timeframe="5"))
        render.assert_not_called()

    def run_mock_pass(self, *, enabled, analysis, failure=None):
        candles = snapshot(_long_shape())
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "BYBITSCANNER_L_SHAPE_OBSERVATIONS": "1" if enabled else "0",
                "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "0",
            }))
            stack.enter_context(patch.object(main, "MAX_SYMBOLS", None))
            stack.enter_context(patch.object(main.config, "TELEGRAM_TEST_MODE", False))
            stack.enter_context(patch.object(main, "get_symbols", return_value=["TESTUSDT"]))
            stack.enter_context(patch.object(main, "analyze_symbol", return_value={"result": analysis, "data": candles}))
            observe = stack.enter_context(patch.object(observer, "observe_l_shape", side_effect=failure, return_value=None))
            lshape_send = stack.enter_context(patch.object(observer, "send_l_shape_observation", return_value=True))
            send = stack.enter_context(patch.object(main, "send_signal", return_value=True))
            stack.enter_context(patch.object(main, "send_message"))
            prepare = stack.enter_context(patch.object(main, "prepare_signal", return_value={"score": 90}))
            update = stack.enter_context(patch.object(main, "update_signal", return_value="NEW"))
            stack.enter_context(patch.object(main, "record_scanner_diary_observation", return_value=SimpleNamespace(setup_instance_id=None)))
            robot = stack.enter_context(patch("notification.create_signal_snapshot"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            main.run_scan_pass()
            robot.assert_not_called()
        return observe, lshape_send, send, prepare, update, candles

    def test_observer_runs_without_wedge_but_does_not_send_without_candidate(self):
        observe, lshape_send, send, prepare, update, candles = self.run_mock_pass(enabled=True, analysis=None)
        observe.assert_called_once_with("TESTUSDT", candles, timeframe=main.config.TIMEFRAME)
        lshape_send.assert_not_called()
        send.assert_not_called()
        prepare.assert_not_called()
        update.assert_not_called()

    def test_old_observer_flag_no_longer_hides_the_pattern(self):
        observe, lshape_send, send, _, _, _ = self.run_mock_pass(enabled=False, analysis=None)
        observe.assert_called_once()
        lshape_send.assert_not_called()
        send.assert_not_called()

    def test_observer_failure_preserves_existing_selection_and_delivery(self):
        analysis = {"pattern": "Falling Wedge", "final_score": 90, "signal": {"approved": True}}
        observe, lshape_send, send, prepare, update, _ = self.run_mock_pass(enabled=True, analysis=analysis, failure=RuntimeError("render failed"))
        observe.assert_called_once()
        lshape_send.assert_not_called()
        prepare.assert_called_once_with("TESTUSDT", analysis)
        update.assert_called_once_with({"score": 90})
        send.assert_called_once_with({**analysis, "symbol": "TESTUSDT"})

    def test_l_shape_candidate_sends_even_when_there_is_no_wedge(self):
        candles = snapshot(_long_shape())
        candidate = {"formation": SimpleNamespace(direction="LONG"), "chart_path": "chart.png"}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"BYBITSCANNER_L_SHAPE_OBSERVATIONS": "0", "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "0"}))
            stack.enter_context(patch.object(main, "MAX_SYMBOLS", None))
            stack.enter_context(patch.object(main.config, "TELEGRAM_TEST_MODE", False))
            stack.enter_context(patch.object(main, "get_symbols", return_value=["TESTUSDT"]))
            stack.enter_context(patch.object(main, "analyze_symbol", return_value={"result": None, "data": candles}))
            stack.enter_context(patch.object(observer, "observe_l_shape", return_value=candidate))
            deliver = stack.enter_context(patch.object(observer, "send_l_shape_observation", return_value=True))
            send_wedge = stack.enter_context(patch.object(main, "send_signal"))
            stack.enter_context(patch.object(main, "send_message"))
            robot = stack.enter_context(patch("notification.create_signal_snapshot"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            main.run_scan_pass()
        deliver.assert_called_once_with("TESTUSDT", candidate, timeframe=main.config.TIMEFRAME, test_mode=False)
        send_wedge.assert_not_called()
        robot.assert_not_called()



class LShapeTelegramTests(unittest.TestCase):
    def candidate(self):
        return {
            "formation": SimpleNamespace(direction="LONG"),
            "origin_time_ms": 1700000000000,
            "impulse_end_time_ms": 1700000300000,
            "source_candle_time_ms": 1700000600000,
            "chart_path": "charts/l_shape/TESTUSDT.png",
        }

    def test_normal_photo_owner_review_buttons_no_robot_and_dedup(self):
        memory = {}
        candidate = self.candidate()
        with patch.object(observer.config, "TELEGRAM_ENABLED", True), \
                patch.object(observer, "get_telegram_chat_ids", return_value=("owner", "friend")), \
                patch.object(observer, "get_telegram_owner_chat_id", return_value="owner"), \
                patch.object(observer, "load_memory", return_value=memory), \
                patch.object(observer, "save_memory") as save, \
                patch.object(observer, "send_photo", return_value={"ok": True}) as photo, \
                patch("notification.create_signal_snapshot") as robot:
            self.assertTrue(observer.send_l_shape_observation("TESTUSDT", candidate, timeframe="5"))
            self.assertFalse(observer.send_l_shape_observation("TESTUSDT", candidate, timeframe="5"))
        self.assertEqual(photo.call_count, 2)
        self.assertEqual(save.call_count, 2)
        robot.assert_not_called()
        owner, friend = photo.call_args_list
        self.assertEqual(owner.args[1], "owner")
        self.assertEqual(friend.args[1], "friend")
        self.assertEqual(owner.args[2], candidate["chart_path"])
        self.assertIn("TESTUSDT", owner.kwargs["caption"])
        self.assertIn("Г-образная · ↑", owner.kwargs["caption"])
        self.assertIn("Таймфрейм: 5м", owner.kwargs["caption"])
        owner_buttons = [b["text"] for row in owner.kwargs["reply_markup"]["inline_keyboard"] for b in row]
        self.assertIn("✅ Хороший", owner_buttons)
        self.assertIn("❌ Геометрия", owner_buttons)
        self.assertNotIn("🤖 Робот", owner_buttons)
        self.assertEqual(len(friend.kwargs["reply_markup"]["inline_keyboard"]), 1)

    def test_partial_delivery_retry_only_failed_recipient(self):
        memory = {}
        candidate = self.candidate()
        with patch.object(observer.config, "TELEGRAM_ENABLED", True), \
                patch.object(observer, "get_telegram_chat_ids", return_value=("owner", "friend")), \
                patch.object(observer, "get_telegram_owner_chat_id", return_value="owner"), \
                patch.object(observer, "load_memory", return_value=memory), \
                patch.object(observer, "save_memory"), \
                patch.object(observer, "send_photo", side_effect=[
                    {"ok": True}, {"ok": False}, {"ok": True},
                ]) as photo:
            self.assertFalse(observer.send_l_shape_observation("TESTUSDT", candidate, timeframe="5"))
            self.assertTrue(observer.send_l_shape_observation("TESTUSDT", candidate, timeframe="5"))
            self.assertFalse(observer.send_l_shape_observation("TESTUSDT", candidate, timeframe="5"))
        self.assertEqual([call.args[1] for call in photo.call_args_list], ["owner", "friend", "friend"])

    def test_test_mode_never_persists_signal_or_robot_candidate(self):
        with patch.object(observer.config, "TELEGRAM_ENABLED", True), \
                patch.object(observer, "get_telegram_chat_ids", return_value=("owner",)), \
                patch.object(observer, "get_telegram_owner_chat_id", return_value="owner"), \
                patch.object(observer, "load_memory", return_value={}), \
                patch.object(observer, "save_memory") as saved, \
                patch.object(observer, "send_photo", return_value={"ok": True}) as photo:
            self.assertTrue(observer.send_l_shape_observation("TESTUSDT", self.candidate(), timeframe="5", test_mode=True))
        saved.assert_not_called()
        self.assertIn("TEST MODE", photo.call_args.kwargs["caption"])


if __name__ == "__main__":
    unittest.main()
