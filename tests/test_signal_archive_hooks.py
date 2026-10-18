"""Scanner senders archive the exact original signal; archiving never affects delivery."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import tests.test_telegram_delivery  # existing offline config/API stubs
import ikigai_box_scanner as box
import l_shape_scanner as observer
import notification
import signal_archive
from tests.test_ikigai_box_scanner_delivery import SOURCE_ID, _candles
import tests.test_l_shape_scanner as l_shape_tests

PHOTO_OK = {"ok": True, "result": {"message_id": 9, "photo": [{"file_id": "FID-1"}]}}


class _ArchiveDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive = Path(self._tmp.name) / "archive"
        env = patch.dict("os.environ", {signal_archive.ARCHIVE_ENV: str(self.archive)})
        env.start()
        self.addCleanup(env.stop)


class WedgeSenderArchiveTests(_ArchiveDir):
    def _send(self, *, candidate_id="cand-wedge", photo_response=PHOTO_OK, recipients=("owner", "friend")):
        with tempfile.TemporaryDirectory() as charts, ExitStack() as stack:
            (Path(charts) / "BTCUSDT_analysis.png").write_bytes(b"ORIGINAL-CHART-BYTES")
            stack.enter_context(patch.object(notification.config, "TELEGRAM_CHAT_IDS", recipients))
            stack.enter_context(patch.object(notification.config, "TELEGRAM_CHAT_ID", "owner"))
            stack.enter_context(patch.object(notification.config, "TELEGRAM_TOKEN", "t"))
            stack.enter_context(patch.object(notification.config, "TELEGRAM_ENABLED", True))
            stack.enter_context(patch.object(notification, "CHARTS_DIR", charts))
            stack.enter_context(patch.object(notification, "send_message", return_value={"ok": True}))
            stack.enter_context(patch.object(notification, "send_photo", return_value=photo_response))
            stack.enter_context(patch.object(
                notification, "prepare_robot_handoff",
                return_value=types.SimpleNamespace(candidate_id=candidate_id, persistence_failed=False)))
            return notification.send_signal({
                "symbol": "BTCUSDT", "pattern": "Falling Wedge", "final_score": 80, "timeframe": "5",
                "robot_handoff_ready": True, "confirmation": {"direction": "LONG", "confirmed": True}})

    def test_owner_delivery_archives_exact_image_text_and_file_id(self):
        self.assertTrue(self._send())
        original = signal_archive.load_original_signal(["cand-wedge"])
        self.assertEqual(Path(original["image_path"]).read_bytes(), b"ORIGINAL-CHART-BYTES")
        self.assertIn("BTCUSDT", original["text"])
        self.assertEqual(original["photo_file_id"], "FID-1")
        self.assertEqual((original["symbol"], original["timeframe"]), ("BTCUSDT", "5"))

    def test_next_signal_for_the_same_ticker_does_not_replace_an_older_original(self):
        self._send(candidate_id="cand-1")
        self._send(candidate_id="cand-2")
        self.assertEqual(Path(signal_archive.load_original_signal(["cand-1"])["image_path"]).read_bytes(),
                         b"ORIGINAL-CHART-BYTES")
        self.assertIsNotNone(signal_archive.load_original_signal(["cand-2"]))

    def test_no_candidate_or_failed_owner_photo_archives_nothing(self):
        self._send(candidate_id=None)
        self._send(candidate_id="cand-x", photo_response={"ok": False})
        self.assertFalse(self.archive.exists() and list(self.archive.iterdir()))

    def test_archive_failure_does_not_change_delivery(self):
        with patch.object(signal_archive.os, "replace", side_effect=OSError("disk full")):
            self.assertTrue(self._send(candidate_id="cand-ok"))
        self.assertIsNone(signal_archive.load_original_signal(["cand-ok"]))


class LShapeSenderArchiveTests(_ArchiveDir):
    def test_owner_delivery_archives_the_photo_that_was_sent(self):
        chart = Path(self._tmp.name) / "l.png"
        chart.write_bytes(b"L-SHAPE-ORIGINAL")
        candidate = l_shape_tests.LShapeTelegramTests.candidate(None)
        candidate["chart_path"] = str(chart)
        with patch.object(observer.config, "TELEGRAM_ENABLED", True), \
                patch.object(observer, "get_telegram_chat_ids", return_value=("owner", "friend")), \
                patch.object(observer, "get_telegram_owner_chat_id", return_value="owner"), \
                patch.object(observer, "load_memory", return_value={}), \
                patch.object(observer, "save_memory"), \
                patch.object(observer, "send_photo", return_value=PHOTO_OK), \
                patch.object(observer, "prepare_robot_handoff", return_value=types.SimpleNamespace(
                    candidate_id="cand-lshape", persistence_failed=False)):
            self.assertTrue(observer.send_l_shape_observation("TESTUSDT", candidate, timeframe="5"))
        original = signal_archive.load_original_signal(["cand-lshape"])
        self.assertEqual(Path(original["image_path"]).read_bytes(), b"L-SHAPE-ORIGINAL")
        self.assertIn("Г-образная", original["text"])
        self.assertEqual(original["pattern"], "L-shape")
        self.assertEqual(original["photo_file_id"], "FID-1")


class IkigaiBoxSenderArchiveTests(_ArchiveDir):
    def test_owner_delivery_archives_under_the_button_handle(self):
        def render(closed, formation, path, **kwargs):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"BOX-ORIGINAL")

        with ExitStack() as stack, tempfile.TemporaryDirectory() as folder:
            stack.enter_context(patch.object(box, "get_telegram_chat_ids", return_value=("owner", "guest")))
            stack.enter_context(patch.object(box, "get_telegram_owner_chat_id", return_value="owner"))
            stack.enter_context(patch.object(box, "load_memory", return_value={}))
            stack.enter_context(patch.object(box, "save_memory"))
            stack.enter_context(patch.object(box, "render_ikigai_box_chart", side_effect=render))
            stack.enter_context(patch.object(box, "send_message", return_value={"ok": True, "result": {"message_id": 3}}))
            stack.enter_context(patch.object(box, "send_photo", return_value=PHOTO_OK))
            stack.enter_context(patch.object(box, "warn_owner_robot_candidate_failed"))
            self.assertTrue(box.send_ikigai_box_observation(
                "TESTUSDT", _candles(), timeframe="5", chart_dir=folder,
                robot_plan_preparer=lambda *args: SOURCE_ID))
        handle = "bp-" + SOURCE_ID.removeprefix("box-plan-")[:40]
        original = signal_archive.load_original_signal([handle])
        self.assertEqual(Path(original["image_path"]).read_bytes(), b"BOX-ORIGINAL")
        self.assertEqual(original["pattern"], "Ikigai Box")
        self.assertEqual(original["text_message_id"], 3)
        self.assertIsNone(signal_archive.load_original_signal([SOURCE_ID]))


if __name__ == "__main__":
    unittest.main()
