"""Trusted content-writer -> signed observe request. Never accept issue text as input."""
from pathlib import Path
import json
import os
import re
import time
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError

from Crypto.Signature import eddsa
from tools import github_diagnostic_protocol as protocol
from tools.github_diagnostic_transport import REQUEST_MARKER
from tools.github_status_reporter import ISSUE_URL

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PUBLIC = Path(".github/diagnostic-public.json")
REQUEST = Path(".github/diagnostic-request.json")


def _object(path):
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("oversize issuer input")
    return json.loads(raw, object_pairs_hook=protocol._unique_pairs)


def make_request(public, request, seed, now):
    if (type(public) is not dict
            or set(public) != {"audience", "issuer_public", "responder_public"}
            or any(type(public[k]) is not str or not HEX64.fullmatch(public[k])
                   for k in ("issuer_public", "responder_public"))
            or public["issuer_public"] == public["responder_public"]
            or type(seed) is not str or not HEX64.fullmatch(seed)
            or type(request) is not dict
            or set(request) != {"request_id", "issued_at", "expires_at"}):
        raise ValueError("invalid issuer configuration")
    key = eddsa.import_private_key(bytes.fromhex(seed))
    if key.public_key().export_key(format="raw").hex() != public["issuer_public"]:
        raise ValueError("issuer key pin mismatch")
    payload = dict(request, version=1, operation="observe", audience=public["audience"])
    return protocol.sign_request(payload, issuer_key=key, audience=public["audience"], now=now)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("unexpected GitHub redirect")


def publish(wire, token):
    if type(token) is not str or not 30 <= len(token) <= 256 or any(c.isspace() for c in token):
        raise ValueError("credential missing or malformed")
    body = REQUEST_MARKER + wire.decode("ascii")
    request = Request(ISSUE_URL, data=json.dumps({"body": body}).encode("utf-8"),
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/vnd.github+json",
                               "User-Agent": "bybitscanner-diagnostic-issuer",
                               "Content-Type": "application/json",
                               "X-GitHub-Api-Version": "2022-11-28"}, method="POST")
    with build_opener(_NoRedirect()).open(request, timeout=10) as response:
        raw = response.read(65537)
        if response.status != 201 or len(raw) > 65536:
            raise ValueError("publication not proven")
        ack = json.loads(raw)
        if type(ack.get("id")) is not int or ack["id"] <= 0 or ack.get("body") != body:
            raise ValueError("publication acknowledgement mismatch")


def main():
    stage = "ROUTE"
    try:
        if (os.environ.get("GITHUB_REPOSITORY") != "svobodaXXI/BybitScanner"
                or os.environ.get("GITHUB_REF") != "refs/heads/diagnostic-issuer"
                or os.environ.get("GITHUB_EVENT_NAME") != "push"):
            raise ValueError("untrusted issuer route")
        stage = "INPUT"
        public, request = _object(PUBLIC), _object(REQUEST)
        stage = "SEED_FORMAT"
        seed = os.environ.get("DIAGNOSTIC_ISSUER_SEED", "")
        if not HEX64.fullmatch(seed):
            raise ValueError("invalid seed")
        stage = "KEY_PIN"
        key = eddsa.import_private_key(bytes.fromhex(seed))
        if key.public_key().export_key(format="raw").hex() != public.get("issuer_public"):
            raise ValueError("issuer key mismatch")
        stage = "REQUEST_VALIDATION"
        wire = make_request(public, request, seed, int(time.time()))
        stage = "PUBLISH"
        publish(wire, os.environ["DIAGNOSTIC_GITHUB_TOKEN"])
        print("SIGNED_OBSERVATION_REQUEST_PUBLISHED")
        return 0
    except HTTPError as exc:
        # Numeric HTTP status only. Never log headers, body, URL or exceptions.
        code = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else 0
        print("SIGNED_OBSERVATION_REQUEST_BLOCKED stage=" + stage + " http=" + str(code))
        return 2
    except Exception:
        print("SIGNED_OBSERVATION_REQUEST_BLOCKED stage=" + stage)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
