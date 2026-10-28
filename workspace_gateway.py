"""Authenticating front door for Trading Workspace (Terminal / Editor / GFL).

One small process in front of the *existing* frontend build and PAPER backend:

    browser -> (any HTTPS tunnel / reverse proxy) -> this gateway -> backend 127.0.0.1:8765

* default deny: nothing but the login page and login/logout is reachable without a valid
  session -- not the static bundle, not any ``/api`` route, not the WebSocket stream;
* login by a short-lived single-use token carried only in the URL fragment
  (``workspace_auth``), then an HttpOnly/Secure/SameSite=Strict session cookie;
* state-changing requests and WebSocket upgrades must be same-origin (CSRF / CSWSH);
* only the API routes the Workspace frontend uses are proxied; ``/api/runtime/*`` and the
  Robot control routes are never reachable through the gateway, LIVE routes are read-only
  unless explicitly enabled; trading rights are still enforced by the backend itself
  (operator / autopilot tokens are passed through untouched, never added or removed);
* the gateway binds loopback only and never forwards the browser's cookie to the backend.

It is plain Python (stdlib), has no Windows, Vite or tunnel dependency, and runs the same
on the owner PC and on a VPS. It does not read or write the PAPER database.

    python workspace_gateway.py serve
    python workspace_gateway.py issue-link --origin https://<public-host> [--next "/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m"]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import logging
import mimetypes
import os
import posixpath
import select
import socket
import sys
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from workspace_auth import (
    AuthConfigError, FailureLimiter, OneTimeLedger, SessionManager, TokenRejected,
    build_login_link, load_auth_key, safe_next, verify_login_token,
)

LOGGER = logging.getLogger("workspace_gateway")
REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 4180
MAX_BODY = 1 << 20
LOGIN_BODY_MAX = 2048
WS_PATHS = frozenset(("/api/workspace/stream",))
# API surface the Workspace frontend actually uses. Anything else under /api is refused.
API_ALLOWED = (
    "/api/accounts", "/api/workspace", "/api/instruments", "/api/public-orderbook",
    "/api/public-klines", "/api/public-trades", "/api/paper-state", "/api/open-positions",
    "/api/diary", "/api/health", "/api/robot/autopilot", "/api/robot/protection-health",
    "/api/market", "/api/limit", "/api/stop", "/api/take", "/api/full-close", "/api/close-all",
)
API_LIVE_PREFIX = "/api/live"
HOP_BY_HOP = frozenset((
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
    "transfer-encoding", "upgrade", "proxy-connection",
))
# Never forwarded to the backend: the browser credential and anything proxy-identifying.
REQUEST_STRIP = HOP_BY_HOP | {"cookie", "host", "authorization", "forwarded", "x-forwarded-for",
                              "x-forwarded-host", "x-forwarded-proto", "x-real-ip"}
RESPONSE_STRIP = HOP_BY_HOP | {"set-cookie", "server", "content-length", "date"}
SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("Pragma", "no-cache"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
)

_LOGIN_SCRIPT = (
    '(function(){var p=new URLSearchParams(location.hash.slice(1)),t=p.get("t");'
    'var n=new URLSearchParams(location.search).get("next")||"/";'
    'if(!(n.charAt(0)==="/"&&n.charAt(1)!=="/"&&n.indexOf("\\\\")<0))n="/";'
    'history.replaceState(null,"",location.pathname);'
    'var m=document.getElementById("m");'
    'if(!t){m.textContent="Login link is missing or already used.";return}'
    'fetch("/auth/redeem",{method:"POST",credentials:"same-origin",'
    'headers:{"Content-Type":"application/json"},body:JSON.stringify({token:t})})'
    '.then(function(r){if(r.ok){location.replace(n)}else{m.textContent="Login link is invalid or expired."}})'
    '.catch(function(){m.textContent="Login failed."});})();'
)
_LOGIN_SCRIPT_HASH = base64.b64encode(hashlib.sha256(_LOGIN_SCRIPT.encode()).digest()).decode()
LOGIN_CSP = (
    f"default-src 'none'; script-src 'sha256-{_LOGIN_SCRIPT_HASH}'; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
LOGIN_PAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="referrer" content="no-referrer"><title>Sign in</title></head>'
    '<body style="font-family:system-ui,sans-serif;padding:24px"><p id="m">Signing in…</p>'
    f"<script>{_LOGIN_SCRIPT}</script></body></html>"
).encode("utf-8")


@dataclass(frozen=True)
class GatewayConfig:
    auth_key: bytes
    allowed_hosts: tuple[str, ...]
    backend_host: str = "127.0.0.1"
    backend_port: int = 8765
    dist_dir: Path = REPO_ROOT / "terminal" / "frontend" / "dist"
    secure_cookie: bool = True
    allow_live: bool = False
    session_ttl_s: int = 12 * 3600


def config_from_env(environ=None) -> GatewayConfig:
    env = os.environ if environ is None else environ
    key = load_auth_key(env)
    hosts = tuple(h.strip().lower() for h in (env.get("BYBITSCANNER_WORKSPACE_ALLOWED_HOSTS") or "").split(",")
                  if h.strip())
    if not hosts:
        raise AuthConfigError("BYBITSCANNER_WORKSPACE_ALLOWED_HOSTS must list the public host name(s)")
    backend = (env.get("BYBITSCANNER_WORKSPACE_BACKEND") or "127.0.0.1:8765").strip()
    host, _, port = backend.rpartition(":")
    if host not in ("127.0.0.1", "localhost", "::1") or not port.isdigit():
        raise AuthConfigError("BYBITSCANNER_WORKSPACE_BACKEND must be a loopback host:port")
    dist = Path(env.get("BYBITSCANNER_WORKSPACE_DIST") or REPO_ROOT / "terminal" / "frontend" / "dist")
    return GatewayConfig(
        auth_key=key, allowed_hosts=hosts, backend_host=host, backend_port=int(port), dist_dir=dist,
        secure_cookie=(env.get("BYBITSCANNER_WORKSPACE_INSECURE_COOKIE") != "1"),
        allow_live=(env.get("BYBITSCANNER_WORKSPACE_ALLOW_LIVE") == "1"),
        session_ttl_s=int(env.get("BYBITSCANNER_WORKSPACE_SESSION_SECONDS") or 12 * 3600),
    )


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def api_decision(method: str, path: str, *, allow_live: bool) -> bool:
    if any(_under(path, prefix) for prefix in API_ALLOWED):
        return True
    if _under(path, API_LIVE_PREFIX):
        return allow_live or method in ("GET", "HEAD")
    return False


def normalize_path(raw: str) -> str | None:
    """Decode once, collapse dot segments; refuse anything ambiguous."""
    if not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        return None
    decoded = unquote(raw)
    if "\x00" in decoded or "\\" in decoded or any(ord(c) < 0x20 for c in decoded):
        return None
    if "%" in decoded:  # double-encoding is never legitimate for this app
        return None
    normalized = posixpath.normpath(decoded)
    if decoded.endswith("/") and normalized != "/":
        normalized += "/"
    if normalized.startswith("//"):
        normalized = "/" + normalized.lstrip("/")
    return normalized


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config: GatewayConfig):
        super().__init__(address, GatewayHandler)
        self.config = config
        self.sessions = SessionManager(config.session_ttl_s)
        self.ledger = OneTimeLedger()
        self.limiter = FailureLimiter()
        self.cookie_name = "__Host-bybitscanner_ws" if config.secure_cookie else "bybitscanner_ws"


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # one request per connection: no smuggling/keep-alive state
    server_version = "workspace-gateway"
    sys_version = ""
    server: GatewayServer

    # -- logging: method, path without query, status; never headers/cookies/bodies ---------
    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler API
        return

    def log_request(self, code="-", size="-"):
        LOGGER.info("%s %s -> %s", self.command, self.path.split("?", 1)[0].split("#", 1)[0][:120], code)

    # -- helpers ---------------------------------------------------------------------------
    @property
    def cfg(self) -> GatewayConfig:
        return self.server.config

    def _send(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8",
              extra=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict, extra=()):
        self._send(status, json.dumps(payload, separators=(",", ":")).encode(),
                   "application/json", extra)

    def _host(self) -> str | None:
        raw = (self.headers.get("Host") or "").strip().lower()
        if not raw or len(raw) > 255 or any(c in raw for c in " /\\@?#"):
            return None
        return raw

    def _host_allowed(self, host: str) -> bool:
        name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        for entry in self.cfg.allowed_hosts:
            if entry.startswith("."):
                if name.endswith(entry) and len(name) > len(entry):
                    return True
            elif name == entry:
                return True
        return False

    def _same_origin(self, host: str) -> bool:
        scheme = "https" if self.cfg.secure_cookie else "http"
        origin = self.headers.get("Origin")
        if origin is None or origin != f"{scheme}://{host}":
            return False
        site = self.headers.get("Sec-Fetch-Site")
        return site is None or site in ("same-origin", "none")

    def _session_cookie(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw or len(raw) > 4096:
            return None
        try:
            jar = SimpleCookie()
            jar.load(raw)
        except Exception:
            return None
        morsel = jar.get(self.server.cookie_name)
        return morsel.value if morsel else None

    def _authenticated(self) -> bool:
        value = self._session_cookie()
        return bool(value) and self.server.sessions.verify(value) is not None

    def _cookie_header(self, value: str, max_age: int) -> str:
        parts = [f"{self.server.cookie_name}={value}", f"Max-Age={max_age}", "Path=/", "HttpOnly",
                 "SameSite=Strict"]
        if self.cfg.secure_cookie:
            parts.append("Secure")
        return "; ".join(parts)

    # -- dispatch --------------------------------------------------------------------------
    def do_GET(self):
        self._dispatch()

    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_GET

    def do_OPTIONS(self):
        self._send(405, b"method not allowed")

    def _dispatch(self):
        host = self._host()
        if host is None or not self._host_allowed(host):
            self._send(421, b"misdirected request")
            return
        raw_path = self.path.split("?", 1)[0]
        query = self.path[len(raw_path):]
        path = normalize_path(raw_path)
        if path is None:
            self._send(400, b"bad request")
            return
        method = self.command

        if path == "/auth/login" and method in ("GET", "HEAD"):
            self._send(200, LOGIN_PAGE, "text/html; charset=utf-8",
                       (("Content-Security-Policy", LOGIN_CSP),))
            return
        if path == "/auth/redeem":
            self._redeem(host) if method == "POST" else self._send(405, b"method not allowed")
            return
        if path == "/auth/logout":
            self._logout(host) if method == "POST" else self._send(405, b"method not allowed")
            return

        # default deny from here on
        if not self._authenticated():
            if path.startswith("/api/"):
                self._json(401, {"ok": False, "error": "authentication_required"})
            else:
                self._send(401, b"authentication required")
            return
        if method not in ("GET", "HEAD") and not self._same_origin(host):
            self._json(403, {"ok": False, "error": "cross_origin_request_refused"})
            return
        if path.startswith("/api/") or path == "/api":
            if not api_decision(method, path, allow_live=self.cfg.allow_live):
                self._json(403, {"ok": False, "error": "route_not_exposed"})
                return
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._websocket(host, path, query)
            else:
                self._proxy(path, query)
            return
        if method in ("GET", "HEAD"):
            self._static(path)
            return
        self._send(405, b"method not allowed")

    # -- auth endpoints --------------------------------------------------------------------
    def _redeem(self, host: str):
        if self.server.limiter.blocked():
            self._json(429, {"ok": False, "error": "try_later"})
            return
        if not self._same_origin(host) or "application/json" not in (self.headers.get("Content-Type") or ""):
            self._json(403, {"ok": False, "error": "refused"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        if not 0 < length <= LOGIN_BODY_MAX:
            self._json(400, {"ok": False, "error": "bad_request"})
            return
        try:
            token = json.loads(self.rfile.read(length)).get("token")
            nonce, expires = verify_login_token(self.cfg.auth_key, token)
            if not self.server.ledger.consume(nonce, expires):
                raise TokenRejected("replay")
        except (TokenRejected, ValueError, AttributeError, TypeError):
            self.server.limiter.record_failure()
            self._json(401, {"ok": False, "error": "login_refused"})
            return
        session = self.server.sessions.issue()
        self._json(200, {"ok": True}, (("Set-Cookie", self._cookie_header(session, self.server.sessions.ttl_s)),))

    def _logout(self, host: str):
        if not self._authenticated():
            self._json(401, {"ok": False, "error": "authentication_required"})
            return
        if not self._same_origin(host):
            self._json(403, {"ok": False, "error": "cross_origin_request_refused"})
            return
        value = self._session_cookie()
        if value:
            self.server.sessions.revoke(value)
        self._json(200, {"ok": True}, (("Set-Cookie", self._cookie_header("", 0)),))

    # -- static bundle ---------------------------------------------------------------------
    def _static(self, path: str):
        root = self.cfg.dist_dir.resolve()
        relative = path.lstrip("/")
        candidate = (root / relative).resolve() if relative else root / "index.html"
        try:
            candidate.relative_to(root)
        except ValueError:
            self._send(404, b"not found")
            return
        if not candidate.is_file():
            last = path.rsplit("/", 1)[-1]
            if "." in last:
                self._send(404, b"not found")
                return
            candidate = root / "index.html"  # client-side routes
            if not candidate.is_file():
                self._send(404, b"not found")
                return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self._send(200, candidate.read_bytes(), content_type)

    # -- reverse proxy ---------------------------------------------------------------------
    def _upstream_headers(self) -> list[tuple[str, str]]:
        return [(k, v) for k, v in self.headers.items() if k.lower() not in REQUEST_STRIP]

    def _proxy(self, path: str, query: str):
        body = b""
        if self.command in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                self._json(400, {"ok": False, "error": "bad_request"})
                return
            body = self.rfile.read(length) if length else b""
        conn = http.client.HTTPConnection(self.cfg.backend_host, self.cfg.backend_port, timeout=120)
        try:
            headers = dict(self._upstream_headers())
            headers["Host"] = f"{self.cfg.backend_host}:{self.cfg.backend_port}"
            headers["Connection"] = "close"
            if body:
                headers["Content-Length"] = str(len(body))
            conn.request(self.command, path + query, body or None, headers)
            response = conn.getresponse()
        except OSError:
            conn.close()
            self._json(502, {"ok": False, "error": "backend_unavailable"})
            return
        try:
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() not in RESPONSE_STRIP and name.lower() not in {h.lower() for h, _ in SECURITY_HEADERS}:
                    self.send_header(name, value)
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command == "HEAD":
                return
            while True:
                chunk = response.read1(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException):
            pass
        finally:
            conn.close()
            self.close_connection = True

    # -- websocket (raw splice after authentication and origin checks) ----------------------
    def _websocket(self, host: str, path: str, query: str):
        if path not in WS_PATHS or self.command != "GET":
            self._json(403, {"ok": False, "error": "route_not_exposed"})
            return
        if not self._same_origin(host):
            self._json(403, {"ok": False, "error": "cross_origin_request_refused"})
            return
        try:
            upstream = socket.create_connection((self.cfg.backend_host, self.cfg.backend_port), timeout=10)
        except OSError:
            self._json(502, {"ok": False, "error": "backend_unavailable"})
            return
        lines = [f"GET {path}{query} HTTP/1.1", f"Host: {self.cfg.backend_host}:{self.cfg.backend_port}"]
        for name, value in self.headers.items():
            lowered = name.lower()
            if lowered in REQUEST_STRIP and lowered not in ("connection", "upgrade"):
                continue
            lines.append(f"{name}: {value}")
        upstream.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        self.close_connection = True
        session_value = self._session_cookie() or ""
        expires = self.server.sessions.expires_at(session_value) or 0
        client = self.connection
        client.settimeout(None)
        upstream.settimeout(None)
        try:
            while True:
                readable, _, _ = select.select([client, upstream], [], [], 5.0)
                if time.time() > expires:
                    break
                for sock in readable:
                    data = sock.recv(65536)
                    if not data:
                        return
                    (upstream if sock is client else client).sendall(data)
        except OSError:
            pass
        finally:
            upstream.close()


def build_server(config: GatewayConfig, port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> GatewayServer:
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise AuthConfigError("the gateway binds loopback only; put the tunnel/reverse proxy in front of it")
    if not config.dist_dir.joinpath("index.html").is_file():
        raise AuthConfigError("frontend build not found; run npm run build in terminal/frontend")
    return GatewayServer((host, port), config)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=int(os.environ.get("BYBITSCANNER_WORKSPACE_GATEWAY_PORT") or DEFAULT_PORT))
    issue = sub.add_parser("issue-link")
    issue.add_argument("--origin", required=True)
    issue.add_argument("--next", default="/")
    issue.add_argument("--ttl", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
            server = build_server(config_from_env(), args.port)
            print(f"Workspace gateway listening on 127.0.0.1:{args.port} (loopback only); "
                  f"hosts={','.join(server.config.allowed_hosts)}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        key = load_auth_key(os.environ)
        print(build_login_link(args.origin, key, next_path=args.next, ttl_s=args.ttl))
        return 0
    except (AuthConfigError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
