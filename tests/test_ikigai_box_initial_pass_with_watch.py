"""Initial-pass Ikigai Box delivery while WATCH is enabled (offline only).

Proves the Scanner control path treats WATCH as an additional observation
mode rather than a replacement for the confirmed-formation sender. No
network, PAPER DB, Robot candidate or live action is reachable from here.
"""

import contextlib
import os
import unittest
from unittest.mock import patch

import pandas as pd

import tests.test_telegram_delivery  # noqa: F401  existing offline stubs
import config
import main
import ikigai_box_scanner as box
import ikigai_box_watch_stream as stream
from tests.test_ikigai_box_detector import (
    _terminal_wick_two_impulses,
    _two_impulses,
)


_STEP_MS = int(config.TIMEFRAME) * 60_000
_SYMBOL = "TESTUSDT"
_CURSOR_KEY = (_SYMBOL, str(config.TIMEFRAME))


def _timed(frame):
    """Stamp a detector fixture onto the Scanner's configured timeframe grid."""
    frame = frame.copy()
    frame["time"] = [
        1_790_000_000_000 + n * _STEP_MS for n in range(len(frame))
    ]
    return frame


def _snapshot(frame, last_closed=None):
    """Append Bybit's newest, still-open candle the way the real feed does."""
    closed = frame if last_closed is None else frame.iloc[:last_closed + 1]
    closed = closed.copy().reset_index(drop=True)
    return pd.concat([closed, pd.DataFrame([{
        "time": int(closed.iloc[-1]["time"]) + _STEP_MS,
        "open": 100_000, "high": 100_001, "low": 99_999, "close": 100_000,
    }])], ignore_index=True)


class IkigaiBoxInitialPassWithWatchTests(unittest.TestCase):
    def setUp(self):
        stream._WATCH_CURSORS.clear()
        self.history = {}
        self.photos = []
        self.messages = []
        self.snapshot = None

    def tearDown(self):
        stream._WATCH_CURSORS.clear()

    @contextlib.contextmanager
    def _scanner(self, watch="1"):
        """Run the real Scanner control path with every side effect stubbed."""
        def render(frame, formation, path, **kwargs):
            # Recorded only; nothing is written under the repository charts/.
            return path

        def message(token, chat_id, text):
            self.messages.append(text)
            return {"ok": True}

        def photo(token, chat_id, path, caption=None, reply_markup=None):
            self.photos.append({"path": path, "caption": caption})
            return {"ok": True}

        with contextlib.ExitStack() as stack:
            enter = stack.enter_context
            enter(patch.dict(os.environ, {
                "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "1",
                "BYBITSCANNER_IKIGAI_BOX_WATCH": watch,
            }))
            enter(patch.object(main, "get_symbols", return_value=[_SYMBOL]))
            enter(patch.object(
                main, "analyze_symbol",
                side_effect=lambda symbol, *, timeframe: {
                    "symbol": symbol, "result": None,
                    "data": self.snapshot if timeframe == str(config.TIMEFRAME) else None,
                },
            ))
            enter(patch.object(main, "send_message", return_value=True))
            enter(patch.object(box, "render_ikigai_box_chart", side_effect=render))
            enter(patch.object(box, "send_message", side_effect=message))
            enter(patch.object(box, "send_photo", side_effect=photo))
            enter(patch.object(
                box, "load_memory", side_effect=lambda: dict(self.history),
            ))
            enter(patch.object(
                box, "save_memory",
                side_effect=lambda record: self.history.update(record),
            ))
            enter(patch.object(
                box, "get_telegram_chat_ids", return_value=("owner",),
            ))
            robot = enter(patch("notification.create_signal_snapshot"))
            yield robot

    def test_initial_pass_sends_existing_formation_while_watch_bootstraps(self):
        frame, _, _ = _two_impulses(second_steps=7)
        self.snapshot = _snapshot(_timed(frame))
        with self._scanner() as robot:
            main.run_scan_pass()

        # The defect under repair: with WATCH on, this first pass used to
        # emit nothing at all, because only the bootstrapping cursor ran.
        self.assertEqual(len(self.photos), 1)
        self.assertEqual(len(self.messages), 1)
        self.assertTrue(self.messages[0].startswith("📡 Сканер: TESTUSDT\n"))
        self.assertEqual(self.photos[0]["caption"], "")
        self.assertNotIn("_WATCH_", self.photos[0]["path"])
        # WATCH still bootstrapped silently instead of flooding history.
        self.assertIn(_CURSOR_KEY, stream._WATCH_CURSORS)
        self.assertIsNone(stream._WATCH_CURSORS[_CURSOR_KEY]["pending"])
        robot.assert_not_called()

    def test_repeated_passes_do_not_duplicate_the_confirmed_card(self):
        frame, _, _ = _two_impulses(second_steps=7)
        self.snapshot = _snapshot(_timed(frame))
        with self._scanner() as robot:
            main.run_scan_pass()
            main.run_scan_pass()
            main.run_scan_pass()

        self.assertEqual(len(self.photos), 1)
        robot.assert_not_called()

    def test_watch_still_emits_on_the_next_closed_candle(self):
        frame, end = _terminal_wick_two_impulses(second=False)
        frame = _timed(frame)
        with self._scanner() as robot:
            self.snapshot = _snapshot(frame, 23)
            main.run_scan_pass()
            # A cold start bootstraps geometry without any historical card.
            self.assertEqual(self.photos, [])
            for closed_end in range(24, end + 1):
                self.snapshot = _snapshot(frame, closed_end)
                main.run_scan_pass()

        self.assertTrue(any("_WATCH_" in item["path"] for item in self.photos))
        self.assertEqual(len(self.messages), len(self.photos))
        self.assertTrue(all(item["caption"] == "" for item in self.photos))
        robot.assert_not_called()

    def test_watch_card_is_suppressed_after_the_confirmed_card_for_same_anchors(self):
        frame, _ = _terminal_wick_two_impulses(second=False)
        frame = _timed(frame)
        watch = next(
            item for item in stream.detect_ikigai_box_watches(frame)
            if item.anchor_identity == ("SHORT", 20, 23)
        )
        snapshot = _snapshot(frame)
        a_time = int(frame.iloc[watch.anchor_start_index]["time"])
        b_time = int(frame.iloc[watch.anchor_end_index]["time"])

        with self._scanner():
            # Control: with no history the same WATCH is deliverable.
            self.assertTrue(box.send_ikigai_box_watch_observation(
                _SYMBOL, snapshot, watch, timeframe=config.TIMEFRAME,
            ))
        self.assertEqual(len(self.photos), 1)

        self.photos.clear()
        self.history = {
            f"ikigai_box:{_SYMBOL}:{config.TIMEFRAME}:{watch.direction}": {
                "anchors": f"{a_time}:{b_time}",
                "pattern": "Ikigai Box",
            },
        }
        with self._scanner():
            # The confirmed sender's own identity record is the single shared
            # dedup mechanism; no second store is introduced by the fix.
            self.assertFalse(box.send_ikigai_box_watch_observation(
                _SYMBOL, snapshot, watch, timeframe=config.TIMEFRAME,
            ))
        self.assertEqual(self.photos, [])


if __name__ == "__main__":
    unittest.main()
