"""Scanner WATCH delivery cursor acceptance: no network, PAPER or live runtime."""

import os
import unittest
from unittest.mock import patch

import pandas as pd

import tests.test_telegram_delivery  # noqa: F401  existing offline stubs
import main
import ikigai_box_watch_stream as stream
from tests.test_ikigai_box_detector import _terminal_wick_two_impulses


def _historical_frame():
    frame, box_end = _terminal_wick_two_impulses(second=False)
    frame["time"] = [
        1_790_000_000_000 + n * 3_600_000
        for n in range(len(frame))
    ]
    return frame, box_end


def _bybit_snapshot(frame, last_closed):
    latest = frame.iloc[:last_closed + 1].copy()
    latest = pd.concat([latest, pd.DataFrame([{
        "time": int(latest.iloc[-1]["time"]) + 3_600_000,
        "open": 100000, "high": 100001,
        "low": 99999, "close": 100000,
    }])], ignore_index=True)
    return latest


class IkigaiBoxWatchStreamTests(unittest.TestCase):
    def setUp(self):
        stream._WATCH_CURSORS.clear()

    def tearDown(self):
        stream._WATCH_CURSORS.clear()

    def test_watch_first_appears_on_fresh_closed_shelf_without_robot(self):
        frame, end = _historical_frame()
        sent = []
        def record(symbol, candles, watch, **kwargs):
            sent.append((watch, candles.copy()))
            return True

        with patch.object(
            stream, "send_ikigai_box_watch_observation", side_effect=record,
        ):
            # Cold start at the end of the first impulse; do not emit stale
            # candidates or peek at the unfinished candle.
            self.assertFalse(stream.process_ikigai_box_watches(
                "HEIUSDT", _bybit_snapshot(frame, 23), timeframe="60",
            ))
            for closed_end in range(24, end + 1):
                snapshot = _bybit_snapshot(frame, closed_end)
                stream.process_ikigai_box_watches(
                    "HEIUSDT", snapshot, timeframe="60",
                )
                if closed_end == end:
                    self.assertFalse(stream.process_ikigai_box_watches(
                        "HEIUSDT", snapshot, timeframe="60",
                    ))
        watches = [w for w, _ in sent if w.anchor_identity == ("SHORT", 20, 23)]
        self.assertTrue(watches)
        self.assertEqual(watches[0].phase, "BOX_READY")
        self.assertLess(watches[0].as_of_index, end + 1)
        self.assertLess(watches[0].fibonacci_1_0,
                        watches[0].fibonacci_1_618)
        self.assertEqual(stream._WATCH_CURSORS[("HEIUSDT", "60")]["end_index"], end)

    def test_frozen_watch_survives_reentry_with_rolling_window(self):
        frame, end = _historical_frame()
        continued = pd.concat([frame, pd.DataFrame([
            {"time": int(frame.iloc[-1]["time"]) + 3_600_000,
             "open": 0.1400, "high": 0.14560,
             "low": 0.1398, "close": 0.14412},
            {"time": int(frame.iloc[-1]["time"]) + 7_200_000,
             "open": 0.14412, "high": 0.1450,
             "low": 0.1390, "close": 0.1400},
            {"time": int(frame.iloc[-1]["time"]) + 10_800_000,
             "open": 0.1400, "high": 0.1410,
             "low": 0.1390, "close": 0.1402},
        ])], ignore_index=True)
        with patch.object(
            stream, "send_ikigai_box_watch_observation", return_value=True,
        ):
            for closed_end in range(23, end + 4):
                snapshot = _bybit_snapshot(continued, closed_end)
                # A real rolling 200-candle Bybit snapshot drops old candles.
                if closed_end >= end + 2:
                    snapshot = snapshot.iloc[1:].reset_index(drop=True)
                stream.process_ikigai_box_watches(
                    "HEIUSDT", snapshot, timeframe="60",
                )
        state = stream._WATCH_CURSORS[("HEIUSDT", "60")]
        target = next(w for w in state["watches"]
                      if w.anchor_start_price == 0.12911
                      and w.anchor_end_price == 0.15198)
        self.assertEqual(target.phase, "BOX_BREAK_OBSERVED")
        self.assertEqual(target.box_high, 0.1420)
        self.assertEqual(target.first_box_exit_index, end + 1 - 1)
        self.assertEqual(target.box_end_index, end - 1)

    def test_gap_or_cold_start_never_backfills_watch_alert(self):
        frame, end = _historical_frame()
        with patch.object(
            stream, "send_ikigai_box_watch_observation",
            return_value=True,
        ) as notify:
            self.assertFalse(stream.process_ikigai_box_watches(
                "HEIUSDT", _bybit_snapshot(frame, end), timeframe="60",
            ))
            # Repeated scan same candle.
            self.assertFalse(stream.process_ikigai_box_watches(
                "HEIUSDT", _bybit_snapshot(frame, end), timeframe="60",
            ))
            gap = pd.concat([frame, pd.DataFrame([
                {"time": int(frame.iloc[-1]["time"]) + 3_600_000,
                 "open": 0.1400, "high": 0.1456,
                 "low": 0.1398, "close": 0.14412},
                {"time": int(frame.iloc[-1]["time"]) + 7_200_000,
                 "open": 0.14412, "high": 0.1460,
                 "low": 0.1430, "close": 0.1450},
            ])], ignore_index=True)
            self.assertFalse(stream.process_ikigai_box_watches(
                "HEIUSDT", _bybit_snapshot(gap, end + 2), timeframe="60",
            ))
        notify.assert_not_called()

    def test_revised_closed_candle_discards_pending_delivery(self):
        frame, end = _historical_frame()
        with patch.object(
            stream, "send_ikigai_box_watch_observation", return_value=False,
        ) as notify:
            stream.process_ikigai_box_watches(
                "HEIUSDT", _bybit_snapshot(frame, 23), timeframe="60",
            )
            last_end = None
            for closed_end in range(24, end + 1):
                snapshot = _bybit_snapshot(frame, closed_end)
                stream.process_ikigai_box_watches(
                    "HEIUSDT", snapshot, timeframe="60",
                )
                if stream._WATCH_CURSORS[("HEIUSDT", "60")]["pending"]:
                    last_end = closed_end
                    break
            self.assertIsNotNone(last_end)
            attempts_before = notify.call_count
            revised = _bybit_snapshot(frame, last_end)
            revised.loc[len(revised) - 2, "high"] += 0.0001
            self.assertFalse(stream.process_ikigai_box_watches(
                "HEIUSDT", revised, timeframe="60",
            ))
            self.assertEqual(notify.call_count, attempts_before)
            self.assertIsNone(
                stream._WATCH_CURSORS[("HEIUSDT", "60")]["pending"]
            )

    def test_main_opt_in_watch_runs_alongside_the_confirmed_box_sender(self):
        frame, end = _historical_frame()
        snapshot = _bybit_snapshot(frame, end)
        with patch.dict(os.environ, {
            "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "1",
            "BYBITSCANNER_IKIGAI_BOX_WATCH": "1",
        }), patch.object(main, "get_symbols", return_value=["HEIUSDT"]), patch.object(
            main, "analyze_symbol",
            return_value={"symbol": "HEIUSDT", "result": None, "data": snapshot},
        ), patch.object(main, "send_message"), patch.object(
            stream, "process_ikigai_box_watches", return_value=True,
        ) as watch, patch(
            "ikigai_box_scanner.send_ikigai_box_observation",
        ) as old_box, patch("notification.create_signal_snapshot") as robot:
            main.run_scan_pass()
        # WATCH supplements the stateless confirmed-formation sender; it must
        # not replace it, or an initial pass could never report an existing
        # Box while its process-local cursor is still bootstrapping.
        watch.assert_called_once()
        old_box.assert_called_once()
        robot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
