"""PROCESS-ISOLATION-1: run one Scanner pass in a child Python process.

The Scanner's CPU-heavy analysis must not share the backend interpreter with the
PAPER owner thread (protection callbacks, ingress queue). The pass therefore runs
in a spawned child process, while every effect that touches the PAPER database
stays in the backend: the child never opens the PAPER DB, it only asks the parent
to run the three existing callbacks (control checkpoint, Box plan preparation,
Robot candidate observer) and waits for their answer. The backend keeps them on
the same dispatch path to its single owner as before.

Lifecycle and fail-closed rules:
- one pass, one child; at most one active child per backend process
  (``ScannerProcessBusy`` for a concurrent request);
- the backend terminates the child whenever the pass ends for any reason;
- the child never outlives the backend: on Windows it runs in a kill-on-close
  Job Object, so even an abrupt backend loss ends it at once (a child that
  cannot be bound is stopped and the pass refused), and a normal backend exit
  stops a still-running child first; elsewhere a lost parent ends the pass at
  its next checkpoint (pipe EOF = stop);
- a child that exits without reporting completion raises ``ScannerProcessError``
  and never touches Robot state.
"""
from __future__ import annotations

import atexit
import importlib
import multiprocessing
import multiprocessing.util  # registers its exit hook before ours, so ours runs first
import sys
import threading
from typing import Callable

SCANNER_PASS_TARGET = "main:run_scan_pass"
CHILD_POLL_S = 0.2
CHILD_EXIT_GRACE_S = 5.0
CHILD_TERMINATE_WAIT_S = 5.0
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

_active_lock = threading.Lock()
_active_process = None


class ScannerProcessError(RuntimeError):
    """The Scanner pass process ended without a proven completion."""


class ScannerProcessBusy(ScannerProcessError):
    """Another Scanner pass process is already active in this backend."""


def run_scan_pass_in_child_process(
    *,
    box_plan_preparer: Callable | None = None,
    control_checkpoint: Callable[[], bool] | None = None,
    robot_candidate_observer: Callable[[str], None] | None = None,
    target: str = SCANNER_PASS_TARGET,
) -> None:
    """Run ``target`` (``module:function``) once in a child and serve its callbacks here."""
    global _active_process
    if not _active_lock.acquire(blocking=False):
        raise ScannerProcessBusy("a Scanner pass process is already active")
    try:
        context = multiprocessing.get_context("spawn")
        parent_end, child_end = context.Pipe()
        enabled = (box_plan_preparer is not None, control_checkpoint is not None,
                   robot_candidate_observer is not None)
        process = context.Process(
            target=_child_main, args=(child_end, target, enabled),
            name="bybitscanner-scanner-pass", daemon=True,
        )
        process.start()
        _active_process = process
        child_end.close()
        job = None
        try:
            if sys.platform == "win32":
                try:
                    job = _bind_child_to_backend_lifetime(process)
                except OSError as error:
                    raise ScannerProcessError(
                        f"Scanner child cannot be bound to the backend lifetime: {error}") from error
            _serve(parent_end, process, box_plan_preparer, control_checkpoint,
                   robot_candidate_observer)
        finally:
            _end_child(process)
            _active_process = None
            parent_end.close()
            if job is not None:
                job.close()
    finally:
        _active_lock.release()


class _KillOnCloseJob:
    """Windows Job Object that kills its processes when its last handle closes.

    The handle is held only by this backend, so the OS ends the Scanner child as
    soon as the backend disappears for any reason, including an abrupt kill.
    """

    def __init__(self, kernel32, handle):
        self._kernel32, self._handle = kernel32, handle

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def _bind_child_to_backend_lifetime(process) -> _KillOnCloseJob:
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", ctypes.c_ulonglong * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    job = _KillOnCloseJob(kernel32, handle)
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    process_handle = getattr(getattr(process, "_popen", None), "_handle", None)
    if (process_handle is None
            or not kernel32.SetInformationJobObject(
                handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info))
            or not kernel32.AssignProcessToJobObject(handle, int(process_handle))):
        error = ctypes.get_last_error()
        job.close()
        raise ctypes.WinError(error)
    return job


@atexit.register
def _stop_active_child_at_exit() -> None:
    """A normal backend exit never leaves a Scanner child behind.

    Runs before multiprocessing's own exit hook, which would end the child with
    TERMINATE and then fail on the shadowed ``signal`` module.
    """
    process = _active_process
    if process is not None and process.exitcode is None:
        _hard_stop(process)


