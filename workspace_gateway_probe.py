"""Check authenticated Cloudflare Access reachability before owner READY messages.

A public URL returning HTTP 200 without credentials is NOT considered safe.
Deployment must provide a restricted Cloudflare Access service token; never
include these values in a link, QR, console output or Telegram messages.
"""
from urllib.parse import urlsplit, urljoin
import requests


def verify_workspace_gateway(url: str, *, client_id: str, client_secret: str,
                             timeout: float = 5.0) -> bool:
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment or not client_id or not client_secret):
        return False
    base = parts._replace(path=parts.path or "/", query="", fragment="").geturl()
    try:
        anonymous = requests.get(base, timeout=timeout, allow_redirects=False)
        # A public 200 is unsafe, including a gateway with no Access policy.
        if anonymous.status_code not in (302, 303, 307, 308, 401, 403):
            return False
        if anonymous.status_code in (302, 303, 307, 308):
            target = anonymous.headers.get("Location", "")
            # Authenticate only if the redirect is a Cloudflare Access login.
            login = urlsplit(urljoin(base, target))
            if login.scheme != "https" or login.hostname != parts.hostname or not login.path.startswith("/cdn-cgi/access/login"):
                return False
        authorized = requests.get(
            base,
            headers={"CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": client_secret},
            timeout=timeout,
            allow_redirects=False,
        )
        return authorized.status_code == 200
    except requests.RequestException:
        return False
