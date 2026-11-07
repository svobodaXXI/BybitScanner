from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord

_previous_config = sys.modules.get("config")
sys.modules["config"] = ModuleType("config")
try:
    import telegram_monitoring as monitoring
finally:
    if _previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = _previous_config

import signal_archive

PNG = b"\x89PNG-original" + b"x" * 80
SENT_AT_MS = 1_792_337_000_000  # 2026-10-18 15:23:20 UTC


def _record(candidate_id="cand-ena", *, symbol="ENAUSDT", status="APPROVED", snapshot=None):
    return RobotCandidateRecord(
        candidate_id=candidate_id,
        trading_account_id=TradingAccountId("paper"),
        symbol=Symbol(symbol),
        status=status,
        signal_snapshot=snapshot if snapshot is not None else
        {"symbol": symbol, "pattern": "Falling Wedge", "quality": "B Setup"},
        snapshot_sha256="deadbeef" * 8,
        robot_state={"phase": "WAITING_RETEST", "pattern": "Falling Wedge", "direction": "LONG"},
        state_revision=1, approved_at_ms=1, updated_at_ms=2,
    )


class SignalRepostTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        env = patch.dict("os.environ", {signal_archive.ARCHIVE_ENV: str(self.dir)})
        env.start()
        self.addCleanup(env.stop)
        for key, value in (("TELEGRAM_CHAT_ID", "123"), ("TELEGRAM_TOKEN", "test")):
            fixture = patch.object(monitoring.config, key, value, create=True)
            fixture.start()
            self.addCleanup(fixture.stop)

    def _archive(self, candidate_id="cand-ena", *, text="Сканер: ENAUSDT\nПаттерн", image=PNG,
                 file_id="FILE-ID", sent_at_ms=SENT_AT_MS, symbol="ENAUSDT", timeframe="5"):
        response = {"ok": True, "result": {"message_id": 5, "photo": [{"file_id": file_id}]}}
        self.assertTrue(signal_archive.record_original_signal(
            candidate_id, symbol=symbol, timeframe=timeframe, pattern="Falling Wedge",
            text=text, image_bytes=image, photo_response=response, sent_at_ms=sent_at_ms))

    def _press(self, records):
        with patch("telegram_monitoring._robot_store") as store:
            store.return_value.__enter__.return_value.load_robot_candidates.return_value = tuple(records)
            for record in records[:1]:
                token = monitoring._candidate_callback_token(record.candidate_id)
            monitoring._send_source_signal_card(123, token)

    # --- archived original -------------------------------------------------
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_reposts_original_with_mark_time_and_text_via_file_id(self, by_id, by_path, text):
        self._archive()
        by_id.return_value = {"ok": True}
        self._press([_record()])
        by_id.assert_called_once()
        args, kwargs = by_id.call_args
        self.assertEqual(args[1:3], (123, "FILE-ID"))
        caption = kwargs["caption"]
        self.assertTrue(caption.startswith("🔁 ДУБЛИРОВАНИЕ"))
        self.assertIn("18.10.2026 15:23:20 UTC", caption)
        self.assertIn("Сканер: ENAUSDT\nПаттерн", caption)
        by_path.assert_not_called()
        text.assert_not_called()

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_falls_back_to_the_archived_image_when_file_id_is_rejected(self, by_id, by_path, text):
        self._archive()
        by_id.return_value = {"ok": False, "description": "wrong file identifier"}
        by_path.return_value = {"ok": True}
        self._press([_record()])
        by_path.assert_called_once()
        self.assertEqual(Path(by_path.call_args.args[2]).read_bytes(), PNG)
        self.assertIn("🔁 ДУБЛИРОВАНИЕ", by_path.call_args.kwargs["caption"])
        text.assert_not_called()

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_telegram_exceptions_are_handled_and_reported_honestly(self, by_id, by_path, text):
        self._archive()
        by_id.side_effect = RuntimeError("network")
        by_path.side_effect = RuntimeError("network")
        self._press([_record()])
        message = text.call_args.args[1]
        self.assertIn("🔁 ДУБЛИРОВАНИЕ", message)
        self.assertIn("не удалось отправить повторно", message)
        self.assertIn("Сканер: ENAUSDT", message)

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_repeated_press_reposts_each_time_and_never_changes_the_archive(self, by_id, by_path, text):
        self._archive()
        by_id.return_value = {"ok": True}
        before = sorted((p.name, p.read_bytes()) for p in self.dir.iterdir())
        self._press([_record()])
        self._press([_record()])
        self.assertEqual(by_id.call_count, 2)
        self.assertEqual(sorted((p.name, p.read_bytes()) for p in self.dir.iterdir()), before)

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_two_signals_of_one_ticker_repost_their_own_original_by_exact_candidate(self, by_id, text):
        self._archive("cand-old", text="OLD signal", file_id="FILE-OLD", sent_at_ms=SENT_AT_MS - 3_600_000)
        self._archive("cand-new", text="NEW signal", file_id="FILE-NEW")
        by_id.return_value = {"ok": True}
        self._press([_record("cand-old"), _record("cand-new")])
        self.assertEqual(by_id.call_args.args[2], "FILE-OLD")
        self.assertIn("OLD signal", by_id.call_args.kwargs["caption"])
        self.assertNotIn("NEW signal", by_id.call_args.kwargs["caption"])
        self.assertIn("14:23:20 UTC", by_id.call_args.kwargs["caption"])

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_closed_archive_candidate_still_reposts(self, by_id, text):
        self._archive()
        by_id.return_value = {"ok": True}
        self._press([_record(status="CLOSED")])
        by_id.assert_called_once()

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_box_handoff_candidate_uses_its_source_plan_id(self, by_id, text):
        plan_id = "box-plan-" + "ab12" * 16
        handle = "bp-" + "ab12" * 10  # what the Box scanner puts into the owner button
        self._archive(handle, text="BOX signal", file_id="FILE-BOX")
        by_id.return_value = {"ok": True}
        robot = _record("robot-1", snapshot={"symbol": "ENAUSDT", "pattern": "Ikigai Box",
                                             "source_box_candidate_id": plan_id})
        self._press([robot])
        self.assertEqual(by_id.call_args.args[2], "FILE-BOX")

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_other_box_plan_of_the_same_ticker_is_not_reused(self, by_id, text):
        self._archive("bp-" + "cd34" * 10, text="OTHER BOX", file_id="FILE-OTHER")
        robot = _record("robot-1", snapshot={"symbol": "ENAUSDT", "pattern": "Ikigai Box",
                                             "source_box_candidate_id": "box-plan-" + "ab12" * 16})
        self._press([robot])
        by_id.assert_not_called()
        self.assertIn("не сохранён", text.call_args.args[1])

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring.telegram_bot.send_photo_by_file_id")
    def test_repost_keyboard_has_no_trading_or_review_actions(self, by_id, text):
        self._archive()
        by_id.return_value = {"ok": True}
        self._press([_record()])
        buttons = [b for row in by_id.call_args.kwargs["reply_markup"]["inline_keyboard"] for b in row]
        for button in buttons:
            data = button.get("callback_data", "")
            self.assertFalse(data.startswith(("robot:", "review:", "metascalp")), data)
            self.assertLessEqual(len(data.encode("utf-8")), 64)
        self.assertTrue(any(b.get("url") for b in buttons))

    def test_caption_respects_the_telegram_limit(self):
        long_original = {"sent_at_ms": SENT_AT_MS, "text": "я" * 3000}
        caption = monitoring._repost_caption(long_original)
        self.assertLessEqual(len(caption), monitoring.TELEGRAM_CAPTION_LIMIT)
        self.assertTrue(caption.startswith("🔁 ДУБЛИРОВАНИЕ"))
        self.assertTrue(caption.endswith("…"))

    def test_source_button_callback_stays_within_telegram_limit(self):
        button = monitoring._signal_button("signal-" + "x" * 200)
        self.assertLessEqual(len(button["callback_data"].encode("utf-8")), 64)

    # --- nothing archived ---------------------------------------------------
    @patch("telegram_monitoring._send_chart_card")
    @patch("telegram_monitoring._send_text")
    def test_existing_candidate_without_archive_gets_an_honest_message(self, text, chart):
        record = _record()  # snapshot has no decision_time_ms
        self._press([record])
        chart.assert_not_called()
        message = text.call_args.args[1]
        self.assertIn("Оригинал сигнала по ENAUSDT не сохранён", message)
        self.assertIn("не подставляю", message)
        self.assertNotIn(record.candidate_id, message)
        self.assertNotIn(record.snapshot_sha256, message)
        self.assertNotIn("ДУБЛИРОВАНИЕ", message)

    @patch("telegram_monitoring._send_chart_card")
    @patch("telegram_monitoring._send_text")
    def test_another_tickers_archive_is_never_used_for_this_candidate(self, text, chart):
        self._archive("cand-other", symbol="XRPUSDT", text="XRP signal")
        self._press([_record()])
        chart.assert_not_called()
        self.assertIn("не сохранён", text.call_args.args[1])
        self.assertNotIn("XRP", text.call_args.args[1])

    @patch("telegram_monitoring._send_chart_card")
    @patch("telegram_monitoring._send_text")
    def test_reconstruction_is_labelled_as_restored_not_original(self, text, chart):
        import pandas as pd

        record = _record(snapshot={"symbol": "ENAUSDT", "pattern": "Falling Wedge",
                                   "decision_time_ms": SENT_AT_MS})
        candles = pd.DataFrame({"time": [SENT_AT_MS - 600_000], "close": [1.0]})
        view = monitoring._candidate_view(record)
        with patch.object(monitoring, "_load_candidate_candles",
                          return_value=(view, candles, "Сохранённая геометрия сигнала · 18.10 15:23 UTC")):
            self._press([record])
        caption = chart.call_args.args[3]
        self.assertIn("ВОССТАНОВЛЕННЫЙ СИГНАЛ (не оригинал)", caption)
        self.assertIn("Точная копия исходного сообщения не сохранена", caption)
        self.assertNotIn("ДУБЛИРОВАНИЕ", caption)
        text.assert_not_called()

    @patch("telegram_monitoring._send_chart_card")
    @patch("telegram_monitoring._send_text")
    def test_reconstruction_error_falls_back_to_the_honest_message(self, text, chart):
        record = _record(snapshot={"symbol": "ENAUSDT", "decision_time_ms": SENT_AT_MS})
        with patch.object(monitoring, "_load_candidate_candles", side_effect=RuntimeError("bybit down")):
            self._press([record])
        chart.assert_not_called()
        self.assertIn("не сохранён", text.call_args.args[1])

    @patch("telegram_monitoring._send_text")
    def test_unknown_or_ambiguous_token_never_posts_a_signal(self, text):
        with patch("telegram_monitoring._robot_store") as store:
            store.return_value.__enter__.return_value.load_robot_candidates.return_value = ()
            monitoring._send_source_signal_card(123, "0123456789abcdef")
        self.assertIn("не найден или ссылка неоднозначна", text.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
