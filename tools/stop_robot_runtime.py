"""Canonical owner runtime shutdown for the PAPER prototype.

One orchestrator behind every owner stop surface:

* ``all``     — Scanner STOPPED -> Robot canonical safe-stop -> Telegram worker
                graceful shutdown -> PAPER backend graceful shutdown (always last).
* ``scanner`` — Scanner STOPPED; the shared runtime is shut down only when the
                durable Robot is already fully STOPPED and no protection coverage
                remains, otherwise backend/Telegram stay alive for the Robot.

Ownership is proven by the exact PAPER DB identity before any mutation, and
processes are only asked to exit through their own identity-checked localhost
shutdown endpoints. Nothing is killed by name, port or PID. No LIVE mutation.

Usage: python -m tools.stop_robot_runtime [all|scanner] [--notify-chat CHAT_ID]
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Callable, ContextManager, Iterator, Mapping

import requests

from urllib.parse import urlsplit

from terminal.application.robot_control import RobotControlRejected, stop_robot
from tools.legacy_runtime_process import (
    BACKEND, TELEGRAM, LegacyOwnerUnproven, resolve_legacy_chain, terminate_exact_pids,
)
from tools.runtime_intent import PROJECT_ROOT, expected_database_identity

SCOPE_ALL = "all"
SCOPE_SCANNER = "scanner"
SCOPES = (SCOPE_ALL, SCOPE_SCANNER)

DEFAULT_BACKEND_URL = "http://127.0.0.1:8765"
DEFAULT_TELEGRAM_PORT = "8766"
EXIT_WAIT_S = 60.0
POLL_INTERVAL_S = 0.5
PROBE_TIMEOUT_S = 5.0
MUTATION_TIMEOUT_S = 15.0

ROBOT_STOPPED_PAIR = ("ROBOT_STOPPED", "ROBOT_STOPPED")
ROBOT_STOPPABLE = {("ROBOT_RUNNING", "READY"), ("ROBOT_RUNNING", "PAUSED")}

ABSENT = "absent"
PRESENT = "present"


class SafeStopError(RuntimeError):
    """A shutdown precondition could not be proven; nothing further is changed."""


class Unreachable(Exception):
    """No HTTP response: nothing is serving the endpoint."""


@dataclass(frozen=True)
class ShutdownResult:
    scope: str
    ok: bool
    message: str
    steps: tuple[str, ...] = field(default_factory=tuple)
    runtime_stopped: bool = False


def _http_get(url: str, timeout: float) -> tuple[int, object]:
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        raise Unreachable(str(exc)) from exc
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def _http_post(url: str, payload: Mapping[str, object], timeout: float) -> tuple[int, object]:
    response = requests.post(url, json=dict(payload), timeout=timeout, allow_redirects=False)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def _post_robot_json(url: str, payload: dict) -> dict:
    try:
        response = requests.post(url, json=payload, timeout=MUTATION_TIMEOUT_S, allow_redirects=False)
    except Exception as exc:
        raise RobotControlRejected(f"Robot backend request failed: {exc}") from exc
    try:
        body = response.json()
    except Exception:
        body = {}
    if response.status_code != 200 or not isinstance(body, dict) or body.get("ok") is not True:
        reason = body.get("error") if isinstance(body, dict) else None
        raise RobotControlRejected(str(reason or f"Robot backend HTTP {response.status_code}"))
    return body


def _database_path(root: Path, env: Mapping[str, str]) -> Path:
    path = Path(env.get("BYBITSCANNER_PAPER_DB") or "paper_runtime.sqlite3")
    return path if path.is_absolute() else root / path


def read_robot_state(database_path: Path) -> tuple[str, str] | None:
    """Durable Robot (mode, recovery_status), read-only; never creates or migrates the DB."""
    if not database_path.exists():
        return None
    try:
        connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT mode, recovery_status FROM robot_runtime_state WHERE trading_account_id = ?",
                ("paper",),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise SafeStopError("durable Robot state is unreadable") from exc
    return None if row is None else (str(row[0]), str(row[1]))


def _assert_legacy_paper_quiescence(connection: sqlite3.Connection) -> None:
    active_candidates = int(connection.execute(
        """SELECT COUNT(*) FROM robot_candidates
           WHERE trading_account_id='paper' AND status IN ('APPROVED', 'OPEN')"""
    ).fetchone()[0])
    active_limits = int(connection.execute(
        """SELECT COUNT(*) FROM paper_limit_orders
           WHERE trading_account_id='paper'
             AND status IN ('open', 'partially_filled')"""
    ).fetchone()[0])
    positions = connection.execute(
        """SELECT side, quantity FROM position_projections
           WHERE trading_account_id='paper' AND category='linear' AND position_idx=0"""
    ).fetchall()
    unresolved_obligations = int(connection.execute(
        """SELECT COUNT(*) FROM paper_protection_obligations
           WHERE trading_account_id='paper' AND status!='RESOLVED'"""
    ).fetchone()[0])

    open_exposure = 0
    for side, raw_quantity in positions:
        quantity = Decimal(str(raw_quantity))
        if not quantity.is_finite() or quantity < 0:
            raise InvalidOperation
        if str(side) != "Flat" and quantity > 0:
            open_exposure += 1

    blockers = (
        ("active Robot candidates", active_candidates),
        ("working PAPER limits", active_limits),
        ("open PAPER exposure", open_exposure),
        ("unresolved protection obligations", unresolved_obligations),
    )
    for label, count in blockers:
        if count:
            raise SafeStopError(f"legacy PAPER shutdown blocked by {label}")


def prove_legacy_paper_quiescence(database_path: Path) -> None:
    """Read-only snapshot proof that an old PAPER backend owns no durable Robot work."""
    if not database_path.exists():
        raise SafeStopError("legacy PAPER database is unavailable")
    try:
        connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("BEGIN")
            _assert_legacy_paper_quiescence(connection)
        finally:
            connection.close()
    except SafeStopError:
        raise
    except (sqlite3.Error, InvalidOperation, TypeError, ValueError) as exc:
        raise SafeStopError("legacy PAPER durable shutdown evidence is unreadable") from exc


@contextmanager
def hold_legacy_paper_quiescence(database_path: Path) -> Iterator[None]:
    """Freeze PAPER SQLite writers after proving quiescence; never edit durable state.

    BEGIN IMMEDIATE takes SQLite's writer reservation before the final legacy
    process proof. query_only is then enabled before any project query so this
    helper cannot modify rows itself. If another writer is active, acquisition
    fails immediately and shutdown remains fail-closed.
    """
    if not database_path.exists():
        raise SafeStopError("legacy PAPER database is unavailable")
    connection = None
    try:
        connection = sqlite3.connect(
            database_path.resolve().as_uri() + "?mode=rw", uri=True, timeout=0.0,
        )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA query_only=ON")
        _assert_legacy_paper_quiescence(connection)
    except SafeStopError:
        if connection is not None:
            connection.close()
        raise
    except (sqlite3.Error, InvalidOperation, TypeError, ValueError) as exc:
        if connection is not None:
            connection.close()
        raise SafeStopError("legacy PAPER durable shutdown barrier is unavailable") from exc
    try:
        yield
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


@dataclass(frozen=True)
class LegacyBackendProof:
    process_instance_id: str
    build_sha: str


class RuntimeShutdown:
    def __init__(
        self,
        *,
        root: Path = PROJECT_ROOT,
        env: Mapping[str, str] | None = None,
        get: Callable[[str, float], tuple[int, object]] = _http_get,
        post: Callable[[str, Mapping[str, object], float], tuple[int, object]] = _http_post,
        robot_state: Callable[[], tuple[str, str] | None] | None = None,
        stop_robot_fn: Callable[[], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        legacy_resolver: Callable[[str, str, int, Path], tuple[int, ...]] = resolve_legacy_chain,
        legacy_terminator: Callable[[tuple[int, ...]], None] = terminate_exact_pids,
        legacy_paper_quiescence: Callable[[], None] | None = None,
        legacy_paper_guard: Callable[[], ContextManager[None]] | None = None,
    ) -> None:
        env = dict(os.environ if env is None else env)
        database_path = _database_path(root, env)
        self._root = root
        self._expected = expected_database_identity(root, env)
        self._backend = (env.get("BYBITSCANNER_PAPER_BACKEND_URL") or DEFAULT_BACKEND_URL).rstrip("/")
        port = env.get("BYBITSCANNER_TELEGRAM_MONITORING_PORT") or DEFAULT_TELEGRAM_PORT
        self._telegram = f"http://127.0.0.1:{port}"
        self._legacy_resolver = legacy_resolver
        self._legacy_terminator = legacy_terminator
        self._legacy_paper_quiescence = (
            legacy_paper_quiescence
            or (lambda: prove_legacy_paper_quiescence(database_path))
        )
        self._legacy_paper_guard = (
            legacy_paper_guard
            or (lambda: hold_legacy_paper_quiescence(database_path))
        )
        self._get = get
        self._post = post
        self._robot_state = robot_state or (lambda: read_robot_state(database_path))
        self._stop_robot = stop_robot_fn or (lambda: stop_robot(
            http_post=_post_robot_json, database_path=database_path, backend_url=self._backend,
        ))
        self._sleep = sleep
        self._monotonic = monotonic

    def run(self, scope: str) -> ShutdownResult:
        if scope not in SCOPES:
            return ShutdownResult(scope, False, f"unknown shutdown scope {scope!r}")
        steps: list[str] = []
        try:
            return self._run(scope, steps)
        except (SafeStopError, RobotControlRejected) as exc:
            return ShutdownResult(scope, False, f"STOP BLOCKED: {exc}", tuple(steps))

    def _run(self, scope: str, steps: list[str]) -> ShutdownResult:
        # Both identities are proven before the first mutation of anything.
        backend = self._probe_backend()
        telegram = self._probe_telegram()

        if backend == PRESENT:
            self._stop_scanner()
            steps.append("scanner:stop")
            if scope == SCOPE_ALL:
                state = self._robot_state()
                if state == ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"):
                    self._reconcile_robot()
                    steps.append("robot:reconcile")
                    state = self._robot_state()
                    if state not in ROBOT_STOPPABLE:
                        raise SafeStopError(
                            "Robot reconcile did not establish a legal stoppable state; runtime kept alive"
                        )
                if state in ROBOT_STOPPABLE:
                    self._stop_robot()
                    steps.append("robot:stop")
                elif state != ROBOT_STOPPED_PAIR:
                    raise SafeStopError(f"Robot state {state} requires the PAPER backend; runtime kept alive")

        state = self._robot_state()
        if state is None and backend == PRESENT:
            # A live backend always initializes the durable Robot row; absence is unproven.
            raise SafeStopError("durable Robot state is unavailable; runtime kept alive")
        if state not in (ROBOT_STOPPED_PAIR, None):
            if scope == SCOPE_SCANNER:
                return ShutdownResult(
                    scope, True, f"Scanner STOPPED; Robot {state[0]}/{state[1]} keeps the runtime alive.",
                    tuple(steps),
                )
            raise SafeStopError(f"Robot is {state} but the PAPER backend is unavailable to stop it")

        if backend == PRESENT and not self._protection_quiescent():
            if scope == SCOPE_SCANNER:
                return ShutdownResult(
                    scope, True, "Scanner STOPPED; Robot protection coverage keeps the runtime alive.",
                    tuple(steps),
                )
            legacy_proof = self._retire_entry_coverage()
            if legacy_proof is None:
                steps.append("protection:retire-entry-arms")
                if not self._protection_quiescent():
                    raise SafeStopError("Robot protection coverage is still active; runtime kept alive")
            else:
                steps.append("protection:legacy-entry-proof")
                # The old backend has no monitor idle guard. Freeze SQLite writers
                # before the final process proof so an already in-flight pre-stop
                # tick cannot create a durable LIMIT between proof and termination.
                with self._legacy_paper_guard():
                    backend_chain = self._prove_legacy_entry_backend_chain(legacy_proof)
                    if telegram == PRESENT:
                        steps.append(self._shutdown(
                            self._telegram + "/shutdown", self._telegram + "/health",
                            "Telegram monitoring", TELEGRAM, "telegram",
                        ))
                    self._terminate_legacy_entry_backend(legacy_proof, backend_chain)
                    steps.append("backend:legacy-terminate")
                    self._wait_gone(self._backend + "/api/health", "PAPER backend")
                return ShutdownResult(
                    scope, True, "Runtime STOPPED.", tuple(steps), runtime_stopped=True,
                )

        if telegram == PRESENT:
            steps.append(self._shutdown(
                self._telegram + "/shutdown", self._telegram + "/health", "Telegram monitoring",
                TELEGRAM, "telegram",
            ))
        if backend == PRESENT:
            steps.append(self._shutdown(
                self._backend + "/api/runtime/shutdown", self._backend + "/api/health",
                "PAPER backend", BACKEND, "backend",
            ))
        return ShutdownResult(scope, True, "Runtime STOPPED.", tuple(steps), runtime_stopped=True)

    def _probe_backend(self) -> str:
        try:
            status, health = self._get(self._backend + "/api/health", PROBE_TIMEOUT_S)
        except Unreachable:
            return ABSENT
        if (
            status == 200 and isinstance(health, dict) and health.get("ok") is True
            and health.get("component") == "paper_backend" and health.get("mode") == "paper"
            and health.get("database_identity") == self._expected
        ):
            return PRESENT
        raise SafeStopError("PAPER backend identity does not match the configured PAPER DB")

    def _probe_telegram(self) -> str:
        try:
            _status, health = self._get(self._telegram + "/health", PROBE_TIMEOUT_S)
        except Unreachable:
            return ABSENT
        if (
            isinstance(health, dict) and health.get("component") == "telegram_monitoring"
            and health.get("database_identity") == self._expected
        ):
            return PRESENT
        raise SafeStopError("Telegram monitoring identity does not match the configured PAPER DB")

    def _stop_scanner(self) -> None:
        try:
            status, body = self._post(self._backend + "/api/scanner/stop", {}, MUTATION_TIMEOUT_S)
        except Exception as exc:
            raise SafeStopError("Scanner stop outcome is unknown; not retried") from exc
        if status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
            raise SafeStopError("Scanner stop was rejected")

    def _reconcile_robot(self) -> None:
        # The backend owns evidence and recovery. Never retry an ambiguous mutation.
        try:
            status, body = self._post(self._backend + "/api/robot/reconcile", {}, MUTATION_TIMEOUT_S)
        except Exception as exc:
            raise SafeStopError(
                "Robot reconcile outcome is unknown; not retried; runtime kept alive"
            ) from exc
        if (
            status != 200 or not isinstance(body, dict)
            or body.get("ok") is not True or body.get("success") is not True
        ):
            raise SafeStopError(
                "Robot reconcile did not confirm success; not retried; runtime kept alive"
            )

    def _retire_entry_coverage(self) -> LegacyBackendProof | None:
        if self._robot_state() != ROBOT_STOPPED_PAIR:
            raise SafeStopError("Robot is not fully STOPPED; runtime kept alive")
        try:
            status, body = self._post(
                self._backend + "/api/runtime/retire-entry-coverage",
                {"database_identity": self._expected}, MUTATION_TIMEOUT_S,
            )
        except Exception as exc:
            raise SafeStopError("Entry coverage retirement outcome is unknown; not retried; runtime kept alive") from exc
        if status in (404, 501):
            return self._prove_legacy_entry_coverage()
        if status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
            raise SafeStopError("Entry coverage retirement was not confirmed; runtime kept alive")
        protection = body.get("protection")
        if (
            not isinstance(protection, dict) or protection.get("healthy") is not True
            or protection.get("covered_symbols") != [] or protection.get("armed_symbols") != []
            or protection.get("unhealthy_symbols") != {}
        ):
            raise SafeStopError("Entry coverage is not proven quiescent; runtime kept alive")
        return None

    def _legacy_backend_attribution(self) -> LegacyBackendProof:
        try:
            status, health = self._get(self._backend + "/api/health", PROBE_TIMEOUT_S)
        except Unreachable as exc:
            raise SafeStopError("legacy PAPER backend disappeared before ownership proof") from exc
        if not (
            status == 200 and isinstance(health, dict) and health.get("ok") is True
            and health.get("component") == "paper_backend" and health.get("mode") == "paper"
            and health.get("database_identity") == self._expected
        ):
            raise SafeStopError("legacy PAPER backend identity changed before termination")
        process_instance_id = health.get("process_instance_id")
        build_sha = health.get("build_sha")
        if not isinstance(process_instance_id, str) or not process_instance_id.strip():
            raise SafeStopError("legacy PAPER backend process instance is unproven")
        if not isinstance(build_sha, str):
            raise SafeStopError("legacy PAPER backend build attribution is unproven")
        return LegacyBackendProof(process_instance_id.strip(), build_sha.strip())

    def _require_scanner_stopped(self) -> None:
        try:
            status, body = self._get(self._backend + "/api/scanner/status", PROBE_TIMEOUT_S)
        except Unreachable as exc:
            raise SafeStopError("Scanner state is unavailable from legacy PAPER backend") from exc
        if not (
            status == 200 and isinstance(body, dict) and body.get("ok") is True
            and body.get("mode") == "SCANNER_STOPPED"
        ):
            raise SafeStopError("Scanner is not proven STOPPED on legacy PAPER backend")

    def _require_temporary_entry_arm_shape(self) -> None:
        try:
            status, health = self._get(
                self._backend + "/api/robot/protection-health", PROBE_TIMEOUT_S,
            )
        except Unreachable as exc:
            raise SafeStopError("Robot protection health is unavailable") from exc
        if (
            status != 200 or not isinstance(health, dict)
            or health.get("healthy") is not True or health.get("unhealthy_symbols") != {}
        ):
            raise SafeStopError("legacy Robot protection is not healthy")
        covered = health.get("covered_symbols")
        armed = health.get("armed_symbols")
        roles = health.get("coverage_roles")
        if (
            not isinstance(covered, (list, tuple))
            or not isinstance(armed, (list, tuple))
            or not isinstance(roles, dict)
        ):
            raise SafeStopError("legacy Robot protection shape is unavailable")
        if (
            any(not isinstance(item, str) or not item.strip() for item in (*covered, *armed))
            or any(not isinstance(key, str) or not key.strip() for key in roles)
        ):
            raise SafeStopError("legacy Robot protection shape is malformed")
        covered_set = {item.strip().upper() for item in covered}
        armed_set = {item.strip().upper() for item in armed}
        normalized_roles = {
            str(key).strip().upper(): str(value).strip().upper()
            for key, value in roles.items()
        }
        if (
            not covered_set
            or len(covered_set) != len(covered)
            or len(armed_set) != len(armed)
            or covered_set != armed_set
            or set(normalized_roles) != covered_set
            or any(role != "ENTRY_PENDING" for role in normalized_roles.values())
        ):
            raise SafeStopError("remaining legacy protection is not stale temporary ENTRY_PENDING coverage")

    def _prove_legacy_entry_coverage(self) -> LegacyBackendProof:
        if self._robot_state() != ROBOT_STOPPED_PAIR:
            raise SafeStopError("Robot is not fully STOPPED; runtime kept alive")
        self._require_scanner_stopped()
        self._require_temporary_entry_arm_shape()
        try:
            self._legacy_paper_quiescence()
        except SafeStopError:
            raise
        except Exception as exc:
            raise SafeStopError("legacy PAPER durable shutdown evidence is unavailable") from exc
        return self._legacy_backend_attribution()

    def _prove_legacy_entry_backend_chain(
        self, proof: LegacyBackendProof,
    ) -> tuple[int, ...]:
        if self._robot_state() != ROBOT_STOPPED_PAIR:
            raise SafeStopError("Robot is not fully STOPPED; runtime kept alive")
        self._require_scanner_stopped()
        self._require_temporary_entry_arm_shape()
        if self._legacy_backend_attribution() != proof:
            raise SafeStopError("legacy PAPER backend identity changed before termination")
        location = urlsplit(self._backend)
        try:
            chain = tuple(self._legacy_resolver(
                BACKEND, location.hostname or "", location.port or 0, self._root,
            ))
        except LegacyOwnerUnproven as exc:
            raise SafeStopError(
                f"PAPER backend legacy ownership could not be proven ({exc}); nothing was terminated"
            ) from exc
        if self._legacy_backend_attribution() != proof:
            raise SafeStopError("legacy PAPER backend identity changed during ownership proof")
        return chain

    def _terminate_legacy_entry_backend(
        self, proof: LegacyBackendProof, expected_chain: tuple[int, ...],
    ) -> None:
        # SQLite writer reservation is held by the caller. Re-prove volatile
        # state and the exact process chain after Telegram is gone, then kill
        # only that unchanged chain while no PAPER writer can race the proof.
        if self._robot_state() != ROBOT_STOPPED_PAIR:
            raise SafeStopError("Robot is not fully STOPPED; runtime kept alive")
        self._require_scanner_stopped()
        self._require_temporary_entry_arm_shape()
        if self._legacy_backend_attribution() != proof:
            raise SafeStopError("legacy PAPER backend identity changed before termination")
        location = urlsplit(self._backend)
        try:
            final_chain = tuple(self._legacy_resolver(
                BACKEND, location.hostname or "", location.port or 0, self._root,
            ))
        except LegacyOwnerUnproven as exc:
            raise SafeStopError(
                f"PAPER backend legacy ownership could not be re-proven ({exc}); nothing was terminated"
            ) from exc
        if final_chain != expected_chain:
            raise SafeStopError("legacy PAPER backend process chain changed; nothing was terminated")
        self._require_temporary_entry_arm_shape()
        if self._legacy_backend_attribution() != proof:
            raise SafeStopError("legacy PAPER backend identity changed during final proof")
        try:
            self._legacy_terminator(final_chain)
        except Exception as exc:
            raise SafeStopError(f"PAPER backend legacy termination failed: {type(exc).__name__}") from exc

    def _protection_quiescent(self) -> bool:
        try:
            status, health = self._get(self._backend + "/api/robot/protection-health", PROBE_TIMEOUT_S)
        except Unreachable as exc:
            raise SafeStopError("Robot protection health is unavailable") from exc
        return (
            status == 200 and isinstance(health, dict) and health.get("healthy") is True
            and health.get("covered_symbols") == [] and health.get("unhealthy_symbols") == {}
            and health.get("armed_symbols", []) == []
        )

    def _shutdown(self, shutdown_url: str, health_url: str, name: str, kind: str, step: str) -> str:
        try:
            status, body = self._post(shutdown_url, {"database_identity": self._expected}, MUTATION_TIMEOUT_S)
        except Exception as exc:
            raise SafeStopError(f"{name} shutdown outcome is unknown; not retried") from exc
        if status in (404, 501):
            # Identity was proven by health and the graceful endpoint is absent: legacy process.
            step = f"{step}:legacy-terminate"
            self._terminate_legacy(health_url, name, kind)
        elif status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
            reason = body.get("error") if isinstance(body, dict) else None
            raise SafeStopError(f"{name} refused shutdown: {reason or status}")
        else:
            step = f"{step}:shutdown"
        self._wait_gone(health_url, name)
        return step

    def _terminate_legacy(self, health_url: str, name: str, kind: str) -> None:
        location = urlsplit(health_url)
        try:
            chain = self._legacy_resolver(kind, location.hostname or "", location.port or 0, self._root)
        except LegacyOwnerUnproven as exc:
            raise SafeStopError(
                f"{name} is a legacy process without a shutdown endpoint and its ownership "
                f"could not be proven ({exc}); nothing was terminated"
            ) from exc
        try:
            self._legacy_terminator(tuple(chain))
        except Exception as exc:
            raise SafeStopError(f"{name} legacy termination failed: {type(exc).__name__}") from exc

    def _wait_gone(self, health_url: str, name: str) -> None:
        deadline = self._monotonic() + EXIT_WAIT_S
        while self._monotonic() < deadline:
            try:
                self._get(health_url, PROBE_TIMEOUT_S)
            except Unreachable:
                return
            self._sleep(POLL_INTERVAL_S)
        raise SafeStopError(f"{name} did not exit within {int(EXIT_WAIT_S)} s")


def launch_detached(scope: str, *, notify_chat: object | None = None, root: Path = PROJECT_ROOT) -> None:
    """Run this helper as an independent, windowless process (Telegram self-shutdown handoff)."""
    if scope not in SCOPES:
        raise ValueError(f"unknown shutdown scope {scope!r}")
    argv = [sys.executable, "-m", "tools.stop_robot_runtime", scope]
    if notify_chat is not None:
        argv += ["--notify-chat", str(notify_chat)]
    subprocess.Popen(
        argv, cwd=str(root),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        ),
    )


def owner_text(result: ShutdownResult) -> str:
    if not result.ok:
        return "⛔ Остановка не выполнена: " + result.message.removeprefix("STOP BLOCKED: ")
    if result.runtime_stopped:
        return "✅ Остановлено: сканер, робот, Telegram и backend."
    return "⏹ Сканер остановлен. Робот продолжает работу — runtime оставлен."


def _notify(chat_id: str, text: str) -> None:
    try:
        import config
        import telegram_bot

        telegram_bot.send_message(config.TELEGRAM_TOKEN, chat_id, text)
    except Exception as exc:
        print(f"[STOP NOTIFY ERROR] {type(exc).__name__}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    notify_chat = None
    if "--notify-chat" in args:
        index = args.index("--notify-chat")
        if index + 1 >= len(args):
            print("usage: python -m tools.stop_robot_runtime [all|scanner] [--notify-chat CHAT_ID]")
            return 64
        notify_chat = args[index + 1]
        del args[index:index + 2]
    if len(args) > 1:
        print("usage: python -m tools.stop_robot_runtime [all|scanner] [--notify-chat CHAT_ID]")
        return 64
    result = RuntimeShutdown().run(args[0] if args else SCOPE_ALL)
    print(result.message)
    if notify_chat is not None:
        _notify(notify_chat, owner_text(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
