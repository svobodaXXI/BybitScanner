"""Read-only market rankings from the existing Bybit public candle source."""
from collections import deque
from dataclasses import dataclass
from threading import Lock
from datetime import datetime, timedelta, timezone
from math import isfinite
from statistics import median
import time

PERIOD_MS = 15 * 60_000
HISTORY_BARS = 97
WINDOWS = (("15м", 1), ("1ч", 4), ("4ч", 16), ("24ч", 96))
TOP = 5
REQUEST_SPACING_SECONDS = 0.25
COLLECTION_LIMIT_SECONDS = 300
MAX_AGE_MS = PERIOD_MS + COLLECTION_LIMIT_SECONDS * 1000


@dataclass(frozen=True)
class MarketRow:
    symbol: str
    changes: tuple[float, ...]
    turnover_ratio: float | None
    range_ratio: float | None
    turnover_15m: float = 0.0

    @property
    def activity(self):
        if self.turnover_ratio is None or self.range_ratio is None:
            return None
        if self.turnover_ratio < 2 or self.range_ratio < 1.5:
            return None
        score = self.turnover_ratio * self.range_ratio
        return score if isfinite(score) else None


@dataclass(frozen=True)
class MarketSnapshot:
    as_of_ms: int
    expected: int
    rows: tuple[MarketRow, ...]


def rank_candles(symbol, frame, cutoff_ms):
    """Reject gaps, forming candles and incomplete history; use close-to-close."""
    try:
        records = frame.to_dict("records")
        if len(records) != HISTORY_BARS:
            return None
        closes, turnover, ranges = [], [], []
        for i, row in enumerate(records):
            expected = cutoff_ms - (HISTORY_BARS - i) * PERIOD_MS
            if float(row["time"]) != expected:
                return None
            op, high, low, close, value = (
                float(row[key]) for key in ("open", "high", "low", "close", "turnover")
            )
            if (not all(isfinite(x) for x in (op, high, low, close, value))
                    or not 0 < low <= min(op, close) <= max(op, close) <= high
                    or value < 0):
                return None
            closes.append(close)
            turnover.append(value)
            ranges.append((high - low) / op)
        changes = tuple((closes[-1] / closes[-1 - n] - 1) * 100 for _, n in WINDOWS)
        if not all(isfinite(x) for x in (*changes, *ranges)):
            return None
        base_turnover, base_range = median(turnover[:-1]), median(ranges[:-1])
        tr = turnover[-1] / base_turnover if base_turnover > 0 else None
        vr = ranges[-1] / base_range if base_range > 0 else None
        return MarketRow(symbol, changes,
                         tr if tr is not None and isfinite(tr) else None,
                         vr if vr is not None and isfinite(vr) else None, turnover[-1])
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def collect_market(get_symbols, get_candles, stop_event, *, clock=time.time,
                   monotonic=time.monotonic):
    """On-demand single-pass collection; never starts Scanner or subscribes L2."""
    cutoff = int(clock() * 1000) // PERIOD_MS * PERIOD_MS
    deadline = monotonic() + COLLECTION_LIMIT_SECONDS
    symbols = sorted(set(get_symbols()))
    rows = []
    for symbol in symbols:
        if stop_event.is_set() or monotonic() >= deadline:
            break
        if not isinstance(symbol, str) or not symbol.endswith("USDT") or not symbol[:-4].isalnum():
            continue
        started = monotonic()
        try:
            frame = get_candles(symbol, "15", HISTORY_BARS, end_ms=cutoff - 1)
            row = rank_candles(symbol, frame, cutoff)
            if row is not None:
                rows.append(row)
        except Exception:
            # One failed instrument must not create fake zero returns.
            pass
        if stop_event.wait(max(0, REQUEST_SPACING_SECONDS - (monotonic() - started))):
            break
    return MarketSnapshot(cutoff, len(symbols), tuple(rows))


