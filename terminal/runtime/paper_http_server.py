"""Minimal local HTTP runtime for PAPER Trading Workspace development."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "127.0.0.1"
PORT = 8765


class PaperHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._json_response(
                200,
                {
                    "ok": True,
                    "mode": "paper",
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
    server = ThreadingHTTPServer((HOST, PORT), PaperHttpHandler)
    print(f"PAPER HTTP runtime listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()