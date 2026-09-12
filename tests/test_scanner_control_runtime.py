from pathlib import Path
import tempfile
import threading
import time
import unittest

from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_runtime import (
    SCANNER_PAUSED,
    SCANNER_RUNNING,
    SCANNER_STOPPED,
    ScannerControlRuntime,
    ScannerControlRuntimeError,
)


ACCOUNT_ID = TradingAccountId("paper")


class _Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        self.value += 1
        return self.value


class ScannerControlRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "terminal.db"
        self.clock = _Clock()
        self.scan_calls = []
        self.runtime = ScannerControlRuntime(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            scan_pass=lambda: self.scan_calls.append(True),
            clock_ms=self.clock,
        )

    def tearDown(self):
        self.runtime.close()
        self.temp_dir.cleanup()

    def test_initial_status_is_stopped(self):
        status = self.runtime.status()
        self.assertEqual(status.mode, SCANNER_STOPPED)
        self.assertEqual(status.version, 1)

    def test_full_start_pause_resume_cycle(self):
        started = self.runtime.start_scanner()
        self.assertEqual(started.mode, SCANNER_RUNNING)

        paused = self.runtime.pause_scanner()
        self.assertEqual(paused.mode, SCANNER_PAUSED)

        resumed = self.runtime.resume_scanner()
        self.assertEqual(resumed.mode, SCANNER_RUNNING)

    def test_invalid_transitions_are_rejected_by_the_runtime(self):
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.pause_scanner()  # STOPPED -> pause is invalid
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.resume_scanner()  # STOPPED -> resume is invalid

        self.runtime.start_scanner()
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.start_scanner()  # RUNNING -> start again is invalid
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.resume_scanner()  # RUNNING -> resume is invalid

    def test_start_and_close_do_not_scan_within_the_interval(self):
        monitor = ScannerControlRuntime(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            scan_pass=lambda: self.scan_calls.append(True),
            clock_ms=self.clock,
            scan_interval_s=60.0,
        )
        monitor.start()
        monitor.close()

        self.assertEqual(self.scan_calls, [])


class ScannerControlRuntimeRealThreadTests(unittest.TestCase):
    """The real-background-thread regression test CR-SCANNER-CONTROL-RUNTIME-001's
    acceptance_criteria requires (see DOCUMENTS/ROBOT_RUN_INDEX.md's post-closure
    fix on RobotBreakoutMonitor for why synchronous-only tests are not enough).
    """

    def test_real_background_thread_scans_using_its_own_store_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "terminal.db"
            scanned = threading.Event()

            runtime = ScannerControlRuntime(
                lambda: SQLiteStore.open(db_path),
                ACCOUNT_ID,
                scan_pass=scanned.set,
                clock_ms=lambda: int(time.time() * 1000),
                scan_interval_s=0.05,
            )
            runtime.start()
            try:
                runtime.start_scanner()
                scanned_in_time = scanned.wait(timeout=5.0)
            finally:
                runtime.close()

            self.assertTrue(
                scanned_in_time,
                "the real background thread never invoked scan_pass() -- this is "
                "exactly the SQLiteStore thread-ownership regression",
            )

            verify_store = SQLiteStore.open(db_path)
            try:
                state = verify_store.get_scanner_runtime_state(ACCOUNT_ID)
            finally:
                verify_store.close()
            self.assertEqual(state.mode, SCANNER_RUNNING)


if __name__ == "__main__":
    unittest.main()
