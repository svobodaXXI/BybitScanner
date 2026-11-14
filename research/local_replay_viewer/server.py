"""Local-only research viewer: loopback HTTP, public Bybit klines, no trading.

Run from Windows via START_LOCAL.cmd in the extracted build package.
The only remote request is a public Bybit /v5/market/kline GET with no credentials.
This service never imports Robot, PAPER, admission, STOP/TAKE or private API.
"""
from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
from secrets import token_hex
import threading
import sys
from typing import Callable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser

HERE = Path(__file__).resolve().parent
# Works both in GitHub source tree and in the packaged Windows zip.
ROOT = HERE if (HERE / "research").is_dir() else HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.export_historical_replay import (
    build_market_only_document, parse_date_utc, SYMBOL_RE,
)
from research.historical_candle_feed import FIVE_MINUTES_MS

MAX_LOCAL_BARS = 2016  # 7 days of VISIBLE candles
GEOMETRY_PRELOAD_BARS = 864  # 72h of earlier CLOSED context; never shown as replay
BYBIT_PUBLIC_KLINE = "https://api.bybit.com/v5/market/kline"
STATIC_DIR = HERE / "dist"
MAX_RESPONSE_BYTES = 2_000_000
# All SIMULATION files are under this fixed local viewer directory. Neither
# browser nor HTTP input may supply arbitrary filesystem paths.
SIM_DATA = HERE / "simulator-v2-data"
# Local owner-imported facts; never shared with VPS or trading runtime.
PAPER_EPISODES = HERE / "paper-episode-facts"
SIM_LOCK = threading.Lock()
MAX_SIM_REQUEST_BYTES = 4_096
MAX_SIM_CONFIG_BYTES = 12_000


