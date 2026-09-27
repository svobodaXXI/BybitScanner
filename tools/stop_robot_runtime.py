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

from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Callable, Mapping

import requests

from terminal.application.robot_control import RobotControlRejected, stop_robot
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
    ) -> None:
        env = dict(os.environ if env is None else env)
        database_path = _database_path(root, env)
        self._expected = expected_database_identity(root, env)
        self._backend = (env.get("BYBITSCANNER_PAPER_BACKEND_URL") or DEFAULT_BACKEND_URL).rstrip("/")
        port = env.get("BYBITSCANNER_TELEGRAM_MONITORING_PORT") or DEFAULT_TELEGRAM_PORT
        self._telegram = f"http://127.0.0.1:{port}"
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
            raise SafeStopError("Robot protection coverage is still active; runtime kept alive")

        if telegram == PRESENT:
            self._shutdown(self._telegram + "/shutdown", self._telegram + "/health", "Telegram monitoring")
            steps.append("telegram:shutdown")
        if backend == PRESENT:
            self._shutdown(
                self._backend + "/api/runtime/shutdown", self._backend + "/api/health", "PAPER backend",
            )
            steps.append("backend:shutdown")
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

    def _protection_quiescent(self) -> bool:
        try:
            status, health = self._get(self._backend + "/api/robot/protection-health", PROBE_TIMEOUT_S)
        except Unreachable as exc:
            raise SafeStopError("Robot protection health is unavailable") from exc
        return (
            status == 200 and isinstance(health, dict) and health.get("healthy") is True
            and health.get("covered_symbols") == [] and health.get("unhealthy_symbols") == {}
        )

    def _shutdown(self, shutdown_url: str, health_url: str, name: str) -> None:
        try:
            status, body = self._post(shutdown_url, {"database_identity": self._expected}, MUTATION_TIMEOUT_S)
        except Exception as exc:
            raise SafeStopError(f"{name} shutdown outcome is unknown; not retried") from exc
        if status in (404, 501):
            raise SafeStopError(
                f"{name} is a legacy process without a shutdown endpoint; close its window once"
            )
        if status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
            reason = body.get("error") if isinstance(body, dict) else None
            raise SafeStopError(f"{name} refused shutdown: {reason or status}")
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
