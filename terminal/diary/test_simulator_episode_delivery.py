"""Scoped trade facts delivery through the existing paired-device bridge only."""
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terminal.diary.simulator_launch_relay import SimulatorLaunchRelay, RelayInvalid
from terminal.runtime import paper_http_server


def _call(base: str, path: str, *, body=None, token="", origin=""):
    headers = {}
    if token:
        headers["X-BybitScanner-Simulator-Device-Token"] = token
    if origin:
        headers.update({"Origin": origin, "Sec-Fetch-Site": "same-origin"})
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


@pytest.mark.parametrize("linked", [True, False])
def test_episode_bridge_exact_device_and_revision(tmp_path: Path, monkeypatch, linked):
    episode = "te_" + "a" * 24
    origin = "https://statistics.example.test"
    token = "a" * 64
    other = "b" * 64
    relay = SimulatorLaunchRelay(
        origin=origin, devices={"owner-laptop": token, "owner-pc": other})
    source = tmp_path / "must-not-be-created.sqlite3"
    calls = []
    snapshot = object()

    def load(path, *, include_wedge_evidence=False):
        assert include_wedge_evidence is True
        calls.append(("read", path))
        return snapshot

    def project(actual, **kwargs):
        calls.append(("project", kwargs))
        assert actual is snapshot
        assert kwargs["account_id"] == "paper"
        assert kwargs["owner"] == "ROBOT"
        assert kwargs["trade_episode_id"] == episode
        assert kwargs["source_revision"] == 9
        return {
            "schema": "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
            "namespace": "PAPER_READ_ONLY",
            "source": "PAPER_EXECUTIONS_ATTRIBUTED",
            "source_revision": 9, "account_id": "paper", "owner": "ROBOT",
            "trade_episode_id": episode, "symbol": "BTCUSDT", "side": "SHORT",
            "opened_at_ms": 1234567890,
            "replay_evidence": "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
            "execution_allocations": [{
                "execution_id": "exec-real", "occurred_at_ms": 1234567890,
                "controller": "ROBOT",
            }],
        }

    def read_d2(path, **scope):
        calls.append(("d2", scope))
        assert path == tmp_path / "missing-d2.sqlite3"
        assert scope == {
            "trade_episode_id": episode, "account_id": "paper",
            "symbol": "BTCUSDT", "side": "SHORT", "opening_controller": "ROBOT",
        }
        return {"status": "EXACT_D2_LINK" if linked else "NO_EXACT_EPISODE_LINK",
                "geometry_status": "NOT_EXPORTED"}

    def attach_geometry(context, **scope):
        calls.append(("geometry", scope))
        assert scope == {"symbol": "BTCUSDT", "opened_at_ms": 1234567890}
        if not linked:
            return context
        return {
            **context, "geometry_status": "ORIGINAL_ARCHIVE_HASH_VERIFIED",
            "original_geometry": {
                "signal_id": "archived-exact-candidate", "sha256": "a" * 64,
                "snapshot": {"boundaries": [{"boundary_id": "original-lower"}]},
            },
        }

    monkeypatch.setattr(paper_http_server, "load_paper_source_snapshot", load)
    monkeypatch.setattr(paper_http_server, "project_paper_closed_episode_facts", project)
    monkeypatch.setattr(paper_http_server, "project_episode_d2_context_read_only", read_d2)
    monkeypatch.setattr(paper_http_server, "attach_verified_original_geometry", attach_geometry)
    server = ThreadingHTTPServer(("127.0.0.1", 0), paper_http_server.PaperHttpHandler)
    server.simulator_launch_relay = relay
    server.diary_source_db_path = source
    server.diary_setup_store_path = tmp_path / "missing-d2.sqlite3"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    bridge = "/api/diary/simulator-bridge/"
    try:
        # Authentication and exact request fields are checked before PAPER reads.
        assert _call(base, bridge + "poll?device_id=owner-laptop&viewer_running=1", token=token)[0] == 200
        assert _call(base, bridge + "poll?device_id=owner-pc&viewer_running=0", token=other)[0] == 200
        code, queued = _call(base, bridge + "request", origin=origin, body={
            "episode_id": episode, "owner": "ROBOT", "source_revision": 9,
        })
        assert code == 200 and queued["state"] == "QUEUED"
        rid = queued["request_id"]
        # Device cannot export a job that was never delivered to it.
        facts = f"facts?device_id=owner-laptop&request_id={rid}"
        assert _call(base, bridge + facts, token=token)[0] == 404
        assert _call(base, bridge + facts)[0] == 403
        assert _call(base, bridge + facts, token=other)[0] == 403
        assert _call(base, bridge + "facts?device_id=owner-laptop&request_id=invalid",
                     token=token)[0] == 404
        code, delivered = _call(
            base, bridge + "poll?device_id=owner-laptop&viewer_running=0", token=token)
        assert code == 200
        assert delivered == {
            "ok": True, "state": "OPEN_EPISODE", "request_id": rid,
            "episode_id": episode, "owner": "ROBOT", "source_revision": 9,
        }
        code, payload = _call(base, bridge + facts, token=token)
        assert code == 200
        assert payload["execution_allocations"][0]["execution_id"] == "exec-real"
        assert payload["setup_context"]["status"] == (
            "EXACT_D2_LINK" if linked else "NO_EXACT_EPISODE_LINK")
        assert payload["setup_context"]["geometry_status"] == (
            "ORIGINAL_ARCHIVE_HASH_VERIFIED" if linked else "NOT_EXPORTED")
        if linked:
            assert payload["setup_context"]["original_geometry"]["signal_id"] == (
                "archived-exact-candidate")
        else:
            assert "original_geometry" not in payload["setup_context"]
        assert [kind for kind, *_ in calls] == ["read", "project", "d2", "geometry"]
        assert _call(base, bridge + "ack", token=token, body={
            "device_id": "owner-laptop", "request_id": rid, "launched": True,
        })[1]["state"] == "LAUNCHED"
        assert _call(base, bridge + facts, token=token)[0] == 404
        assert len(calls) == 4
        assert not source.exists()
        assert not server.diary_setup_store_path.exists()

        # Legacy ID-only locator is allowed to open but never retrieve facts.
        code, old = _call(base, bridge + "request", origin=origin,
                          body={"episode_id": episode})
        assert code == 200
        code, job = _call(base, bridge + "poll?device_id=owner-laptop&viewer_running=0",
                          token=token)
        assert code == 200 and job["request_id"] == old["request_id"]
        assert "owner" not in job and "source_revision" not in job
        assert _call(base, bridge + f"facts?device_id=owner-laptop&request_id={old['request_id']}",
                     token=token)[0] == 404
        assert len(calls) == 4
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_episode_bridge_malformed_scope_fails_closed():
    relay = SimulatorLaunchRelay(
        origin="https://statistics.example.test", devices={"owner-laptop": "x" * 64})
    for owner, revision in [
        ("ROBOT", None), (None, 3), ("ROBOT", 0),
        ("MAIN", 9), ("ROBOT", True), ("ROBOT", "9"),
    ]:
        try:
            relay.enqueue("te_" + "b" * 24, request_origin=relay.origin,
                          fetch_site="same-origin", owner=owner, source_revision=revision)
        except RelayInvalid:
            pass
        else:
            raise AssertionError("Malformed scope was accepted")