def local_simulation_status() -> dict[str, object]:
    """Discovery only; files/checksums are validated again on each run."""
    try:
        engine = importlib.util.find_spec("research.simulator_v2.wedge_cli") is not None
    except (ImportError, ModuleNotFoundError):
        engine = False
    deps = importlib.util.find_spec("pandas") is not None
    data = (
        SIM_DATA.is_dir() and not SIM_DATA.is_symlink()
        and (SIM_DATA / "m1-cache").is_dir()
        and not (SIM_DATA / "m1-cache").is_symlink()
        and (SIM_DATA / "manifest.json").is_file()
        and not (SIM_DATA / "manifest.json").is_symlink()
    )
    risk = (SIM_DATA / "wedge-risk.json").is_file() and not (
        SIM_DATA / "wedge-risk.json"
    ).is_symlink()
    # UI-only hint from a bounded local manifest header, NOT a SHA verification.
    # The original manifest/cache proof is rechecked by run_local_simulation.
    archive_hint = None
    if data:
        try:
            with (SIM_DATA / "manifest.json").open("rb") as fh:
                manifest_bytes = fh.read(125_001)
            if len(manifest_bytes) <= 125_000:
                manifest = json.loads(manifest_bytes)
                first, last = manifest.get("start_ms"), manifest.get("end_ms")
                days, symbol = manifest.get("days"), manifest.get("symbol")
                day_ms = 86_400_000
                if (
                    manifest.get("schema") == "SIMULATOR_V2_PUBLIC_TRADES_DERIVED_M1_RANGE_V1"
                    and type(first) is int and type(last) is int
                    and type(days) is int and 2 <= days <= 90
                    and first >= 0 and first % day_ms == 0
                    and last == first + days * day_ms
                    and last <= int(datetime.now(timezone.utc).timestamp() * 1000)
                    and isinstance(symbol, str) and SYMBOL_RE.fullmatch(symbol)
                ):
                    start_ms = first + day_ms  # Full first day warms the Scanner.
                    fmt = lambda ms: datetime.fromtimestamp(
                        ms / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M")
                    archive_hint = {
                        "symbol": symbol,
                        "start_utc": fmt(start_ms),
                        "end_utc_inclusive": fmt(start_ms + day_ms - 60_000),
                    }
        except (OSError, ValueError, TypeError, OverflowError, AttributeError):
            pass
    result = {
        "namespace": "SIMULATION", "wedge_engine_available": engine,
        "python_dependencies_available": deps, "archive_files_present": data,
        "wedge_risk_profile_present": risk,
        "can_attempt": engine and deps and data and risk,
        "supported_strategies": ["WEDGE_FALLING", "WEDGE_RISING", "IKIGAI_BOX"],
        "archive_validation": "RECHECKED_ON_RUN_NOT_CLAIMED_READY",
    }
    if archive_hint is not None:
        result["archive_hint"] = archive_hint
    return result


def run_local_simulation(
    request_data: object, *,
    on_stream: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Original Wedge or Ikigai Box on known local public M1 cache.

    Does not download anything, import production Scanner/Robot runtimes,
    accept arbitrary file paths, or write to any exchange/PAPER ledger.
    """
    if not isinstance(request_data, dict) or set(request_data) != {
        "symbol", "start_utc", "end_utc_inclusive",
        "selected_strategies", "initial_balance",
    }:
        raise ValueError("expected exact local wedge run selection")
    if any(
        not isinstance(request_data[k], str) or not 1 <= len(request_data[k]) <= 40
        for k in ("symbol", "start_utc", "end_utc_inclusive", "initial_balance")
    ):
        raise ValueError("invalid local wedge run field")
    selected = request_data["selected_strategies"]
    if (not isinstance(selected, list) or not selected or len(selected) > 2
            or any(s not in ("WEDGE_RISING", "WEDGE_FALLING", "IKIGAI_BOX")
                   for s in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("only implemented Wedge or Ikigai Box may trade")
    if "IKIGAI_BOX" in selected and len(selected) != 1:
        raise ValueError("Ikigai Box currently requires an isolated one-strategy run")

    status = local_simulation_status()
    if not status["can_attempt"]:
        raise ValueError(
            "Локальный движок, pandas, проверенный архив или профиль риска отсутствует"
        )
    from research.simulator_v2.wedge_cli import (
        MAX_MANIFEST_BYTES, parse_manifest, run_from_time_machine_config,
    )
    from research.simulator_v2.history import last_closed_m1_boundary_ms

    manifest_file = SIM_DATA / "manifest.json"
    risk_file = SIM_DATA / "wedge-risk.json"
    with manifest_file.open("rb") as fh:
        raw_manifest = fh.read(MAX_MANIFEST_BYTES + 1)
    with risk_file.open("rb") as fh:
        raw_profile = fh.read(MAX_SIM_CONFIG_BYTES + 1)
    if len(raw_manifest) > MAX_MANIFEST_BYTES or len(raw_profile) > MAX_SIM_CONFIG_BYTES:
        raise ValueError("local public manifest or virtual risk profile exceeds limit")
    manifest = json.loads(raw_manifest)
    profile = json.loads(raw_profile)
    if (not isinstance(profile, dict)
            or set(profile) != {"scanner", "risk"}
            or not isinstance(profile["scanner"], dict)
            or not isinstance(profile["risk"], dict)):
        raise ValueError("explicit local Wedge risk profile is required")
    # Manifest SHA and every *daily cache SHA* will be validated by the
    # existing trade_range loader before success is reported.
    latest = last_closed_m1_boundary_ms()
    parse_manifest(manifest, latest_closed_boundary_ms=latest)
    configuration = {
        "schema": "TIME_MACHINE_WEDGE_SIMULATION_V1",
        "namespace": "SIMULATION",
        "simulation_run_id": "local_wedge_" + token_hex(9),
        **request_data,
        "scanner": profile["scanner"], "risk": profile["risk"],
    }
    if on_stream is not None:
        on_stream("start", {
            "simulation_run_id": configuration["simulation_run_id"],
            "symbol": configuration["symbol"],
            "start_utc": configuration["start_utc"],
            "end_utc_inclusive": configuration["end_utc_inclusive"],
        })
    result = run_from_time_machine_config(
        config=configuration, manifest=manifest,
        cache_dir=SIM_DATA / "m1-cache",
        latest_closed_boundary_ms=latest,
        capture_replay=True,
        on_replay_events=(
            (lambda events: on_stream("events", {"events": events}))
            if on_stream is not None else None
        ),
    )
    payload = result.to_payload()
    payload["risk_terms_source"] = profile["risk"]["terms_source"]
    payload["risk_terms_status"] = "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED"
    return payload



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


class NativeScannerStudyUnavailable(RuntimeError):
    """Local analytical failure, never a failed Bybit kline request."""


def load_public_history(
    *, symbol: str, start: str, end: str,
    fetch_candles: Callable[..., object] = fetch_public_klines,
    strategies: tuple[str, ...] = (),
) -> dict[str, object]:
    """Closed public M5; optionally run native research detectors, no trades."""
    if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("Select a linear USDT symbol, e.g. BTCUSDT")
    start_ms, end_ms = parse_date_utc(start), parse_date_utc(end)
    if end_ms <= start_ms or end_ms - start_ms > MAX_LOCAL_BARS * FIVE_MINUTES_MS:
        raise ValueError("Select 1 to 7 complete UTC days")
    # Reject unsupported research scan windows BEFORE downloading public data.
    # Plain MARKET_ONLY still supports the pre-existing seven-day window.
    if strategies and end_ms - start_ms > 288 * FIVE_MINUTES_MS:
        raise ValueError("Local native Scanner research supports one UTC day per scan")
    end_of_last_closed = (
        int(datetime.now(timezone.utc).timestamp() * 1000) // FIVE_MINUTES_MS
    ) * FIVE_MINUTES_MS
    if end_ms > end_of_last_closed:
        raise ValueError("Future/incomplete candles are not available")
    # The response remains entirely in RAM; no overwrite of PAPER or SIM files.
    from secrets import token_hex
    doc = build_market_only_document(
        symbol=symbol, start_ms=start_ms, end_ms=end_ms,
        run_id="local_" + token_hex(8), fetch_candles=fetch_candles,
        geometry_warmup_bars=GEOMETRY_PRELOAD_BARS,
    )
    if strategies:
        from research.simulator_v2.public_m5_scan import (
            MAX_PUBLIC_SCAN_BARS, SELECTABLE, scan_public_closed_m5,
        )
        if (len(doc["events"]) > MAX_PUBLIC_SCAN_BARS
                or len(set(strategies)) != len(strategies)
                or any(x not in SELECTABLE for x in strategies)):
            raise ValueError("Public research Scanner: one UTC day, only Wedge/Ikigai Box")
        try:
            observations = scan_public_closed_m5(doc, strategies)
        except (ImportError, ModuleNotFoundError, ValueError):
            raise
        except Exception as exc:
            raise NativeScannerStudyUnavailable(
                "Native Scanner study failed; no pattern/Robot claims published"
            ) from exc
        doc["scanner_research"] = {
            "scope": "PUBLIC_M5_OBSERVATIONS_NO_ROBOT_EXECUTION",
            "detectors": list(strategies),
            "configuration": "RESEARCH_HUNTER_SCORE50_NATIVE_WEDGE_AND_BOX",
        }
        doc["scanner_observations"] = observations
    return doc


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
            if url.path == "/local-replay/paper-episode":
                from research.local_replay_viewer.paper_episode_local_store import load_episode
                if (self.headers.get("Sec-Fetch-Site") == "cross-site"
                    or self.headers.get("Origin") not in (
                        None, "", f"http://127.0.0.1:{self.server.server_address[1]}",
                        f"http://localhost:{self.server.server_address[1]}",
                    )):
                    self._error(403, "Local owner archive only")
                    return
                try:
                    params = parse_qs(url.query, strict_parsing=True)
                    if set(params) != {"trade_episode_id"} or len(params["trade_episode_id"]) != 1:
                        raise ValueError("invalid_episode_lookup")
                    raw = load_episode(PAPER_EPISODES, params["trade_episode_id"][0])
                except (ValueError, OSError):
                    self._error(422, "Invalid local episode evidence")
                    return
                if raw is None:
                    self._error(404, "NOT_SYNCED_LOCAL")
                    return
                self._send(200, raw, "application/json; charset=utf-8")
                return
            if url.path == "/local-replay/simulation/status":
                if url.query or self.headers.get("Sec-Fetch-Site") == "cross-site":
                    self._error(403, "Local SIMULATION only")
                    return
                info = local_simulation_status()
                self._send(
                    200, json.dumps(info, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return
            if url.path == "/local-replay/bundled":
                # One immutable PUBLIC, MARKET_ONLY archive shipped with the
                # Windows viewer; never arbitrary filesystem paths or accounts.
                if url.query or self.headers.get("Sec-Fetch-Site") == "cross-site" or (
                    self.headers.get("Origin") not in (
                        None, "", f"http://127.0.0.1:{self.server.server_address[1]}",
                        f"http://localhost:{self.server.server_address[1]}",
                    )
                ):
                    self._error(403, "Local bundled history only")
                    return
                bundled = HERE / "real-h1-august.json"
                try:
                    if not bundled.is_file():
                        self._send(204, b"", "application/json")
                        return
                    if bundled.stat().st_size > 24 * 1024 * 1024:
                        self._error(413, "Bundled public archive too large")
                        return
                    self._send(200, bundled.read_bytes(), "application/json")
                except OSError:
                    self._error(500, "Bundled public archive unavailable")
                return
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
                    if not {"symbol", "start", "end"} <= set(fields) or not set(fields) <= {"symbol", "start", "end", "strategies"} or any(len(x) != 1 for x in fields.values()):
                        raise ValueError("Expected symbol, start and end once")
                    names = fields.get("strategies", [""])[0]
                    if names:
                        choices = tuple(names.split(","))
                        from research.simulator_v2.public_m5_scan import SELECTABLE
                        if (len(choices) != len(set(choices))
                                or len(choices) > 3 or any(name not in SELECTABLE for name in choices)):
                            raise ValueError("Only local Wedge and Ikigai Box M5 research supported")
                        doc = history_loader(
                            symbol=fields["symbol"][0], start=fields["start"][0],
                            end=fields["end"][0], strategies=choices,
                        )
                    else:
                        doc = history_loader(
                            symbol=fields["symbol"][0], start=fields["start"][0],
                            end=fields["end"][0],
                        )
                    body = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                except (ValueError, OverflowError) as exc:
                    self._error(400, str(exc))
                except (ImportError, ModuleNotFoundError):
                    self._error(503, "Native Scanner requires local Python 3.11 with bundled offline analytical wheels")
                except NativeScannerStudyUnavailable as exc:
                    self._error(503, str(exc))
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
            # POST only computes an in-memory local virtual account. It cannot
            # create files, send market orders, or change PAPER/VPS state.
            if not self._trusted_host():
                self._error(403, "Local Wedge SIMULATION only")
                return
            path = urlsplit(self.path).path
            if path == "/local-replay/paper-episode/import":
                from research.local_replay_viewer.paper_episode_local_store import (
                    MAX_BYTES, LocalEpisodeConflict, store_episode,
                )
                address = f"http://127.0.0.1:{self.server.server_address[1]}"
                local = f"http://localhost:{self.server.server_address[1]}"
                if (self.headers.get("Origin") not in (address, local)
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    or self.headers.get("X-Local-Paper-Import") != "explicit-file"
                    or self.headers.get("Content-Type") != "application/json"
                    or urlsplit(self.path).query):
                    self._error(403, "Explicit same-origin PAPER import only")
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 2 <= size <= MAX_BYTES:
                        self._error(413, "PAPER facts exceed local import limit")
                        return
                    episode_id = store_episode(PAPER_EPISODES, self.rfile.read(size))
                except LocalEpisodeConflict:
                    self._error(409, "Existing local episode conflicts with import")
                    return
                except (OSError, ValueError):
                    self._error(422, "Invalid PAPER episode import")
                    return
                self._send(200, json.dumps({
                    "ok": True, "trade_episode_id": episode_id, "stored_locally": True,
                }).encode("utf-8"), "application/json")
                return
            if path not in (
                "/local-replay/simulation/wedge",
                "/local-replay/simulation/wedge-stream",
            ):
                self._error(405, "Only local SIMULATION Wedge POST is supported")
                return
            streaming = path.endswith("/wedge-stream")
            address = f"http://127.0.0.1:{self.server.server_address[1]}"
            local = f"http://localhost:{self.server.server_address[1]}"
            if (self.headers.get("Origin") not in (address, local)
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    or self.headers.get("X-Local-Simulation") != "wedge"
                    or self.headers.get("Content-Type") != "application/json"
                    or urlsplit(self.path).query):
                self._error(403, "Same-origin SIMULATION JSON only")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 2 or length > MAX_SIM_REQUEST_BYTES:
                self._error(413, "SIMULATION request exceeds limit")
                return
            if not SIM_LOCK.acquire(blocking=False):
                self._error(409, "Other local SIMULATION run already active")
                return
            try:
                data = json.loads(self.rfile.read(length))
                if streaming:
                    # Streaming is a *single* original Wedge session, not
                    # per-day backtests or independent trading decisions.
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()

                    def emit(kind: str, fields: dict[str, object]) -> None:
                        frame = json.dumps(
                            {"type": kind, **fields}, ensure_ascii=False, allow_nan=False,
                            separators=(",", ":"),
                        ).encode("utf-8") + b"\n"
                        self.wfile.write(frame)
                        self.wfile.flush()

                    try:
                        result = run_local_simulation(data, on_stream=emit)
                        replay = result.pop("replay")
                        emit("complete", {
                            "report": result,
                            "source_id": replay["source_id"],
                            "event_count": len(replay["events"]),
                        })
                    except (ValueError, TypeError, KeyError, FileNotFoundError, ImportError, OSError) as exc:
                        emit("error", {"error": str(exc)[:250]})
                    except Exception:
                        emit("error", {"error": "SIMULATION aborted; no completed report"})
                else:
                    result = run_local_simulation(data)
                    body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
            except (ValueError, TypeError, KeyError, FileNotFoundError, ImportError, OSError) as exc:
                if not streaming:
                    self._error(422, str(exc)[:250])
            except Exception:
                if not streaming:
                    self._error(500, "SIMULATION aborted; no completed report")
            finally:
                SIM_LOCK.release()

        def do_PUT(self) -> None:
            self._error(405, "Read-only GET service")

        def log_message(self, fmt: str, *args: object) -> None:
            # Only local access, and do not print raw query strings.
            sys.stderr.write("[LOCAL REPLAY] " + fmt % args + "\n")

    return LocalReplayHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only read-only historical simulator viewer")
    parser.add_argument("--check", action="store_true", help="verify packaged assets/imports, no network")
    parser.add_argument("--no-browser", action="store_true", help="run loopback server without opening the browser")
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
    if not args.no_browser:
        webbrowser.open(uri)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
