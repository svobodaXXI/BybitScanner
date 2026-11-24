"""Bounded official Bybit public trade archive retrieval, no account API."""
from datetime import date
from pathlib import Path
from time import monotonic
from urllib.request import Request, urlopen

from research.simulator_v2.timeline import SYMBOL_RE
from research.simulator_v2.trade_archive import MAX_ARCHIVE_BYTES


def fetch_public_trade_day(destination: Path, *, symbol: str, utc_day: date,
                           byte_limit: int = MAX_ARCHIVE_BYTES) -> int:
    """Fetch one immutable closed-day archive into a caller-owned temporary file."""
    if (not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT")
            or type(utc_day) is not date
            or destination.name != f"{symbol}{utc_day.isoformat()}.csv.gz"
            or not 0 < byte_limit <= MAX_ARCHIVE_BYTES):
        raise ValueError("invalid public trade archive coordinates")
    url = f"https://public.bybit.com/trading/{symbol}/{destination.name}"
    request = Request(url, method="GET",
                      headers={"User-Agent": "BybitScanner-SimulatorV2-Research/1.0"})
    size = 0
    deadline = monotonic() + 180
    with urlopen(request, timeout=30) as response, destination.open("xb") as output:
        if response.geturl() != url:
            raise ValueError("unapproved public archive redirect")
        while True:
            if monotonic() > deadline:
                raise TimeoutError("public trade archive download deadline")
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > byte_limit:
                raise ValueError("bounded public trade archive exceeds size limit")
            output.write(block)
    if size == 0:
        raise ValueError("empty public Bybit daily archive")
    return size
