"""Bounded, read-only public trade burst for the informational market radar.

No credentials, background threads, reconnect loop, Robot hub or order access.
Not wired into the live Telegram worker until resource acceptance is established.
"""
from dataclasses import dataclass
from math import isfinite
import json
import time

PERIOD_SECONDS = 300
WINDOW_SECONDS = 15
ACK_SECONDS = 15
CPU_SECONDS = 12
MAX_BYTES = 32 * 1024 * 1024
MAX_TRADES = 100_000
PUBLIC_URL = "wss://stream.bybit.com/v5/public/linear"


class BurstCadence:
    """Single-owner, start-to-start cadence, including failed attempts."""

    def __init__(self):
        self.next_due = None

    def claim(self, now):
        if self.next_due is not None and now < self.next_due:
            return False
        self.next_due = now + PERIOD_SECONDS
        return True


@dataclass(frozen=True)
class BurstRow:
    symbol: str
    prints: int
    turnover: float
    last_print_ms: int


@dataclass(frozen=True)
class BurstReceipt:
    status: str
    expected: int
    acked: int
    start_ms: int | None
    end_ms: int | None
    rows: tuple[BurstRow, ...]
    raw_bytes: int
    cpu_seconds: float


class TradeWindow:
    """Common event-time window; observed trades only, never inferred zeros."""

    def __init__(self, symbols, start_ms):
        self.symbols = frozenset(symbols)
        self.start_ms = start_ms
        self.end_ms = start_ms + WINDOW_SECONDS * 1000
        self._seen = {}
        self._rows = {}

    def ingest(self, message):
        topic = message["topic"]
        if not isinstance(topic, str) or not topic.startswith("publicTrade."):
            raise ValueError("unexpected topic")
        symbol = topic[len("publicTrade."):]
        if symbol not in self.symbols:
            raise ValueError("unexpected symbol")
        rows = message["data"]
        if not isinstance(rows, list) or not 0 < len(rows) <= 1024:
            raise ValueError("invalid trade batch")
        for trade in rows:
            ts, identity = trade["T"], trade["i"]
            if (trade["s"] != symbol or type(ts) is not int or ts <= 0
                    or not isinstance(identity, str) or not identity
                    or trade["S"] not in ("Buy", "Sell")):
                raise ValueError("invalid trade identity")
            if not self.start_ms <= ts < self.end_ms:
                continue
            price, size = float(trade["p"]), float(trade["v"])
            notional = price * size
            if not all(isfinite(x) and x > 0 for x in (price, size, notional)):
                raise ValueError("invalid trade amount")
            key = (symbol, identity)
            fact = (ts, price, size, trade["S"])
            if key in self._seen:
                if self._seen[key] != fact:
                    raise ValueError("conflicting duplicate")
                continue
            if len(self._seen) >= MAX_TRADES:
                raise OverflowError("trade limit")
            self._seen[key] = fact
            count, amount, last = self._rows.get(symbol, (0, 0.0, 0))
            amount += notional
            if not isfinite(amount):
                raise ValueError("invalid aggregate")
            self._rows[symbol] = (count + 1, amount, max(last, ts))

    def rows(self):
        return tuple(BurstRow(symbol, *values)
                     for symbol, values in sorted(self._rows.items()))


def sample_public_burst(symbols, *, should_continue=lambda: True,
                        connect=None, monotonic=time.monotonic,
                        clock=time.time, cpu_clock=time.thread_time):
    """One 15-second post-ACK window, with no retry or partial ranking.

    Event timestamps depend on the host/exchange clocks. A completed window
    proves observations, not exchange completeness or minute-long continuity.
    The caller owns Scanner lifecycle and the five-minute cadence.
    """
    import websocket

    symbols = tuple(sorted(set(symbols)))
    if (not symbols or any(not isinstance(s, str) or not s.endswith("USDT")
                           or not s[:-4].isalnum() for s in symbols)):
        raise ValueError("invalid universe")
    topics = ["publicTrade." + s for s in symbols]
    if len(json.dumps(topics)) > 21000:
        raise ValueError("subscription args limit")
    batches = {str(i): topics[i:i + 100]
               for i in range(0, len(topics), 100)}
    acked = set()
    window = None
    deadline = None
    wire = 0
    started, cpu_start = monotonic(), cpu_clock()
    next_ping = started + 20
    status = "UNAVAILABLE"
    ws = None

    def guard():
        if not should_continue():
            return "CANCELLED"
        if cpu_clock() - cpu_start >= CPU_SECONDS or wire > MAX_BYTES:
            return "RESOURCE_LIMIT"
        return None

    try:
        if guard() is not None:
            status = guard() or "CANCELLED"
        else:
            factory = connect or websocket.create_connection
            ws = factory(PUBLIC_URL, timeout=3)
            ws.settimeout(0.5)
            for rid, batch in batches.items():
                status = guard() or "UNAVAILABLE"
                if status != "UNAVAILABLE":
                    break
                ws.send(json.dumps({"op": "subscribe", "req_id": rid,
                                    "args": batch}))
            else:
                while True:
                    status = guard() or "UNAVAILABLE"
                    if status != "UNAVAILABLE":
                        break
                    now = monotonic()
                    if deadline is not None and now >= deadline:
                        status = "OBSERVED"
                        break
                    if deadline is None and now - started >= ACK_SECONDS:
                        status = "ACK_INCOMPLETE"
                        break
                    if now >= next_ping:
                        ws.send('{"op":"ping"}')
                        next_ping = now + 20
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        status = "DISCONNECTED"
                        break
                    wire += len(raw.encode("utf-8") if isinstance(raw, str) else raw)
                    if wire > MAX_BYTES:
                        status = "RESOURCE_LIMIT"
                        break
                    data = json.loads(raw)
                    if data.get("op") == "subscribe":
                        rid = data.get("req_id")
                        if data.get("success") is not True or rid not in batches:
                            status = "ACK_REJECTED"
                            break
                        acked.add(rid)
                        if window is None and len(acked) == len(batches):
                            window = TradeWindow(symbols, int(clock() * 1000))
                            deadline = monotonic() + WINDOW_SECONDS
                    elif window is not None and "topic" in data:
                        window.ingest(data)
    except OverflowError:
        status = "RESOURCE_LIMIT"
    except (ValueError, KeyError, TypeError, AttributeError):
        status = "INVALID_DATA"
    except Exception:
        status = "UNAVAILABLE"
    finally:
        if ws is not None:
            try:
                ws.close(timeout=1)
            except Exception:
                pass

    # A failed/cancelled cycle cannot publish an earlier or partial leaderboard.
    if status == "OBSERVED":
        status = guard() or status
    return BurstReceipt(status, len(symbols),
                        sum(len(batches[rid]) for rid in acked),
                        window.start_ms if window else None,
                        window.end_ms if status == "OBSERVED" else None,
                        window.rows() if status == "OBSERVED" else (),
                        wire, cpu_clock() - cpu_start)
