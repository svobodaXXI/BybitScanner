"""No live APIs, token files, GitHub service or host mutations."""
import json

import pytest
from Crypto.PublicKey import ECC

from tools import github_diagnostic_protocol as protocol
from tests.test_github_status_reporter import status_payload

NOW = 1_800_000_000
AUDIENCE = "a" * 32


@pytest.fixture
def context():
    issuer = ECC.generate(curve="Ed25519")
    responder = ECC.generate(curve="Ed25519")
    payload = {"version": 1, "operation": "observe", "audience": AUDIENCE,
               "request_id": "b" * 32, "issued_at": NOW - 1, "expires_at": NOW + 60}
    wire = protocol.sign_request(payload, issuer_key=issuer, audience=AUDIENCE, now=NOW)
    claims, reads = {}, []
    source = status_payload()
    def reserve(rid, digest):
        if rid in claims:
            return False
        claims[rid] = digest
        return True
    def fetch(url):
        reads.append(url)
        return source[url]
    kwargs = dict(issuer_public=issuer.public_key(), responder_key=responder,
                  audience=AUDIENCE, clock=lambda: NOW, reserve=reserve, fetch=fetch)
    verify = dict(expected_request=wire, issuer_public=issuer.public_key(),
                  responder_public=responder.public_key(), audience=AUDIENCE, now=NOW)
    return payload, wire, kwargs, verify, issuer, responder, claims, reads


def test_signed_roundtrip_reuses_public_observer_and_correlates(context):
    _, wire, kw, verify, _, _, claims, reads = context
    result = protocol.process_request(wire, **kw)
    assert len(claims) == 1 and len(reads) == 7
    observed = protocol.verify_response(result, **verify)
    assert observed["position_count"] == 1
    assert observed["assessment"] == "ATTENTION"
    assert b"SECRETUSDT" not in result and b"PRIVATE" not in result
    with pytest.raises(ValueError):
        protocol.process_request(wire, **kw)
    assert len(reads) == 7


@pytest.mark.parametrize("defect", ["forge", "edit", "unknown_action", "extra_field",
                                    "wrong_audience", "expired", "future", "duplicate",
                                    "oversize", "wrong_key", "unproven_reservation"])
def test_refusal_precedes_any_observation(context, defect):
    payload, wire, kw, _, issuer, responder, _, reads = context
    if defect == "forge":
        wire = protocol._sign("request", payload, ECC.generate(curve="Ed25519"))
    elif defect == "edit":
        wire = wire.replace(b'"observe"', b'"update"')
    elif defect == "unknown_action":
        wire = protocol._sign("request", {**payload, "operation": "start"}, issuer)
    elif defect == "extra_field":
        wire = protocol._sign("request", {**payload, "command": "forbidden"}, issuer)
    elif defect == "wrong_audience":
        kw["audience"] = "c" * 32
    elif defect == "expired":
        kw["clock"] = lambda: NOW + 60
    elif defect == "future":
        kw["clock"] = lambda: NOW - 2
    elif defect == "duplicate":
        wire = wire.replace(b'"version":1', b'"version":1,"version":1')
    elif defect == "oversize":
        wire = b"x" * (protocol.MAX_WIRE + 1)
    elif defect == "wrong_key":
        kw["responder_key"] = issuer
    elif defect == "unproven_reservation":
        kw["reserve"] = lambda *_: False
    with pytest.raises(ValueError):
        protocol.process_request(wire, **kw)
    assert reads == []


def test_edited_forged_stale_and_cross_request_response_rejected(context):
    payload, wire, kw, verify, issuer, responder, _, _ = context
    result = protocol.process_request(wire, **kw)
    with pytest.raises(ValueError):
        protocol.verify_response(result.replace(b'"position_count":1', b'"position_count":0'), **verify)
    forged = protocol._sign("response", json.loads(result)["payload"],
                            ECC.generate(curve="Ed25519"))
    with pytest.raises(ValueError):
        protocol.verify_response(forged, **verify)
    with pytest.raises(ValueError):
        protocol.verify_response(result, **{**verify, "now": NOW + 60})
    other = protocol.sign_request({**payload, "request_id": "d" * 32},
                                  issuer_key=issuer, audience=AUDIENCE, now=NOW)
    with pytest.raises(ValueError):
        protocol.verify_response(result, **{**verify, "expected_request": other})


