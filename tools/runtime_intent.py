"""Desktop bootstrap for one-action owner runtime intents (RUNTIME_INTENT_RECONCILER_PLAN.md §5.1).

Proves or prepares the canonical PAPER backend and Telegram worker for the
expected PAPER DB, then sends exactly one POST /api/runtime/intent. Robot and
Scanner transitions and their capability gates belong to that backend route;
this module only owns process bootstrap and dependency identity.

Usage: python -m tools.runtime_intent [ALL|SCANNER|ROBOT]
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable, Mapping
import urllib.error
import urllib.request

INTENTS = ("ALL", "SCANNER", "ROBOT")
DEFAULT_BACKEND_URL = "http://127.0.0.1:8765"
DEFAULT_TELEGRAM_PORT = "8766"
READY_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.5
PROBE_TIMEOUT_S = 2.0
INTENT_TIMEOUT_S = 180.0

EXIT_OK = 0
EXIT_BOOTSTRAP_FAILED = 1
EXIT_BLOCKED = 2
EXIT_INTENT_ERROR = 3
EXIT_USAGE = 64

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ABSENT = "absent"
STARTING = "starting"
READY = "ready"


class Unreachable(Exception):
    """No HTTP response at all: nothing is serving the endpoint (yet)."""


class Mismatch(Exception):
    """Something answered, but it is not the expected canonical dependency."""


class HttpResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def http_get(url: str, timeout: float) -> HttpResponse:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return HttpResponse(response.status, response.read())
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, error.read())
    except OSError as error:
        raise Unreachable(str(error)) from error


def http_post_json(url: str, payload: Mapping[str, object], timeout: float) -> HttpResponse:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(response.status, response.read())
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, error.read())


def spawn_console(argv: list[str], cwd: Path) -> None:
    """Start a dependency in its own visible console that stays open after exit."""
    subprocess.Popen(
        ["cmd.exe", "/k", *argv], cwd=str(cwd),
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


def backend_argv(root: Path) -> list[str]:
    return [str(root / "start_paper_backend.bat")]


def telegram_argv(root: Path, python: str) -> list[str]:
    return [python, str(root / "telegram_monitoring.py")]


def expected_database_identity(root: Path, env: Mapping[str, str]) -> str:
    """SQLiteStore.database_identity for the launcher's DB path, without opening SQLite."""
    path = Path(env.get("BYBITSCANNER_PAPER_DB") or "paper_runtime.sqlite3")
    if not path.is_absolute():
        path = root / path
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def _json_or_none(response: HttpResponse):
    try:
        return response.json()
    except (ValueError, UnicodeDecodeError):
        return None


