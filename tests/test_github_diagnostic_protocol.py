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