def format_market(snapshot, *, now_ms, tapes=()):
    if not 0 <= now_ms - snapshot.as_of_ms <= MAX_AGE_MS:
        return "Рынок: данные устарели. Ожидается автоматическое обновление."
    stamp = datetime.fromtimestamp(snapshot.as_of_ms / 1000,
                                  timezone(timedelta(hours=3))).strftime("%d.%m %H:%M")
    rows = snapshot.rows
    lines = ["📊 Рынок Bybit · USDT perpetual", f"Закрытые свечи до {stamp} МСК",
             f"Покрытие: {len(rows)}/{snapshot.expected}"]
    if not snapshot.expected or not rows:
        return "\n".join(lines + ["Подтверждённая история недоступна."])
    if len(rows) != snapshot.expected:
        lines.append("Неполный охват — рейтинг только по проверенным инструментам.")
    lines.extend(["", "🔥 Монеты в игре"])
    fresh = {t.symbol: t for t in tapes if t.activity_state(now_ms) != "UNKNOWN"}
    lines.append(f"Свежая лента: {len(fresh)}/{snapshot.expected} · выборочная проверка")
    active = [(r, fresh[r.symbol]) for r in rows if r.symbol in fresh
              and fresh[r.symbol].activity_state(now_ms).startswith("ACTIVE_")]
    active.sort(key=lambda item: (
        -(item[0].activity or 0), -item[1].turnover_1m,
        -item[1].prints_1m, item[0].symbol))
    for r, t in active[:TOP]:
        bound = "≥" if t.truncated_1m else ""
        state = ("живой поток" if t.activity_state(now_ms) == "ACTIVE_SUSTAINED_OBSERVED"
                 else "всплеск; непрерывность н/д")
        lines.append(f"{r.symbol} · {bound}{t.prints_1m} сделок/мин · "
                     f"{bound}{t.turnover_1m:,.0f} USDT/мин · {state}")
    if not active:
        lines.append("Нет подтверждённой активности в свежей проверенной выборке.")
    lines.append("Пробный фильтр: 30 сделок/мин, 3000 USDT/мин; "
                 "последний принт ≤5с; активность в 5 из 6 интервалов для живого потока.")
    for heading, direction in (("🟢 Лидеры роста", 1), ("🔴 Лидеры падения", -1)):
        lines.extend(["", heading])
        for index, (window, _) in enumerate(WINDOWS):
            leaders = sorted((r for r in rows if direction * r.changes[index] > 0),
                             key=lambda r: (-direction * r.changes[index], r.symbol))[:TOP]
            lines.extend(["", f"{window}:"])
            lines.extend(f"{r.symbol} {r.changes[index]:+.2f}%" for r in leaders)
            if not leaders:
                lines.append("—")
    lines.extend(["", "ΔOI и ликвидации: н/д."])
    return "\n".join(lines)


# Initial shadow-calibration thresholds from owner sample in issue #1255.
# Informational provisional gates only; never trading admission rules.
TAPE_LIMIT = 1000
TAPE_FRESH_MS = 10_000
TAPE_LAST_PRINT_MS = 5_000
TAPE_MIN_PRINTS = 30
TAPE_MIN_TURNOVER = 3000
TAPE_MIN_BUCKETS = 5


@dataclass(frozen=True)
class TapeObservation:
    """Timestamped REST observation, not a proof of complete exchange flow."""

    symbol: str
    as_of_ms: int
    last_print_ms: int
    prints_1m: int
    prints_5m: int
    turnover_1m: float
    turnover_5m: float
    active_10s_buckets: int
    truncated_1m: bool
    truncated_5m: bool

    def activity_state(self, now_ms):
        """Separate observed sustained activity, capped bursts and unknown data."""
        if not 0 <= now_ms - self.as_of_ms <= TAPE_FRESH_MS:
            return "UNKNOWN"
        if now_ms - self.last_print_ms > TAPE_LAST_PRINT_MS:
            return "QUIET"
        if (self.prints_1m < TAPE_MIN_PRINTS
                or self.turnover_1m < TAPE_MIN_TURNOVER):
            return "UNKNOWN" if self.truncated_1m else "QUIET"
        if self.active_10s_buckets >= TAPE_MIN_BUCKETS:
            return "ACTIVE_SUSTAINED_OBSERVED"
        if self.truncated_1m:
            # A capped busy tape proves recent intensity, but does not prove
            # continuous activity in the unobserved prefix of the minute.
            return "ACTIVE_BURST_OBSERVED"
        return "QUIET"


