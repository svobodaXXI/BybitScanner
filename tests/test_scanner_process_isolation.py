"""PROCESS-ISOLATION-1: the Scanner pass runs in a child process; the backend keeps
the PAPER DB, the owner callbacks and the lifecycle. Temporary databases only."""

import importlib
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from terminal.domain.models import TradingAccountId
from terminal.paper.ikigai_box_plan import IkigaiBoxPlanRejected
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime import paper_runtime, scanner_process
from terminal.runtime.paper_runtime import SCANNER_RUNNING, SCANNER_STOPPED, ScannerControlRuntime
from terminal.runtime.scanner_process import (
    ScannerProcessBusy, ScannerProcessError, _child_main, run_scan_pass_in_child_process,
)

ME = "tests.test_scanner_process_isolation"
ACCOUNT_ID = TradingAccountId("paper")


# ---- child-side scan passes (imported by the spawned child) ----------------------
def _pass_exercises_callbacks(*, box_plan_preparer, control_checkpoint, robot_candidate_observer):
    report = robot_candidate_observer
    report(f"pid:{os.getpid()}")
    report(f"checkpoint:{control_checkpoint()}")
    report(f"plan:{box_plan_preparer('AKEUSDT', '5', {'p1': 0.0268, 'levels': [1, 2]})}")
    try:
        box_plan_preparer("REJUSDT", "5", {})
    except IkigaiBoxPlanRejected as rejection:
        report(f"rejected:{rejection}")
    try:
        box_plan_preparer("BADUSDT", "5", {})
    except ScannerProcessError:
        report("technical-failure")


def _pass_until_stopped(*, box_plan_preparer, control_checkpoint, robot_candidate_observer):
    while control_checkpoint():
        robot_candidate_observer("tick")


def _pass_imports_analyzer_signal_package(*, box_plan_preparer, control_checkpoint, robot_candidate_observer):
    from signal.quality import evaluate_quality  # what analyzer/core.py imports

    robot_candidate_observer(f"signal-package:{callable(evaluate_quality)}")


def _pass_never_checkpoints(**_callbacks):
    # A long analysis: never reaches a checkpoint, so only the parent supervisor can end it.
    pid_file = os.environ.get("SCANNER_CHILD_PID_FILE")
    if pid_file:
        Path(pid_file).write_text(str(os.getpid()))
    while True:
        time.sleep(0.05)


def _pass_reports_progress(*, progress_observer, **_callbacks):
    progress_observer({"symbols_done": 1, "symbols_total": 1, "symbol": "BTCUSDT"})


def _pass_hangs_once(*, progress_observer, **_callbacks):
    marker = Path(os.environ["SCANNER_HANG_ONCE_FILE"])
    if not marker.exists():
        marker.write_text(str(os.getpid()))
        while True:
            time.sleep(0.05)
    progress_observer({"symbols_done": 1, "symbols_total": 1, "symbol": "BTCUSDT"})


def _pass_crashes(**_callbacks):
    os._exit(3)


def _pass_raises(**_callbacks):
    raise ValueError("analysis failed")


def _pass_slow(*, box_plan_preparer, control_checkpoint, robot_candidate_observer):
    while control_checkpoint():
        time.sleep(0.05)


_LOCAL_CHECKPOINTS = []


def _pass_records_checkpoint_locally(*, box_plan_preparer, control_checkpoint, robot_candidate_observer):
    _LOCAL_CHECKPOINTS.append(control_checkpoint())


class _Parent:
    """Backend-side callbacks; records the process and thread that served them."""

    def __init__(self, checkpoints=(True,)):
        self.calls, self.served_in = [], set()
        self._checkpoints = list(checkpoints)

    def _seen(self):
        self.served_in.add(os.getpid())

    def checkpoint(self):
        self._seen()
        return self._checkpoints.pop(0) if self._checkpoints else False

    def box_plan(self, symbol, timeframe, formation):
        self._seen()
        self.calls.append(("plan", symbol, timeframe, formation))
        if symbol == "REJUSDT":
            raise IkigaiBoxPlanRejected("grid below minimum")
        if symbol == "BADUSDT":
            raise RuntimeError("owner unavailable")
        return "box-plan-abc"

    def observe(self, candidate_id):
        self._seen()
        self.calls.append(("observe", candidate_id))

    def run(self, target):
        run_scan_pass_in_child_process(
            box_plan_preparer=self.box_plan, control_checkpoint=self.checkpoint,
            robot_candidate_observer=self.observe, target=f"{ME}:{target}")


