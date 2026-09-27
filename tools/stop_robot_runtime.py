"""Canonical owner-safe PAPER Robot shutdown orchestration.

Stops Scanner admission first, then delegates durable Robot stop semantics to
terminal.application.robot_control.stop_robot. Backend and Telegram processes
are intentionally left alive so protection/reconciliation authority remains
available. No LIVE mutation is authorized here.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

import requests

from terminal.application.robot_control import RobotControlRejected, stop_robot
from terminal.persistence.sqlite_store import SQLiteStore


DEFAULT_BACKEND_URL = "http://127.0.0.1:8765"


class SafeStopError(RuntimeError):
    """Raised when canonical safe-stop preconditions cannot be proven."""


def _backend_url() -> str:
    return os.environ.get("BYBITSCANNER_PAPER_BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/")


def _database_path() -> Path:
    return Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))


def _expected_database_identity(path: Path) -> str:
    store = SQLiteStore.open(path)
    try:
        return store.database_identity
    finally:
        store.close()


def _json_response(response, *, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:
        raise SafeStopError(f"{action} returned non-JSON response") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        reason = payload.get("error") if isinstance(payload, dict) else None
        raise SafeStopError(f"{action} rejected: {reason or 'unproven response'}")
    return payload


def verify_canonical_backend(*, backend_url: str, database_path: Path) -> None:
    try:
        response = requests.get(
            backend_url + "/api/health",
            timeout=10,
            allow_redirects=False,
        )
    except Exception as exc:
        raise SafeStopError("PAPER backend health is unavailable") from exc

    if response.status_code != 200:
        raise SafeStopError("PAPER backend health is unavailable")
    health = _json_response(response, action="PAPER backend health")
    expected = _expected_database_identity(database_path)
    if (
        health.get("component") != "paper_backend"
        or health.get("mode") != "paper"
        or health.get("database_identity") != expected
    ):
        raise SafeStopError("PAPER backend identity does not match the configured database")


def stop_scanner(*, backend_url: str) -> None:
    try:
        response = requests.post(
            backend_url + "/api/scanner/stop",
            json={},
            timeout=10,
            allow_redirects=False,
        )
    except Exception as exc:
        raise SafeStopError("Scanner stop request failed") from exc
    if response.status_code != 200:
        raise SafeStopError("Scanner stop request was rejected")
    _json_response(response, action="Scanner stop")


def _post_robot_json(url: str, payload: dict) -> dict:
    try:
        response = requests.post(
            url,
            json=payload,
            timeout=15,
            allow_redirects=False,
        )
    except Exception as exc:
        raise RobotControlRejected(f"Robot backend request failed: {exc}") from exc
    if response.status_code != 200:
        try:
            body = response.json()
        except Exception:
            body = {}
        raise RobotControlRejected(
            str(body.get("error") or f"Robot backend HTTP {response.status_code}")
        )
    body = response.json()
    if not isinstance(body, dict) or body.get("ok") is not True:
        raise RobotControlRejected(
            str(body.get("error") if isinstance(body, dict) else "Robot backend rejected request")
        )
    return body


def safe_stop() -> None:
    database_path = _database_path()
    backend_url = _backend_url()

    verify_canonical_backend(
        backend_url=backend_url,
        database_path=database_path,
    )
    stop_scanner(backend_url=backend_url)
    stop_robot(
        http_post=_post_robot_json,
        database_path=database_path,
        backend_url=backend_url,
    )


def main() -> int:
    try:
        safe_stop()
    except (SafeStopError, RobotControlRejected) as exc:
        print(f"SAFE STOP BLOCKED: {exc}")
        return 1
    print("Scanner STOPPED; Robot STOPPED. Backend/Telegram left running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
