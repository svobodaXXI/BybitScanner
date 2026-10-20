"""Safe workspace links and local QR creation, without credential-bearing URLs.

This module does not start a server or send Telegram messages. Call only after
the HTTPS endpoint is authenticated and verified reachable by the owner service.
"""
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
import ipaddress
import re


def workspace_link(base_url: str, mode: str, symbol: str, timeframe: str, signal_id: str | None = None) -> str:
    parts = urlsplit(base_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.port not in (None, 443)):
        raise ValueError("A plain authenticated HTTPS origin is required")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith(".local") or host.endswith(".localhost"):
        raise ValueError("A publicly reachable HTTPS hostname is required")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private or reserved HTTPS IP address")
    except ValueError as exc:
        if str(exc) == "Private or reserved HTTPS IP address":
            raise
    if mode not in ("EDITOR", "TERMINAL"):
        raise ValueError("Unsupported workspace mode")
    if not re.fullmatch(r"[A-Z0-9]{2,32}USDT", symbol):
        raise ValueError("Invalid trading symbol")
    if timeframe not in ("15s", "1m", "5m", "15m", "1h", "1d"):
        raise ValueError("Invalid timeframe")
    if signal_id is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", signal_id):
        raise ValueError("Invalid signal identifier")
    values = {"mode": mode, "symbol": symbol, "timeframe": timeframe}
    if signal_id:
        values["signal_id"] = signal_id
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(values), ""))


def write_workspace_qr(url: str, destination: Path) -> Path:
    """Generate QR locally: no third-party image API, no secrets in URL."""
    if urlsplit(url).scheme != "https":
        raise ValueError("HTTPS URL required")
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("Install project QR dependency before QR generation") from exc
    image = qrcode.make(url)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination
