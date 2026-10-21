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


def _held_scan(release, calls):
    def run(*, control_checkpoint, child_started, stop_requested):
        calls.append(True)
        if not child_started(4242):
            return
        while not release.wait(0.01) and not stop_requested():
            pass
    return run


class ScannerControlRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "terminal.db"
        self.clock = _Clock()
        self.scan_calls = []
        self.release = threading.Event()
        self.runtime = ScannerControlRuntime(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            scan_pass=_held_scan(self.release, self.scan_calls),
            clock_ms=self.clock,
            scan_interval_s=0.05,
        )
        self.runtime.start()

    def tearDown(self):
        self.release.set()
        for runtime in getattr(self, "_fresh_runtimes", ()):
            runtime.close()
        self.runtime.close()
        self.temp_dir.cleanup()

    def test_initial_status_is_stopped(self):
        status = self.runtime.status()
        self.assertEqual(status.mode, SCANNER_STOPPED)
        self.assertEqual(status.version, 1)

    def test_full_start_pause_resume_cycle(self):
        self.assertEqual(self.runtime.start_scanner().mode, SCANNER_RUNNING)
        self.assertEqual(self.runtime.pause_scanner().mode, SCANNER_PAUSED)
        self.assertEqual(self.runtime.resume_scanner().mode, SCANNER_RUNNING)
        self.assertEqual(self.runtime.stop_scanner().mode, SCANNER_STOPPED)

    def test_invalid_transitions_are_rejected_by_the_runtime(self):
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.pause_scanner()
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.resume_scanner()

        self.runtime.start_scanner()
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.start_scanner()
        with self.assertRaises(ScannerControlRuntimeError):
            self.runtime.resume_scanner()

    def test_pause_blocks_same_pass_until_resume_and_stop_ends_it(self):
        entered = threading.Event()
        first_checkpoint = threading.Event()
        continued = threading.Event()
        second_checkpoint = threading.Event()
        finished = threading.Event()

        def pass_with_checkpoints(*, control_checkpoint, child_started, stop_requested):
            self.assertTrue(child_started(5252))
            entered.set()
            self.assertTrue(first_checkpoint.wait(timeout=5.0))
            if not control_checkpoint():
                finished.set()
                return
            continued.set()
            self.assertTrue(second_checkpoint.wait(timeout=5.0))
            self.assertFalse(control_checkpoint())
            finished.set()

        runtime = ScannerControlRuntime(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            scan_pass=pass_with_checkpoints,
            clock_ms=self.clock,
            scan_interval_s=0.05,
        )
        runtime.start()
        try:
            runtime.start_scanner()
            self.assertTrue(entered.wait(timeout=5.0))
            runtime.pause_scanner()
            first_checkpoint.set()
            time.sleep(0.15)
            self.assertFalse(continued.is_set())
            runtime.resume_scanner()
            self.assertTrue(continued.wait(timeout=5.0))
            runtime.stop_scanner()
            second_checkpoint.set()
            self.assertTrue(finished.wait(timeout=5.0))
            self.assertEqual(runtime.status().mode, SCANNER_STOPPED)
        finally:
            runtime.close()

    def test_running_is_not_published_without_child_confirmation(self):
        def never_confirms(**_callbacks):
            time.sleep(0.20)

        with tempfile.TemporaryDirectory() as temp:
            runtime = ScannerControlRuntime(
                lambda: SQLiteStore.open(Path(temp) / "paper.sqlite3"),
                ACCOUNT_ID,
                scan_pass=never_confirms,
                clock_ms=lambda: int(time.time() * 1000),
                scan_interval_s=0.01,
                start_timeout_s=0.05,
            )
            runtime.start()
            try:
                with self.assertRaisesRegex(ScannerControlRuntimeError, "scanner_start_timeout"):
                    runtime.start_scanner()
                state = runtime.status()
                self.assertEqual((state.mode, state.reason),
                                 (SCANNER_STOPPED, "scanner_start_timeout"))
            finally:
                runtime.close()

    def test_start_and_close_do_not_scan_without_a_request(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            runtime = ScannerControlRuntime(
                lambda: SQLiteStore.open(Path(temp) / "paper.sqlite3"),
                ACCOUNT_ID,
                scan_pass=lambda **_callbacks: calls.append(True),
                clock_ms=self.clock,
                scan_interval_s=0.05,
            )
            runtime.start()
            time.sleep(0.12)
            runtime.close()
        self.assertEqual(calls, [])

    def _fresh_process_runtime(self):
        release = threading.Event()
        runtime = ScannerControlRuntime(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            scan_pass=_held_scan(release, self.scan_calls),
            clock_ms=self.clock,
            scan_interval_s=0.05,
        )
        runtime._test_release = release
        self.__dict__.setdefault("_fresh_runtimes", []).append(runtime)
        return runtime

    def test_fresh_start_recovers_stale_paused_to_stopped(self):
        self.runtime.start_scanner()
        self.runtime.pause_scanner()
        fresh = self._fresh_process_runtime()
        fresh.start()
        state = fresh.status()
        self.assertEqual((state.mode, state.reason), (SCANNER_STOPPED, "restart_recovery"))
        with self.assertRaises(ScannerControlRuntimeError):
            fresh.resume_scanner()
        self.assertEqual(fresh.start_scanner().mode, SCANNER_RUNNING)
        fresh._test_release.set()

    def test_fresh_start_recovers_stale_running_to_stopped(self):
        self.runtime.start_scanner()
        fresh = self._fresh_process_runtime()
        fresh.start()
        self.assertEqual(
            (fresh.status().mode, fresh.status().reason),
            (SCANNER_STOPPED, "restart_recovery"),
        )

    def test_fresh_start_keeps_stopped_unchanged(self):
        before = self.runtime.status()
        fresh = self._fresh_process_runtime()
        fresh.start()
        self.assertEqual(fresh.status(), before)


class ScannerControlRuntimeRealThreadTests(unittest.TestCase):
    def test_real_background_thread_scans_using_its_own_store_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "terminal.db"
            scanned = threading.Event()

            def scan_once(*, child_started, **_callbacks):
                self.assertTrue(child_started(6262))
                scanned.set()

            runtime = ScannerControlRuntime(
                lambda: SQLiteStore.open(db_path),
                ACCOUNT_ID,
                scan_pass=scan_once,
                clock_ms=lambda: int(time.time() * 1000),
                scan_interval_s=0.05,
            )
            runtime.start()
            try:
                self.assertEqual(runtime.start_scanner().mode, SCANNER_RUNNING)
                self.assertTrue(scanned.wait(timeout=5.0))
                deadline = time.monotonic() + 5
                while runtime.status().mode != SCANNER_STOPPED and time.monotonic() < deadline:
                    time.sleep(0.01)
            finally:
                runtime.close()

            verify_store = SQLiteStore.open(db_path)
            try:
                state = verify_store.get_scanner_runtime_state(ACCOUNT_ID)
            finally:
                verify_store.close()
            self.assertEqual(state.mode, SCANNER_STOPPED)

    def test_one_start_runs_only_one_normal_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []

            def scan_once(*, child_started, **_callbacks):
                self.assertTrue(child_started(7272))
                calls.append(True)

            runtime = ScannerControlRuntime(
                lambda: SQLiteStore.open(Path(temp) / "paper.sqlite3"),
                ACCOUNT_ID,
                scan_pass=scan_once,
                clock_ms=lambda: int(time.time() * 1000),
                scan_interval_s=0.05,
            )
            runtime.start()
            try:
                runtime.start_scanner()
                time.sleep(0.20)
                self.assertEqual(calls, [True])
                self.assertEqual(runtime.status().mode, SCANNER_STOPPED)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
