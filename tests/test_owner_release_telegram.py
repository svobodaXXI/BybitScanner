"""Offline full proposal -> Telegram proof -> one-use canonical dispatch."""
from copy import deepcopy
import hashlib
import json

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa
import pytest

from tools import owner_release_telegram as approval
from tools import owner_release_telegram_runtime as runtime
from tools import owner_update_grant as grants
from tools import telegram_release_inbox as relay

NOW = 1800000000
OWNER, BOT = "12345", "55555"
AUDIENCE = "a" * 32
PREVIOUS, TARGET, RID = "b" * 40, "c" * 40, "d" * 32


@pytest.fixture
def context(tmp_path):
    gateway, signer, issuer, responder = [ECC.generate(curve="Ed25519") for _ in range(4)]
    value = dict(version=1, operation="update-and-start", owner_request_id=RID,
                 expected_installed_sha=PREVIOUS, target_sha=TARGET,
                 issued_at=NOW, expires_at=NOW + 300)
    state = {"pending": None}
    now = [NOW]
    installed = [PREVIOUS]
    calls, sent = [], []
    inbox = {}
    ledgers = {}
    for name in ("prompts", "grants"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        ledgers[name] = grants.GrantLedger(path)
        ledgers[name].initialize()

    def save(value):
        state.clear()
        state.update(deepcopy(value))

    def send(text, keyboard):
        sent.append((text, keyboard))
        return 123

    def submit(*args, **kwargs):
        calls.append((args, kwargs))
        return 0

    settings = dict(load=lambda: deepcopy(state), save=save,
                    prompts=ledgers["prompts"], ledger=ledgers["grants"],
                    fetch=lambda: deepcopy(value), send=send,
                    receive=lambda nonce: inbox.get(nonce), installed_sha=lambda: installed[0],
                    callback_public=gateway.public_key(), owner_id=OWNER, bot_id=BOT,
                    approval_key=signer, diagnostic_issuer_public=issuer.public_key(),
                    diagnostic_responder_public=responder.public_key(), audience=AUDIENCE,
                    clock=lambda: now[0], submit=submit)

    def click(decision="yes", **changes):
        challenge = state["pending"]
        payload = dict(version=1, nonce=challenge["nonce"], decision=decision,
                       owner_id=OWNER, bot_id=BOT, message_id=challenge["message_id"],
                       text_sha256=challenge["text_sha256"], observed_at=now[0], update_id=7)
        payload.update(changes)
        signature = eddsa.new(gateway, "rfc8032").sign(
            approval.DOMAIN + grants._canonical(payload))
        wire = grants._canonical(dict(payload=payload, signature=signature.hex()))
        inbox[challenge["nonce"]] = wire
        return wire

    return settings, state, now, installed, calls, sent, click, inbox, value


def test_flow_exact_visible_prompt_and_one_time_update_and_start(context):
    settings, state, _, _, calls, sent, click, _, value = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    assert not calls
    prompt, keys = sent[0]
    assert PREVIOUS in prompt and TARGET in prompt and "LIVE запрещён" in prompt
    assert "Обновить и запустить PAPER" in prompt
    challenge = deepcopy(state["pending"])
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == challenge["text_sha256"]
    assert keys["inline_keyboard"][0][0]["callback_data"] == "owner-release:yes:" + challenge["nonce"]
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    assert len(sent) == 1
    click()
    assert runtime.cycle(**settings) == "SUBMITTED"
    assert state == {"pending": None}
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:3] == ("update-and-start", TARGET, RID)
    assert kwargs == {"expected_installed_sha": PREVIOUS}
    assert runtime.cycle(**settings) == "ALREADY_SEEN"
    assert len(calls) == 1 and len(sent) == 1


def test_decline_does_not_dispatch_and_will_not_reprompt(context):
    settings, state, _, _, calls, sent, click, _, _ = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    click("no")
    assert runtime.cycle(**settings) == "DECLINED"
    assert state["pending"] is None
    assert runtime.cycle(**settings) == "ALREADY_SEEN"
    assert not calls and len(sent) == 1


@pytest.mark.parametrize("changes", [
    {"owner_id": "12346"}, {"bot_id": "55556"}, {"message_id": 124},
    {"nonce": "f" * 32}, {"text_sha256": "f" * 64},
    {"observed_at": NOW - 121}, {"observed_at": NOW + 1},
    {"decision": "start"},
])
def test_wrong_callback_never_authorizes(context, changes):
    settings, state, _, _, calls, _, click, _, _ = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    click(**changes)
    with pytest.raises(ValueError, match="confirmation unproven"):
        runtime.cycle(**settings)
    assert state["pending"] is not None and not calls


def test_gateway_bearer_or_untrusted_relay_cannot_forge_confirmation(context):
    settings, state, _, _, calls, _, click, inbox, _ = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    raw = json.loads(click("no"))
    raw["payload"]["decision"] = "yes"
    inbox[state["pending"]["nonce"]] = grants._canonical(raw)
    with pytest.raises(ValueError):
        runtime.cycle(**settings)
    assert not calls


def test_expired_or_changed_release_never_dispatches(context):
    settings, state, now, installed, calls, _, click, _, _ = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    click()
    installed[0] = "f" * 40
    with pytest.raises(ValueError, match="installed release changed"):
        runtime.cycle(**settings)
    now[0] += 301
    assert runtime.cycle(**settings) == "EXPIRED"
    assert state["pending"] is None and not calls