def test_failed_observation_never_reports_flat(context):
    _, wire, kw, verify, *_ = context
    def fail(_):
        raise TimeoutError("PRIVATE_REASON")
    reply = protocol.process_request(wire, **{**kw, "fetch": fail})
    snapshot = protocol.verify_response(reply, **verify)
    assert snapshot["assessment"] == "UNKNOWN"
    assert snapshot["position_count"] is None
    assert b"PRIVATE_REASON" not in reply


@pytest.fixture
def durable_context(context, tmp_path):
    pytest.importorskip("fcntl")
    from tools.github_diagnostic_journal import DiagnosticJournal
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    journal = DiagnosticJournal(root)
    journal.initialize()
    payload, wire, kw, verify, issuer, responder, claims, reads = context
    kw.pop("reserve")
    return journal, payload, wire, kw, verify, issuer, responder, reads


def test_durable_restart_and_historical_delivery(durable_context):
    from tools.github_diagnostic_journal import DiagnosticJournal, verify_historical_response
    journal, _, wire, kw, verify, _, _, reads = durable_context
    reply = journal.process(wire, **kw)
    restarted = DiagnosticJournal(journal.directory)
    with pytest.raises(ValueError):
        restarted.process(wire, **kw)
    assert len(reads) == 7
    args = {k: v for k, v in verify.items() if k not in {"expected_request", "now"}}
    delayed = NOW + 3600
    attempts = []
    def lost_ack(request, response):
        attempts.append((request, response))
        raise TimeoutError("unknown POST outcome")
    with pytest.raises(TimeoutError):
        restarted.deliver_pending(**args, clock=lambda: delayed, post=lost_ack)
    def acknowledged(request, response):
        attempts.append((request, response))
        return True
    assert restarted.deliver_pending(**args, clock=lambda: delayed, post=acknowledged) == 1
    assert restarted.deliver_pending(**args, clock=lambda: delayed, post=acknowledged) == 0
    assert attempts == [(wire, reply), (wire, reply)]
    with pytest.raises(ValueError):
        protocol.verify_response(reply, **{**verify, "now": delayed})
    historical = verify_historical_response(reply, **{**verify, "now": delayed})
    assert historical["observed_at"] == NOW and historical["fresh"] is False
    assert historical["snapshot"]["position_count"] == 1
    assert len(reads) == 7


def test_interrupted_reservation_is_never_reobserved(durable_context, monkeypatch):
    from tools import github_diagnostic_protocol as p
    from tools.github_diagnostic_journal import DiagnosticJournal
    journal, _, wire, kw, _, _, _, reads = durable_context
    def interrupted(_):
        raise KeyboardInterrupt
    with monkeypatch.context() as patch:
        patch.setattr(p, "observe", interrupted)
        with pytest.raises(KeyboardInterrupt):
            journal.process(wire, **kw)
    with pytest.raises(ValueError):
        DiagnosticJournal(journal.directory).process(wire, **kw)
    assert not reads


def test_missing_or_tampered_journal_fails_closed(durable_context):
    journal, _, wire, kw, _, _, _, reads = durable_context
    journal.path.unlink()
    with pytest.raises(FileNotFoundError):
        journal.process(wire, **kw)
    assert not reads


def test_pruning_preserves_pending_and_blocks_clock_rollback(durable_context):
    from tools.github_diagnostic_journal import RETENTION_SECONDS
    journal, payload, wire, kw, verify, issuer, _, reads = durable_context
    journal.process(wire, **kw)
    args = {k: v for k, v in verify.items() if k not in {"expected_request", "now"}}
    later = NOW + RETENTION_SECONDS + 100
    new = {**payload, "request_id": "c"*32, "issued_at": later, "expires_at": later+60}
    wire_new = protocol.sign_request(new, issuer_key=issuer, audience=AUDIENCE, now=later)
    journal.process(wire_new, **{**kw, "clock": lambda: later})
    assert len(journal._load()["entries"]) == 2  # old unacknowledged receipt stays
    assert journal.deliver_pending(**args, clock=lambda: later, post=lambda *_: True) == 2
    newest = {**new, "request_id": "d"*32}
    journal.process(protocol.sign_request(newest, issuer_key=issuer, audience=AUDIENCE,
                                         now=later), **{**kw, "clock": lambda: later})
    assert "b"*32 not in journal._load()["entries"]
    with pytest.raises(ValueError):
        journal.process(wire, **kw)
    assert len(reads) == 21


