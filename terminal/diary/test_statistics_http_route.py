from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from terminal.runtime import paper_http_server
from terminal.runtime.paper_http_server import PaperHttpHandler


class _SerializedRuntimeStub:
    def __init__(self) -> None:
        self.state = SimpleNamespace(store=object())

    def call(self, operation, timeout: float = 15.0):
        return operation(self.state)


def test_diary_statistics_get_route_projects_active_account_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    factor_store_path = tmp_path / "paper_runtime.trading_diary.sqlite3"
    runtime = _SerializedRuntimeStub()
    runtime.state.account_catalog = lambda: {
        "active_account_id": "paper",
        "session_generation": 7,
        "accounts": [
            {
                "id": "paper",
                "display_name": "Paper / Virtual",
                "provider": "PAPER",
                "environment": "PAPER",
                "status": "READY",
            }
        ],
    }
    expected = {
        "active_account_id": "paper",
        "session_generation": 7,
        "environment": "PAPER",
        "statistics": {
            "sample": {
                "total": 0,
                "eligible_closed_ready": 0,
                "excluded_open": 0,
                "excluded_incomplete": 0,
            },
        },
    }
    calls: list[tuple[object, dict[str, object], Path]] = []

    def fake_project(store, *, account_catalog, factor_store_path):
        calls.append((store, account_catalog, Path(factor_store_path)))
        return expected

    monkeypatch.setattr(
        paper_http_server,
        "project_active_account_statistics",
        fake_project,
        raising=False,
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = runtime
    server.diary_factor_store_path = factor_store_path
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urlopen(f"http://{host}:{port}/api/diary/statistics", timeout=2) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))

        assert payload == {"ok": True, **expected}
        assert len(calls) == 1
        store, catalog, observed_path = calls[0]
        assert store is runtime.state.store
        assert catalog["active_account_id"] == "paper"
        assert observed_path == factor_store_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_diary_statistics_route_fails_closed_when_projection_breaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    runtime = _SerializedRuntimeStub()
    runtime.state.account_catalog = lambda: {
        "active_account_id": "paper",
        "session_generation": 1,
        "accounts": [{
            "id": "paper",
            "display_name": "Paper / Virtual",
            "provider": "PAPER",
            "environment": "PAPER",
            "status": "READY",
        }],
    }

    def fail_projection(*args, **kwargs):
        raise RuntimeError("broken read model")

    monkeypatch.setattr(
        paper_http_server,
        "project_active_account_statistics",
        fail_projection,
        raising=False,
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = runtime
    server.diary_factor_store_path = tmp_path / "missing.trading_diary.sqlite3"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with pytest.raises(HTTPError) as captured:
            urlopen(f"http://{host}:{port}/api/diary/statistics", timeout=2)
        assert captured.value.code == 503
        payload = json.loads(captured.value.read().decode("utf-8"))
        assert payload == {"ok": False, "error": "diary_statistics_unavailable"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
