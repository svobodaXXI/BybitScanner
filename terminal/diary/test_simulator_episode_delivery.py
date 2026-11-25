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


@pytest.fixture
def connect_proxy():
    """An actual loopback CONNECT tunnel, restricted to the test TLS server."""
    import select
    import socket
    import socketserver

    seen = []
    allowed = []

    class Tunnel(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            line = self.rfile.readline(1024).decode("ascii").strip()
            headers = []
            while True:
                header = self.rfile.readline(1024)
                if header in (b"\r\n", b"\n", b""):
                    break
                headers.append(header.lower())
            method, target, version = line.split()
            assert method == "CONNECT" and target == allowed[0]
            assert not any(b"x-bybitscanner-simulator-device-token" in h for h in headers)
            seen.append(target)
            host, port = target.rsplit(":", 1)
            with socket.create_connection((host, int(port)), timeout=5) as upstream:
                self.connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                while True:
                    readable, _, _ = select.select([self.connection, upstream], [], [], 5)
                    if not readable:
                        return
                    for src in readable:
                        data = src.recv(65536)
                        if not data:
                            return
                        dst = upstream if src is self.connection else self.connection
                        dst.sendall(data)

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Tunnel) as proxy:
        proxy.daemon_threads = True
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{proxy.server_address[1]}", allowed, seen
        finally:
            proxy.shutdown()
            thread.join(timeout=3)


@pytest.mark.parametrize("linked,tls_pairing", [(True, False), (False, False), (True, "direct"), (True, "proxy")])
def test_episode_bridge_exact_device_and_revision(tmp_path: Path, monkeypatch, linked, tls_pairing, connect_proxy):
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
    if tls_pairing:
        import ssl
        import subprocess
        cert, key = tmp_path / "test-cert.pem", tmp_path / "test-key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
        ], check=True, capture_output=True, timeout=15)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        origin = f"https://127.0.0.1:{server.server_address[1]}"
        relay.origin = origin
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = origin if tls_pairing else f"http://127.0.0.1:{server.server_address[1]}"
    bridge = "/api/diary/simulator-bridge/"
    try:
        if tls_pairing:
            # Actual HTTPS client/backend, one-time code, device poll, local
            # same-origin claim, immutable store and ACK. Only financial data
            # projection (above) and Windows process registration/open are test doubles.
            import ssl
            from urllib.error import URLError
            from research.local_replay_viewer import launch_bridge_agent as agent
            from research.local_replay_viewer.paper_episode_local_store import load_episode
            from research.local_replay_viewer.server import handler_factory

            app = tmp_path / "MachineTime"
            app.mkdir()
            (app / "trusted-statistics-origin.txt").write_text(origin + "\n", encoding="ascii")
            monkeypatch.setattr(agent, "HERE", app)
            monkeypatch.setattr(agent, "CONFIG_PATH", app / "simulator-v2-data" / "launch-bridge.json")
            proxy_url, allowed, seen = connect_proxy
            allowed.append(origin.removeprefix("https://"))
            # Exercise both the direct path and the same configured HTTPS proxy
            # mechanism used by the Windows owner's networking environment.
            for name in ("HTTPS_PROXY", "https_proxy"):
                monkeypatch.setenv(name, proxy_url)
            for name in ("NO_PROXY", "no_proxy"):
                monkeypatch.setenv(name, "" if tls_pairing == "proxy" else "*")
            # Reject an untrusted test certificate on the selected transport.
            with pytest.raises(URLError) as untrusted:
                agent._relay_https_opener().open(base + bridge + "poll?device_id=owner-pc&viewer_running=0", timeout=3)
            assert isinstance(untrusted.value.reason, ssl.SSLCertVerificationError)
            assert agent.read_config() is None
            # Trust only the ephemeral loopback test certificate; no disabled TLS.
            monkeypatch.setenv("SSL_CERT_FILE", str(cert))
            # Owner-side request uses the real direct HTTPS transport too.
            def owner_call(route, payload):
                req = Request(base + bridge + route, data=json.dumps(payload).encode(),
                              headers={"Origin": origin, "Sec-Fetch-Site": "same-origin",
                                       "Content-Type": "application/json"})
                with agent._direct_https_opener().open(req, timeout=3) as reply:
                    return json.load(reply)

            issued = owner_call("pair-code", {"device_id": "owner-pc"})
            assert issued["ok"] and len(issued["code"]) == 24 and "token" not in issued
            registered = []
            monkeypatch.setattr(agent, "install_if_configured", lambda: registered.append(True) or True)
            monkeypatch.setattr(agent, "viewer_is_running", lambda: True)
            local = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory())
            local_thread = threading.Thread(target=local.serve_forever, daemon=True)
            local_thread.start()
            local_origin = f"http://127.0.0.1:{local.server_address[1]}"
            try:
                def local_claim(code):
                    req = Request(local_origin + "/local-replay/pair-claim",
                                  data=json.dumps({"device_id": "owner-pc", "code": code}).encode(),
                                  headers={"Origin": local_origin, "X-Local-Pair-Code": "explicit-click",
                                           "Content-Type": "application/json"})
                    return agent._direct_https_opener().open(req, timeout=5)
                with local_claim(issued["code"]) as reply:
                    assert json.load(reply) == {"configuration_saved": True}
                config = agent.read_config()
                assert config == {"origin": origin, "device_id": "owner-pc", "token": other}
                assert registered == [True]
                saved = agent.CONFIG_PATH.read_bytes()
                with pytest.raises(HTTPError) as repeat:
                    local_claim(issued["code"])
                assert repeat.value.code == 409
                assert agent.CONFIG_PATH.read_bytes() == saved
                # Real authenticated heartbeat and owner job, actual fact retrieval
                # and cache, then ACK. The callback asserts store-before-open.
                assert agent.poll_once(config) == "IDLE"
                queued = owner_call("request", {"episode_id": episode, "owner": "ROBOT",
                                               "source_revision": 9})
                assert queued["state"] == "QUEUED"
                opened = []
                def launch(episode_id):
                    assert episode_id == episode
                    record = json.loads(load_episode(app / "paper-episode-facts", episode_id))
                    assert record["source_revision"] == 9
                    assert record["setup_context"]["original_geometry"]["signal_id"] == "archived-exact-candidate"
                    opened.append(episode_id)
                assert agent.poll_once(config, launch=launch) == "OPEN_REQUESTED"
                assert opened == [episode]
                assert owner_call("status", {"request_id": queued["request_id"]})["state"] == "LAUNCHED"
                assert agent.poll_once(config) == "IDLE"
                assert [kind for kind, *_ in calls] == ["read", "project", "d2", "geometry"]
                assert not source.exists()
                assert len(seen) >= 7 if tls_pairing == "proxy" else not seen
                print("PAIR_TLS_CLAIM_PERSIST_FACTS_ACK_OK", tls_pairing)
            finally:
                local.shutdown()
                local.server_close()
                local_thread.join(timeout=3)
            return

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
