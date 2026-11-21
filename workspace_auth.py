"""Workspace authentication primitives: stdlib only, host- and tunnel-independent.

Used by ``workspace_gateway`` (the authenticating front door for Terminal/GFL). Nothing
here reads trading state, touches the PAPER database, or grants any trading right: it
only decides whether a browser may talk to the gateway at all.

Model
-----
* The owner holds one long-lived secret, ``BYBITSCANNER_WORKSPACE_AUTH_KEY`` (>= 32
  chars, same convention as the operator/autopilot tokens). It never appears in a URL,
  QR code, cookie or log.
* Login uses a short-lived, single-use token derived from that key (HMAC). The token is
  carried only in the URL *fragment* of the login link, which browsers do not send to
  servers, proxies or tunnels and which the login page removes immediately.
* Redeeming the token yields a browser session: an opaque cookie signed with a
  per-process random key (so a gateway restart invalidates every session), with an
  absolute lifetime and explicit revocation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from urllib.parse import quote, urlsplit

AUTH_KEY_ENV = "BYBITSCANNER_WORKSPACE_AUTH_KEY"
MIN_KEY_LENGTH = 32
LOGIN_TOKEN_DEFAULT_TTL_S = 300
LOGIN_TOKEN_MAX_TTL_S = 600
SESSION_DEFAULT_TTL_S = 12 * 3600
SESSION_MAX_TTL_S = 24 * 3600
CLOCK_SKEW_S = 5
_LOGIN_PREFIX = b"workspace-login-v1|"
_SESSION_PREFIX = b"workspace-session-v1|"


class AuthConfigError(RuntimeError):
    """The gateway must not start (fail closed)."""


class TokenRejected(ValueError):
    """A login token or session value was not accepted. The reason is internal only."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def load_auth_key(environ) -> bytes:
    value = (environ.get(AUTH_KEY_ENV) or "").strip()
    if len(value) < MIN_KEY_LENGTH:
        raise AuthConfigError(f"{AUTH_KEY_ENV} must be set to at least {MIN_KEY_LENGTH} characters")
    return value.encode("utf-8")


def safe_next(path: object) -> str:
    """Same-origin, absolute-path-only redirect target; anything else becomes ``/``."""
    if not isinstance(path, str) or not path or len(path) > 512:
        return "/"
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in path):
        return "/"
    if path.startswith("/auth/"):
        return "/"
    return path


def issue_login_token(key: bytes, *, ttl_s: int = LOGIN_TOKEN_DEFAULT_TTL_S, now: float | None = None) -> str:
    ttl = int(ttl_s)
    if not 1 <= ttl <= LOGIN_TOKEN_MAX_TTL_S:
        raise ValueError(f"login token lifetime must be 1..{LOGIN_TOKEN_MAX_TTL_S} seconds")
    issued = int(time.time() if now is None else now)
    nonce = _b64(secrets.token_bytes(16))
    body = f"{nonce}.{issued}.{issued + ttl}"
    signature = hmac.new(key, _LOGIN_PREFIX + body.encode("ascii"), hashlib.sha256).digest()
    return f"bl1.{body}.{_b64(signature)}"


