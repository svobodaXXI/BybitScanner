"""Offline tests: public allowlist, outage containment and bounded replay."""
import json
import os
from pathlib import Path

import pytest

from tools.github_status_reporter import BACKEND, TELEGRAM, observe, report_once


def status_payload(*, positions=1, covered=True, robot="RECONCILIATION_REQUIRED"):
    sensitive = {
        "symbol": "SECRETUSDT", "position_quantity": "990",
        "average_entry": "0.123456", "private_key": "DO_NOT_PUBLISH",
    }
    return {
        BACKEND + "/api/health": {"ok": True, "component": "paper_backend",
            "mode": "paper", "paper_live_safe": True,
            "build_sha": "a" * 40, "database_identity": "PRIVATE_ID"},
        BACKEND + "/api/robot/state": {"mode": "ROBOT_RUNNING",
            "recovery_status": robot, "reason": "PRIVATE_REASON"},
        BACKEND + "/api/scanner/status": {"mode": "SCANNER_STOPPED"},
        BACKEND + "/api/robot/autopilot": {"mode": "OFF"},
        BACKEND + "/api/open-positions": {"positions": [
            dict(sensitive) for _ in range(positions)
        ]},
        BACKEND + "/api/robot/protection-health": {
            "healthy": covered, "covered_symbols": ["SECRETUSDT"] if covered else [],
            "unhealthy_symbols": {"SECRETUSDT": "PRIVATE_FAILURE"},
        },
        TELEGRAM + "/health": {"component": "telegram_monitoring", "status": "ready"},
    }


def _token_file(tmp_path):
    file = tmp_path / "token"
    file.write_text("example_only_" + "x" * 48)
    file.chmod(0o600)
    return file


def test_snapshot_public_allowlist_and_no_false_protection():
    source = status_payload(covered=False)
    result = observe(lambda url: source[url])
    assert result["position_count"] == 1
    assert result["coverage"] == "REPORTED_MISSING"
    assert result["assessment"] == "ATTENTION"
    serialized = json.dumps(result)
    for secret in ("SECRETUSDT", "990", "PRIVATE", "0.123456"):
        assert secret not in serialized


def test_missing_backend_never_claims_flat():
    result = observe(lambda _: (_ for _ in ()).throw(OSError("PRIVATE")))
    assert result["backend"] == "UNAVAILABLE"
    assert result["position_count"] is None
    assert result["assessment"] == "UNKNOWN"


def test_delivery_retries_persisted_event_without_trading(tmp_path):
    data = status_payload()
    token = _token_file(tmp_path)
    state_dir = tmp_path / "outbox"
    seen = []
    def fail(_token, _body):
        raise TimeoutError("unknown GitHub POST outcome")
    assert report_once(token_file=token, state_dir=state_dir,
        fetch=lambda url: data[url], post=fail, now_ms=1_800_000_000_000) == 2
    state = json.loads((state_dir / "pending.json").read_text())
    assert len(state["queue"]) == 1
    assert report_once(token_file=token, state_dir=state_dir,
        fetch=lambda url: data[url], post=lambda t, b: seen.append(b),
        now_ms=1_800_000_030_000) == 0
    assert len(seen) == 1
    assert "event_id=" in seen[0]
    assert "SECRETUSDT" not in seen[0]
    assert json.loads((state_dir / "pending.json").read_text())["queue"] == []
    # No redundant post before the heartbeat threshold.
    assert report_once(token_file=token, state_dir=state_dir,
        fetch=lambda url: data[url], post=lambda t, b: seen.append(b),
        now_ms=1_800_000_060_000) == 0
    assert len(seen) == 1


def test_missing_or_insecure_token_performs_no_http(tmp_path):
    not_safe = _token_file(tmp_path)
    not_safe.chmod(0o644)
    assert report_once(token_file=not_safe, state_dir=tmp_path / "state",
        fetch=lambda _: pytest.fail("must not read API"),
        post=lambda *_: pytest.fail("must not post")) == 2
    assert not (tmp_path / "state").exists()


def test_unknown_api_fields_and_payload_do_not_escape(tmp_path):
    data = status_payload()
    data[BACKEND + "/api/robot/state"]["recovery_status"] = "SECRET_STATUS"
    token = _token_file(tmp_path)
    outputs = []
    assert report_once(token_file=token, state_dir=tmp_path / "queue",
        fetch=lambda url: data[url], post=lambda t, b: outputs.append(b),
        now_ms=1_800_000_000_000) == 0
    assert '"recovery": "UNKNOWN"' in outputs[0]
    assert "SECRET_STATUS" not in outputs[0]


def test_changed_status_emits_new_event(tmp_path):
    data = status_payload()
    token = _token_file(tmp_path)
    out = []
    for index in range(2):
        if index:
            data[BACKEND + "/api/robot/state"]["recovery_status"] = "PAUSED"
        assert report_once(token_file=token, state_dir=tmp_path / "state",
            fetch=lambda url: data[url], post=lambda t, b: out.append(b),
            now_ms=1_800_000_000_000 + index * 32_000) == 0
    assert len(out) == 2
    assert "RECONCILIATION_REQUIRED" in out[0]
    assert '"recovery": "PAUSED"' in out[1]


def test_symlink_state_is_never_followed(tmp_path):
    token = _token_file(tmp_path)
    outer = tmp_path / "unrelated.json"
    outer.write_text('{"critical":true}')
    outbox = tmp_path / "outbox"
    outbox.mkdir(mode=0o700)
    (outbox / "pending.json").symlink_to(outer)
    assert report_once(token_file=token, state_dir=outbox,
        fetch=lambda url: status_payload()[url],
        post=lambda *_: pytest.fail("must not post"),
        now_ms=1_800_000_000_000) == 2
    assert outer.read_text() == '{"critical":true}'


def test_backend_safety_flag_failure_is_public_attention():
    data = status_payload()
    data[BACKEND + "/api/health"]["paper_live_safe"] = False
    result = observe(lambda url: data[url])
    assert result["backend"] == "SAFETY_FLAG_FAILED"
    assert result["assessment"] == "ATTENTION"
    assert result["position_count"] is None
    assert "PRIVATE" not in json.dumps(result)


def test_telegram_unavailable_is_attention_when_backend_known():
    data = status_payload(positions=0, robot="READY")
    def fetch(url):
        if url == TELEGRAM + "/health":
            raise OSError("private network error")
        return data[url]
    result = observe(fetch)
    assert result["backend"] == "REACHABLE"
    assert result["telegram"] == "UNAVAILABLE"
    assert result["assessment"] == "ATTENTION"
