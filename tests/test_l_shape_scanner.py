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
            observe = stack.enter_context(patch.object(observer, "observe_l_shape", side_effect=failure))
            send = stack.enter_context(patch.object(main, "send_signal", return_value=True))
            stack.enter_context(patch.object(main, "send_message"))
            prepare = stack.enter_context(patch.object(main, "prepare_signal", return_value={"score": 90}))
            update = stack.enter_context(patch.object(main, "update_signal", return_value="NEW"))
            stack.enter_context(patch.object(main, "record_scanner_diary_observation", return_value=SimpleNamespace(setup_instance_id=None)))
            robot = stack.enter_context(patch("notification.create_signal_snapshot"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            main.run_scan_pass()
            robot.assert_not_called()
        return observe, send, prepare, update, candles

    def test_observer_runs_without_wedge_and_never_delivers_a_signal(self):
        observe, send, prepare, update, candles = self.run_mock_pass(enabled=True, analysis=None)
        observe.assert_called_once_with("TESTUSDT", candles, timeframe=main.config.TIMEFRAME)
        send.assert_not_called()
        prepare.assert_not_called()
        update.assert_not_called()

    def test_disabled_observer_is_not_called(self):
        observe, send, _, _, _ = self.run_mock_pass(enabled=False, analysis=None)
        observe.assert_not_called()
        send.assert_not_called()

    def test_observer_failure_preserves_existing_selection_and_delivery(self):
        analysis = {"pattern": "Falling Wedge", "final_score": 90, "signal": {"approved": True}}
        observe, send, prepare, update, _ = self.run_mock_pass(enabled=True, analysis=analysis, failure=RuntimeError("render failed"))
        observe.assert_called_once()
        prepare.assert_called_once_with("TESTUSDT", analysis)
        update.assert_called_once_with({"score": 90})
        send.assert_called_once_with({**analysis, "symbol": "TESTUSDT"})


if __name__ == "__main__":
    unittest.main()
