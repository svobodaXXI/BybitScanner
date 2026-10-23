"""Exact archive identity in owner-only Telegram EDITOR callback."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from notification import build_tradingview_keyboard
import signal_archive
import telegram_review


class EditorSignalCallbackIdentityTests(unittest.TestCase):
    def test_long_signal_identity_resolves_exactly_through_bounded_callback(self):
        signal_id = "box-robot-" + "ab12" * 16
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {signal_archive.ARCHIVE_ENV: temp}
        ):
            self.assertTrue(signal_archive.record_original_signal(
                signal_id, symbol="ZHIPUUSDT", timeframe="1",
                pattern="Falling Wedge", text="signal", image_bytes=b"png",
            ))
            keyboard = build_tradingview_keyboard(
                "ZHIPUUSDT", "1", signal_id=signal_id,
            )
            callback = keyboard["inline_keyboard"][-1][0]["callback_data"]
            self.assertLessEqual(len(callback.encode("utf-8")), 64)
            parsed = telegram_review._parse_workspace_callback(callback)
            self.assertEqual(parsed["signal_token"], signal_archive.signal_callback_token(signal_id))
            with patch(
                "workspace_owner_launcher.request_owner_workspace_open"
            ) as launch, patch.object(telegram_review, "_answer_callback"):
                telegram_review._run_workspace_callback({"id": "cb"}, parsed)
            launch.assert_called_once_with(
                "EDITOR", "ZHIPUUSDT", "1m", signal_id=signal_id,
            )

    def test_same_symbol_signals_keep_distinct_archive_handles(self):
        first = signal_archive.signal_callback_token("candidate-first")
        second = signal_archive.signal_callback_token("candidate-second")
        self.assertNotEqual(first, second)

    def test_tampered_archive_metadata_does_not_resolve(self):
        signal_id = "candidate-original"
        with tempfile.TemporaryDirectory() as temp:
            self.assertTrue(signal_archive.record_original_signal(
                signal_id, symbol="UMAUSDT", timeframe="5",
                pattern="Falling Wedge", text="signal", image_bytes=b"png",
                directory=temp,
            ))
            token = signal_archive.signal_callback_token(signal_id)
            meta_path = Path(temp) / f"{token}.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["candidate_id"] = "candidate-forged"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            self.assertIsNone(signal_archive.resolve_signal_callback_token(
                token, directory=temp,
            ))

    def test_legacy_callback_stays_supported(self):
        parsed = telegram_review._parse_workspace_callback(
            "workspace:EDITOR:ZHIPUUSDT:1m"
        )
        self.assertIsNone(parsed["signal_id"])

    def test_malicious_and_overlong_callbacks_are_rejected(self):
        self.assertIsNone(telegram_review._parse_workspace_callback(
            "workspace:EDITOR:UMAUSDT:5m:../../secret"
        ))
        self.assertIsNone(telegram_review._parse_workspace_callback(
            "workspace:TERMINAL:UMAUSDT:5m:candidate"
        ))
        self.assertIsNone(telegram_review._parse_workspace_callback(
            "ws:E:" + "a" * 39 + "z"
        ))

    def test_missing_archive_fails_closed_without_launcher(self):
        callback = "ws:E:" + "a" * signal_archive.SIGNAL_CALLBACK_TOKEN_HEX_LENGTH
        parsed = telegram_review._parse_workspace_callback(callback)
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {signal_archive.ARCHIVE_ENV: temp}
        ), patch(
            "workspace_owner_launcher.request_owner_workspace_open"
        ) as launch, patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback({"id": "cb"}, parsed)
        launch.assert_not_called()
        answer.assert_called_once_with("cb", "Редактор/Терминал недоступен на ПК")


if __name__ == "__main__":
    unittest.main()
