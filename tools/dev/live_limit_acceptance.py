"""Local operator CLI for durable LIVE Limit acceptance administration."""

from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_BACKEND = "http://127.0.0.1:8765"
TOKEN_ENV = "BYBITSCANNER_OPERATOR_TOKEN"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="Show non-secret runtime and session diagnostics")

    arm = commands.add_parser("arm", help="Create one explicitly authorized acceptance session")
    arm.add_argument("--acceptance-session-id", required=True)
    arm.add_argument("--account-id", required=True)
    arm.add_argument("--environment", required=True)
    arm.add_argument("--symbol", required=True)
    arm.add_argument("--capability", required=True)
    arm.add_argument("--max-create-count", required=True, type=int)
    arm.add_argument("--aggregate-notional-ceiling", required=True)
    arm.add_argument("--per-order-ceiling", required=True)
    arm.add_argument("--expires-at-ms", required=True, type=int)
    arm.add_argument("--operator-authorization-reference", required=True)
    arm.add_argument("--authorized-build-sha", required=True)
    arm.add_argument("--authorized-database-identity", required=True)
    arm.add_argument("--authorized-session-generation", required=True, type=int)

    revoke = commands.add_parser("revoke", help="Durably revoke an ARMED session")
    revoke.add_argument("--acceptance-session-id", required=True)
    revoke.add_argument("--account-id", required=True)
    revoke.add_argument("--environment", required=True)
    revoke.add_argument("--symbol", required=True)
    revoke.add_argument("--capability", required=True)
    return parser


def _request(backend: str, path: str, token: str, payload: dict | None = None) -> dict:
    parsed = urlparse(backend)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("operator backend must be a local HTTP endpoint")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload else None
    request = Request(
        backend.rstrip("/") + path, data=body,
        headers={
            "X-BybitScanner-Operator-Token": token,
            **({"Content-Type": "application/json"} if body else {}),
        },
        method="POST" if body else "GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = json.loads(exc.read().decode("utf-8"))
        raise RuntimeError(detail.get("error", "operator request rejected")) from exc
    except (URLError, OSError, ValueError) as exc:
        raise RuntimeError("local operator backend is unavailable") from exc


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(f"{TOKEN_ENV} must be explicitly configured for backend and CLI")
    if args.command == "inspect":
        result = _request(args.backend, "/api/operator/live-limit-acceptance", token)
    elif args.command == "arm":
        result = _request(args.backend, "/api/operator/live-limit-acceptance/arm", token, {
            "acceptance_session_id": args.acceptance_session_id,
            "account_id": args.account_id,
            "environment": args.environment,
            "symbol": args.symbol,
            "capability": args.capability,
            "max_create_count": args.max_create_count,
            "aggregate_notional_ceiling": args.aggregate_notional_ceiling,
            "per_order_ceiling": args.per_order_ceiling,
            "expires_at_ms": args.expires_at_ms,
            "operator_authorization_reference": args.operator_authorization_reference,
            "authorized_build_sha": args.authorized_build_sha,
            "authorized_database_identity": args.authorized_database_identity,
            "authorized_session_generation": args.authorized_session_generation,
        })
    else:
        result = _request(args.backend, "/api/operator/live-limit-acceptance/revoke", token, {
            "acceptance_session_id": args.acceptance_session_id,
            "account_id": args.account_id,
            "environment": args.environment,
            "symbol": args.symbol,
            "capability": args.capability,
        })
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
