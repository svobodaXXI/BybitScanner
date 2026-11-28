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


@pytest.fixture
def observer_setup(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tools import vps_release_identity as identity

    root = tmp_path / "release"
    units = tmp_path / "systemd"
    units.mkdir()
    names = ("bybitscanner-github-status.service", "bybitscanner-github-status.timer")
    paths = ("terminal/runtime/paper_http_server.py", "tools/vps_release_identity.py",
             "tools/github_status_reporter.py", *("deploy/systemd/" + n for n in names))
    blobs = {}
    for rel in paths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = ("fixture " + rel).encode()
        path.write_bytes(data)
        blobs[rel] = identity.git_blob_hash(data)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"build_sha": "a" * 40, "blobs": blobs}))
    verify = identity.verify_release
    monkeypatch.setattr(identity, "verify_release",
                        lambda r, m: verify(r, m, require_protected_manifest=False))
    events = []
    reloaded = False
    enabled = False

    def runner(cmd, **kwargs):
        nonlocal reloaded, enabled
        events.append(cmd[1:])
        if cmd[1] == "daemon-reload":
            reloaded = True
        elif cmd[1:3] == ["enable", "--now"]:
            assert cmd[3] == names[1]
            enabled = True
        elif cmd[1] == "show":
            name = cmd[3]
            present = (units / name).exists() and reloaded
            return SimpleNamespace(
                returncode=0 if present else 1,
                stdout="\n".join((
                    "LoadState=" + ("loaded" if present else "not-found"),
                    "FragmentPath=" + (str(units / name) if present else ""),
                    "DropInPaths=",
                    "NeedDaemonReload=no",
                    "UnitFileState=" + ("enabled" if enabled and name == names[1] else ""),
                    "ActiveState=" + ("active" if enabled and name == names[1] else "inactive"),
                )))
        else:
            pytest.fail("unexpected systemd command")
        return SimpleNamespace(returncode=0, stdout="")

    return SimpleNamespace(root=root, units=units, names=names, manifest=manifest,
                           events=events, kwargs=dict(root=root, unit_dir=units,
                           token_file=_token_file(tmp_path), manifest_path=manifest,
                           uid=os.geteuid(), run=runner))


def test_observer_enable_only_installs_pinned_observer_and_starts_timer(observer_setup):
    from tools.github_status_reporter import enable_observer
    setup = observer_setup
    result = enable_observer("a" * 40, **setup.kwargs)
    assert result == "READY: GitHub observer timer enabled and active; delivery unverified"
    assert sorted(p.name for p in setup.units.iterdir()) == sorted(setup.names)
    for name in setup.names:
        assert (setup.units / name).read_bytes() == (setup.root / "deploy/systemd" / name).read_bytes()
    assert [e for e in setup.events if e[0] != "show"] == [
        ["daemon-reload"], ["enable", "--now", setup.names[1]]]
    # The explicit operation is idempotent; never overwrite existing units.
    assert enable_observer("a" * 40, **setup.kwargs) == result


@pytest.mark.parametrize("obstacle", ["token", "release", "untracked", "conflict", "symlink"])
def test_observer_enable_blocks_before_mutation(observer_setup, obstacle):
    from tools.github_status_reporter import enable_observer
    setup = observer_setup
    sha = "a" * 40
    unit = setup.units / setup.names[1]
    if obstacle == "token":
        setup.kwargs["token_file"].chmod(0o644)
    elif obstacle == "release":
        sha = "b" * 40
    elif obstacle == "untracked":
        manifest = json.loads(setup.manifest.read_text())
        del manifest["blobs"]["deploy/systemd/" + setup.names[1]]
        setup.manifest.write_text(json.dumps(manifest))
    elif obstacle == "conflict":
        unit.write_text("owner configuration")
    else:
        unit.symlink_to(setup.root / "deploy/systemd" / setup.names[1])
    before = list(setup.units.iterdir())
    assert enable_observer(sha, **setup.kwargs).startswith("BLOCKED:")
    assert list(setup.units.iterdir()) == before
    assert all(e[0] == "show" for e in setup.events)
    if obstacle == "conflict":
        assert unit.read_text() == "owner configuration"


def test_observer_enable_rejects_effective_dropin(observer_setup):
    from tools.github_status_reporter import enable_observer
    setup = observer_setup
    runner = setup.kwargs["run"]
    def with_dropin(cmd, **kwargs):
        result = runner(cmd, **kwargs)
        if cmd[1] == "show" and cmd[3] == setup.names[1]:
            result.stdout = result.stdout.replace("DropInPaths=", "DropInPaths=/etc/override.conf")
        return result
    setup.kwargs["run"] = with_dropin
    assert enable_observer("a" * 40, **setup.kwargs).startswith("BLOCKED:")
    assert not list(setup.units.iterdir())
    assert all(e[0] == "show" for e in setup.events)


