"""Read-only market rankings from the existing Bybit public candle source."""
from dataclasses import dataclass
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
                         vr if vr is not None and isfinite(vr) else None)
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


def format_market(snapshot, *, now_ms):
    if not 0 <= now_ms - snapshot.as_of_ms <= MAX_AGE_MS:
        return "Рынок: данные устарели. Запросите рынок заново."
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
    active = sorted((r for r in rows if r.activity is not None),
                    key=lambda r: (-r.activity, r.symbol))[:TOP]
    for r in active:
        lines.append(f"{r.symbol} · оборот ×{r.turnover_ratio:.1f} · диапазон ×{r.range_ratio:.1f}")
    if not active:
        lines.append("Нет инструментов выше порога активности.")
    lines.append("15м против медианы предыдущих 24ч; оборот ≥2×, диапазон ≥1,5×.")
    for heading, direction in (("🟢 Лидеры роста", 1), ("🔴 Лидеры падения", -1)):
        lines.extend(["", heading])
        for index, (window, _) in enumerate(WINDOWS):
            leaders = sorted((r for r in rows if direction * r.changes[index] > 0),
                             key=lambda r: (-direction * r.changes[index], r.symbol))[:TOP]
            lines.extend(["", f"{window}:"])
            lines.extend(f"{r.symbol} {r.changes[index]:+.2f}%" for r in leaders)
            if not leaders:
                lines.append("—")
    lines.extend(["", "Число сделок и ΔOI: н/д."])
    return "\n".join(lines)