def test_lost_send_receipt_never_reprompts_or_accepts_unknown_message(context):
    settings, state, now, _, calls, sent, _, _, _ = context
    def lost(*args):
        sent.append(args)
        raise OSError("response lost")
    with pytest.raises(OSError):
        runtime.cycle(**dict(settings, send=lost))
    assert state["pending"]["message_id"] is None
    assert runtime.cycle(**settings) == "PROMPT_UNPROVEN"
    assert len(sent) == 1
    now[0] += 301
    assert runtime.cycle(**settings) == "EXPIRED"
    assert not calls


def test_lost_submit_receipt_never_replays(context):
    settings, state, _, _, calls, sent, click, _, _ = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    click()
    def lost(*args, **kwargs):
        calls.append(args)
        raise OSError("response lost")
    with pytest.raises(OSError):
        runtime.cycle(**dict(settings, submit=lost))
    assert state["pending"] is None
    assert runtime.cycle(**settings) == "ALREADY_SEEN"
    assert len(calls) == 1 and len(sent) == 1


def test_ordinary_poller_only_carries_bounded_receipt(tmp_path, context):
    settings, state, _, _, calls, _, click, _, _ = context
    assert runtime.cycle(**settings) == "AWAITING_OWNER"
    signed = json.loads(click())
    nonce = state["pending"]["nonce"]
    inbox = tmp_path / "inbox"
    inbox.mkdir(mode=0o700)
    update = dict(callback_query={"data": "owner-release:yes:" + nonce},
                  owner_release_receipt=signed)
    assert relay.relay(update, inbox=inbox) is True
    assert (inbox / ("receipt-" + nonce + ".json")).read_bytes() == grants._canonical(signed)
    assert relay.relay({"callback_query": {"data": "robot:cmd:start"}}, inbox=inbox) is None
    assert relay.relay({"callback_query": {"data": "owner-release:yes:" + nonce}}, inbox=inbox) is False
    assert not calls


def test_read_only_activation_preflight_checks_actual_unit_bytes(tmp_path):
    import os
    from pathlib import Path
    root = tmp_path / "release"
    units = tmp_path / "systemd"
    root.mkdir()
    units.mkdir()
    blobs = {}
    for name in runtime.OWNER_UNIT_NAMES:
        rel = "deploy/systemd/" + name
        tracked = root / rel
        tracked.parent.mkdir(parents=True, exist_ok=True)
        tracked.write_bytes(("unit=" + name).encode())
        installed = units / name
        installed.write_bytes(tracked.read_bytes())
        blobs[rel] = grants.hashlib.sha1(
            b"blob " + str(len(tracked.read_bytes())).encode() + b"\0"
            + tracked.read_bytes()).hexdigest()
    manifest = dict(build_sha="a" * 40,
                    blobs={**blobs, "tools/vps_release_identity.py": "b"*40,
                           "terminal/runtime/paper_http_server.py": "c"*40})
    file = tmp_path / "manifest.json"
    file.write_text(json.dumps(manifest))
    uid = os.geteuid()
    before = {str(p):p.read_bytes() for p in [file, *units.iterdir()]}
    runtime._check_units(root, file, units, uid=uid)
    assert before == {str(p):p.read_bytes() for p in [file, *units.iterdir()]}
    (units / runtime.OWNER_UNIT_NAMES[0]).write_bytes(b"changed unit")
    with pytest.raises(ValueError, match="not pinned"):
        runtime._check_units(root, file, units, uid=uid)
    (units / runtime.OWNER_UNIT_NAMES[0]).unlink()
    with pytest.raises(Exception):
        runtime._check_units(root, file, units, uid=uid)


def test_preflight_refuses_missing_or_damaged_one_use_ledger(tmp_path):
    import os
    path = tmp_path / "grant-ledger"
    path.mkdir(mode=0o700)
    ledger = grants.GrantLedger(path)
    ledger.initialize()
    runtime._check_ledger(path, uid=os.geteuid())
    marker = path / "initialized"
    marker.chmod(0o644)
    with pytest.raises(ValueError, match="not initialized"):
        runtime._check_ledger(path, uid=os.geteuid())
    marker.chmod(0o600)
    marker.write_bytes(b"forged")
    with pytest.raises(ValueError, match="not initialized"):
        runtime._check_ledger(path, uid=os.geteuid())
    marker.unlink()
    with pytest.raises(OSError):
        runtime._check_ledger(path, uid=os.geteuid())


def test_read_only_preflight_never_enters_live_cycle(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "run_once", lambda: pytest.fail("live cycle invoked"))
    monkeypatch.setattr(runtime, "preflight", lambda: "HOST_PRECHECK_OK_DISABLED")
    assert runtime.main(["--preflight"]) == 0
    assert "HOST_PRECHECK_OK_DISABLED" in capsys.readouterr().out
    monkeypatch.setattr(runtime, "preflight", lambda: (_ for _ in ()).throw(ValueError("PRIVATE")))
    assert runtime.main(["--preflight"]) == 2
    printed = capsys.readouterr().out
    assert "OWNER_RELEASE_PREFLIGHT=BLOCKED" in printed
    assert "PRIVATE" not in printed
