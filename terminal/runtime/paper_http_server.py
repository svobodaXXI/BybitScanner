"""Minimal local HTTP runtime for PAPER Trading Workspace development."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from terminal.api.models import (
    ClientActionId,
    CommandResult,
    CommandResultStatus,
    FullCloseCommandRequest,
    LimitCommandRequest,
    MarketCommandRequest,
    PaperLimitCancelRequest,
    PaperLimitAmendRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
    to_primitive,
)
from terminal.domain.models import OrderSide
from terminal.runtime.paper_runtime import PaperRuntime


HOST = "127.0.0.1"
PORT = 8765
MARKET_FIELDS = {
    "client_action_id",
    "symbol",
    "side",
    "volume",
    "sizing_reference_price",
    "slippage_type",
    "slippage_value",
}
VOLUME_FIELDS = {"unit", "amount"}
FULL_CLOSE_FIELDS = {"client_action_id", "symbol"}
LIMIT_FIELDS = {
    "client_action_id", "symbol", "side", "volume", "sizing_reference_price",
    "limit_price", "time_in_force",
}
LIMIT_CANCEL_FIELDS = {"client_action_id", "symbol", "order_id"}
LIMIT_AMEND_FIELDS = {"client_action_id", "symbol", "order_id", "limit_price"}


class PaperHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            self._json_response(
                200,
                {
                    "ok": True,
                    "mode": "paper",
                },
            )
            return

        if parsed.path == "/api/paper-state":
            query = parse_qs(parsed.query)
            symbols = query.get("symbol", [])
            if len(symbols) != 1:
                self._json_response(
                    400,
                    {
                        "ok": False,
                        "error": "symbol_required",
                    },
                )
                return

            try:
                state = self.server.runtime.paper_state(symbols[0])
            except Exception:
                self._json_response(
                    400,
                    {
                        "ok": False,
                        "error": "invalid_paper_state_request",
                    },
                )
                return

            self._json_response(
                200,
                {
                    "ok": True,
                    **state,
                },
            )
            return

        self._json_response(
            404,
            {
                "ok": False,
                "error": "not_found",
            },
        )

    def do_POST(self) -> None:
        if self.path == "/api/limit/amend":
            try:
                payload = self._payload(LIMIT_AMEND_FIELDS)
                result = self.server.runtime.amend_limit(PaperLimitAmendRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    payload["order_id"], _decimal(payload["limit_price"]),
                ))
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(result))
            return

        if self.path == "/api/limit":
            try:
                payload = self._payload(LIMIT_FIELDS)
                volume = payload["volume"]
                if not isinstance(volume, dict) or set(volume) != VOLUME_FIELDS:
                    raise ValueError("invalid volume fields")
                request = LimitCommandRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    OrderSide(payload["side"]),
                    VolumeRequest(VolumeUnit(volume["unit"]), _decimal(volume["amount"])),
                    _decimal(payload["sizing_reference_price"]),
                    _decimal(payload["limit_price"]), TimeInForce(payload["time_in_force"]),
                )
                result = self.server.runtime.create_limit(request)
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(result))
            return

        if self.path == "/api/limit/cancel":
            try:
                payload = self._payload(LIMIT_CANCEL_FIELDS)
                result = self.server.runtime.cancel_limit(PaperLimitCancelRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    payload["order_id"],
                ))
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(result))
            return

        if self.path == "/api/full-close":
            try:
                payload = self._payload(FULL_CLOSE_FIELDS)
                request = FullCloseCommandRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"]
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(self.server.runtime.api.full_close(request)))
            return

        if self.path != "/api/market":
            self._json_response(404, {"ok": False, "error": "not_found"})
            return

        try:
            request = self._market_request()
        except Exception:
            self._json_response(400, to_primitive(_validation_error()))
            return

        result = self.server.runtime.api.market(request)
        self._json_response(200, to_primitive(result))

    def _market_request(self) -> MarketCommandRequest:
        payload = self._payload(MARKET_FIELDS)
        volume = payload["volume"]
        if not isinstance(volume, dict) or set(volume) != VOLUME_FIELDS:
            raise ValueError("invalid volume fields")
        return MarketCommandRequest(
            ClientActionId(payload["client_action_id"]),
            payload["symbol"],
            OrderSide(payload["side"]),
            VolumeRequest(VolumeUnit(volume["unit"]), _decimal(volume["amount"])),
            _decimal(payload["sizing_reference_price"]),
            payload["slippage_type"],
            _decimal(payload["slippage_value"]),
        )

    def _payload(self, fields: set[str]) -> dict:
        content_length = int(self.headers.get("Content-Length", ""))
        if content_length <= 0:
            raise ValueError("request body is required")
        payload = json.loads(
            self.rfile.read(content_length).decode("utf-8"),
            parse_float=Decimal,
        )
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError("invalid request fields")
        return payload

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    database_path = Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))
    port = int(os.environ.get("BYBITSCANNER_PAPER_PORT", str(PORT)))
    runtime = PaperRuntime(database_path)
    server = HTTPServer((HOST, port), PaperHttpHandler)
    server.runtime = runtime
    try:
        print(f"PAPER HTTP runtime listening on http://{HOST}:{port}")
        server.serve_forever()
    finally:
        server.server_close()
        runtime.close()


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("decimal value is invalid")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("decimal value must be finite")
    return result


def _validation_error() -> CommandResult:
    return CommandResult(
        "",
        CommandResultStatus.VALIDATION_ERROR,
        "validation_error",
        "command request is invalid",
    )


if __name__ == "__main__":
    main()
