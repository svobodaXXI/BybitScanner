"""Offline authorization to existing owner monolith; no real host actions."""
from contextlib import contextmanager
import hashlib
import json
import subprocess

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa
import pytest

from tools import owner_update_grant as grant
from tools import paper_maintenance as maintenance
from tools import vps_owner_control as control
from tools import vps_release_identity as release

NOW = 1800000000
PREVIOUS, TARGET, AUDIENCE, RID = "a" * 40, "b" * 40, "c" * 32, "d" * 32


@pytest.fixture
def setup(tmp_path):
    owner, issuer, responder = [ECC.generate(curve="Ed25519") for _ in range(3)]
    path = tmp_path / "ledger"
    path.mkdir(mode=0o700)
    ledger = grant.GrantLedger(path)
    ledger.initialize()
    pins = dict(approval_public=owner.public_key(),
                diagnostic_issuer_public=issuer.public_key(),
                diagnostic_responder_public=responder.public_key(),
                audience=AUDIENCE)
    payload = dict(version=1, operation="update", audience=AUDIENCE,
                   owner_request_id=RID, expected_installed_sha=PREVIOUS,
                   target_sha=TARGET, approved_at=NOW, expires_at=NOW + 120)
    calls = []
    def submit(*args, **kw):
        calls.append((args, kw))
        return 0
    kw = dict(**pins, enabled=True, ledger=ledger, installed_sha=lambda: PREVIOUS,
              clock=lambda: NOW, submit=submit)
    def sign(p=None):
        return grant.sign_grant(payload if p is None else p, approval_key=owner,
                                audience=AUDIENCE, now=NOW)
    return payload, sign, kw, calls, path, issuer


@pytest.mark.parametrize("action", ["update", "update-and-start"])
def test_one_grant_exact_canonical_dispatch_and_no_replay(setup, action):
    payload, sign, kw, calls, path, _ = setup
    wire = sign(dict(payload, operation=action))
    assert grant.submit_granted_update(wire, **kw) == 0
    digest = hashlib.sha256(wire).hexdigest()
    assert calls == [((action, TARGET, RID, "owner-grant-" + digest[:48]),
                     {"expected_installed_sha": PREVIOUS})]
    assert (path / (RID + ".used")).read_text().strip() == digest
    with pytest.raises(ValueError, match="consumed"):
        grant.submit_granted_update(wire, **kw)
    assert len(calls) == 1


@pytest.mark.parametrize("change", [
    {"enabled": False}, {"clock": lambda: NOW + 120},
    {"installed_sha": lambda: "e" * 40}, {"audience": "e" * 32},
])
def test_rejected_grant_does_not_reserve_or_dispatch(setup, change):
    _, sign, kw, calls, path, _ = setup
    with pytest.raises(ValueError):
        grant.submit_granted_update(sign(), **dict(kw, **change))
    assert not calls and not (path / (RID + ".used")).exists()


def test_diagnostic_key_cannot_grant_owner_authority(setup):
    payload, sign, kw, calls, path, issuer = setup
    wire = grant.sign_grant(payload, approval_key=issuer, audience=AUDIENCE, now=NOW)
    for supplied in (kw, dict(kw, approval_public=issuer.public_key())):
        with pytest.raises(ValueError):
            grant.submit_granted_update(wire, **supplied)
    assert not calls
    assert not (path / (RID + ".used")).exists()


@pytest.mark.parametrize("action", ["start", "stop", "live", "shell"])
def test_unapproved_verb_not_signable_even_with_owner_key(setup, action):
    payload, sign, kw, calls, path, _ = setup
    with pytest.raises(ValueError):
        sign(dict(payload, operation=action))
    assert not calls


def test_mutated_approval_cannot_upgrade_to_start(setup):
    _, sign, kw, calls, path, _ = setup
    wire = json.loads(sign())
    wire["payload"]["operation"] = "update-and-start"
    with pytest.raises(ValueError):
        grant.submit_granted_update(grant._canonical(wire), **kw)
    assert not calls and not (path / (RID + ".used")).exists()


def test_consumption_survives_lost_submit_response(setup):
    _, sign, kw, calls, path, _ = setup
    wire = sign()
    def lost(*args, **kwargs):
        calls.append(args)
        raise OSError("lost response")
    with pytest.raises(OSError):
        grant.submit_granted_update(wire, **dict(kw, submit=lost))
    with pytest.raises(ValueError, match="consumed"):
        grant.submit_granted_update(wire, **kw)
    assert len(calls) == 1


def test_changed_predecessor_after_reservation_consumes_without_dispatch(setup):
    _, sign, kw, calls, path, _ = setup
    wire = sign()
    reads = iter((PREVIOUS, "e" * 40))
    with pytest.raises(ValueError, match="changed after claim"):
        grant.submit_granted_update(wire, **dict(kw, installed_sha=lambda: next(reads)))
    assert (path / (RID + ".used")).is_file()
    assert not calls


def test_uninitialized_or_unprotected_ledger_fails_closed(setup):
    _, sign, kw, calls, path, _ = setup
    wire = sign()
    (path / "initialized").unlink()
    with pytest.raises(OSError):
        grant.submit_granted_update(wire, **kw)
    path.chmod(0o775)
    with pytest.raises(ValueError, match="unprotected"):
        grant.submit_granted_update(wire, **kw)
    assert not calls


def test_detached_command_carries_approved_predecessor(monkeypatch, tmp_path):
    import os
    original = control._owner_request_path
    monkeypatch.setattr(control, "_owner_request_path",
                        lambda request, *, create=False: original(
                            request, create=create, root=tmp_path / "transactions",
                            trusted_uid=os.geteuid()))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0,
            stdout="LoadState=not-found\n" if command[0] == "systemctl" else "", stderr="")
    assert control.submit("update-and-start", TARGET, RID, "owner-test",
                          run=run, uid=0, expected_installed_sha=PREVIOUS) == 0
    assert len(calls) == 2
    assert calls[1][0] == "systemd-run"
    assert calls[1][-7:] == ["-m", "tools.paper_maintenance", TARGET, "--action",
                             "update-and-start", "--expected-installed-sha", PREVIOUS]
    with pytest.raises(ValueError):
        control.submit("start", TARGET, RID, "owner-test", run=run, uid=0,
                       expected_installed_sha=PREVIOUS)
    assert len(calls) == 2


@pytest.mark.parametrize("observed", [PREVIOUS, "e" * 40])
def test_predecessor_rechecked_inside_monolith_lock_before_staging(monkeypatch, capsys, observed):
    events = []
    @contextmanager
    def lock():
        events.append("lock")
        yield
        events.append("unlock")
    def installed(*args, **kwargs):
        assert events == ["lock"]
        events.append("verify")
        return observed
    def stage(*args, **kwargs):
        events.append("stage")
        raise ValueError("offline stop before staging")
    monkeypatch.setattr(maintenance, "_owner_action_lifecycle_guard", lock)
    monkeypatch.setattr(release, "verify_release", installed)
    monkeypatch.setattr(maintenance, "_prepare_approved_editor_stage", stage)
    rc = maintenance.main([TARGET, "--action", "update-and-start", "--expected-installed-sha", PREVIOUS])
    assert rc == 2
    if observed == PREVIOUS:
        assert events == ["lock", "verify", "stage", "unlock"]
    else:
        assert events == ["lock", "verify", "unlock"]
        assert "approved_predecessor_changed" in capsys.readouterr().out
