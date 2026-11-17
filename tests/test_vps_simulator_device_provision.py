"""Offline fail-closed proof of the existing one-shot owner-PC monolith path."""
import json
import os
from pathlib import Path

import pytest

from tools import paper_maintenance as maintenance
from tools import vps_simulator_device_provision as pairing
from tools import vps_manual_main_gateway as gateway
from tools import vps_release_identity as identity
from tools.vps_check import parse_env_lines
from tools import vps_release_resume as resume

SHA = "5" * 40
TOKEN = "A" * 64


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    owner = private / "owner.env"
    owner.write_text("BYBITSCANNER_AUTOPILOT_OWNER_TOKEN=existing_owner_token\n")
    owner.chmod(0o600)
    original = owner.read_bytes()
    paper = private / "paper.env"
    paper.write_text("BYBITSCANNER_PAPER_TEST=0\n")
    paper.chmod(0o644)
    state = {"stop": 0, "resume": 0, "live": {}}
    monkeypatch.setattr(identity, "verify_release", lambda root: SHA)
    monkeypatch.setattr(gateway, "inspect_authenticated_site",
                        lambda **kwargs: (private / "site", pairing.FACTS_ROUTE,
                                          pairing.FACTS_ROUTE))
    monkeypatch.setattr(maintenance, "_durable_editor_freeze", lambda *a, **k: "b" * 64)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready", lambda *a, **k: True)
    monkeypatch.setattr(maintenance, "_paper_start_quiescent", lambda *a, **k: True)
    monkeypatch.setattr(pairing, "_robot_stopped", lambda **kwargs: True)
    monkeypatch.setattr(pairing, "_runtime_env", lambda **kwargs: state["live"].copy())
    monkeypatch.setattr(pairing.secrets, "token_urlsafe", lambda n: TOKEN if n == 48 else None)
    monkeypatch.setattr(resume, "check_resume", lambda target, **kwargs: "RESUME_READY: exact stop")

    def stop(*a, **kw):
        state["stop"] += 1
        return "READY: canonical PAPER STOP confirmed; no update or restart"

    def start(*a, **kw):
        state["resume"] += 1
        state["live"] = parse_env_lines(owner.read_text().splitlines())
        return "READY: exact EDITOR_ONLY"

    monkeypatch.setattr(maintenance, "_stop_exact_installed_paper_once", stop)
    monkeypatch.setattr(maintenance, "resume_installed_release", start)
    def invoke():
        return pairing.provision_owner_pc(
            SHA, root=tmp_path, owner_env=owner, env_file=paper,
            uid=os.geteuid(),
        )
    return owner, original, state, invoke


def test_provision_uses_exact_existing_stop_and_editor_only_resume(scenario):
    owner, original, state, invoke = scenario
    outcome = invoke()
    assert outcome.startswith("READY:")
    assert TOKEN not in outcome
    assert state["stop"] == 1 and state["resume"] == 1
    assert owner.read_bytes().startswith(original)
    cfg = parse_env_lines(owner.read_text().splitlines())
    assert cfg["BYBITSCANNER_SIMULATOR_BRIDGE_ORIGIN"] == pairing.ORIGIN
    assert json.loads(cfg["BYBITSCANNER_SIMULATOR_BRIDGE_DEVICES_JSON"]) == {"owner-pc": TOKEN}
    assert owner.stat().st_mode & 0o077 == 0


def test_preflight_rejects_non_flat_or_non_editor_without_stop(scenario, monkeypatch):
    owner, original, state, invoke = scenario
    monkeypatch.setattr(maintenance, "_paper_start_quiescent", lambda *a, **k: False)
    assert invoke().startswith("BLOCKED: simulator_owner_pc_preflight:")
    assert owner.read_bytes() == original
    assert state["stop"] == state["resume"] == 0


def test_canonical_stop_block_does_not_write_or_restart(scenario, monkeypatch):
    owner, original, state, invoke = scenario
    def stopped(*a, **kw):
        state["stop"] += 1
        return "BLOCKED: canonical STOP outcome unknown"
    monkeypatch.setattr(maintenance, "_stop_exact_installed_paper_once", stopped)
    assert "canonical_stop_unproven" in invoke()
    assert owner.read_bytes() == original
    assert state["stop"] == 1 and state["resume"] == 0


def test_existing_device_never_overwritten(scenario):
    owner, original, state, invoke = scenario
    owner.write_bytes(original + b"BYBITSCANNER_SIMULATOR_BRIDGE_DEVICES_JSON='{}'\n")
    observed = owner.read_bytes()
    assert "existing_pairing_preserved" in invoke()
    assert owner.read_bytes() == observed
    assert state["stop"] == state["resume"] == 0


@pytest.mark.parametrize("mode", [0o644, 0o660])
def test_weak_secret_permissions_fail_before_stop(scenario, mode):
    owner, original, state, invoke = scenario
    owner.chmod(mode)
    assert "owner_env_permissions_untrusted" in invoke()
    assert owner.read_bytes() == original
    assert state["stop"] == state["resume"] == 0


def test_symlinked_owner_file_never_replaced(scenario):
    owner, original, state, invoke = scenario
    other = owner.with_name("protected")
    owner.rename(other)
    owner.symlink_to(other)
    assert "owner_env_symlink" in invoke()
    assert other.read_bytes() == original
    assert state["stop"] == state["resume"] == 0


def test_partial_resume_does_not_retry_stop_or_secret_write(scenario, monkeypatch):
    owner, original, state, invoke = scenario
    def failed_resume(*a, **kw):
        state["resume"] += 1
        return "BLOCKED: unknown resume"
    monkeypatch.setattr(maintenance, "resume_installed_release", failed_resume)
    outcome = invoke()
    assert "editor_only_resume_unproven" in outcome
    assert TOKEN not in outcome
    assert state["stop"] == state["resume"] == 1
    assert owner.read_bytes().startswith(original)


def test_untrusted_runtime_origin_blocks_before_stop(scenario):
    owner, original, state, invoke = scenario
    state["live"] = {"BYBITSCANNER_SIMULATOR_BRIDGE_ORIGIN": "https://unexpected.invalid"}
    assert "runtime_relay_already_configured" in invoke()
    assert owner.read_bytes() == original
    assert state["stop"] == state["resume"] == 0


def test_conflicting_paper_env_pairing_is_refused_before_stop(scenario):
    owner, original, state, invoke = scenario
    paper = owner.parent / "paper.env"
    paper.write_text("BYBITSCANNER_SIMULATOR_BRIDGE_ORIGIN=https://unknown.invalid\n")
    assert "paper_env_relay_conflict" in invoke()
    assert owner.read_bytes() == original
    assert state["stop"] == state["resume"] == 0


def test_paper_env_change_after_stop_blocks_before_secret_write(scenario, monkeypatch):
    owner, original, state, invoke = scenario
    paper = owner.parent / "paper.env"

    def stop(*args, **kwargs):
        state["stop"] += 1
        paper.write_text("BYBITSCANNER_PAPER_TEST=1\n")
        return "READY: canonical PAPER STOP confirmed; no update or restart"

    monkeypatch.setattr(maintenance, "_stop_exact_installed_paper_once", stop)
    assert "post_stop_editor_freeze_unproven" in invoke()
    assert owner.read_bytes() == original
    assert state["stop"] == 1 and state["resume"] == 0
