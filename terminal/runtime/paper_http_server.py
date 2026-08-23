"""Minimal local HTTP runtime for PAPER Trading Workspace development."""

from __future__ import annotations

import json
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from terminal.api.models import (
    ClientActionId,
    CommandResult,
    CommandResultStatus,
    MarketCommandRequest,
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
        content_length = int(self.headers.get("Content-Length", ""))
        if content_length <= 0:
            raise ValueError("request body is required")
        payload = json.loads(
            self.rfile.read(content_length).decode("utf-8"),
            parse_float=Decimal,
        )
        if not isinstance(payload, dict) or set(payload) != MARKET_FIELDS:
            raise ValueError("invalid market request fields")
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
    runtime = PaperRuntime(Path("paper_runtime.sqlite3"))
    server = HTTPServer((HOST, PORT), PaperHttpHandler)
    server.runtime = runtime
    try:
        print(f"PAPER HTTP runtime listening on http://{HOST}:{PORT}")
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
