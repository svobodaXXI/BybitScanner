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

    def __call__(self, database_path, account, *, candidate_store_dir):
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
        worker.start()  # idempotent: still one thread
        self.assertTrue(recorder.ran.wait(2))
        self.assertEqual(len([t for t in threading.enumerate() if t.name == worker.THREAD_NAME]), 1)
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


if __name__ == "__main__":
    unittest.main()
