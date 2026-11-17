"""Scoped trade facts delivery through the existing paired-device bridge only."""
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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


def test_episode_bridge_exact_device_and_revision(tmp_path: Path, monkeypatch):
    episode = "te_" + "a" * 24
    origin = "https://statistics.example.test"
    token = "a" * 64
    other = "b" * 64
    relay = SimulatorLaunchRelay(
        origin=origin, devices={"owner-laptop": token, "owner-pc": other})
    source = tmp_path / "must-not-be-created.sqlite3"
    calls = []
    snapshot = object()

    def load(path):
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
            "trade_episode_id": episode,
            "replay_evidence": "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
            "execution_allocations": [{"execution_id": "exec-real", "occurred_at_ms": 1234567890}],
        }

    monkeypatch.setattr(paper_http_server, "load_paper_source_snapshot", load)
    monkeypatch.setattr(paper_http_server, "project_paper_closed_episode_facts", project)
    server = ThreadingHTTPServer(("127.0.0.1", 0), paper_http_server.PaperHttpHandler)
    server.simulator_launch_relay = relay
    server.diary_source_db_path = source
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
        assert len(calls) == 2
        assert _call(base, bridge + "ack", token=token, body={
            "device_id": "owner-laptop", "request_id": rid, "launched": True,
        })[1]["state"] == "LAUNCHED"
        assert _call(base, bridge + facts, token=token)[0] == 404
        assert len(calls) == 2
        assert not source.exists()

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
        assert len(calls) == 2
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
