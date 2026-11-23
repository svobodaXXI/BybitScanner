"""Focused protected device → exact closed PAPER facts → D2/geometry regression.

Only an ephemeral loopback HTTPServer, no trading runtime, DB or external network.
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import terminal.runtime.paper_http_server as backend
from terminal.diary.simulator_launch_relay import RelayForbidden


EPISODE = "te_" + "a" * 24
REQUEST_ID = "b" * 32
DEVICE = "owner-laptop"
TOKEN = "test-only-paired-device-token"
URL = f"/api/diary/simulator-bridge/facts?device_id={DEVICE}&request_id={REQUEST_ID}"


class _AuthorizedRequest:
    def authorized_facts_scope(self, *, device, token, request_id):
        if device != DEVICE or token != TOKEN:
            raise RelayForbidden("unauthorized")
        assert request_id == REQUEST_ID
        return EPISODE, "ROBOT", 17


def _get(server, token=TOKEN):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{URL}",
        headers={"X-BybitScanner-Simulator-Device-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


@pytest.fixture
def device_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), backend.PaperHttpHandler)
    server.simulator_launch_relay = _AuthorizedRequest()
    server.diary_source_db_path = "/fixture/immutable-paper.sqlite"
    server.diary_setup_store_path = "/fixture/immutable-d2.sqlite"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


@pytest.mark.parametrize("linked", [True, False])
def test_paired_facts_carry_exact_d2_and_only_proven_archived_geometry(
    monkeypatch, device_server, linked,
):
    source = object()
    calls = []
    proof = {
        "status": "EXACT_D2_LINK" if linked else "NO_EXACT_EPISODE_LINK",
        "geometry_status": "NOT_EXPORTED",
        "source": "TRADING_DIARY_D2",
        "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
    }
    geometry = {
        "signal_id": "candidate-original", "sha256": "a" * 64,
        "boundaries": [{"boundary_id": "lower", "kind": "ray"}],
    }

    def source_reader(path):
        calls.append(("source", path))
        return source

    def project(snapshot, **kwargs):
        assert snapshot is source
        assert kwargs == {
            "account_id": "paper", "owner": "ROBOT",
            "trade_episode_id": EPISODE, "source_revision": 17,
            "now_ms": kwargs["now_ms"],
        }
        return {
            "trade_episode_id": EPISODE, "symbol": "BTCUSDT",
            "side": "SHORT", "opened_at_ms": 1_800_000_000_000,
            "execution_allocations": [{"controller": "ROBOT"}],
        }

    def d2_read(path, **kwargs):
        calls.append(("d2", path, kwargs))
        assert kwargs == {
            "trade_episode_id": EPISODE, "account_id": "paper",
            "symbol": "BTCUSDT", "side": "SHORT", "opening_controller": "ROBOT",
        }
        return proof

    def attach(context, **kwargs):
        calls.append(("geometry", context, kwargs))
        assert context is proof
        assert kwargs == {"symbol": "BTCUSDT", "opened_at_ms": 1_800_000_000_000}
        return {**context, "geometry_status": "ORIGINAL_ARCHIVE_HASH_VERIFIED",
                "original_geometry": geometry} if linked else context

    monkeypatch.setattr(backend, "load_paper_source_snapshot", source_reader)
    monkeypatch.setattr(backend, "project_paper_closed_episode_facts", project)
    monkeypatch.setattr(backend, "project_episode_d2_context_read_only", d2_read)
    monkeypatch.setattr(backend, "attach_verified_original_geometry", attach)

    code, body = _get(device_server)
    assert code == 200
    assert body["ok"] is True
    assert body["trade_episode_id"] == EPISODE
    assert body["setup_context"]["status"] == proof["status"]
    assert body["setup_context"]["geometry_status"] == (
        "ORIGINAL_ARCHIVE_HASH_VERIFIED" if linked else "NOT_EXPORTED"
    )
    if linked:
        assert body["setup_context"]["original_geometry"] == geometry
    else:
        assert "original_geometry" not in body["setup_context"]
    assert [x[0] for x in calls] == ["source", "d2", "geometry"]


def test_unpaired_device_cannot_read_episode_or_d2(monkeypatch, device_server):
    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized request accessed protected PAPER or D2")

    monkeypatch.setattr(backend, "load_paper_source_snapshot", forbidden)
    monkeypatch.setattr(backend, "project_episode_d2_context_read_only", forbidden)
    code, body = _get(device_server, "invalid")
    assert code == 403
    assert body["error"] == "simulator_device_unauthorized"