def verify_login_token(key: bytes, token: object, *, now: float | None = None) -> tuple[str, int]:
    """Return ``(nonce, expires_at)`` or raise TokenRejected. Single use is the ledger's job."""
    moment = time.time() if now is None else now
    if not isinstance(token, str) or len(token) > 256:
        raise TokenRejected("malformed")
    parts = token.split(".")
    if len(parts) != 5 or parts[0] != "bl1":
        raise TokenRejected("malformed")
    _, nonce, issued_text, expires_text, signature_text = parts
    try:
        issued, expires = int(issued_text), int(expires_text)
        signature = _unb64(signature_text)
    except (ValueError, TypeError):
        raise TokenRejected("malformed") from None
    body = f"{nonce}.{issued}.{expires}"
    expected = hmac.new(key, _LOGIN_PREFIX + body.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        raise TokenRejected("signature")
    if expires - issued < 1 or expires - issued > LOGIN_TOKEN_MAX_TTL_S:
        raise TokenRejected("lifetime")
    if issued > moment + CLOCK_SKEW_S or moment > expires:
        raise TokenRejected("expired")
    return nonce, expires


class OneTimeLedger:
    """Remembers consumed login nonces until they could no longer verify anyway."""

    def __init__(self) -> None:
        self._used: dict[str, int] = {}
        self._lock = threading.Lock()

    def consume(self, nonce: str, expires_at: int, *, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        with self._lock:
            for stale in [n for n, exp in self._used.items() if exp + CLOCK_SKEW_S < moment]:
                del self._used[stale]
            if nonce in self._used:
                return False
            self._used[nonce] = expires_at
            return True


class FailureLimiter:
    """Global (tunnel peers share one address) sliding-window limiter for failed logins."""

    def __init__(self, limit: int = 8, window_s: int = 60) -> None:
        self._limit, self._window = limit, window_s
        self._events: list[float] = []
        self._lock = threading.Lock()

    def blocked(self, *, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._events = [t for t in self._events if moment - t < self._window]
            return len(self._events) >= self._limit

    def record_failure(self, *, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._events.append(moment)


class SessionManager:
    """Opaque signed browser sessions. The signing key lives only in this process."""

    def __init__(self, ttl_s: int = SESSION_DEFAULT_TTL_S) -> None:
        if not 60 <= int(ttl_s) <= SESSION_MAX_TTL_S:
            raise AuthConfigError(f"session lifetime must be 60..{SESSION_MAX_TTL_S} seconds")
        self.ttl_s = int(ttl_s)
        self._key = secrets.token_bytes(32)
        self._revoked: dict[str, int] = {}
        self._lock = threading.Lock()

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._key, _SESSION_PREFIX + body.encode("ascii"), hashlib.sha256).digest())

    def issue(self, *, now: float | None = None) -> str:
        expires = int((time.time() if now is None else now) + self.ttl_s)
        body = f"{_b64(secrets.token_bytes(16))}.{expires}"
        return f"bs1.{body}.{self._sign(body)}"

    def verify(self, value: object, *, now: float | None = None) -> str | None:
        """Return the session id when the cookie value is valid, else None."""
        moment = time.time() if now is None else now
        if not isinstance(value, str) or len(value) > 200:
            return None
        parts = value.split(".")
        if len(parts) != 4 or parts[0] != "bs1":
            return None
        _, sid, expires_text, signature = parts
        try:
            expires = int(expires_text)
        except ValueError:
            return None
        if not hmac.compare_digest(self._sign(f"{sid}.{expires}"), signature):
            return None
        if moment > expires or expires - moment > self.ttl_s + CLOCK_SKEW_S:
            return None
        with self._lock:
            if sid in self._revoked:
                return None
        return sid

    def expires_at(self, value: str) -> int | None:
        try:
            return int(value.split(".")[2])
        except (IndexError, ValueError):
            return None

    def revoke(self, value: str, *, now: float | None = None) -> None:
        sid = self.verify(value, now=now)
        if sid is None:
            return
        with self._lock:
            self._revoked[sid] = int((time.time() if now is None else now) + self.ttl_s + CLOCK_SKEW_S)
            moment = time.time() if now is None else now
            for stale in [s for s, exp in self._revoked.items() if exp < moment]:
                del self._revoked[stale]


def build_login_link(origin: str, key: bytes, *, next_path: str = "/",
                     ttl_s: int = LOGIN_TOKEN_DEFAULT_TTL_S, now: float | None = None) -> str:
    """One-time login link. The token is only in the fragment; ``next`` is a same-origin path."""
    parts = urlsplit(origin)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ("", "/")):
        raise ValueError("A plain HTTPS origin is required")
    token = issue_login_token(key, ttl_s=ttl_s, now=now)
    return f"https://{parts.netloc}/auth/login?next={quote(safe_next(next_path), safe='')}#t={token}"
