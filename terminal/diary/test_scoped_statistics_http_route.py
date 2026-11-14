from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from terminal.diary.scoped_statistics_archive import ScopedStatisticsArchive
from terminal.runtime.paper_http_server import PaperHttpHandler


def _get(url: str) -> tuple[int, dict]:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_scoped_statistics_http_requires_explicit_authorized_paper_scope(tmp_path: Path, monkeypatch):
    archive_path = tmp_path / "scoped_diary_statistics.sqlite3"
    archive = ScopedStatisticsArchive(archive_path)
    try:
        for owner in ("MANUAL", "ROBOT"):
            archive.publish(
                account_id="paper", owner=owner, source_revision=1,
                episodes=(), origin_evidence={}, factor_store_path=tmp_path / "not-created.sqlite3",
            )
    finally:
        archive.close()
    monkeypatch.setenv("BYBITSCANNER_DIARY_ARCHIVE_DB", str(archive_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        root = f"http://{host}:{port}/api/diary/scoped-statistics"
        for owner in ("MANUAL", "ROBOT"):
            status, result = _get(root + "?account_id=paper&owner=" + owner)
            assert status == 200
            assert result["ok"] is True
            assert result["account_id"] == "paper"
            assert result["owner"] == owner
            assert result["source_revision"] == 1
        for query in ("", "?account_id=paper", "?account_id=paper&owner=ROBOT&owner=MANUAL"):
            status, result = _get(root + query)
            assert (status, result["error"]) == (400, "statistics_scope_required")
        for query in ("?account_id=bybit-main&owner=MANUAL",
                      "?account_id=paper&owner=OTHER"):
            status, result = _get(root + query)
            assert (status, result["error"]) == (404, "statistics_scope_unavailable")
        assert not (tmp_path / "not-created.sqlite3").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_scoped_statistics_http_never_falls_back_to_global_or_invents_empty_report(
    tmp_path: Path, monkeypatch,
):
    path = tmp_path / "missing" / "scoped_diary_statistics.sqlite3"
    monkeypatch.setenv("BYBITSCANNER_DIARY_ARCHIVE_DB", str(path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        status, result = _get(
            f"http://{host}:{port}/api/diary/scoped-statistics?account_id=paper&owner=ROBOT"
        )
        assert (status, result["error"]) == (503, "statistics_archive_unavailable")
        assert not path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