def test_observer_enable_does_not_retry_unknown_activation(observer_setup):
    from tools.github_status_reporter import enable_observer
    setup = observer_setup
    runner = setup.kwargs["run"]
    def fail_enable(cmd, **kwargs):
        result = runner(cmd, **kwargs)
        if cmd[1] == "enable":
            raise TimeoutError("unknown outcome")
        return result
    setup.kwargs["run"] = fail_enable
    assert enable_observer("a" * 40, **setup.kwargs).startswith("BLOCKED:")
    assert [e for e in setup.events if e[0] != "show"] == [
        ["daemon-reload"], ["enable", "--now", setup.names[1]]]


@pytest.mark.parametrize("complete", [True, False])
def test_wedge_archive_watch_exact_pair_and_private_retry(tmp_path, complete):
    from tools.github_status_reporter import wedge_archive_watch, WEDGE_WATCH_CUTOFF_MS
    from mirror_scanner import empty_state, save_state, mirror_first_card_archive_id
    from mirror_levels.levels import line_level, LevelRegistry
    from signal_archive import record_original_signal
    from dataclasses import replace

    root = tmp_path / "evidence"
    archive = tmp_path / "archive"
    outbox = tmp_path / "outbox"
    outbox.mkdir(mode=0o700)
    symbol, tf = "SECRETUSDT", "1"
    t = WEDGE_WATCH_CUTOFF_MS
    start = t - t % 60000
    provenance = {"decision_index": 2, "parent_formation_id": "PRIVATE_FORMATION",
                  "formation_end_open_ms": start + 60000}
    level = line_level(symbol=symbol, timeframe=tf, pattern="Falling Wedge",
                       side="upper", first=(start, 10.0), second=(start+60000, 9.8),
                       confirmed_at_ms=start+180000, provenance=provenance)
    pair = line_level(symbol=symbol, timeframe=tf, pattern="Falling Wedge",
                      side="lower", first=(start, 8.0), second=(start+60000, 7.9),
                      confirmed_at_ms=start+180000, provenance=provenance)
    level = replace(level, provenance={**provenance, "chart_only_counterpart": pair.to_dict()})
    state = empty_state(symbol, tf)
    state["registry"] = LevelRegistry(levels={level.level_id: level}).to_dict()
    state["records"] = {level.level_id: {}}
    save_state(state, root)
    sid = mirror_first_card_archive_id(symbol, tf, level.level_id)
    bars = [{"open_time_ms": start+i*60000, "open": 9.0, "high": 11.0,
             "low": 7.0, "close": 9.0} for i in range(4)]
    boundaries = [{"boundary_id": lv.level_id, "kind": "ray",
                   "anchors": [{"bar_open_time_ms": a, "price": p} for a,p in lv.anchors]}
                  for lv in ((level, pair) if complete else (level,))]
    snapshot = {"schema_version": 1, "signal_id": sid, "symbol": symbol,
                "timeframe": tf, "bars": bars, "boundaries": boundaries}
    assert record_original_signal(sid, symbol=symbol, timeframe=tf,
                                  pattern="Falling Wedge", text="PRIVATE_TEXT",
                                  image_bytes=b"fake-private-png", directory=archive,
                                  geometry_snapshot=snapshot)
    event = {"event": "mirror_delivery", "kind": "breakout", "delivered": True,
             "test_mode": False, "chart_frozen": True, "recorded_at_ms": start+240000,
             "symbol": symbol, "timeframe": tf, "level_id": level.level_id}
    journal = root / "events.jsonl"
    journal.write_text(json.dumps({**event, "test_mode": True})+"\n"+json.dumps(event))
    kwargs = dict(token="not-a-real-token", state_dir=outbox, build_sha="a"*40,
                  now_ms=start+300000, root=root, archive_roots=(archive,))
    bodies = []
    wedge_archive_watch(**kwargs, post=lambda _,body: bodies.append(body))
    assert not bodies  # partial final line must not be treated as delivery
    with journal.open("a") as f:
        f.write("\n")
    def ambiguous(_token, body):
        bodies.append(body)
        raise TimeoutError("unknown POST outcome")
    with pytest.raises(TimeoutError):
        wedge_archive_watch(**kwargs, post=ambiguous)
    wedge_archive_watch(**kwargs, post=lambda _,body: bodies.append(body))
    assert len(bodies) == 2 and bodies[0] == bodies[1]
    assert ("ARCHIVE_MATCHED" if complete else "ARCHIVE_UNPROVEN") in bodies[0]
    for private in (symbol, sid, level.level_id, pair.level_id, "PRIVATE", "7.9", str(root)):
        assert private not in bodies[0]
    wedge_archive_watch(**kwargs, post=lambda *_: pytest.fail("one-shot receipt already sent"))
    assert state["registry"] == json.loads((root/"state"/f"{symbol}_{tf}.json").read_text())["registry"]


def test_wedge_watch_failure_does_not_break_existing_status(tmp_path):
    token = _token_file(tmp_path)
    outputs = []
    def fail(**kwargs):
        raise OSError("private archive unavailable")
    assert report_once(token_file=token, state_dir=tmp_path/"state",
                       fetch=lambda url: status_payload()[url],
                       post=lambda _,body: outputs.append(body), wedge_watch=fail,
                       now_ms=1_800_000_000_000) == 0
    assert len(outputs) == 1 and outputs[0].startswith("BYBITSCANNER_PUBLIC_STATUS_V1")
