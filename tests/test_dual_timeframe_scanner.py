from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import signal_memory


class DualTimeframeScannerContractTests(unittest.TestCase):
    def test_each_symbol_runs_5m_then_1m_before_next_symbol(self):
        calls: list[tuple[str, str]] = []

        def analyze(symbol, *, timeframe):
            calls.append((symbol, timeframe))
            return {"symbol": symbol, "result": None, "data": None}

        with patch.object(main, "MAX_SYMBOLS", None), \
                patch.object(main, "get_symbols", return_value=["AAAUSDT", "BBBUSDT"]), \
                patch.object(main, "analyze_symbol", side_effect=analyze), \
                patch.object(main, "send_message"), \
                contextlib.redirect_stdout(io.StringIO()):
            main.run_scan_pass()

        self.assertEqual(calls, [
            ("AAAUSDT", "5"),
            ("AAAUSDT", "1"),
            ("BBBUSDT", "5"),
            ("BBBUSDT", "1"),
        ])

    def test_signal_memory_is_independent_by_symbol_timeframe_pattern_and_formation(self):
        signal = {
            "symbol": "AAAUSDT",
            "score": 80,
            "direction": "LONG",
            "pattern": "Falling Wedge",
        }
        with tempfile.TemporaryDirectory() as folder, patch.object(
            signal_memory, "MEMORY_FILE", str(Path(folder) / "signals.json"),
        ):
            self.assertEqual(signal_memory.update_signal({
                **signal, "timeframe": "5", "formation_id": "A:B",
            }), "NEW")
            self.assertEqual(signal_memory.update_signal({
                **signal, "timeframe": "1", "formation_id": "A:B",
            }), "NEW")
            self.assertEqual(signal_memory.update_signal({
                **signal, "timeframe": "5", "formation_id": "C:D",
            }), "NEW")
            self.assertEqual(signal_memory.update_signal({
                **signal, "timeframe": "5", "formation_id": "A:B", "score": 86,
            }), "STRENGTHENING")

            memory = signal_memory.load_memory()

        self.assertIn("scanner:AAAUSDT:5:Falling Wedge:A:B", memory)
        self.assertIn("scanner:AAAUSDT:1:Falling Wedge:A:B", memory)
        self.assertIn("scanner:AAAUSDT:5:Falling Wedge:C:D", memory)
        self.assertEqual(
            memory["scanner:AAAUSDT:5:Falling Wedge:A:B"]["current_score"], 86,
        )
        self.assertEqual(
            memory["scanner:AAAUSDT:1:Falling Wedge:A:B"]["current_score"], 80,
        )
        self.assertEqual(
            memory["scanner:AAAUSDT:5:Falling Wedge:C:D"]["current_score"], 80,
        )


if __name__ == "__main__":
    unittest.main()