def test_bounded_cycle_ignores_unsigned_and_replayed_requests(durable_context):
    journal, payload, wire, kw, _, issuer, _, reads = durable_context
    other = protocol.sign_request({**payload, "request_id": "c"*32},
                                  issuer_key=issuer, audience=AUDIENCE, now=NOW)
    class Transport:
        sent = []
        def requests(self, now):
            return [b"unsigned", wire, wire, other]
        def post(self, request, response):
            self.sent.append((request, response))
            return True
    transport = Transport()
    assert journal.run_once(enabled=False, transport=transport, **kw)["observed"] == 0
    assert journal.run_once(enabled=True, transport=transport, **kw)["observed"] == 1
    assert journal.run_once(enabled=True, transport=transport, **kw)["observed"] == 1
    assert journal.run_once(enabled=True, transport=transport, **kw)["observed"] == 0
    assert len(reads) == 14
    assert [x[0] for x in transport.sent] == [wire, other]


def test_fixed_github_transport_no_redirect_or_dynamic_endpoint(context):
    from tools.github_diagnostic_transport import (
        GitHubDiagnosticTransport, REQUEST_MARKER, RESPONSE_MARKER, ISSUE_URL)
    _, wire, kw, _, _, _, _, _ = context
    signed = protocol.process_request(wire, **kw)
    calls = []
    class Reply:
        def __init__(self, code, payload):
            self.status_code = code
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def iter_content(self, chunk_size):
            yield json.dumps(self.payload).encode()
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return Reply(200, [{"body": "untrusted"}, {"body": REQUEST_MARKER+wire.decode()}])
        return Reply(201, {"id": 1, "body": kwargs["json"]["body"]})
    transport = GitHubDiagnosticTransport(request=request, token="x"*40)
    assert transport.requests(NOW) == [wire]
    assert transport.post(wire, signed) is True
    assert calls[1][2]["json"]["body"] == RESPONSE_MARKER+signed.decode()
    assert all(url == ISSUE_URL and kwargs["allow_redirects"] is False
               for _, url, kwargs in calls)
    transport = GitHubDiagnosticTransport(request=lambda *a, **k: Reply(302, {}), token="x"*40)
    with pytest.raises(ValueError):
        transport.requests(NOW)


def test_trusted_issuer_binds_key_and_fixed_request(context):
    from tools.github_diagnostic_issuer import make_request
    payload, wire, _, _, issuer, responder, *_ = context
    public = {"audience": AUDIENCE,
              "issuer_public": issuer.public_key().export_key(format="raw").hex(),
              "responder_public": responder.public_key().export_key(format="raw").hex()}
    request = {k: payload[k] for k in ("request_id", "issued_at", "expires_at")}
    seed = issuer.seed.hex()
    assert make_request(public, request, seed, NOW) == wire
    with pytest.raises(ValueError):
        make_request(public, {**request, "operation": "start"}, seed, NOW)
    with pytest.raises(ValueError):
        make_request(public, request, responder.seed.hex(), NOW)
    with pytest.raises(ValueError):
        make_request(public, request, seed, request["expires_at"])


def test_runtime_opt_in_and_pinned_release_precede_network(durable_context, tmp_path, monkeypatch):
    import os
    from tools import github_diagnostic_runtime as runtime
    journal, _, _, _, _, issuer, responder, _ = durable_context
    directory = tmp_path / "protected"
    directory.mkdir(mode=0o700)
    path = directory / "config.json"
    config = {"enabled": False, "release_sha": "a"*40, "audience": AUDIENCE,
              "issuer_public": issuer.public_key().export_key(format="raw").hex(),
              "responder_seed": responder.seed.hex()}
    def put():
        path.write_text(json.dumps(config))
        path.chmod(0o600)
    put()
    calls = []
    def pin(*args, **kwargs):
        calls.append("pin")
        raise ValueError("unpinned release")
    def network():
        pytest.fail("unexpected network session")
    monkeypatch.setattr(runtime, "_pin_release", pin)
    args = {"config_dir": directory, "state_dir": journal.directory,
            "session_factory": network, "uid": os.geteuid()}
    assert runtime.run_once(**args)["enabled"] is False
    assert not calls
    config["enabled"] = True
    put()
    with pytest.raises(ValueError, match="unpinned"):
        runtime.run_once(**args)
    assert calls == ["pin"]
    path.chmod(0o644)
    with pytest.raises(ValueError, match="unprotected"):
        runtime.run_once(**args)
    assert calls == ["pin"]
    config["issuer_public"] = responder.public_key().export_key(format="raw").hex()
    put()
    with pytest.raises(ValueError, match="independent"):
        runtime.run_once(**args)
    assert calls == ["pin"]