def _end_child(process) -> None:
    """Let a finishing child exit by itself; hard-stop only one that does not."""
    process.join(CHILD_EXIT_GRACE_S)
    if process.exitcode is not None:
        return
    _hard_stop(process)


def _hard_stop(process) -> None:
    handle = getattr(getattr(process, "_popen", None), "_handle", None)
    if sys.platform == "win32" and handle is not None:
        # Exit code 1, not multiprocessing's TERMINATE: its wait() maps TERMINATE to
        # signal.SIGTERM, and this repository's own ``signal`` package (analyzer)
        # shadows the standard module whenever the project root is on sys.path.
        import _winapi

        try:
            _winapi.TerminateProcess(int(handle), 1)
        except OSError:
            pass
    else:
        process.terminate()
    process.join(CHILD_TERMINATE_WAIT_S)


def _serve(connection, process, box_plan_preparer, control_checkpoint, observer) -> None:
    while True:
        if not connection.poll(CHILD_POLL_S):
            if process.is_alive():
                continue
            if not connection.poll(0):
                break
        try:
            kind, payload = connection.recv()
        except (EOFError, OSError):
            break
        if kind == "done":
            return
        if kind == "error":
            raise ScannerProcessError(f"Scanner pass process failed: {payload}")
        try:
            connection.send(_answer(kind, payload, box_plan_preparer, control_checkpoint, observer))
        except (EOFError, OSError):
            break
    process.join(1.0)
    raise ScannerProcessError(
        f"Scanner pass process ended without completion; exitcode={process.exitcode}")


def _answer(kind, payload, box_plan_preparer, control_checkpoint, observer):
    if kind == "checkpoint":
        try:
            return bool(control_checkpoint())
        except Exception as error:
            print(f"[SCANNER PROCESS CHECKPOINT ERROR] error_class={type(error).__name__}")
            return False  # an unknown control state stops the pass
    if kind == "box_plan":
        from terminal.paper.ikigai_box_plan import IkigaiBoxPlanRejected

        try:
            result = box_plan_preparer(*payload)
        except IkigaiBoxPlanRejected as rejection:
            return ("rejected", str(rejection))
        except Exception as error:
            return ("error", f"{type(error).__name__}: {error}")
        return ("ok", None if result is None else str(result))
    if kind == "candidate":
        try:
            observer(payload)
        except Exception as error:
            return ("error", type(error).__name__)
        return ("ok", None)
    return ("error", f"unknown request {kind!r}")


def _use_project_signal_package() -> None:
    """Give the child the backend's import view of ``signal``.

    The spawn bootstrap imports the standard ``signal`` before the parent's
    sys.path applies, while the Scanner's analyzer imports this repository's own
    ``signal`` package (``signal.quality``/``signal.filter``), exactly as it
    resolves inside the backend. Dropping the cached standard module lets the
    project package resolve; modules that already bound the standard one keep it.
    """
    module = sys.modules.get("signal")
    if module is not None and not hasattr(module, "__path__"):
        del sys.modules["signal"]


def _child_main(connection, target: str, enabled: tuple[bool, bool, bool]) -> None:
    """Child process entry: never opens the PAPER DB; every effect goes to the parent."""
    _use_project_signal_package()

    def call(kind, payload):
        connection.send((kind, payload))
        return connection.recv()

    def checkpoint() -> bool:
        try:
            return bool(call("checkpoint", None))
        except (EOFError, OSError):
            return False  # parent gone: stop the pass

    def box_plan(symbol, timeframe, formation):
        status, value = call("box_plan", (symbol, timeframe, formation))
        if status == "ok":
            return value
        if status == "rejected":
            from terminal.paper.ikigai_box_plan import IkigaiBoxPlanRejected

            raise IkigaiBoxPlanRejected(value)
        raise ScannerProcessError(value)

    def observe(candidate_id) -> None:
        status, value = call("candidate", str(candidate_id))
        if status != "ok":
            raise ScannerProcessError(value)

    module_name, function_name = target.split(":", 1)
    try:
        scan_pass = getattr(importlib.import_module(module_name), function_name)
        scan_pass(
            box_plan_preparer=box_plan if enabled[0] else None,
            control_checkpoint=checkpoint if enabled[1] else None,
            robot_candidate_observer=observe if enabled[2] else None,
        )
    except BaseException as error:
        try:
            connection.send(("error", f"{type(error).__name__}: {error}"))
        except (EOFError, OSError):
            pass
        raise
    try:
        connection.send(("done", None))
    except (EOFError, OSError):
        pass  # parent already gone; nothing left to report
