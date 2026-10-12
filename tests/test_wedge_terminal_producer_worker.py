"""A3-R6 focused tests: background Wedge terminal producer worker lifecycle.

The pass itself is a stub (no network, no sidecar); the mode reader is injected.
"""
import threading
import unittest

from terminal.application.wedge_source_terminal_producer import WedgeTerminalProducerWorker
from terminal.domain.models import TradingAccountId

ACCOUNT = TradingAccountId("paper")


class _Recorder:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.threads = set()
        self.ran = threading.Event()

    def __call__(self, database_path, account, *, candidate_store_dir, should_stop):
        self.calls.append((database_path, account, candidate_store_dir))
        self.threads.add(threading.current_thread().name)
        self.ran.set()
        if self.fail:
            raise RuntimeError("producer failure")
        return {}


def _worker(run_pass, mode="SHADOW", interval_s=0.01):
    return WedgeTerminalProducerWorker(
        "paper.sqlite3", ACCOUNT, interval_s=interval_s, run_pass=run_pass,
        autopilot_mode=lambda: mode)


class WorkerLifecycleTests(unittest.TestCase):
    def test_runs_passes_off_the_calling_thread_in_shadow(self):
        recorder = _Recorder()
        worker = _worker(recorder)
        worker.start()
        self.addCleanup(worker.close)
        self.assertTrue(recorder.ran.wait(2))
        self.assertEqual(recorder.calls[0], ("paper.sqlite3", ACCOUNT, None))
        self.assertNotIn(threading.current_thread().name, recorder.threads)

    def test_no_pass_unless_autopilot_is_shadow(self):
        for mode in ("OFF", "PAPER_AUTO", None):
            with self.subTest(mode=mode):
                recorder = _Recorder()
                worker = _worker(recorder, mode=mode)
                worker.start()
                self.assertFalse(recorder.ran.wait(0.15))
                worker.close()

    def test_close_joins_the_thread_and_restart_works(self):
        recorder = _Recorder()
        worker = _worker(recorder)
        worker.start()
        first = worker._thread
        worker.start()  # idempotent: still the same single thread
        self.assertIs(worker._thread, first)
        self.assertTrue(recorder.ran.wait(2))
        worker.close()
        self.assertFalse(worker.is_alive())
        recorder.ran.clear()
        worker.start()
        self.addCleanup(worker.close)
        self.assertTrue(recorder.ran.wait(2))

    def test_close_before_first_interval_never_runs_a_pass(self):
        recorder = _Recorder()
        worker = _worker(recorder, interval_s=60)
        worker.start()
        worker.close()
        self.assertEqual(recorder.calls, [])
        self.assertFalse(worker.is_alive())

    def test_producer_failure_keeps_the_worker_running(self):
        recorder = _Recorder(fail=True)
        worker = _worker(recorder)
        worker.start()
        self.addCleanup(worker.close)
        self.assertTrue(recorder.ran.wait(2))
        recorder.ran.clear()
        self.assertTrue(recorder.ran.wait(2))  # a later pass still runs
        self.assertTrue(worker.is_alive())

    def test_mode_reader_failure_skips_the_pass(self):
        recorder = _Recorder()

        def broken_mode():
            raise RuntimeError("db unavailable")

        worker = WedgeTerminalProducerWorker("paper.sqlite3", ACCOUNT, interval_s=0.01,
                                             run_pass=recorder, autopilot_mode=broken_mode)
        worker.start()
        self.assertFalse(recorder.ran.wait(0.15))
        self.assertTrue(worker.is_alive())
        worker.close()


class _SlowPass:
    """A pass stuck in a 'network request' until released; records what it would append."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.appended = []

    def __call__(self, database_path, account, *, candidate_store_dir, should_stop):
        self.entered.set()
        self.release.wait(5)
        if not should_stop():
            self.appended.append("event")
        return {}


class LongPassShutdownTests(unittest.TestCase):
    def test_close_timeout_is_reported_and_nothing_is_appended_afterwards(self):
        slow = _SlowPass()
        worker = _worker(slow)
        worker.start()
        self.assertTrue(slow.entered.wait(2))
        self.assertFalse(worker.close(timeout_s=0.05))  # surfaced, not a silent success
        self.assertTrue(worker.is_alive())
        with self.assertRaises(RuntimeError):
            worker.start()  # never a second worker over the still-finishing one
        slow.release.set()
        worker.close(timeout_s=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(slow.appended, [])  # the late result was discarded
        slow.entered.clear()
        slow.release.clear()
        worker.start()  # a clean restart once the old thread is gone
        self.addCleanup(worker.close)
        self.addCleanup(slow.release.set)
        self.assertTrue(slow.entered.wait(2))

    def test_close_returns_true_when_the_thread_stops_in_time(self):
        recorder = _Recorder()
        worker = _worker(recorder)
        worker.start()
        self.assertTrue(recorder.ran.wait(2))
        self.assertTrue(worker.close())

    def test_paper_runtime_close_raises_after_closing_everything_else(self):
        import tempfile
        from pathlib import Path
        from tests.test_terminal_paper_runtime import _runtime

        with tempfile.TemporaryDirectory() as directory:
            runtime = _runtime(Path(directory) / "paper.sqlite3")
            stuck = runtime._wedge_terminal_producer
            real_close = stuck.close
            self.addCleanup(lambda: self.assertTrue(real_close()))  # no thread left behind
            stuck.close = lambda timeout_s=5.0: False
            with self.assertRaises(RuntimeError):
                runtime.close()
            with self.assertRaises(Exception):
                runtime.store.get_robot_autopilot_state(runtime._paper_account_id)  # store was closed


class PaperRuntimeWiringTests(unittest.TestCase):
    def test_paper_runtime_starts_and_closes_the_worker(self):
        import tempfile
        from pathlib import Path
        from tests.test_terminal_paper_runtime import _runtime

        with tempfile.TemporaryDirectory() as directory:
            runtime = _runtime(Path(directory) / "paper.sqlite3")
            worker = runtime._wedge_terminal_producer
            self.assertIsInstance(worker, WedgeTerminalProducerWorker)
            self.assertTrue(worker.is_alive())
            runtime.close()
            self.assertFalse(worker.is_alive())



from tests.test_wedge_source_terminal_producer import ProducerRunTests, _frame, QUIET, T0, MIN  # noqa: E402
from terminal.application.wedge_source_terminal_producer import run_wedge_terminal_producer_once  # noqa: E402


class CooperativeStopTests(ProducerRunTests):
    """Same fixture as the producer tests; inherited cases also run against the stop-aware code."""

    def test_stop_before_fetch_appends_nothing(self):
        self.allow("w1")
        self.assertEqual(self.run_once(_frame(QUIET), should_stop=lambda: True), {"w1": "STOPPED"})
        self.assertEqual(self.loads, [])
        self.assertFalse(self.sidecar.exists())

    def test_stop_during_fetch_discards_the_result(self):
        self.allow("w1")
        stopped = []
        load = self.loader(_frame(QUIET))

        def slow_load(symbol, start_ms, end_ms):
            frame = load(symbol, start_ms, end_ms)
            stopped.append(True)  # close() happened while the request was in flight
            return frame

        result = run_wedge_terminal_producer_once(
            self.store.path, ACCOUNT, candidate_store_dir=self.db.candidates,
            candle_range_loader=slow_load, now_ms=T0 + 12 * MIN, should_stop=lambda: bool(stopped))
        self.assertEqual(result, {"w1": "STOPPED"})
        self.assertFalse(self.sidecar.exists())


if __name__ == "__main__":
    unittest.main()
