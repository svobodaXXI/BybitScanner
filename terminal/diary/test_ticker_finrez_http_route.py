"""Read-only HTTP contract for the first Finrez screen."""
from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from terminal.runtime import paper_http_server
from terminal.runtime.paper_http_server import PaperHttpHandler


def _get(url: str) -> tuple[int, dict]:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_finrez_route_reuses_attributed_paper_diary_source(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "paper.sqlite3"
    calls = []
    snapshot = object()

    def read_source(path):
        calls.append(("source", path))
        return snapshot

    def project(source, *, account_id, owner, period, now_ms):
        calls.append(("project", source, account_id, owner, period))
        assert isinstance(now_ms, int) and now_ms > 0
        return {
            "account_id": "paper", "owner": owner, "period": period,
            "source_revision": 9, "period_start_ms": 0, "as_of_ms": now_ms,
            "source": "PAPER_EXECUTIONS_ATTRIBUTED",
            "pnl_basis": "REALIZED_PRICE_MINUS_EXECUTION_FEES",
            "tickers": [{"symbol": "BTCUSDT", "pnl_usdt": "2.5", "trade_count": 2}],
        }

    monkeypatch.setattr(paper_http_server, "load_paper_source_snapshot", read_source)
    monkeypatch.setattr(paper_http_server, "project_paper_ticker_pnl", project)
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.diary_source_db_path = source_path
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        root = f"http://{host}:{port}/api/diary/ticker-finrez"
        for period in ("TODAY", "ALL"):
            status, payload = _get(root + f"?account_id=paper&owner=ROBOT&period={period}")
            assert status == 200
            assert payload["ok"] is True
            assert payload["owner"] == "ROBOT"
            assert payload["period"] == period
            assert payload["tickers"][0]["pnl_usdt"] == "2.5"

        assert calls[0] == ("source", source_path)
        assert calls[1] == ("project", snapshot, "paper", "ROBOT", "TODAY")
        for query in (
            "", "?account_id=paper&owner=ROBOT",
            "?account_id=paper&owner=ROBOT&period=WEEK",
            "?account_id=paper&owner=ROBOT&period=ALL&owner=MANUAL",
            "?account_id=paper&owner=ROBOT&period=ALL&extra=1",
        ):
            status, payload = _get(root + query)
            assert (status, payload["error"]) == (400, "finrez_scope_required")
        status, payload = _get(root + "?account_id=bybit-main&owner=ROBOT&period=TODAY")
        assert (status, payload["error"]) == (404, "finrez_scope_unavailable")
        assert len(calls) == 4  # invalid/cross-account requests never read the ledger
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_finrez_route_does_not_fabricate_zero_when_paper_source_is_missing(tmp_path: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.diary_source_db_path = tmp_path / "missing.sqlite3"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        status, payload = _get(
            f"http://{host}:{port}/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=TODAY"
        )
        assert (status, payload["error"]) == (503, "finrez_evidence_unavailable")
        assert not server.diary_source_db_path.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