def test_exact_candidate_archive_preserves_d2_absence_and_rejects_conflicts(monkeypatch):
    from types import SimpleNamespace
    from terminal.diary import episode_context, wedge_lineage
    import signal_archive
    import signal_geometry_snapshot

    episode = "te_" + "a" * 24
    trade = {"trading_account_id": "paper", "candidate_id": "candidate-42",
             "symbol": "BTCUSDT", "direction": "SHORT", "pattern": "Rising Wedge",
             "source_timeframe": "5m", "signal_time_ms": 100}
    snapshot = SimpleNamespace(source_revision=9, wedge_evidence={"trades": [trade]})
    projection = {"account_id": "paper", "owner": "ROBOT", "cohort": "ROBOT",
                  "source_revision": 9, "trade_episode_id": episode, "symbol": "BTCUSDT",
                  "side": "SHORT", "opened_at_ms": 300, "execution_allocations": [{}, {}]}
    proof = {"status": "PROVEN", "trade_episode_id": episode, "source_revision": 9,
             "candidate_id": "candidate-42", "pattern": "Rising Wedge",
             "source_timeframe": "5m",
             "evidence_scope": "EXACT_WEDGE_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
             "provenance": "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY"}
    def attach(actual, report):
        assert actual is snapshot
        assert report["closed_episodes"][0]["execution_count"] == 2
        return {**report, "closed_episodes": [{**report["closed_episodes"][0],
                                                "verified_signal": proof}]}
    monkeypatch.setattr(wedge_lineage, "attach_verified_wedge_signals", attach)
    meta = {"candidate_id": "candidate-42", "symbol": "BTCUSDT", "timeframe": "5m",
            "pattern": "Rising Wedge", "sent_at_ms": 200, "geometry_sha256": "a" * 64}
    frozen = {"bars": [{"open_time_ms": 90}], "boundaries": [{"boundary_id": "original"}]}
    monkeypatch.setattr(signal_archive, "load_original_signal", lambda ids: meta if ids == ["candidate-42"] else None)
    monkeypatch.setattr(signal_archive, "load_frozen_signal_geometry", lambda candidate: frozen)
    monkeypatch.setattr(signal_geometry_snapshot, "validate_snapshot", lambda *args, **kwargs: (frozen, "a" * 64))
    d2 = {"status": "D2_STORE_ABSENT", "geometry_status": "NOT_EXPORTED"}
    project = episode_context.project_exact_candidate_archive_geometry
    result = project(snapshot, projection, d2)
    assert result["geometry"]["snapshot"] is frozen
    assert result["geometry"]["linkage_basis"] == "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE"
    assert d2 == {"status": "D2_STORE_ABSENT", "geometry_status": "NOT_EXPORTED"}
    assert project(snapshot, projection, {"status": "CONFLICTING_D2_LINK"}) is None
    assert project(snapshot, {**projection, "source_revision": 8}, d2) is None
    assert project(snapshot, {**projection, "cohort": "JOINT_MANAGEMENT"}, d2) is None
    for key, invalid in [("pattern", "Falling Wedge"), ("timeframe", "1m"),
                         ("sent_at_ms", 99), ("sent_at_ms", 301), ("geometry_sha256", "b" * 64)]:
        prior = meta[key]
        meta[key] = invalid
        assert project(snapshot, projection, d2) is None
        meta[key] = prior
    snapshot.wedge_evidence["trades"].append(trade)
    assert project(snapshot, projection, d2) is None
