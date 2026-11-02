"""Isolated Editor feedback HTTP round-trip; no PAPER runtime or trading DB."""
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import signal_archive
from geometry_feedback_store import bars_digest, source_revision
from terminal.runtime.paper_http_server import PaperHttpHandler


@pytest.fixture()
def source():
    return {
        "schema_version": 1,
        "signal_id": "source:TESTUSDT:5:abc",
        "symbol": "TESTUSDT",
        "timeframe": "5",
        "bars": [
            {"open_time_ms": 1000, "open": 10, "high": 14, "low": 9, "close": 12},
            {"open_time_ms": 301000, "open": 12, "high": 15, "low": 10, "close": 11},
        ],
        "boundaries": [
            {"boundary_id": "upper", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 1000, "price": 13},
                {"bar_open_time_ms": 301000, "price": 14},
            ]},
            {"boundary_id": "lower", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 1000, "price": 9},
                {"bar_open_time_ms": 301000, "price": 11},
            ]},
        ],
    }


def test_geometry_feedback_owner_route_roundtrip_without_paper_db(monkeypatch, tmp_path, source):
    monkeypatch.setenv("BYBITSCANNER_GEOMETRY_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setattr(
        signal_archive, "load_frozen_signal_geometry",
        lambda signal_id: source if signal_id == source["signal_id"] else None,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    signal_url = url + "/api/workspace/signal-geometry?signal_id=" + source["signal_id"]
    try:
        with urlopen(signal_url, timeout=3) as reply:
            original = json.load(reply)
        assert original["ok"] is True
        assert original["snapshot"] == source
        assert original["snapshot_revision"] == source_revision(source)
        assert original["bars_sha256"] == bars_digest(source)
        assert original["latest_review"] is None

        body = {
            "schema_version": 1, "signal_id": source["signal_id"],
            "snapshot_revision": original["snapshot_revision"],
            "bars_sha256": original["bars_sha256"],
            "label": "GEOMETRY_CORRECTED",
            "idempotency_key": "review-http-test-token-1234567",
            "note": "Исправил верхний луч",
            "corrected_boundaries": [
                {"id": "upper", "type": "ray", "anchors": [
                    {"bar_open_time_ms": 1000, "price": 12.5},
                    {"bar_open_time_ms": 301000, "price": 14},
                ]},
                {"id": "lower", "type": "ray", "anchors": [
                    {"bar_open_time_ms": 1000, "price": 9},
                    {"bar_open_time_ms": 301000, "price": 11},
                ]},
            ],
        }

        def send(payload):
            req = Request(
                url + "/api/workspace/geometry-feedback",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=3) as response:
                return json.load(response)

        recorded = send(body)
        assert recorded["ok"] is True
        assert recorded["review"]["submission"]["corrected_boundaries"][0]["anchors"][0]["price"] == 12.5
        assert send(body)["review"]["review_id"] == recorded["review"]["review_id"]
        with urlopen(signal_url, timeout=3) as reply:
            reopened = json.load(reply)
        assert reopened["latest_review"]["review_id"] == recorded["review"]["review_id"]
        assert reopened["snapshot"]["boundaries"][0]["anchors"][0]["price"] == 13

        with pytest.raises(HTTPError) as error:
            send({**body, "bars_sha256": "0" * 64})
        assert error.value.code == 409
        assert len(list(tmp_path.rglob("*.json"))) == 1
    finally:
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()
