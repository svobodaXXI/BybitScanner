"""Deterministic end-to-end doctor for the running PAPER Workspace backend."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlencode, urlparse, urlunparse

import websocket

from terminal.market_data.workspace_errors import WorkspaceErrorDetails
from terminal.runtime.paper_http_server import SUPPORTED_KLINE_INTERVALS


DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class DoctorFailure(RuntimeError):
    def __init__(self, result: WorkspaceErrorDetails) -> None:
        super().__init__(result.message)
        self.result = result


class WorkspaceDoctorClient:
    def __init__(self, base_url: str, request_id: str, *, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_id = request_id
        self.timeout = timeout

    def get_json(self, path: str) -> dict:
        return self._json_request(path)

    def post_json(self, path: str, payload: dict[str, object]) -> dict:
        return self._json_request(
            path, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )

    def open_workspace_stream(self, symbol: str, interval: str) -> dict:
        parsed = urlparse(self.base_url)
        stream_url = urlunparse((
            "wss" if parsed.scheme == "https" else "ws",
            parsed.netloc,
            "/api/workspace/stream",
            "",
            urlencode({"symbol": symbol, "interval": interval}),
            "",
        ))
        try:
            connection = websocket.create_connection(
                stream_url, timeout=self.timeout,
                header=[f"X-Request-ID: {self.request_id}"],
            )
            try:
                payload = json.loads(connection.recv())
            finally:
                connection.close()
        except Exception as exc:
            raise self._upstream_failure("workspace_stream", exc) from exc
        if not isinstance(payload, dict):
            raise self._upstream_failure("workspace_stream", ValueError("invalid stream payload"))
        return payload

    def _json_request(self, path: str, data: bytes | None = None) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": self.request_id,
            },
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                payload = json.load(exc)
            except (TypeError, ValueError):
                raise self._upstream_failure("http", exc) from exc
            diagnostic = payload.get("workspace_error") if isinstance(payload, dict) else None
            if isinstance(diagnostic, dict):
                raise DoctorFailure(_details_from_dict(diagnostic)) from exc
            raise self._upstream_failure("http", exc) from exc
        except (OSError, ValueError) as exc:
            raise self._upstream_failure("http", exc) from exc
        if not isinstance(payload, dict):
            raise self._upstream_failure("http", ValueError("invalid JSON payload"))
        return payload

    def _upstream_failure(self, stage: str, cause: Exception) -> DoctorFailure:
        return DoctorFailure(WorkspaceErrorDetails(
            code="upstream_market_data_failure",
            stage=stage,
            requested_symbol=None,
            active_symbol=None,
            retryable=True,
            request_id=self.request_id,
            message=f"Required Workspace backend component is unavailable: {type(cause).__name__}",
        ))


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: str
    lines: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "PASS" else 1

    def render(self) -> str:
        return "\n".join((f"STATUS {self.status}", *self.lines))


def diagnose(
    symbol: str, interval: str, client: WorkspaceDoctorClient,
) -> DoctorReport:
    normalized = symbol.strip().upper()
    lines: list[str] = []
    current_stage = "INPUT"
    try:
        if not normalized or interval not in SUPPORTED_KLINE_INTERVALS:
            raise DoctorFailure(WorkspaceErrorDetails(
                code="invalid_doctor_request", stage="input_validation",
                requested_symbol=normalized or None, active_symbol=None,
                retryable=False, request_id=client.request_id,
                message="Symbol or interval is invalid",
            ))

        current_stage = "INSTRUMENT"
        instruments = client.get_json("/api/instruments").get("instruments", [])
        instrument = next(
            (item for item in instruments if item.get("symbol") == normalized), None,
        )
        if instrument is None:
            raise DoctorFailure(WorkspaceErrorDetails(
                code="unsupported_instrument", stage="instrument_lookup",
                requested_symbol=normalized, active_symbol=None, retryable=False,
                request_id=client.request_id,
                message=f"Unsupported Workspace instrument: {normalized}",
            ))
        lines.append(f"INSTRUMENT PASS symbol={normalized}")

        current_stage = "SWITCH"
        switched = client.post_json("/api/workspace/symbol", {"symbol": normalized})
        generation = int(switched["generation"])
        active_symbol = str(switched["symbol"])
        if active_symbol != normalized or generation <= 0:
            raise ValueError("invalid activation acknowledgement")
        lines.append(f"SWITCH PASS active_symbol={active_symbol} generation={generation}")

        current_stage = "READINESS"
        state = client.get_json("/api/workspace/state")["workspace"]
        readiness = state["readiness"]
        if not readiness.get("ready"):
            last_error = state.get("last_error")
            if isinstance(last_error, dict):
                raise DoctorFailure(_details_from_dict(last_error, client.request_id))
            raise DoctorFailure(WorkspaceErrorDetails(
                code="candidate_not_ready", stage="candidate_readiness",
                requested_symbol=normalized, active_symbol=state.get("active_symbol"),
                retryable=True, request_id=client.request_id,
                message="Active Workspace is not composite-ready",
            ))
        lines.append("READINESS PASS book=true trades=true candles=true")

        current_stage = "STREAM"
        snapshot = client.open_workspace_stream(normalized, interval)
        if (
            snapshot.get("kind") != "workspace_snapshot"
            or snapshot.get("state") != "READY"
            or snapshot.get("symbol") != normalized
            or int(snapshot.get("workspace_generation", 0)) != generation
        ):
            raise DoctorFailure(WorkspaceErrorDetails(
                code="upstream_market_data_failure", stage="workspace_stream",
                requested_symbol=normalized, active_symbol=active_symbol,
                retryable=True, request_id=client.request_id,
                message="Workspace stream did not provide a ready active-generation snapshot",
            ))
        lines.append(f"STREAM PASS kind=workspace_snapshot generation={generation}")

        current_stage = "STATE"
        final_state = client.get_json("/api/workspace/state")["workspace"]
        if (
            final_state.get("active_symbol") != normalized
            or int(final_state.get("active_generation", 0)) != generation
        ):
            raise ValueError("diagnostic state does not match activation acknowledgement")
        lines.append(
            f"STATE PASS switch_state={final_state['switch_state']} "
            f"active_symbol={normalized} generation={generation}"
        )
        return DoctorReport("PASS", tuple(lines))
    except DoctorFailure as exc:
        return DoctorReport("FAIL", (*lines, f"{current_stage} FAIL", _format_error(exc.result)))
    except (KeyError, TypeError, ValueError) as exc:
        error = WorkspaceErrorDetails(
            code="upstream_market_data_failure", stage=current_stage.lower(),
            requested_symbol=normalized or None, active_symbol=None,
            retryable=True, request_id=client.request_id,
            message=f"Invalid Workspace backend response: {type(exc).__name__}",
        )
        return DoctorReport("FAIL", (*lines, f"{current_stage} FAIL", _format_error(error)))


def _details_from_dict(
    payload: dict[str, object], fallback_request_id: str | None = None,
) -> WorkspaceErrorDetails:
    return WorkspaceErrorDetails(
        code=str(payload.get("code") or "workspace_failure"),
        stage=str(payload.get("stage") or "workspace"),
        requested_symbol=_optional_text(payload.get("requested_symbol")),
        active_symbol=_optional_text(payload.get("active_symbol")),
        retryable=bool(payload.get("retryable")),
        request_id=_optional_text(payload.get("request_id")) or fallback_request_id,
        message=str(payload.get("message") or "Workspace diagnostic failure"),
    )


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _format_error(error: WorkspaceErrorDetails) -> str:
    fields = (
        ("code", error.code), ("stage", error.stage),
        ("requested_symbol", error.requested_symbol),
        ("active_symbol", error.active_symbol),
        ("retryable", str(error.retryable).lower()),
        ("request_id", error.request_id), ("message", error.message),
    )
    return "ERROR " + " ".join(f"{key}={json.dumps(value)}" for key, value in fields)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args(argv)
    symbol = args.symbol.strip().upper()
    request_id = f"workspace-doctor:{symbol or 'invalid'}:{args.interval}"
    report = diagnose(
        symbol, args.interval,
        WorkspaceDoctorClient(args.base_url, request_id),
    )
    print(report.render())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