class ChildProcessBoundaryTests(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(multiprocessing.active_children(), [])  # no orphan Scanner child

    def test_pass_runs_in_another_process_and_callbacks_run_in_the_backend(self):
        parent = _Parent()
        parent.run("_pass_exercises_callbacks")
        observed = [value for kind, value, *_ in parent.calls if kind == "observe"]
        child_pid = int(observed[0].split(":")[1])
        self.assertNotEqual(child_pid, os.getpid())
        self.assertEqual(parent.served_in, {os.getpid()})
        self.assertEqual(observed[1:], ["checkpoint:True", "plan:box-plan-abc",
                                        "rejected:grid below minimum", "technical-failure"])
        self.assertIn(("plan", "AKEUSDT", "5", {"p1": 0.0268, "levels": [1, 2]}), parent.calls)

    def test_child_resolves_the_project_signal_package_like_the_backend(self):
        parent = _Parent()
        parent.run("_pass_imports_analyzer_signal_package")
        self.assertEqual(parent.calls, [("observe", "signal-package:True")])

    def test_stop_at_checkpoint_ends_the_pass_normally(self):
        parent = _Parent(checkpoints=(True, True, False))
        parent.run("_pass_until_stopped")
        self.assertEqual([c for c in parent.calls if c[0] == "observe"], [("observe", "tick")] * 2)

    def test_checkpoint_failure_is_a_stop_not_a_continue(self):
        parent = _Parent()
        parent.checkpoint = lambda: 1 / 0
        parent.run("_pass_until_stopped")
        self.assertEqual(parent.calls, [])

    def test_child_crash_raises_and_releases_the_single_flight_slot(self):
        with self.assertRaisesRegex(ScannerProcessError, "exitcode=3"):
            _Parent().run("_pass_crashes")
        _Parent(checkpoints=(False,)).run("_pass_until_stopped")  # a fresh pass may start

    def test_child_exception_is_reported_to_the_backend(self):
        with self.assertRaisesRegex(ScannerProcessError, "ValueError: analysis failed"):
            _Parent().run("_pass_raises")

    def test_a_second_concurrent_pass_is_refused(self):
        release = threading.Event()
        slow = _Parent(checkpoints=())
        slow.checkpoint = lambda: not release.is_set()
        first = threading.Thread(target=slow.run, args=("_pass_slow",))
        first.start()
        try:
            deadline = time.monotonic() + 20
            while not scanner_process._active_lock.locked() and time.monotonic() < deadline:
                time.sleep(0.01)
            with self.assertRaises(ScannerProcessBusy):
                _Parent(checkpoints=(False,)).run("_pass_until_stopped")
        finally:
            release.set()
            first.join(30)
        self.assertFalse(first.is_alive())

    def test_lost_parent_stops_the_child_pass(self):
        parent_end, child_end = multiprocessing.Pipe()
        parent_end.close()
        recorded = importlib.import_module(ME)._LOCAL_CHECKPOINTS  # the module _child_main runs
        recorded.clear()
        _child_main(child_end, f"{ME}:_pass_records_checkpoint_locally", (False, True, False, False))
        self.assertEqual(recorded, [])


_BACKEND_STAND_IN = """
import os, sys, threading, time
from terminal.runtime.scanner_process import run_scan_pass_in_child_process
threading.Thread(target=run_scan_pass_in_child_process, daemon=True, kwargs=dict(
    target="tests.test_scanner_process_isolation:_pass_never_checkpoints")).start()
deadline = time.time() + 60
while not os.path.exists(os.environ["SCANNER_CHILD_PID_FILE"]) and time.time() < deadline:
    time.sleep(0.05)
print("child-ready", flush=True)
if sys.argv[1] == "exit":
    sys.exit(0)
time.sleep(600)
"""


def _alive(pid):
    import _winapi
    try:
        handle = _winapi.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    except OSError:
        return False
    try:
        return _winapi.GetExitCodeProcess(handle) == 259  # STILL_ACTIVE
    finally:
        _winapi.CloseHandle(handle)


def _kill(pid):
    import _winapi
    try:
        handle = _winapi.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        _winapi.TerminateProcess(handle, 1)
        _winapi.CloseHandle(handle)
    except OSError:
        pass


@unittest.skipUnless(os.name == "nt", "the PAPER runtime host is Windows")
class BackendLossTests(unittest.TestCase):
    """The Scanner child must never outlive its backend (one Scanner owner)."""

    def start_backend(self, mode):
        import subprocess
        import sys

        self.pid_file = Path(tempfile.mkdtemp()) / "child.pid"
        env = {**os.environ, "SCANNER_CHILD_PID_FILE": str(self.pid_file)}
        # -c from the project root: the project's own `signal` package shadows the
        # standard module exactly as it does inside the real backend.
        backend = subprocess.Popen(
            [sys.executable, "-c", _BACKEND_STAND_IN, mode], cwd=Path(__file__).resolve().parents[1],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(backend.stdout.readline().strip(), "child-ready")
        # The child wrote its pid and then loops forever: only the OS can end it.
        child = int(self.pid_file.read_text())
        self.addCleanup(_kill, child)
        if mode == "kill":
            self.assertTrue(_alive(child))
        return backend, child

    def assert_gone(self, pid):
        deadline = time.monotonic() + 10
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(_alive(pid), "Scanner child outlived its backend")

    def test_killed_backend_takes_the_scanner_child_with_it(self):
        backend, child = self.start_backend("kill")
        backend.kill()  # abrupt loss: no Python cleanup runs
        backend.communicate(timeout=30)
        self.assert_gone(child)

    def test_backend_exit_with_a_running_child_is_clean(self):
        backend, child = self.start_backend("exit")
        _out, err = backend.communicate(timeout=60)
        self.assertEqual(backend.returncode, 0, err)
        self.assertNotIn("SIGTERM", err)
        self.assertNotIn("Exception ignored", err)
        self.assert_gone(child)


class CoordinatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "paper.sqlite3"

    def coordinator(self, target, *, require_progress=False, first_progress_timeout_s=10.0):
        runtime = ScannerControlRuntime(
            lambda: SQLiteStore.open(self.db_path), ACCOUNT_ID,
            scan_pass=lambda **callbacks: run_scan_pass_in_child_process(
                **callbacks,
                require_progress=require_progress,
                first_progress_timeout_s=first_progress_timeout_s,
                target=f"{ME}:{target}",
            ),
            clock_ms=lambda: int(time.time() * 1000), scan_interval_s=0.05)
        self.addCleanup(runtime.close)
        return runtime

    def wait_for(self, runtime, mode):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if runtime.status().mode == mode:
                return
            time.sleep(0.05)
        self.fail(f"Scanner never reached {mode}")

    def test_owner_stop_ends_the_child_and_the_durable_state_is_stopped(self):
        runtime = self.coordinator("_pass_slow")
        runtime.start()
        self.assertEqual(runtime.start_scanner().mode, SCANNER_RUNNING)
        deadline = time.monotonic() + 20
        while not scanner_process._active_lock.locked() and time.monotonic() < deadline:
            time.sleep(0.02)
        runtime.stop_scanner()
        self.wait_for(runtime, SCANNER_STOPPED)
        deadline = time.monotonic() + 20
        while scanner_process._active_lock.locked() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(multiprocessing.active_children(), [])

    def test_stop_releases_a_hung_child_and_allows_a_repeated_start(self):
        marker = Path(self.temp_dir.name) / "hung-once.pid"
        with patch.dict(os.environ, {"SCANNER_HANG_ONCE_FILE": str(marker)}):
            runtime = self.coordinator("_pass_hangs_once", require_progress=True)
            runtime.start()
            self.assertEqual(runtime.start_scanner().mode, SCANNER_RUNNING)
            deadline = time.monotonic() + 20
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "hung Scanner child did not start")

            runtime.stop_scanner()
            deadline = time.monotonic() + 20
            while scanner_process._active_lock.locked() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(scanner_process._active_lock.locked())
            self.assertEqual(multiprocessing.active_children(), [])

            self.assertEqual(runtime.start_scanner().mode, SCANNER_RUNNING)
            self.wait_for(runtime, SCANNER_STOPPED)
            self.assertEqual(multiprocessing.active_children(), [])

    def test_missing_first_progress_stops_with_a_diagnostic_reason(self):
        runtime = self.coordinator(
            "_pass_never_checkpoints",
            require_progress=True,
            first_progress_timeout_s=0.2,
        )
        runtime.start()
        self.assertEqual(runtime.start_scanner().mode, SCANNER_RUNNING)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = runtime.status()
            if state.mode == SCANNER_STOPPED and state.reason == "first_progress_timeout":
                break
            time.sleep(0.02)
        self.assertEqual((state.mode, state.reason),
                         (SCANNER_STOPPED, "first_progress_timeout"))

    def test_normal_pass_reports_progress_and_releases_the_child(self):
        runtime = self.coordinator("_pass_reports_progress", require_progress=True)
        runtime.start()
        self.assertEqual(runtime.start_scanner().mode, SCANNER_RUNNING)
        self.wait_for(runtime, SCANNER_STOPPED)
        self.assertFalse(scanner_process._active_lock.locked())
        self.assertEqual(multiprocessing.active_children(), [])

    def test_child_crash_returns_the_scanner_to_stopped_without_raising(self):
        runtime = self.coordinator("_pass_crashes")
        runtime.start()
        runtime.start_scanner()
        self.wait_for(runtime, SCANNER_STOPPED)
        self.assertEqual(multiprocessing.active_children(), [])


class WiringTests(unittest.TestCase):
    def test_backend_scan_pass_uses_the_child_process_with_the_same_callbacks(self):
        callbacks = dict(box_plan_preparer=object(), control_checkpoint=object(),
                         robot_candidate_observer=object())
        with patch.object(scanner_process, "run_scan_pass_in_child_process") as child:
            paper_runtime._run_scanner_scan_pass(**callbacks)
        child.assert_called_once_with(
            **callbacks,
            child_started=None,
            stop_requested=None,
            require_progress=True,
        )

    def test_the_child_entry_never_opens_the_paper_database(self):
        source = Path(scanner_process.__file__).read_text(encoding="utf-8")
        self.assertNotIn("SQLiteStore", source)
        self.assertNotIn("sqlite3", source)


if __name__ == "__main__":
    unittest.main()
