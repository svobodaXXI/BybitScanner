"""Loopback-only Telegram Mini App authentication sidecar for a protected Nginx ingress.

No trading/backend import, outbound network access, or PAPER DB access.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

MAX_BODY = 8192
SESSION_TTL = 3600
INITDATA_MAX_AGE = 300

def _config():
    token = os.environ["BYBITSCANNER_TELEGRAM_BOT_TOKEN"]
    user_id = int(os.environ["BYBITSCANNER_TELEGRAM_OWNER_USER_ID"])
    origin = os.environ["BYBITSCANNER_TERMINAL_PUBLIC_ORIGIN"].rstrip("/")
    secret = os.environ["BYBITSCANNER_TERMINAL_SESSION_SECRET"].encode()
    parsed = urlsplit(origin)
    if (not token or user_id <= 0 or len(secret) < 32
            or parsed.scheme != "https" or not parsed.hostname
            or parsed.path or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError("Invalid terminal ingress configuration")
    return token, user_id, origin, secret

def verify_init_data(raw, token, allowed_user_id, now=None):
    if not isinstance(raw, str) or len(raw) > MAX_BODY:
        return False
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          max_num_fields=32)
        fields = dict(pairs)
        if len(fields) != len(pairs) or "hash" not in fields:
            return False
        digest = fields.pop("hash")
        if len(digest) != 64:
            return False
        auth_date = int(fields["auth_date"])
        now = int(time.time() if now is None else now)
        if auth_date > now + 30 or now - auth_date > INITDATA_MAX_AGE:
            return False
        user_id = json.loads(fields["user"])["id"]
        if type(user_id) is not int or user_id != allowed_user_id:
            return False
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected = hmac.new(key, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest.lower(), expected)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False

def sign_session(user_id, secret, now=None):
    issued = int(time.time() if now is None else now)
    nonce = secrets.token_hex(12)
    data = f"{user_id}.{issued}.{nonce}"
    tag = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{tag}"

def verify_session(value, user_id, secret, now=None):
    try:
        uid, timestamp, nonce, signature = value.split(".")
        issued = int(timestamp)
        now = int(time.time() if now is None else now)
        if (int(uid) != user_id or issued > now + 30 or now - issued > SESSION_TTL
                or len(nonce) != 24 or len(signature) != 64):
            return False
        expected = hmac.new(secret, f"{uid}.{timestamp}.{nonce}".encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except (ValueError, AttributeError):
        return False

LOGIN_HTML = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BybitScanner Terminal</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<body><p id="status">Авторизация через Telegram…</p>
<script>
(async()=>{
 const w=window.Telegram&&Telegram.WebApp;
 if(!w||!w.initData){document.getElementById("status").textContent="Откройте Терминал через Telegram.";return;}
 try{
  const r=await fetch("/_telegram_auth",{method:"POST",credentials:"same-origin",
   headers:{"Content-Type":"text/plain"},body:w.initData,cache:"no-store"});
  if(!r.ok)throw Error("auth");
  const params=new URLSearchParams(location.search);
  const view=params.get("view");
  const mode=params.get("mode"), symbol=params.get("symbol"), timeframe=params.get("timeframe");
  if(view==="positions" && !mode){location.replace("/?view=positions");return;}
  if(!["EDITOR","TERMINAL"].includes(mode) ||
     !/^[A-Z0-9]{2,32}USDT$/.test(symbol||"") ||
     !["15s","1m","5m","15m","1h","1d"].includes(timeframe)){
    location.replace("/");return;
  }
  const target=new URL("/",location.origin);
  target.searchParams.set("mode",mode);
  target.searchParams.set("symbol",symbol);
  target.searchParams.set("timeframe",timeframe);
  location.replace(target.pathname+target.search);
 }catch(e){document.getElementById("status").textContent="Доступ не разрешён.";}
})();
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    config = None

    def log_message(self, format, *args):
        # Do not log request cookies, signed initData or secrets.
        pass

    def _respond(self, code, body=b"", content_type="text/plain; charset=utf-8",
                 cookie=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline' https://telegram.org; connect-src 'self'; style-src 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _origin_ok(self):
        return self.headers.get("Origin") == self.config[2]

    def _auth(self):
        cookie = self.headers.get("Cookie", "")
        values = [c.strip().split("=", 1)[1] for c in cookie.split(";")
                  if c.strip().startswith("__Host-terminal=")]
        if len(values) != 1 or not verify_session(values[0], self.config[1], self.config[3]):
            return False
        method = self.headers.get("X-Original-Method", "")
        upgrade = self.headers.get("X-Original-Upgrade", "").lower()
        if method not in ("GET", "HEAD", "OPTIONS") or upgrade == "websocket":
            return self.headers.get("X-Original-Origin") == self.config[2]
        return True

    def do_GET(self):
        if self.path == "/_auth":
            self._respond(204 if self._auth() else 401)
        elif self.path.split("?", 1)[0] == "/login":
            self._respond(200, LOGIN_HTML.encode(), "text/html; charset=utf-8")
        else:
            self._respond(404)

    def do_POST(self):
        if self.path != "/_telegram_auth" or not self._origin_ok():
            self._respond(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if size < 1 or size > MAX_BODY:
            self._respond(413)
            return
        raw = self.rfile.read(size).decode("utf-8", "strict")
        if not verify_init_data(raw, self.config[0], self.config[1]):
            self._respond(403)
            return
        session = sign_session(self.config[1], self.config[3])
        self._respond(204, cookie=f"__Host-terminal={session}; Path=/; Max-Age={SESSION_TTL}; Secure; HttpOnly; SameSite=Strict")

def main():
    Handler.config = _config()
    # Explicit loopback binding; no public port and no trading runtime import.
    ThreadingHTTPServer(("127.0.0.1", 8091), Handler).serve_forever()

if __name__ == "__main__":
    main()