class RuntimeIntentBootstrap:
    def __init__(
        self,
        *,
        root: Path = PROJECT_ROOT,
        env: Mapping[str, str] | None = None,
        get: Callable[[str, float], HttpResponse] = http_get,
        post: Callable[[str, Mapping[str, object], float], HttpResponse] = http_post_json,
        spawn: Callable[[str, list[str], Path], None] | None = None,
        python: str = sys.executable,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        out: Callable[[str], None] = lambda line: print(line, flush=True),
    ) -> None:
        self._root = root
        self._env = dict(os.environ if env is None else env)
        self._get = get
        self._post = post
        self._spawn = spawn or (lambda _name, argv, cwd: spawn_console(argv, cwd))
        self._python = python
        self._sleep = sleep
        self._monotonic = monotonic
        self._out = out
        self._expected = expected_database_identity(root, self._env)
        self._backend = (
            self._env.get("BYBITSCANNER_PAPER_BACKEND_URL") or DEFAULT_BACKEND_URL
        ).rstrip("/")
        port = self._env.get("BYBITSCANNER_TELEGRAM_MONITORING_PORT") or DEFAULT_TELEGRAM_PORT
        self._telegram_health = f"http://127.0.0.1:{port}/health"

    def run(self, intent: str) -> int:
        if intent not in INTENTS:
            self._out(f"ERROR: unknown intent {intent!r}; expected one of {', '.join(INTENTS)}")
            return EXIT_USAGE
        try:
            self._ensure("PAPER backend", self._probe_backend, backend_argv(self._root))
            self._ensure(
                "Telegram monitoring", self._probe_telegram,
                telegram_argv(self._root, self._python),
            )
        except (Mismatch, TimeoutError, OSError) as error:
            self._out(f"FAILED: {error}. Runtime intent {intent} was not sent.")
            return EXIT_BOOTSTRAP_FAILED
        return self._send_intent(intent)

    def _ensure(self, name: str, probe: Callable[[], str], argv: list[str]) -> None:
        state = probe()
        if state == READY:
            return
        if state == ABSENT:
            self._out(f"Starting {name}...")
            self._spawn(name, argv, self._root)
        deadline = self._monotonic() + READY_TIMEOUT_S
        while self._monotonic() < deadline:
            self._sleep(POLL_INTERVAL_S)
            if probe() == READY:
                return
        raise TimeoutError(f"{name} did not prove READY within {int(READY_TIMEOUT_S)} s")

    def _probe_backend(self) -> str:
        try:
            response = self._get(self._backend + "/api/health", PROBE_TIMEOUT_S)
        except Unreachable:
            return ABSENT
        health = _json_or_none(response)
        if (
            response.status == 200
            and isinstance(health, dict)
            and health.get("ok") is True
            and health.get("component") == "paper_backend"
            and health.get("mode") == "paper"
            and health.get("database_identity") == self._expected
        ):
            return READY
        raise Mismatch(
            f"{self._backend} answered without proving the canonical PAPER backend "
            "for the expected PAPER DB"
        )

    def _probe_telegram(self) -> str:
        try:
            response = self._get(self._telegram_health, PROBE_TIMEOUT_S)
        except Unreachable:
            return ABSENT
        health = _json_or_none(response)
        if not isinstance(health, dict) or health.get("component") != "telegram_monitoring":
            raise Mismatch(f"{self._telegram_health} is not the Telegram monitoring worker")
        identity = health.get("database_identity")
        if health.get("status") == "ready" and response.status == 200:
            if identity == self._expected:
                return READY
            raise Mismatch("Telegram monitoring is READY for a different or unproven PAPER DB")
        if health.get("status") == "not_ready":
            if identity is not None and identity != self._expected:
                raise Mismatch("Telegram monitoring is starting for a different PAPER DB")
            return STARTING
        raise Mismatch(f"{self._telegram_health} answered with an unknown worker status")

    def _send_intent(self, intent: str) -> int:
        url = self._backend + "/api/runtime/intent"
        try:
            response = self._post(url, {"intent": intent}, INTENT_TIMEOUT_S)
        except Exception as error:
            self._out(
                f"ERROR: intent={intent} outcome unknown ({type(error).__name__}); "
                "not retried. Check the PAPER backend window."
            )
            return EXIT_INTENT_ERROR
        result = _json_or_none(response)
        if not (
            isinstance(result, dict)
            and result.get("intent") == intent
            and isinstance(result.get("ok"), bool)
            and isinstance(result.get("changed"), list)
            and isinstance(result.get("final"), dict)
            and isinstance(result.get("blocked_by"), list)
        ):
            self._out(f"ERROR: intent={intent} HTTP {response.status} without a runtime intent result")
            return EXIT_INTENT_ERROR
        final = " ".join(f"{key}={value}" for key, value in result["final"].items())
        changed = ",".join(result["changed"]) or "none"
        if response.status == 200 and result["ok"] is True and not result["blocked_by"]:
            self._out(f"READY: intent={intent} changed={changed} {final}".rstrip())
            return EXIT_OK
        if response.status == 409 and result["ok"] is False and result["blocked_by"]:
            self._out(
                f"BLOCKED: intent={intent} blocked_by={','.join(result['blocked_by'])} "
                f"changed={changed} {final}".rstrip()
            )
            return EXIT_BLOCKED
        self._out(f"ERROR: intent={intent} HTTP {response.status} with an inconsistent result")
        return EXIT_INTENT_ERROR


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: python -m tools.runtime_intent [ALL|SCANNER|ROBOT]", flush=True)
        return EXIT_USAGE
    return RuntimeIntentBootstrap().run(args[0] if args else "ALL")


if __name__ == "__main__":
    sys.exit(main())
