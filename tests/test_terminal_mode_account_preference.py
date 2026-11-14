"""Regression tests for independent account preference persistence."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal.domain.models import TradingAccountId
from terminal.application.trading_accounts import paper_account_manager
from terminal.runtime.paper_runtime import PaperRuntime
from unittest.mock import MagicMock
from terminal.persistence.mode_account_preference import (
    ModeAccountPreferenceError,
    ModeAccountPreferenceStore,
)


class ModeAccountPreferenceTests(unittest.TestCase):

    def test_runtime_selection_is_not_global_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = paper_account_manager()
            store = ModeAccountPreferenceStore(Path(directory) / "modes.json")
            runtime = object.__new__(PaperRuntime)
            runtime._paper_account_id = TradingAccountId("paper")
            runtime._account_manager = manager
            runtime._mode_account_preference_store = store
            runtime._live_account_store = None
            generation = manager.session_token
            self.assertEqual(runtime.save_mode_account_preference("TERMINAL", "paper"),
                             {"mode": "TERMINAL", "account_id": "paper"})
            self.assertEqual(runtime.save_mode_account_preference("AUTOPILOT", "paper"),
                             {"mode": "AUTOPILOT", "account_id": "paper"})
            self.assertEqual(runtime.mode_account_preferences(),
                             {"TERMINAL": "paper", "AUTOPILOT": "paper"})
            self.assertEqual(manager.session_token, generation)
            with self.assertRaisesRegex(RuntimeError, "autopilot_account_not_supported"):
                runtime.save_mode_account_preference("AUTOPILOT", "bybit-main")
            with self.assertRaises(LookupError):
                runtime.save_mode_account_preference("TERMINAL", "bybit-main")
            self.assertEqual(manager.session_token, generation)

    def test_modes_persist_independently_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mode_accounts.json"
            store = ModeAccountPreferenceStore(path)
            self.assertIsNone(store.load("TERMINAL"))
            self.assertIsNone(store.load("AUTOPILOT"))
            store.save("TERMINAL", TradingAccountId("bybit-main"))
            store.save("AUTOPILOT", TradingAccountId("paper"))
            restored = ModeAccountPreferenceStore(path)
            self.assertEqual(restored.load("TERMINAL"), TradingAccountId("bybit-main"))
            self.assertEqual(restored.load("AUTOPILOT"), TradingAccountId("paper"))
            restored.save("TERMINAL", TradingAccountId("paper"))
            self.assertEqual(restored.load("AUTOPILOT"), TradingAccountId("paper"))
            self.assertEqual(json.loads(path.read_text()), {
                "version": 1,
                "accounts": {"TERMINAL": "paper", "AUTOPILOT": "paper"},
            })

    def test_unknown_modes_and_invalid_identity_are_rejected_without_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mode_accounts.json"
            store = ModeAccountPreferenceStore(path)
            with self.assertRaises(ValueError):
                store.save("EDITOR", TradingAccountId("paper"))
            with self.assertRaises(TypeError):
                store.save("TERMINAL", "paper")
            self.assertFalse(path.exists())

    def test_corrupt_envelope_fails_closed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mode_accounts.json"
            path.write_text('{"version":1,"accounts":{"EDITOR":"paper"}}')
            store = ModeAccountPreferenceStore(path)
            with self.assertRaisesRegex(ModeAccountPreferenceError, "read_failed"):
                store.load("TERMINAL")
            with self.assertRaisesRegex(ModeAccountPreferenceError, "read_failed"):
                store.save("AUTOPILOT", TradingAccountId("paper"))
            self.assertIn('"EDITOR"', path.read_text())

    def test_failed_atomic_replace_preserves_previous_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mode_accounts.json"
            store = ModeAccountPreferenceStore(path)
            store.save("AUTOPILOT", TradingAccountId("paper"))
            before = path.read_bytes()
            with patch("terminal.persistence.mode_account_preference.os.replace",
                       side_effect=OSError("disk failure")):
                with self.assertRaisesRegex(ModeAccountPreferenceError, "write_failed"):
                    store.save("TERMINAL", TradingAccountId("bybit-main"))
            self.assertEqual(path.read_bytes(), before)
            self.assertIsNone(store.load("TERMINAL"))
            self.assertEqual(store.load("AUTOPILOT"), TradingAccountId("paper"))


if __name__ == "__main__":
    unittest.main()
