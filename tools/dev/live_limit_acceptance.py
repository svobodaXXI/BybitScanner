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
MUTATION_GATE_KEYS = (
    "live_mainnet_authorized",
    "live_limit_mutations_enabled",
    "live_market_mutations_enabled",
    "live_parity_mutations_enabled",
)


def _add_arm_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--acceptance-session-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--max-create-count", required=True, type=int)
    parser.add_argument("--aggregate-notional-ceiling", required=True)
    parser.add_argument("--per-order-ceiling", required=True)
    parser.add_argument("--expires-at-ms", required=True, type=int)
    parser.add_argument("--operator-authorization-reference", required=True)
    parser.add_argument("--authorized-build-sha", required=True)
    parser.add_argument("--authorized-database-identity", required=True)
    parser.add_argument("--authorized-session-generation", required=True, type=int)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="Show non-secret runtime and session diagnostics")

    arm = commands.add_parser("arm", help="Create one explicitly authorized acceptance session")
    _add_arm_arguments(arm)

    rehearse = commands.add_parser(
        "rehearse", help="Safely inspect, validate, diagnose and revoke with all LIVE gates off",
    )
    _add_arm_arguments(rehearse)

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


def _arm_payload(args: argparse.Namespace) -> dict:
    return {
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
    }


def _revoke_payload(args: argparse.Namespace) -> dict:
    return {
        "acceptance_session_id": args.acceptance_session_id,
        "account_id": args.account_id,
        "environment": args.environment,
        "symbol": args.symbol,
        "capability": args.capability,
    }


def _require_rehearsal_safe(diagnostics: dict) -> None:
    gates = diagnostics.get("live_gates")
    capabilities = diagnostics.get("live_capabilities")
    if not isinstance(gates, dict) or any(gates.get(key) is not False for key in MUTATION_GATE_KEYS):
        raise RuntimeError("rehearsal requires every LIVE mutation gate to be explicitly off")
    if not isinstance(capabilities, dict) or any(capabilities.get(key) is not False for key in ("market", "limit", "parity")):
        raise RuntimeError("rehearsal requires every LIVE capability to be inactive")


def _rehearse(args: argparse.Namespace, token: str, requester=_request) -> dict:
    stages: list[str] = []
    arm_attempted = False
    try:
        before = requester(args.backend, "/api/operator/live-limit-acceptance", token)
        _require_rehearsal_safe(before)
        stages.append("INSPECTED_GATES_OFF")
        arm_attempted = True
        requester(
            args.backend, "/api/operator/live-limit-acceptance/arm", token,
            _arm_payload(args),
        )
        stages.append("ARM_REQUEST_VALIDATED")
        active = requester(args.backend, "/api/operator/live-limit-acceptance", token)
        _require_rehearsal_safe(active)
        current = active.get("current_acceptance_session")
        if not isinstance(current, dict) or current.get("acceptance_session_id") != args.acceptance_session_id or current.get("state") != "ARMED":
            raise RuntimeError("armed acceptance session is not authoritative in diagnostics")
        if current.get("authority_matches_runtime") is not True:
            raise RuntimeError("armed acceptance session authority does not match runtime")
        stages.append("ARMED_DIAGNOSTICS_CONFIRMED")
        requester(
            args.backend, "/api/operator/live-limit-acceptance/revoke", token,
            _revoke_payload(args),
        )
        arm_attempted = False
        stages.append("REVOKED")
        final = requester(args.backend, "/api/operator/live-limit-acceptance", token)
        _require_rehearsal_safe(final)
        sessions = final.get("acceptance_sessions")
        if not isinstance(sessions, (list, tuple)) or not any(
            isinstance(item, dict)
            and item.get("acceptance_session_id") == args.acceptance_session_id
            and item.get("state") == "REVOKED"
            for item in sessions
        ):
            raise RuntimeError("revoked acceptance session is not authoritative in diagnostics")
        stages.append("FINAL_DIAGNOSTICS_CONFIRMED")
        return {
            "status": "PASS",
            "workflow": stages,
            "live_gates": "OFF",
            "exchange_mutation": "NOT_REQUESTED",
            "acceptance_session_id": args.acceptance_session_id,
        }
    except Exception as exc:
        if arm_attempted:
            try:
                requester(
                    args.backend, "/api/operator/live-limit-acceptance/revoke", token,
                    _revoke_payload(args),
                )
            except Exception as cleanup_exc:
                raise RuntimeError(
                    f"rehearsal failed: {exc}; revoke cleanup failed: {cleanup_exc}"
                ) from cleanup_exc
        raise


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(f"{TOKEN_ENV} must be explicitly configured for backend and CLI")
    if args.command == "inspect":
        result = _request(args.backend, "/api/operator/live-limit-acceptance", token)
    elif args.command == "arm":
        result = _request(
            args.backend, "/api/operator/live-limit-acceptance/arm", token,
            _arm_payload(args),
        )
    elif args.command == "rehearse":
        result = _rehearse(args, token)
    else:
        result = _request(
            args.backend, "/api/operator/live-limit-acceptance/revoke", token,
            _revoke_payload(args),
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