def test_host_enable_rejects_uninitialized_journal_before_systemd(durable_context, tmp_path, monkeypatch):
    import os
    from tools import github_diagnostic_runtime as runtime
    _, _, _, _, _, issuer, responder, _ = durable_context
    directory = tmp_path / "protected"
    directory.mkdir(mode=0o700)
    path = directory / "config.json"
    path.write_text(json.dumps({"enabled": True, "release_sha": "a"*40,
                               "audience": AUDIENCE,
                               "issuer_public": issuer.public_key().export_key(format="raw").hex(),
                               "responder_seed": responder.seed.hex()}))
    path.chmod(0o600)
    monkeypatch.setattr(runtime, "_pin_release", lambda *a, **k: None)
    monkeypatch.setattr(runtime, "_token", lambda _: "x"*40)
    def systemd(*args, **kwargs):
        pytest.fail("systemd must not be invoked")
    result = runtime.enable_diagnostic("a"*40, config_dir=directory,
                                       state_dir=tmp_path / "missing",
                                       uid=os.geteuid(), run=systemd)
    assert result.startswith("BLOCKED:")


@pytest.mark.parametrize("defect, expected", [
    ("format", "stage=SEED_FORMAT"),
    ("pin", "stage=KEY_PIN"),
    ("expired", "stage=REQUEST_VALIDATION"),
    ("http", "stage=PUBLISH http=403"),
    ("publish", "stage=PUBLISH"),
])
def test_issuer_failure_evidence_is_bounded(context, monkeypatch, capsys, defect, expected):
    from urllib.error import HTTPError
    from tools import github_diagnostic_issuer as module
    payload, _, _, _, issuer, responder, *_ = context
    public = {"audience": AUDIENCE,
              "issuer_public": issuer.public_key().export_key(format="raw").hex(),
              "responder_public": responder.public_key().export_key(format="raw").hex()}
    request = {k: payload[k] for k in ("request_id", "issued_at", "expires_at")}
    seed = issuer.seed.hex()
    if defect == "format":
        seed = "SECRET_WRONG_FORMAT"
    if defect == "pin":
        seed = responder.seed.hex()
    monkeypatch.setenv("GITHUB_REPOSITORY", "svobodaXXI/BybitScanner")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/diagnostic-issuer")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("DIAGNOSTIC_ISSUER_SEED", seed)
    monkeypatch.setenv("DIAGNOSTIC_GITHUB_TOKEN", "SECRET_TOKEN_NOT_FOR_LOGS")
    monkeypatch.setattr(module, "_object", lambda path: public if path == module.PUBLIC else request)
    monkeypatch.setattr(module.time, "time", lambda: NOW if defect != "expired" else request["expires_at"])
    def publish(*args):
        if defect == "http":
            raise HTTPError("https://example.invalid/SECRET", 403, "SECRET_HTTP_BODY", {}, None)
        if defect == "publish":
            raise RuntimeError("SECRET_EXCEPTION")
        pytest.fail("publication must not be attempted")
    monkeypatch.setattr(module, "publish", publish)
    assert module.main() == 2
    out = capsys.readouterr().out
    assert out == "SIGNED_OBSERVATION_REQUEST_BLOCKED " + expected + "\n"
    assert "SECRET" not in out and seed not in out


@pytest.mark.parametrize("token", ["ghs_" + "x" * 36, "ghs_123_" + "x" * 230 + "." + "y" * 230 + "." + "z" * 60])
def test_issuer_accepts_opaque_actions_credentials(monkeypatch, token):
    from tools import github_diagnostic_issuer as module
    calls = []
    class Response:
        status = 201
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return module.json.dumps({"id": 1, "body": module.REQUEST_MARKER + "signed"}).encode()
    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Authorization") == "Bearer " + token
            calls.append(True)
            return Response()
    monkeypatch.setattr(module, "build_opener", lambda *args: Opener())
    module.publish(b"signed", token)
    assert calls == [True]


