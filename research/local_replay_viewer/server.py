"""Local-only research viewer: loopback HTTP, public Bybit klines, no trading.

Run from Windows via START_LOCAL.cmd in the extracted build package.
The only remote request is a public Bybit /v5/market/kline GET with no credentials.
This service never imports Robot, PAPER, admission, STOP/TAKE or private API.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import sys
from typing import Callable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser

HERE = Path(__file__).resolve().parent
# Works both in GitHub source tree and in the packaged Windows zip.
ROOT = HERE if (HERE / "research").is_dir() else HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.export_historical_replay import (
    build_market_only_document, parse_date_utc, SYMBOL_RE,
)
from research.historical_candle_feed import FIVE_MINUTES_MS

MAX_LOCAL_BARS = 2016  # 7 days, 3+ paginated Bybit requests
BYBIT_PUBLIC_KLINE = "https://api.bybit.com/v5/market/kline"
STATIC_DIR = HERE / "dist"
MAX_RESPONSE_BYTES = 2_000_000


def fetch_public_klines(symbol: str, interval: str, limit: int, *, end_ms: int):
    """Public read-only exchange adapter; deliberately no signed/private APIs."""
    if not SYMBOL_RE.fullmatch(symbol) or interval != "5":
        raise ValueError("invalid local historical market query")
    if not 1 <= limit <= 1000 or end_ms < 0:
        raise ValueError("invalid public history pagination")
    query = urlencode({
        "category": "linear", "symbol": symbol, "interval": "5",
        "limit": limit, "end": end_ms,
    })
    request = Request(
        BYBIT_PUBLIC_KLINE + "?" + query,
        headers={"User-Agent": "BybitScanner-Local-Research-Replay/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urlopen(request, timeout=12) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("unexpectedly large public market response")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise ValueError("Bybit public historical candle endpoint rejected the request")
    result = payload.get("result")
    rows = result.get("list") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Bybit returned an invalid history payload")
    normalized = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            raise ValueError("Bybit returned an invalid kline row")
        normalized.append({
            "time": row[0], "open": row[1], "high": row[2],
            "low": row[3], "close": row[4], "volume": row[5],
        })
    return normalized


def load_public_history(
    *, symbol: str, start: str, end: str,
    fetch_candles: Callable[..., object] = fetch_public_klines,
) -> dict[str, object]:
    """Strict UTC date bounds; no account state, history write or order calls."""
    if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("Select a linear USDT symbol, e.g. BTCUSDT")
    start_ms, end_ms = parse_date_utc(start), parse_date_utc(end)
    if end_ms <= start_ms or end_ms - start_ms > MAX_LOCAL_BARS * FIVE_MINUTES_MS:
        raise ValueError("Select 1 to 7 complete UTC days")
    end_of_last_closed = (
        int(datetime.now(timezone.utc).timestamp() * 1000) // FIVE_MINUTES_MS
    ) * FIVE_MINUTES_MS
    if end_ms > end_of_last_closed:
        raise ValueError("Future/incomplete candles are not available")
    # The response remains entirely in RAM; no overwrite of PAPER or SIM files.
    from secrets import token_hex
    return build_market_only_document(
        symbol=symbol, start_ms=start_ms, end_ms=end_ms,
        run_id="local_" + token_hex(8), fetch_candles=fetch_candles,
    )


def handler_factory(static_dir: Path = STATIC_DIR,
                    history_loader: Callable[..., object] = load_public_history):
    resolved_dir = static_dir.resolve()

    class LocalReplayHandler(BaseHTTPRequestHandler):
        server_version = "MachineTimeLocal/1.0"
        protocol_version = "HTTP/1.0"

        def _trusted_host(self) -> bool:
            host = self.headers.get("Host", "")
            expected_port = self.server.server_address[1]
            return host in (f"127.0.0.1:{expected_port}", f"localhost:{expected_port}")

        def _send(self, status: int, body: bytes, mime: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, code: int, message: str) -> None:
            body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            if not self._trusted_host():
                self._error(403, "Local viewer only")
                return
            url = urlsplit(self.path)
            if url.path == "/local-replay/history":
                if self.command != "GET":
                    self._error(405, "GET only")
                    return
                if self.headers.get("Sec-Fetch-Site") == "cross-site" or (
                    self.headers.get("Origin") not in (None, "", f"http://127.0.0.1:{self.server.server_address[1]}", f"http://localhost:{self.server.server_address[1]}")
                ):
                    self._error(403, "Cross-site history requests forbidden")
                    return
                try:
                    fields = parse_qs(url.query, strict_parsing=True)
                    if set(fields) != {"symbol", "start", "end"} or any(len(x) != 1 for x in fields.values()):
                        raise ValueError("Expected symbol, start and end once")
                    doc = history_loader(symbol=fields["symbol"][0], start=fields["start"][0], end=fields["end"][0])
                    body = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                except (ValueError, OverflowError) as exc:
                    self._error(400, str(exc))
                except Exception:
                    # Failed remote market request: no fallback to cached, stale,
                    # proxy, PAPER or invented data.
                    self._error(502, "Public Bybit history unavailable; nothing was simulated")
                return
            if url.path == "/":
                requested = "/replay.html"
            else:
                requested = unquote(url.path)
            if not requested.startswith("/") or "\\" in requested or "\0" in requested:
                self._error(404, "Not found")
                return
            try:
                candidate = (resolved_dir / requested.lstrip("/")).resolve()
                if not candidate.is_relative_to(resolved_dir) or not candidate.is_file():
                    self._error(404, "Not found")
                    return
                body = candidate.read_bytes()
            except OSError:
                self._error(404, "Not found")
                return
            mimetype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self._send(200, body, mimetype + ("; charset=utf-8" if mimetype.startswith("text/") or mimetype == "application/javascript" else ""))

        def do_POST(self) -> None:
            self._error(405, "Read-only GET service")

        def do_PUT(self) -> None:
            self._error(405, "Read-only GET service")

        def log_message(self, fmt: str, *args: object) -> None:
            # Only local access, and do not print raw query strings.
            sys.stderr.write("[LOCAL REPLAY] " + fmt % args + "\n")

    return LocalReplayHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only read-only historical simulator viewer")
    parser.add_argument("--check", action="store_true", help="verify packaged assets/imports, no network")
    args = parser.parse_args()
    if not (STATIC_DIR / "replay.html").is_file():
        raise SystemExit("Missing standalone replay build: dist/replay.html")
    if args.check:
        print("LOCAL_REPLAY_PACKAGE_OK (assets and imports); no HTTP/network exercised")
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory())
    port = server.server_address[1]
    uri = f"http://127.0.0.1:{port}/replay.html"
    print("Local research simulation viewer: " + uri, flush=True)
    print("NO PAPER / NO VPS / NO LIVE. Close this window to stop.", flush=True)
    webbrowser.open(uri)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
