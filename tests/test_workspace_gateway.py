"""Workspace gateway: default deny, one-time login, session, CSRF/CSWSH, route allowlist, no bypass.

Real sockets, no mocks of the gateway itself: a fake backend records every request it receives, so
"the backend was never contacted" is a direct observation, not an inference.
"""
import http.client
import json
import logging
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import workspace_auth as auth
import workspace_gateway as gw

KEY = ("k" * 40).encode()
HOST = "workspace.test"
ORIGIN = f"https://{HOST}"


class FakeBackend(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FakeBackendHandler)
        self.requests = []


class FakeBackendHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def _record(self):
        self.server.requests.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}))

    def _handle(self):
        self._record()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if self.path.startswith("/api/workspace/stream") and self.headers.get("Upgrade", "").lower() == "websocket":
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", "x")
            self.end_headers()
            while True:
                data = self.connection.recv(4096)
                if not data:
                    return
                self.connection.sendall(b"echo:" + data)
        if self.path.startswith("/api/public-orderbook/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Set-Cookie", "leak=1")
            self.end_headers()
            self.wfile.write(b"data: 1\n\n")
            self.wfile.flush()
            time.sleep(0.2)
            self.wfile.write(b"data: 2\n\n")
            return
        payload = json.dumps({"ok": True, "path": self.path, "body": body.decode() or None}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = _handle


class GatewayTestCase(unittest.TestCase):
    secure = True

    def setUp(self):
        self.backend = FakeBackend()
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        dist = root / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>app</html>")
        (dist / "assets" / "app.js").write_text("console.log(1)")
        (root / "secret.txt").write_text("TOP-SECRET")
        config = gw.GatewayConfig(
            auth_key=KEY, allowed_hosts=(HOST, ".tunnel.test"), backend_port=self.backend.server_address[1],
            dist_dir=dist, secure_cookie=self.secure, session_ttl_s=3600,
        )
        self.gateway = gw.build_server(config, 0)
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()
        self.port = self.gateway.server_address[1]

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()
        self.backend.shutdown()
        self.backend.server_close()
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------------------------
    def request(self, method, path, *, headers=None, body=None, host=HOST):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        merged = {"Host": host}
        merged.update(headers or {})
        conn.request(method, path, body, merged)
        response = conn.getresponse()
        data = response.read()
        result = (response.status, response, data)
        conn.close()
        return result

    def login(self, token=None):
        token = auth.issue_login_token(KEY) if token is None else token
        status, response, _ = self.request(
            "POST", "/auth/redeem", body=json.dumps({"token": token}),
            headers={"Origin": ORIGIN, "Content-Type": "application/json"})
        cookie = response.getheader("Set-Cookie")
        return status, cookie

    def session_header(self):
        status, cookie = self.login()
        self.assertEqual(status, 200)
        return {"Cookie": cookie.split(";", 1)[0]}

    def backend_hits(self):
        return list(self.backend.requests)


class DefaultDenyTests(GatewayTestCase):
    def test_unauthenticated_requests_never_reach_backend_or_static_files(self):
        for path in ("/", "/index.html", "/assets/app.js", "/api/health", "/api/paper-state?symbol=BTCUSDT",
                     "/api/workspace/state", "/api/robot/autopilot"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 401, path)
            self.assertNotIn(b"app", body.replace(b"authentication required", b""), path)
        for method in ("POST", "PUT", "DELETE"):
            status, _, _ = self.request(method, "/api/market", body="{}", headers={"Origin": ORIGIN})
            self.assertEqual(status, 401)
        self.assertEqual(self.backend_hits(), [])

    def test_forged_and_malformed_cookies_are_rejected(self):
        name = self.gateway.cookie_name
        other = auth.SessionManager(3600).issue()  # valid shape, wrong signing key
        for cookie in (f"{name}=", f"{name}=garbage", f"{name}={other}", "x=" + "A" * 5000,
                       f"{name}=bs1.a.9999999999.bad"):
            status, _, _ = self.request("GET", "/api/health", headers={"Cookie": cookie})
            self.assertEqual(status, 401, cookie[:30])
        self.assertEqual(self.backend_hits(), [])

    def test_unauthenticated_websocket_upgrade_is_refused_without_contacting_backend(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall((f"GET /api/workspace/stream?symbol=BTCUSDT HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: abc\r\n"
                      f"Origin: {ORIGIN}\r\n\r\n").encode())
        reply = sock.recv(4096)
        sock.close()
        self.assertTrue(reply.startswith(b"HTTP/1.0 401"), reply[:40])
        self.assertEqual(self.backend_hits(), [])

    def test_host_header_must_be_allowed_for_every_route(self):
        for host in ("evil.example", "workspace.test.evil.example", "tunnel.test", "127.0.0.1:1"):
            for path in ("/auth/login", "/", "/api/health"):
                status, _, _ = self.request("GET", path, host=host)
                self.assertEqual(status, 421, (host, path))
        status, _, _ = self.request("GET", "/auth/login", host="random.tunnel.test")
        self.assertEqual(status, 200)  # leading-dot suffix entries match subdomains only
        self.assertEqual(self.backend_hits(), [])

    def test_absolute_form_and_ambiguous_targets_are_rejected(self):
        for target in ("http://evil.example/api/health", "//evil.example/x", "/a\\b", "/%00", "/%252e%252e/x"):
            sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            sock.sendall(f"GET {target} HTTP/1.0\r\nHost: {HOST}\r\n\r\n".encode())
            reply = sock.recv(4096)
            sock.close()
            self.assertTrue(reply.startswith((b"HTTP/1.0 400", b"HTTP/1.0 401")), (target, reply[:30]))
        self.assertEqual(self.backend_hits(), [])


class LoginAndSessionTests(GatewayTestCase):
    def test_login_page_is_public_carries_no_secret_and_has_strict_csp(self):
        status, response, body = self.request("GET", "/auth/login?next=%2F")
        self.assertEqual(status, 200)
        csp = response.getheader("Content-Security-Policy")
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("script-src 'sha256-", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertNotIn(KEY, body)

    def test_valid_token_creates_hardened_session_and_is_single_use(self):
        token = auth.issue_login_token(KEY)
        status, cookie = self.login(token)
        self.assertEqual(status, 200)
        for attribute in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/", "Max-Age=3600"):
            self.assertIn(attribute, cookie)
        self.assertTrue(cookie.startswith("__Host-bybitscanner_ws="))
        self.assertNotIn("Domain", cookie)
        self.assertNotIn(token, cookie)
        replay_status, replay_cookie = self.login(token)
        self.assertEqual(replay_status, 401)
        self.assertIsNone(replay_cookie)

    def test_expired_tampered_wrong_key_and_overlong_tokens_are_refused(self):
        now = time.time()
        good = auth.issue_login_token(KEY)
        tampered = good[:-3] + ("AAA" if good[-3:] != "AAA" else "BBB")
        other_key = auth.issue_login_token(b"z" * 40)
        expired = auth.issue_login_token(KEY, ttl_s=1, now=now - 100)
        for token in (tampered, other_key, expired, "", "bl1.a.b.c.d", "x" * 400, None):
            status, cookie = self.login("null" if token is None else token)
            self.assertEqual(status, 401, str(token)[:20])
            self.assertIsNone(cookie)
        with self.assertRaises(ValueError):
            auth.issue_login_token(KEY, ttl_s=auth.LOGIN_TOKEN_MAX_TTL_S + 1)
        # a token the key holder signed with an over-long lifetime is refused by the verifier too
        long_lived = auth.issue_login_token(KEY, ttl_s=auth.LOGIN_TOKEN_MAX_TTL_S)
        with self.assertRaises(auth.TokenRejected):
            auth.verify_login_token(KEY, long_lived, now=time.time() + auth.LOGIN_TOKEN_MAX_TTL_S + 60)

    def test_redeem_requires_same_origin_json_post_and_is_rate_limited(self):
        token = auth.issue_login_token(KEY)
        body = json.dumps({"token": token})
        status, _, _ = self.request("POST", "/auth/redeem", body=body, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 403)  # no Origin
        status, _, _ = self.request("POST", "/auth/redeem", body=body,
                                    headers={"Origin": "https://evil.example", "Content-Type": "application/json"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/auth/redeem", body=body,
                                    headers={"Origin": ORIGIN, "Content-Type": "text/plain"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("GET", "/auth/redeem")[0], 405)
        for _ in range(8):
            self.assertEqual(self.login("bl1.a.1.2.sig")[0], 401)
        self.assertEqual(self.login()[0], 429)  # a valid token is also refused while blocked

    def test_session_expiry_and_logout_revocation(self):
        sessions = auth.SessionManager(120)
        value = sessions.issue(now=1000)
        self.assertIsNotNone(sessions.verify(value, now=1050))
        self.assertIsNone(sessions.verify(value, now=1000 + 121))
        sessions.revoke(value, now=1050)
        self.assertIsNone(sessions.verify(value, now=1051))
        with self.assertRaises(auth.AuthConfigError):
            auth.SessionManager(auth.SESSION_MAX_TTL_S + 1)
        header = self.session_header()
        self.assertEqual(self.request("GET", "/api/health", headers=header)[0], 200)
        status, response, _ = self.request("POST", "/auth/logout", headers={**header, "Origin": ORIGIN})
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", response.getheader("Set-Cookie"))
        self.assertEqual(self.request("GET", "/api/health", headers=header)[0], 401)

    def test_sessions_do_not_survive_a_gateway_restart(self):
        value = auth.SessionManager(3600).issue()
        other = auth.SessionManager(3600)
        self.assertIsNone(other.verify(value))

    def test_login_link_keeps_the_token_out_of_the_query_and_blocks_open_redirects(self):
        link = auth.build_login_link(ORIGIN, KEY, next_path="/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m")
        base, _, fragment = link.partition("#")
        self.assertTrue(fragment.startswith("t=bl1."))
        self.assertNotIn("bl1.", base)
        self.assertTrue(base.startswith(f"{ORIGIN}/auth/login?next="))
        for hostile in ("//evil.example", "https://evil.example", "/\\evil", "/auth/redeem", "x", "", "/a\nb"):
            self.assertEqual(auth.safe_next(hostile), "/")
        for origin in ("http://workspace.test", "https://workspace.test/x", "https://u:p@workspace.test",
                       "https://workspace.test?x=1"):
            with self.assertRaises(ValueError):
                auth.build_login_link(origin, KEY)


class AuthorizedTrafficTests(GatewayTestCase):
    def test_authorized_get_is_proxied_without_the_browser_cookie(self):
        header = self.session_header()
        status, response, body = self.request(
            "GET", "/api/paper-state?symbol=BTCUSDT",
            headers={**header, "X-Forwarded-For": "1.2.3.4", "Authorization": "Bearer abc", "X-Custom": "kept"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["path"], "/api/paper-state?symbol=BTCUSDT")
        method, path, seen = self.backend_hits()[-1]
        self.assertNotIn("cookie", seen)
        self.assertNotIn("authorization", seen)
        self.assertNotIn("x-forwarded-for", seen)
        self.assertEqual(seen["x-custom"], "kept")
        self.assertTrue(seen["host"].startswith("127.0.0.1:"))
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")

    def test_static_bundle_requires_session_and_cannot_escape_dist(self):
        header = self.session_header()
        self.assertEqual(self.request("GET", "/", headers=header)[2], b"<html>app</html>")
        self.assertEqual(self.request("GET", "/assets/app.js", headers=header)[2], b"console.log(1)")
        self.assertEqual(self.request("GET", "/some/client/route", headers=header)[2], b"<html>app</html>")
        for target in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/secret.txt"):
            status, _, body = self.request("GET", target, headers=header)
            self.assertNotIn(b"TOP-SECRET", body, target)
            self.assertIn(status, (200, 400, 404), target)
        self.assertEqual(self.request("GET", "/missing.js", headers=header)[0], 404)

    def test_backend_admin_and_unknown_routes_are_not_reachable_through_the_gateway(self):
        header = {**self.session_header(), "Origin": ORIGIN}
        for method, path in (
            ("POST", "/api/runtime/shutdown"), ("POST", "/api/runtime/retire-entry-coverage"),
            ("POST", "/api/robot/reconcile"), ("POST", "/api/robot/close-all-now"),
            ("POST", "/api/robot/synchronize-pending-entries"), ("GET", "/api/unknown"),
            ("GET", "/api/health/../runtime/shutdown"),
            ("GET", "/api/runtime"), ("GET", "/api"),
        ):
            status, _, _ = self.request(method, path, headers=header, body="{}" if method == "POST" else None)
            self.assertIn(status, (400, 403, 404), (method, path))
        # Dot segments are collapsed before routing: this one leaves /api and becomes a static
        # (client-side route) request -- it must never be proxied to the backend.
        status, _, body = self.request("GET", "/api/%2e%2e/runtime/shutdown", headers=header)
        self.assertEqual(body, b"<html>app</html>")
        self.assertEqual(self.backend_hits(), [])

    def test_live_routes_are_read_only_unless_explicitly_enabled(self):
        header = {**self.session_header(), "Origin": ORIGIN}
        self.assertEqual(self.request("GET", "/api/live/limit/state", headers=header)[0], 200)
        for path in ("/api/live/market", "/api/live/limit", "/api/live/full-close"):
            self.assertEqual(self.request("POST", path, headers=header, body="{}")[0], 403, path)
        self.assertEqual([h for h in self.backend_hits() if h[0] == "POST"], [])

    def test_state_changing_requests_need_same_origin_csrf_protection(self):
        header = self.session_header()
        for headers in ({}, {"Origin": "https://evil.example"}, {"Origin": "null"},
                        {"Origin": "http://workspace.test"}, {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"}):
            status, _, _ = self.request("POST", "/api/market", body='{"x":1}', headers={**header, **headers})
            self.assertEqual(status, 403, headers)
        self.assertEqual([h for h in self.backend_hits() if h[0] == "POST"], [])
        status, _, body = self.request("POST", "/api/market", body='{"x":1}',
                                       headers={**header, "Origin": ORIGIN, "Sec-Fetch-Site": "same-origin",
                                                "Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["body"], '{"x":1}')

    def test_trading_rights_headers_are_passed_through_unchanged_never_injected(self):
        header = {**self.session_header(), "Origin": ORIGIN}
        self.request("POST", "/api/robot/autopilot", body="{}", headers=header)
        seen = self.backend_hits()[-1][2]
        self.assertNotIn("x-bybitscanner-operator-token", seen)
        self.request("POST", "/api/robot/autopilot", body="{}",
                     headers={**header, "X-BybitScanner-Operator-Token": "client-supplied"})
        self.assertEqual(self.backend_hits()[-1][2]["x-bybitscanner-operator-token"], "client-supplied")

    def test_streaming_response_is_relayed_and_backend_cookies_are_dropped(self):
        header = self.session_header()
        status, response, body = self.request("GET", "/api/public-orderbook/stream?symbol=BTCUSDT", headers=header)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"data: 1\n\ndata: 2\n\n")
        self.assertIsNone(response.getheader("Set-Cookie"))
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")

    def test_backend_down_is_a_clean_502_not_a_leak(self):
        header = self.session_header()
        self.backend.shutdown()
        self.backend.server_close()
        status, _, body = self.request("GET", "/api/health", headers=header)
        self.assertEqual(status, 502)
        self.assertNotIn(b"Traceback", body)


class WebSocketTests(GatewayTestCase):
    def _upgrade(self, cookie, origin):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        lines = [f"GET /api/workspace/stream?symbol=BTCUSDT&interval=5 HTTP/1.1", f"Host: {HOST}",
                 "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Version: 13",
                 "Sec-WebSocket-Key: abc", f"Cookie: {cookie}"]
        if origin:
            lines.append(f"Origin: {origin}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        return sock

    def test_authorized_same_origin_upgrade_is_spliced_end_to_end(self):
        cookie = self.session_header()["Cookie"]
        sock = self._upgrade(cookie, ORIGIN)
        reply = b""
        while b"\r\n\r\n" not in reply:
            reply += sock.recv(4096)
        self.assertIn(b"101", reply.split(b"\r\n", 1)[0])
        sock.sendall(b"ping")
        echoed = sock.recv(4096)
        sock.close()
        self.assertEqual(echoed, b"echo:ping")
        seen = self.backend_hits()[-1][2]
        self.assertNotIn("cookie", seen)

    def test_cross_site_websocket_hijack_is_refused(self):
        cookie = self.session_header()["Cookie"]
        for origin in (None, "https://evil.example", "null"):
            sock = self._upgrade(cookie, origin)
            reply = sock.recv(4096)
            sock.close()
            self.assertTrue(reply.startswith(b"HTTP/1.0 403"), (origin, reply[:30]))
        self.assertEqual(self.backend_hits(), [])

    def test_only_the_workspace_stream_may_be_upgraded(self):
        cookie = self.session_header()["Cookie"]
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall((f"GET /api/health HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Cookie: {cookie}\r\nOrigin: {ORIGIN}\r\n\r\n").encode())
        reply = sock.recv(4096)
        sock.close()
        self.assertTrue(reply.startswith(b"HTTP/1.0 403"))
        self.assertEqual(self.backend_hits(), [])


class ConfigAndLoggingTests(unittest.TestCase):
    def test_gateway_refuses_to_start_without_a_strong_key_hosts_or_loopback_backend(self):
        base = {"BYBITSCANNER_WORKSPACE_AUTH_KEY": "k" * 40, "BYBITSCANNER_WORKSPACE_ALLOWED_HOSTS": "a.test"}
        self.assertEqual(gw.config_from_env(base).allowed_hosts, ("a.test",))
        for bad in (
            {**base, "BYBITSCANNER_WORKSPACE_AUTH_KEY": "short"},
            {k: v for k, v in base.items() if k != "BYBITSCANNER_WORKSPACE_AUTH_KEY"},
            {**base, "BYBITSCANNER_WORKSPACE_ALLOWED_HOSTS": ""},
            {**base, "BYBITSCANNER_WORKSPACE_BACKEND": "10.0.0.5:8765"},
        ):
            with self.assertRaises(auth.AuthConfigError):
                gw.config_from_env(bad)
        self.assertFalse(gw.config_from_env(base).allow_live)
        self.assertTrue(gw.config_from_env(base).secure_cookie)

    def test_gateway_only_binds_loopback_and_needs_a_frontend_build(self):
        with tempfile.TemporaryDirectory() as empty:
            config = gw.GatewayConfig(auth_key=KEY, allowed_hosts=(HOST,), dist_dir=Path(empty))
            with self.assertRaises(auth.AuthConfigError):
                gw.build_server(config, 0)
            (Path(empty) / "index.html").write_text("x")
            with self.assertRaises(auth.AuthConfigError):
                gw.build_server(config, 0, host="0.0.0.0")

    def test_logs_never_contain_tokens_cookies_or_the_key(self):
        class Case(GatewayTestCase):
            def runTest(self):
                pass
        case = Case()
        case.setUp()
        try:
            with self.assertLogs("workspace_gateway", level="INFO") as captured:
                token = auth.issue_login_token(KEY)
                status, cookie = case.login(token)
                case.request("GET", "/api/health?symbol=BTCUSDT", headers={"Cookie": cookie.split(";", 1)[0]})
                case.request("GET", "/api/health?token=" + token)
            joined = "\n".join(captured.output)
            self.assertNotIn(token, joined)
            self.assertNotIn(cookie.split("=", 1)[1].split(";", 1)[0], joined)
            self.assertNotIn(KEY.decode(), joined)
            self.assertNotIn("symbol=BTCUSDT", joined)  # query strings are never logged
        finally:
            case.tearDown()


if __name__ == "__main__":
    unittest.main()