@pytest.mark.parametrize("token", ["", "a b", "a\nb", "a\rb", "a\tb", "a" + chr(127), "a" + chr(233)])
def test_issuer_rejects_invalid_authorization_header(monkeypatch, token):
    from tools import github_diagnostic_issuer as module
    monkeypatch.setattr(module, "build_opener", lambda *_: pytest.fail("network forbidden"))
    with pytest.raises(module.InvalidPublicationCredential):
        module.publish(b"signed", token)


@pytest.mark.parametrize("defect", [None, "disabled", "missing_receipt", "wrong_predecessor",
                                    "changed_unit", "wrong_installed_bytes", "unprotected_pin",
                                    "missing_journal"])
def test_release_pin_continues_only_with_exact_owner_transaction(tmp_path, context, defect):
    import os
    from tools import github_diagnostic_runtime as runtime
    from tools.github_diagnostic_journal import DiagnosticJournal
    from tools.vps_release_identity import git_blob_hash

    _, _, _, _, issuer, responder, _, _ = context
    old, target = "c" * 40, "d" * 40
    root, config_dir, state_dir, unit_dir, transactions = (
        tmp_path / name for name in ("release", "config", "state", "units", "transactions"))
    for directory in (root, config_dir, state_dir, unit_dir, transactions):
        directory.mkdir(mode=0o700)
    DiagnosticJournal(state_dir).initialize()
    journal = DiagnosticJournal(state_dir)
    before_journal = journal.path.read_bytes()
    config = {"enabled": defect != "disabled", "release_sha": old, "audience": AUDIENCE,
              "issuer_public": issuer.public_key().export_key(format="raw").hex(),
              "responder_seed": responder.seed.hex()}
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    before_config = config_path.read_bytes()
    blobs = {}
    for name in (*runtime.PINNED, "terminal/runtime/paper_http_server.py"):
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        data = name.encode("ascii")
        file.write_bytes(data)
        file.chmod(0o644)
        blobs[name] = git_blob_hash(data)
    for name in runtime.NAMES:
        unit = unit_dir / name
        unit.write_bytes((root / "deploy/systemd" / name).read_bytes())
        unit.chmod(0o644)
    target_manifest = {"build_sha": target, "blobs": blobs}
    previous = {"build_sha": old, "blobs": dict(blobs)}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(target_manifest))
    manifest_path.chmod(0o600)
    transaction = transactions / target
    transaction.mkdir(mode=0o700)
    (transactions / ".release.lock").touch(mode=0o600)
    if defect == "wrong_predecessor":
        previous["build_sha"] = "e" * 40
    if defect == "changed_unit":
        previous["blobs"]["deploy/systemd/" + runtime.NAMES[0]] = "f" * 40
    for name, data in (("old.json", previous), ("target.json", target_manifest)):
        file = transaction / name
        file.write_text(json.dumps(data))
        file.chmod(0o600)
    intent = transactions / (".stop-invoked-" + target)
    intent.write_bytes(b"STOP_INVOKED; not install authorization\n")
    intent.chmod(0o600)
    if defect != "missing_receipt":
        receipt = transactions / (".stop-confirmed-" + target)
        receipt.write_bytes(f"CANONICAL_ALL_STOP_CONFIRMED:{old}:{target}\n".encode("ascii"))
        receipt.chmod(0o600)
    if defect == "wrong_installed_bytes":
        (root / "terminal/runtime/paper_http_server.py").write_bytes(b"changed")
    if defect == "unprotected_pin":
        (root / runtime.PINNED[0]).chmod(0o664)
    if defect == "missing_journal":
        journal.path.unlink()
    kw = dict(root=root, manifest_path=manifest_path, transactions=transactions,
              config_dir=config_dir, state_dir=state_dir, unit_dir=unit_dir, uid=os.geteuid())
    if defect is None:
        assert runtime.carry_forward_pin(**kw) == "ADVANCED"
        assert json.loads(config_path.read_bytes()) == {**config, "release_sha": target}
        assert config_path.stat().st_mode & 0o777 == 0o600
        assert runtime.carry_forward_pin(**kw) == "UNCHANGED"
    elif defect == "disabled":
        assert runtime.carry_forward_pin(**kw) == "SKIPPED_DISABLED"
        assert config_path.read_bytes() == before_config
    else:
        with pytest.raises((ValueError, OSError)):
            runtime.carry_forward_pin(**kw)
        assert config_path.read_bytes() == before_config
    if defect == "missing_journal":
        assert not journal.path.exists()
    else:
        assert journal.path.read_bytes() == before_journal
