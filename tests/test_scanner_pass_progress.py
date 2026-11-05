"""#449: Scanner progress must not claim ticker completion before MIRROR ends.

All tests run offline with frozen synthetic candles and a temporary progress
directory. No Scanner process, PAPER DB, Telegram or Bybit endpoints are opened.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

# Local config.py is gitignored and may contain secrets; use the canonical
# tracked-only import stubs rather than reading developer-specific credentials.
import tests.test_telegram_delivery  # noqa: F401

import main
from horn_scanner import PROGRESS_FILE


def _frame():
    return pd.DataFrame([
        {"time": 1000, "open": 1.0, "high": 1.01, "low": 0.99, "close": 1.0},
        {"time": 2000, "open": 1.0, "high": 1.02, "low": 0.98, "close": 1.0},
    ])


class ScannerProgressCompletionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.progress_file = Path(self.dir.name) / PROGRESS_FILE
        self.env = patch.dict(os.environ, {
            "BYBITSCANNER_HORN_EVIDENCE_DIR": self.dir.name,
            "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "0",
            "BYBITSCANNER_HORN_OBSERVATION": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def _run(self, *, symbols=None, checkpoint=None, mirror=None, observer=None):
        symbols = ["TESTUSDT"] if symbols is None else symbols
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(main, "get_symbols", return_value=symbols))
            stack.enter_context(patch.object(main, "MAX_SYMBOLS", None))
            stack.enter_context(patch.object(
                main, "analyze_symbol",
                return_value={"result": None, "data": _frame()},
            ))
            stack.enter_context(patch("l_shape_scanner.observe_l_shape", return_value=None))
            stack.enter_context(patch("mirror_scanner.mirror_observation_enabled", return_value=True))
            stack.enter_context(patch.object(
                main, "observe_mirror_symbol",
                side_effect=mirror if mirror is not None else lambda *_: (0, 0, 0),
            ))
            stack.enter_context(patch.object(main, "send_message"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            main.run_scan_pass(control_checkpoint=checkpoint, progress_observer=observer)
        return json.loads(self.progress_file.read_text(encoding="utf-8"))

    def test_mirror_runs_before_a_symbol_can_be_marked_complete(self):
        events = []
        def inspect_mirror(symbol, snapshots):
            on_disk = json.loads(self.progress_file.read_text(encoding="utf-8"))
            events.append(("mirror", on_disk["symbols_done"], on_disk["status"],
                           on_disk["timeframes_done"], on_disk["mirror_candidates"]))
            self.assertEqual(set(snapshots), {"5", "1"})
            return 1, 1, 0

        def progress(report):
            events.append(("progress", report["symbols_done"], report["status"],
                           report["timeframes_done"], report["mirror_candidates"]))

        final = self._run(mirror=inspect_mirror, observer=progress)
        self.assertEqual(events, [
            ("progress", 0, "RUNNING", 1, 0),
            ("mirror", 0, "RUNNING", 1, 0),
            ("progress", 1, "COMPLETE", 2, 1),
        ])
        self.assertEqual(final["symbols_done"], 1)
        self.assertEqual(final["symbols_total"], 1)
        self.assertEqual(final["timeframes_done"], 2)
        self.assertEqual(final["timeframes_total"], 2)
        self.assertEqual(final["sent_to_telegram"], 1)

    def test_two_symbols_never_count_an_unfinished_symbol(self):
        events = []
        mirrors = []
        def mirror(symbol, _snapshots):
            mirrors.append((symbol, json.loads(self.progress_file.read_text(encoding="utf-8"))["symbols_done"]))
            return 0, 0, 0
        final = self._run(
            symbols=["AAAUSDT", "BBBUSDT"],
            mirror=mirror,
            observer=lambda report: events.append((
                report["symbol"], report["timeframe"],
                report["symbols_done"], report["timeframes_done"], report["status"],
            )),
        )
        self.assertEqual(mirrors, [("AAAUSDT", 0), ("BBBUSDT", 1)])
        self.assertEqual(events, [
            ("AAAUSDT", "5", 0, 1, "RUNNING"),
            ("AAAUSDT", "1", 1, 2, "RUNNING"),
            ("BBBUSDT", "5", 1, 3, "RUNNING"),
            ("BBBUSDT", "1", 2, 4, "COMPLETE"),
        ])
        self.assertEqual(final["symbols_done"], 2)

    def test_owner_checkpoint_stops_without_complete_or_extra_heartbeat(self):
        events = []
        with patch.object(main, "observe_mirror_symbol") as mirror:
            snapshot = self._run(
                checkpoint=lambda: False,
                observer=events.append,
            )
        mirror.assert_not_called()
        self.assertEqual(events, [])
        self.assertEqual((snapshot["status"], snapshot["symbols_done"], snapshot["timeframes_done"]),
                         ("INTERRUPTED", 0, 0))

    def test_unhandled_mirror_error_never_marks_previous_pass_as_complete(self):
        previous = self._run()
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            self._run(mirror=lambda *_: (_ for _ in ()).throw(RuntimeError("synthetic failure")))
        pending = json.loads(self.progress_file.read_text(encoding="utf-8"))
        self.assertNotEqual(pending["scan_pass_id"], previous["scan_pass_id"])
        self.assertEqual(pending["status"], "RUNNING")
        self.assertEqual(pending["symbols_done"], 0)
        self.assertEqual(pending["timeframes_done"], 1)

    def test_no_symbols_proves_empty_complete_pass(self):
        snapshot = self._run(symbols=[])
        self.assertEqual(snapshot["status"], "COMPLETE")
        self.assertEqual((snapshot["symbols_done"], snapshot["timeframes_done"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
