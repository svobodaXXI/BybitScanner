"""Causal M1 input seam for the owner-approved Machine Time laboratory.

Historical bars are released one CLOSED minute at a time. M5/H1 become
visible only on their own full UTC close. No network, filesystem, credentials,
production Scanner/Robot service or PAPER/REAL account is touched.

The optional neckline probe invokes the actual production Scanner snapshot
builder and Robot's existing pattern-confirmation verifier, not a rewritten
detector or trading strategy. It emits evidence only: no order/fill/PnL.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


M1_MS = 60_000
M5_MS = 300_000
H1_MS = 3_600_000
SYMBOL = re.compile(r"^[A-Z0-9]{3,30}$")


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean OHLCV input")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid OHLCV input") from exc
    if not number.is_finite():
        raise ValueError("non-finite OHLCV input")
    return number


@dataclass(frozen=True)
class ClosedBar:
    start_ms: int
    interval_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.interval_ms

    @classmethod
    def from_m1_row(cls, row: Mapping[str, object]) -> "ClosedBar":
        stamp = row["time"]
        if isinstance(stamp, bool):
            raise ValueError("invalid M1 start time")
        try:
            start = int(stamp)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("invalid M1 start time") from exc
        if str(start) != str(stamp) or start < 0 or start % M1_MS:
            raise ValueError("unaligned M1 start time")
        values = {key: _decimal(row[key]) for key in
                  ("open", "high", "low", "close", "volume")}
        if (min(values["open"], values["high"], values["low"], values["close"]) <= 0
                or values["volume"] < 0
                or values["low"] > min(values["open"], values["close"])
                or values["high"] < max(values["open"], values["close"])):
            raise ValueError("invalid M1 OHLCV")
        return cls(start, M1_MS, **values)

    def scanner_row(self) -> dict[str, object]:
        return {
            "time": self.start_ms, "open": str(self.open),
            "high": str(self.high), "low": str(self.low),
            "close": str(self.close), "volume": str(self.volume),
        }


class ClosedPrefix(Sequence[ClosedBar]):
    """O(1) historical view pinned to a close, never exposing future appends."""

    def __init__(self, bars: list[ClosedBar]) -> None:
        self.__bars = bars
        self.__length = len(bars)

    def __len__(self) -> int:
        return self.__length

    def __getitem__(self, key):
        if isinstance(key, slice):
            return tuple(self.__bars[i] for i in range(*key.indices(self.__length)))
        if not isinstance(key, int):
            raise TypeError("history indices must be integers")
        index = key + self.__length if key < 0 else key
        if not 0 <= index < self.__length:
            raise IndexError(key)
        return self.__bars[index]


@dataclass(frozen=True)
class ClosedMinuteStep:
    symbol: str
    virtual_time_ms: int
    minute: ClosedBar
    newly_closed_m5: ClosedBar | None
    newly_closed_h1: ClosedBar | None
    m1_history: ClosedPrefix
    m5_history: ClosedPrefix
    h1_history: ClosedPrefix


class CausalMinuteFeed:
    """One symbol, contiguous preloaded M1, deterministic causal M5/H1."""

    def __init__(self, symbol: str) -> None:
        if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol) or not symbol.endswith("USDT"):
            raise ValueError("invalid single SIMULATION symbol")
        self.symbol = symbol
        self._minute: list[ClosedBar] = []
        self._five: list[ClosedBar] = []
        self._hour: list[ClosedBar] = []
        self._pending_five: list[ClosedBar] = []
        self._pending_hour: list[ClosedBar] = []

    @staticmethod
    def _build_closed(
        pending: list[ClosedBar], next_bar: ClosedBar, interval: int,
    ) -> tuple[list[ClosedBar], ClosedBar | None]:
        bucket_start = (next_bar.start_ms // interval) * interval
        if pending and pending[0].start_ms // interval != next_bar.start_ms // interval:
            pending = []
        pending.append(next_bar)
        complete = (len(pending) == interval // M1_MS
                    and pending[0].start_ms == bucket_start
                    and next_bar.end_ms == bucket_start + interval)
        aggregate = None
        if complete:
            aggregate = ClosedBar(
                bucket_start, interval,
                pending[0].open, max(item.high for item in pending),
                min(item.low for item in pending), pending[-1].close,
                sum((item.volume for item in pending), Decimal(0)),
            )
        if next_bar.end_ms == bucket_start + interval:
            pending = []
        return pending, aggregate

    def observe_closed_m1(self, row: Mapping[str, object]) -> ClosedMinuteStep:
        bar = ClosedBar.from_m1_row(row)
        if self._minute and bar.start_ms != self._minute[-1].end_ms:
            raise ValueError("M1 gaps/duplicates/out-of-order: simulation stopped")
        self._minute.append(bar)
        self._pending_five, m5 = self._build_closed(self._pending_five, bar, M5_MS)
        self._pending_hour, h1 = self._build_closed(self._pending_hour, bar, H1_MS)
        if m5 is not None:
            self._five.append(m5)
        if h1 is not None:
            self._hour.append(h1)
        return ClosedMinuteStep(
            self.symbol, bar.end_ms, bar, m5, h1,
            ClosedPrefix(self._minute), ClosedPrefix(self._five),
            ClosedPrefix(self._hour),
        )


@dataclass(frozen=True)
class OriginalRobotPatternProof:
    """Original Scanner snapshot + original Robot verifier; observational ONLY."""

    pattern: str
    timeframe: str
    confirmed_at_ms: int
    frozen_snapshot: Mapping[str, object]
    robot_proof: object


def original_neckline_proofs(
    step: ClosedMinuteStep, *, source_window: int,
) -> tuple[OriginalRobotPatternProof, ...]:
    """One genuine Scanner/Robot path. No fabricated EntryIntent/order fill.

    The window MUST be supplied from the owning Scanner configuration; it is
    not a new strategy lookback. Future pattern families require their own
    original Scanner-to-Robot handoff, not rules copied into this module.
    """
    if type(source_window) is not int or source_window < 1:
        raise ValueError("source Scanner window must be a positive integer")

    from geometry.double_extremum import frozen_neckline_snapshot
    from terminal.application.robot_reentry_adapter import proven_pattern_entry

    results: list[OriginalRobotPatternProof] = []
    for timeframe, history, newly_closed in (
        ("1", step.m1_history, step.minute),
        ("5", step.m5_history, step.newly_closed_m5),
    ):
        if newly_closed is None or len(history) < 9:
            continue
        rows = [item.scanner_row() for item in history[-source_window:]]
        frozen = frozen_neckline_snapshot(step.symbol, timeframe, rows)
        if frozen is None:
            continue
        proof = proven_pattern_entry(frozen, now_ms=step.virtual_time_ms)
        if proof is None:
            # Scanner snapshot may be observational; it must never bypass Robot.
            continue
        if proof.confirmed_at_ms != step.virtual_time_ms:
            raise ValueError("Robot proof is not from the current closed bar")
        results.append(OriginalRobotPatternProof(
            proof.pattern, timeframe, proof.confirmed_at_ms, frozen, proof,
        ))
    return tuple(results)