def observe_recent_trades(symbol, response):
    """Parse Bybit V5 linear recent-trade, with conservative capped windows.

    Invalid, empty or inconsistent responses yield None, never fake zeros.
    Observed counts/notional are lower bounds when the 1000-row cap truncates
    a window. Duplicate execution IDs count once; conflicting facts reject
    the observation. No subscription, request or order side effects.
    """
    try:
        if (not isinstance(symbol, str) or not symbol.endswith("USDT")
                or not symbol[:-4].isalnum() or response["retCode"] != 0):
            return None
        if type(response["time"]) is not int or response["time"] <= 0:
            return None
        now = response["time"]
        result = response["result"]
        if result["category"] != "linear":
            return None
        rows = result["list"]
        if not isinstance(rows, list) or not 0 < len(rows) <= TAPE_LIMIT:
            return None
        trades = {}
        for row in rows:
            if row["symbol"] != symbol:
                return None
            trade_id = row["execId"]
            if not isinstance(trade_id, str) or not trade_id:
                return None
            raw_time = row["time"]
            if not isinstance(raw_time, str) or not raw_time.isascii() or not raw_time.isdecimal():
                return None
            ts = int(raw_time)
            price, size = float(row["price"]), float(row["size"])
            notional = price * size
            side = row["side"]
            if (not 0 < ts <= now or not isfinite(price) or not isfinite(size)
                    or not isfinite(notional) or price <= 0 or size <= 0
                    or notional <= 0 or side not in ("Buy", "Sell")):
                return None
            fact = (ts, price, size, side)
            if trade_id in trades and trades[trade_id] != fact:
                return None
            trades[trade_id] = fact
        stamps = [fact[0] for fact in trades.values()]
        oldest, last = min(stamps), max(stamps)
        m1 = [f for f in trades.values() if now - 60_000 < f[0] <= now]
        m5 = [f for f in trades.values() if now - 300_000 < f[0] <= now]
        v1 = sum(f[1] * f[2] for f in m1)
        v5 = sum(f[1] * f[2] for f in m5)
        if not isfinite(v1) or not isfinite(v5):
            return None
        capped = len(rows) == TAPE_LIMIT
        return TapeObservation(
            symbol, now, last, len(m1), len(m5), v1, v5,
            len({(now - f[0]) // 10_000 for f in m1}),
            capped and oldest > now - 60_000,
            capped and oldest > now - 300_000,
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None


# One public request at a time; one in four tape slots rotates through
# the entire known universe rather than repeatedly checking just the winners.
RADAR_PRIORITY_LIMIT = 12
RADAR_INTERVAL_SECONDS = 0.5


class MarketRadar:
    """Single-writer, lock-protected cache; Telegram reads without exchange I/O.

    Candle sweep and recent-trade sampling interleave on one worker.
    Tape coverage is deliberately partial: a REST sweep cannot prove that
    every symbol is active at one common instant. Never keep expired prints
    in the live leaderboard or carry forward a failed observation.
    """

    def __init__(self):
        self._lock = Lock()
        self._snapshot = None
        self._tapes = {}
        self._pending = deque()
        self._rows = []
        self._symbols = ()
        self._priority = ()
        self._cutoff = None
        self._deadline = 0
        self._slot = 0
        self._priority_index = 0
        self._universe_index = 0
        self._turn = 0

    def clear(self):
        # Called by the sole worker when Scanner is not confirmed RUNNING.
        with self._lock:
            self._snapshot = None
            self._tapes.clear()
        self._pending.clear()
        self._rows = []
        self._symbols = ()
        self._priority = ()
        self._cutoff = None
        self._slot = self._priority_index = self._universe_index = self._turn = 0

    def card(self, now_ms):
        with self._lock:
            snapshot = self._snapshot
            tapes = tuple(self._tapes.values())
        if snapshot is None:
            return ("Рынок: фоновый снимок ещё не готов. "
                    "Обновляется автоматически при работающем Сканере.")
        return format_market(snapshot, now_ms=now_ms, tapes=tapes)

    def _publish(self):
        rows = tuple(self._rows)
        anomaly = sorted((r for r in rows if r.activity is not None),
                         key=lambda r: (-r.activity, r.symbol))
        liquid = sorted(rows, key=lambda r: (-r.turnover_15m, r.symbol))
        self._priority = tuple(dict.fromkeys(
            r.symbol for r in (*anomaly[:RADAR_PRIORITY_LIMIT // 2],
                               *liquid[:RADAR_PRIORITY_LIMIT])))
        self._priority = self._priority[:RADAR_PRIORITY_LIMIT]
        self._priority_index = 0
        with self._lock:
            self._snapshot = MarketSnapshot(self._cutoff, len(self._symbols), rows)
            allowed = {r.symbol for r in rows}
            self._tapes = {s: t for s, t in self._tapes.items() if s in allowed}

    def step(self, get_symbols, get_candles, get_recent_trades, *,
             now_ms, monotonic_now):
        """At most one symbol/candle/tape request per step (universe pagination
        remains owned by the existing source). A failed symbol is isolated."""
        cutoff = now_ms // PERIOD_MS * PERIOD_MS
        if self._pending and monotonic_now >= self._deadline:
            self._pending.clear()
            self._publish()
        if not self._pending and self._cutoff != cutoff:
            symbols = tuple(sorted(set(get_symbols())))
            self._symbols = symbols
            self._cutoff = cutoff
            self._rows = []
            self._pending = deque(symbols)
            self._deadline = monotonic_now + COLLECTION_LIMIT_SECONDS
            if not self._pending:
                self._publish()
            return

        self._turn += 1
        if self._pending and (not self._priority or self._turn % 2 == 0):
            symbol = self._pending.popleft()
            try:
                row = rank_candles(symbol, get_candles(
                    symbol, "15", HISTORY_BARS, end_ms=self._cutoff - 1), self._cutoff)
                if row is not None:
                    self._rows.append(row)
            except Exception:
                pass
            if not self._pending:
                self._publish()
            return

        if not self._symbols:
            return
        # Sampling of the full universe continues during the candle refresh.
        self._slot += 1
        if self._priority and self._slot % 4 != 0:
            symbol = self._priority[self._priority_index % len(self._priority)]
            self._priority_index += 1
        else:
            symbol = self._symbols[self._universe_index % len(self._symbols)]
            self._universe_index += 1
        try:
            observation = observe_recent_trades(symbol, get_recent_trades(symbol))
        except Exception:
            observation = None
        with self._lock:
            if observation is None:
                self._tapes.pop(symbol, None)
            else:
                self._tapes[symbol] = observation
