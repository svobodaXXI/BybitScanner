"""Durable Robot v0.1 admission-gate operator control commands.

Implements ``start_robot()``, ``pause_robot()``, ``resume_robot()`` and
``stop_robot()`` exactly per
``DOCUMENTS/AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md`` v1.2 Sections 1,
2, 5 and 6. Each function is a pure durable-state transition on
``robot_runtime_state`` and opens its own ``SQLiteStore`` connection against
the shared PAPER database, exactly like
``terminal.application.robot_admission.admit_robot_candidate`` — none of them
submit, retry, amend, cancel or close an order.

``close_all_now()`` (Section 4) is different: unlike the four commands above,
it must execute a real Market close through the live, already-running PAPER
backend process (``terminal.runtime.paper_http_server``), which a pure
``SQLiteStore`` write cannot reach — ``telegram_review.py`` and that backend
run as separate OS processes with no shared memory (see CR-ROBOT-CONTROL-001
revision 1.1). Legality is still validated the same way as the other four
commands (a direct durable-state read), but execution is bridged over that
backend's existing localhost REST API, reusing
``PaperRuntime.robot_close_all()`` on the server side — the same trust model
already accepted for its sibling ``/api/full-close``/``/api/close-all``
routes (bound to 127.0.0.1, gated by ``require_paper_mutations()``, no
additional operator-token authentication).

``close_all_now()`` deliberately takes its HTTP transport (``http_post``) as a
required parameter rather than importing ``requests`` itself:
``tests/test_terminal_execution_engine.py``'s
``test_no_mutation_or_network_api_is_exposed`` asserts that nothing under
``terminal/application/`` imports a network client, so the actual
``requests.post`` call is supplied by the caller (``telegram_review.py``,
which already depends on ``requests``) instead of living in this module.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from terminal.application.robot_recovery import (
    PAUSED,
    READY,
    ROBOT_RUNNING,
    ROBOT_STOPPED,
    RobotRecoveryCoordinator,
)
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import (
    PersistenceError,
    RobotRuntimeStateRecord,
    SQLiteStore,
)

PAPER_ACCOUNT_ID = TradingAccountId("paper")
DEFAULT_DATABASE_PATH = Path(
    os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3")
)
DEFAULT_PAPER_BACKEND_URL = os.environ.get(
    "BYBITSCANNER_PAPER_BACKEND_URL", "http://127.0.0.1:8765"
)


class RobotControlRejected(PersistenceError):
    """Raised when an operator control command is illegal from the current durable state."""


def _clock(clock_ms: Callable[[], int] | None) -> Callable[[], int]:
    return clock_ms or (lambda: int(time.time() * 1000))


def _now_ms(clock_ms: Callable[[], int] | None) -> int:
    value = _clock(clock_ms)()
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RobotControlRejected("Robot control clock returned invalid timestamp")
    return value


def _open_store(database_path: Path | str | None) -> SQLiteStore:
    resolved = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    return SQLiteStore.open(resolved)


def start_robot(
    *, database_path: Path | str | None = None, clock_ms: Callable[[], int] | None = None,
) -> RobotRuntimeStateRecord:
    """``Запустить робота``. Legal only from durable ``ROBOT_STOPPED`` (Section 1).

    From any other durable state, including ``RECONCILIATION_REQUIRED``,
    rejected with an explicit error and no side effect on durable state.
    Delegates the actual reconciliation to
    ``RobotRecoveryCoordinator.start()``, which never revives a previously
    stopped/terminal candidate.
    """
    store = _open_store(database_path)
    try:
        now = _now_ms(clock_ms)
        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            runtime = store.initialize_robot_runtime_state(PAPER_ACCOUNT_ID, updated_at_ms=now)
        # Legal only from the fully clean (ROBOT_STOPPED, ROBOT_STOPPED) pair.
        # (ROBOT_STOPPED, RECONCILIATION_REQUIRED) shares mode=ROBOT_STOPPED but
        # must still be rejected: recovering out of RECONCILIATION_REQUIRED is a
        # separate, unresolved problem that start_robot() must never shortcut.
        if runtime.mode != ROBOT_STOPPED or runtime.recovery_status != ROBOT_STOPPED:
            raise RobotControlRejected("start_robot is legal only from (ROBOT_STOPPED, ROBOT_STOPPED)")
        coordinator = RobotRecoveryCoordinator(store, PAPER_ACCOUNT_ID, clock_ms=_clock(clock_ms))
        result = coordinator.start()
        return result.runtime_state
    finally:
        store.close()


def pause_robot(
    *, database_path: Path | str | None = None, clock_ms: Callable[[], int] | None = None,
) -> RobotRuntimeStateRecord:
    """Legal only from ``(ROBOT_RUNNING, READY)`` (Section 2).

    Stops admission of new candidates immediately. Never touches an
    already-open Robot position or its STOP/TAKE lifecycle.
    """
    store = _open_store(database_path)
    try:
        now = _now_ms(clock_ms)
        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            raise RobotControlRejected("Robot runtime state is unavailable")
        if runtime.mode != ROBOT_RUNNING or runtime.recovery_status != READY:
            raise RobotControlRejected("pause_robot is legal only from (ROBOT_RUNNING, READY)")
        return store.update_robot_runtime_state(
            PAPER_ACCOUNT_ID, mode=ROBOT_RUNNING, recovery_status=PAUSED, reason=None,
            expected_version=runtime.version, updated_at_ms=now,
        )
    finally:
        store.close()


def resume_robot(
    *, database_path: Path | str | None = None, clock_ms: Callable[[], int] | None = None,
) -> RobotRuntimeStateRecord:
    """Legal only from ``(ROBOT_RUNNING, PAUSED)`` (Section 6).

    Symmetric to ``start_robot()``: rejected with an explicit error from
    ``RECONCILIATION_REQUIRED`` and every other state, including
    ``ROBOT_STOPPED`` (this is not a substitute for ``start_robot()``).
    """
    store = _open_store(database_path)
    try:
        now = _now_ms(clock_ms)
        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None or runtime.mode != ROBOT_RUNNING or runtime.recovery_status != PAUSED:
            raise RobotControlRejected("resume_robot is legal only from (ROBOT_RUNNING, PAUSED)")
        return store.update_robot_runtime_state(
            PAPER_ACCOUNT_ID, mode=ROBOT_RUNNING, recovery_status=READY, reason=None,
            expected_version=runtime.version, updated_at_ms=now,
        )
    finally:
        store.close()


def close_all_now(
    *,
    http_post: Callable[[str, dict], dict],
    database_path: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
    backend_url: str | None = None,
) -> dict:
    """Legal only from ``(ROBOT_RUNNING, READY)`` or ``(ROBOT_RUNNING, PAUSED)`` (Section 4).

    Rejected with an explicit error from ``RECONCILIATION_REQUIRED`` and
    every other state. Acts exclusively on Robot-owned open positions
    (``PaperRuntime.robot_close_all()`` on the server side, not the
    account-wide ``PaperRuntime.close_all()``). Does not by itself change
    admission mode on success or as a no-op; a close that cannot be
    authoritatively confirmed lands the runtime in
    ``(ROBOT_RUNNING, RECONCILIATION_REQUIRED)`` (handled server-side, inside
    the same request that attempted the close).

    ``http_post(url, payload) -> dict`` performs the actual network call and
    is supplied by the caller — see the module docstring for why this
    function never imports a network client itself.
    """
    store = _open_store(database_path)
    try:
        now = _now_ms(clock_ms)
        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            raise RobotControlRejected("Robot runtime state is unavailable")
        if runtime.mode != ROBOT_RUNNING or runtime.recovery_status not in (READY, PAUSED):
            raise RobotControlRejected(
                "close_all_now is legal only from (ROBOT_RUNNING, READY) "
                "or (ROBOT_RUNNING, PAUSED)"
            )
    finally:
        store.close()

    url = f"{backend_url or DEFAULT_PAPER_BACKEND_URL}/api/robot/close-all-now"
    client_action_id = f"robot-close-all-{now}"
    try:
        return http_post(url, {"client_action_id": client_action_id})
    except RobotControlRejected:
        raise
    except Exception as exc:
        raise RobotControlRejected(
            f"close_all_now could not reach the PAPER backend at {url}: {exc}"
        ) from exc


def stop_robot(
    *, database_path: Path | str | None = None, clock_ms: Callable[[], int] | None = None,
) -> RobotRuntimeStateRecord:
    """Legal only from ``(ROBOT_RUNNING, READY)`` or ``(ROBOT_RUNNING, PAUSED)`` (Section 5, v1.1).

    Rejected with an explicit error when a Robot-owned position is open
    (never itself initiates a close — call ``pause_robot()`` then
    ``close_all_now()`` first) or when durable state is
    ``RECONCILIATION_REQUIRED``.
    """
    store = _open_store(database_path)
    try:
        now = _now_ms(clock_ms)
        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            raise RobotControlRejected("Robot runtime state is unavailable")
        if runtime.mode != ROBOT_RUNNING or runtime.recovery_status not in (READY, PAUSED):
            raise RobotControlRejected(
                "stop_robot is legal only from (ROBOT_RUNNING, READY) or (ROBOT_RUNNING, PAUSED)"
            )
        candidates = store.load_robot_candidates(PAPER_ACCOUNT_ID)
        if any(item.status == "OPEN" for item in candidates):
            raise RobotControlRejected(
                "stop_robot is rejected while a Robot-owned position is open; "
                "call pause_robot() and then close_all_now() first"
            )
        return store.update_robot_runtime_state(
            PAPER_ACCOUNT_ID, mode=ROBOT_STOPPED, recovery_status=ROBOT_STOPPED, reason=None,
            expected_version=runtime.version, updated_at_ms=now,
        )
    finally:
        store.close()
