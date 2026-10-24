"""
mirror_levels.levels

M1 of #613: one registry of candidate mirror levels from every source.

A ``MirrorLevel`` wraps the existing ``geometry.naked_retest.Boundary`` (so the
breakout and first-retest mechanics stay the existing, tested ones) with
provenance: symbol, timeframe, source, pattern, side, anchors, when the level
became known (``confirmed_at_ms``) and a deterministic ``level_id``.

Sources (adapters below, no new pattern detector):
- ``pattern_boundary``: Wedge (``mirror_retest_observer.boundaries_from_candidate_snapshot``),
  any engine geometry with index-based ``upper_line``/``lower_line`` (Triangle,
  Broadening/HORN, channels), Ikigai Box ``box_high``/``box_low``, L-shape ``breakout_level``;
- ``swing_zone``: confirmed pivot zones without any recognised pattern (``mirror_levels.swing``).

Causality: ``Boundary.as_of_time_ms`` is the close time of the candle at which
the source could know the level (pattern decision candle, pivot confirmation
candle); ``naked_retest`` ignores every candle opening before it.

Identity: ``level_id`` hashes only source facts that never change after the
level is known (symbol, timeframe, source, pattern, side, anchor times and
prices), so a restart or a re-scan rebuilds the same id and a tested level is
never rediscovered as a new untested one.

Not responsible for: breakout/retest decisions, orders, Robot, Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from geometry.naked_retest import Boundary
from mirror_retest_observer import boundaries_from_candidate_snapshot


SOURCE_PATTERN_BOUNDARY = "pattern_boundary"
SOURCE_SWING_ZONE = "swing_zone"
SOURCES = frozenset({SOURCE_PATTERN_BOUNDARY, SOURCE_SWING_ZONE})

SIDE_UPPER = "upper"
SIDE_LOWER = "lower"
SIDES = frozenset({SIDE_UPPER, SIDE_LOWER})

TIMEFRAME_MS = {"1": 60_000, "5": 300_000, "15": 900_000, "60": 3_600_000, "240": 14_400_000}

PRICE_DIGITS = 12


class MirrorLevelError(ValueError):
    pass


def timeframe_ms(timeframe: str) -> int:
    try:
        return TIMEFRAME_MS[str(timeframe).strip()]
    except KeyError as exc:
        raise MirrorLevelError(f"unsupported timeframe: {timeframe!r}") from exc


def _price(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MirrorLevelError(f"{field_name} must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise MirrorLevelError(f"{field_name} must be a positive finite price")
    return number


def _time(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or value < 0:
        raise MirrorLevelError(f"{field_name} must be a non-negative integer timestamp")
    return int(value)


def level_identity(*, symbol: str, timeframe: str, source: str, pattern: str | None, side: str,
                   anchors: Sequence[tuple[int, float]]) -> str:
    """Deterministic id from immutable source facts only."""

    payload = {
        "symbol": symbol, "timeframe": str(timeframe), "source": source,
        "pattern": pattern or "", "side": side,
        "anchors": [[int(t), round(float(p), PRICE_DIGITS)] for t, p in anchors],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return f"lvl-{digest.hexdigest()[:24]}"


@dataclass(frozen=True)
class MirrorLevel:
    level_id: str
    symbol: str
    timeframe: str
    source: str
    pattern: str | None
    side: str
    anchors: tuple[tuple[int, float], ...]
    boundary: Boundary
    confirmed_at_ms: int
    touches: int = 0
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise MirrorLevelError(f"unknown level source: {self.source!r}")
        if self.side not in SIDES:
            raise MirrorLevelError(f"unknown level side: {self.side!r}")
        if not str(self.symbol or "").strip():
            raise MirrorLevelError("symbol is required")
        timeframe_ms(self.timeframe)
        if not self.anchors:
            raise MirrorLevelError("a level needs at least one anchor")
        if self.boundary.boundary_id != self.level_id:
            raise MirrorLevelError("boundary id must equal level id")
        if self.boundary.as_of_time_ms < self.confirmed_at_ms:
            raise MirrorLevelError("a level cannot be usable before it is confirmed")
        if any(t > self.confirmed_at_ms for t, _ in self.anchors):
            raise MirrorLevelError("an anchor cannot lie after the level confirmation")

    @property
    def is_horizontal(self) -> bool:
        return self.boundary.is_horizontal

    def price_at(self, time_ms: int) -> float:
        return self.boundary.price_at(time_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id, "symbol": self.symbol, "timeframe": self.timeframe,
            "source": self.source, "pattern": self.pattern, "side": self.side,
            "anchors": [[t, p] for t, p in self.anchors],
            "boundary": {"anchor_time_ms": self.boundary.anchor_time_ms,
                         "anchor_price": self.boundary.anchor_price,
                         "slope_per_ms": self.boundary.slope_per_ms,
                         "as_of_time_ms": self.boundary.as_of_time_ms},
            "confirmed_at_ms": self.confirmed_at_ms, "touches": self.touches,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MirrorLevel":
        try:
            b = raw["boundary"]
            boundary = Boundary(raw["level_id"], int(b["anchor_time_ms"]), float(b["anchor_price"]),
                                float(b["slope_per_ms"]), int(b["as_of_time_ms"]))
            return cls(raw["level_id"], raw["symbol"], str(raw["timeframe"]), raw["source"],
                       raw.get("pattern"), raw["side"],
                       tuple((int(t), float(p)) for t, p in raw["anchors"]), boundary,
                       int(raw["confirmed_at_ms"]), int(raw.get("touches", 0)),
                       dict(raw.get("provenance") or {}))
        except (KeyError, TypeError, ValueError) as exc:
            raise MirrorLevelError("malformed persisted level") from exc


def _build(*, symbol: str, timeframe: str, source: str, pattern: str | None, side: str,
           anchors: Sequence[tuple[int, float]], anchor_time_ms: int, anchor_price: float,
           slope_per_ms: float, confirmed_at_ms: int, touches: int = 0,
           provenance: Mapping[str, Any] | None = None) -> MirrorLevel:
    anchors = tuple((int(t), float(p)) for t, p in anchors)
    level_id = level_identity(symbol=symbol, timeframe=timeframe, source=source, pattern=pattern,
                              side=side, anchors=anchors)
    boundary = Boundary(level_id, int(anchor_time_ms), float(anchor_price), float(slope_per_ms),
                        int(confirmed_at_ms))
    return MirrorLevel(level_id, symbol, str(timeframe), source, pattern, side, anchors, boundary,
                       int(confirmed_at_ms), touches, dict(provenance or {}))


# --- pattern-boundary adapters -------------------------------------------------------------------

def line_level(*, symbol: str, timeframe: str, pattern: str, side: str,
               first: tuple[int, float], second: tuple[int, float], confirmed_at_ms: int,
               provenance: Mapping[str, Any] | None = None) -> MirrorLevel:
    """A boundary through two dated anchors (any sloped or flat pattern line)."""

    t1, p1 = _time(first[0], "first anchor time"), _price(first[1], "first anchor price")
    t2, p2 = _time(second[0], "second anchor time"), _price(second[1], "second anchor price")
    if t2 <= t1:
        raise MirrorLevelError("line anchors must be strictly chronological")
    return _build(symbol=symbol, timeframe=timeframe, source=SOURCE_PATTERN_BOUNDARY,
                  pattern=pattern, side=side, anchors=((t1, p1), (t2, p2)),
                  anchor_time_ms=t1, anchor_price=p1, slope_per_ms=(p2 - p1) / (t2 - t1),
                  confirmed_at_ms=_time(confirmed_at_ms, "confirmed_at_ms"), provenance=provenance)


def horizontal_level(*, symbol: str, timeframe: str, source: str, pattern: str | None, side: str,
                     price: float, anchor_time_ms: int, confirmed_at_ms: int, touches: int = 0,
                     provenance: Mapping[str, Any] | None = None) -> MirrorLevel:
    price = _price(price, "level price")
    anchor = _time(anchor_time_ms, "anchor_time_ms")
    return _build(symbol=symbol, timeframe=timeframe, source=source, pattern=pattern, side=side,
                  anchors=((anchor, price),), anchor_time_ms=anchor, anchor_price=price,
                  slope_per_ms=0.0, confirmed_at_ms=_time(confirmed_at_ms, "confirmed_at_ms"),
                  touches=touches, provenance=provenance)


def levels_from_geometry(*, symbol: str, timeframe: str, pattern: str,
                         geometry: Mapping[str, Any], candle_times_ms: Sequence[int],
                         decision_index: int) -> tuple[MirrorLevel, ...]:
    """Upper/lower boundaries of an engine geometry with index-based lines.

    Lines are ``price(index) = slope * index + intercept`` over the detector's own
    candle frame (Wedge, Triangle, Broadening, channels). Both anchors must be
    real candles not later than ``decision_index``; the level is known at the
    close of the decision candle. Missing or inconsistent geometry returns ()
    instead of a guessed line.
    """

    step = timeframe_ms(timeframe)
    if not 0 <= decision_index < len(candle_times_ms):
        return ()
    confirmed = int(candle_times_ms[decision_index]) + step
    out = []
    for side in (SIDE_UPPER, SIDE_LOWER):
        line = geometry.get(f"{side}_line") if isinstance(geometry, Mapping) else None
        if not isinstance(line, Mapping):
            return ()
        try:
            slope, intercept = float(line["slope"]), float(line["intercept"])
            i1, i2 = int(line["anchor_index"]), int(line["second_index"])
        except (KeyError, TypeError, ValueError):
            return ()
        if not (0 <= i1 < i2 <= decision_index):
            return ()
        try:
            out.append(line_level(
                symbol=symbol, timeframe=timeframe, pattern=pattern, side=side,
                first=(int(candle_times_ms[i1]), slope * i1 + intercept),
                second=(int(candle_times_ms[i2]), slope * i2 + intercept),
                confirmed_at_ms=confirmed,
                provenance={"anchor_index": i1, "second_index": i2, "decision_index": decision_index},
            ))
        except MirrorLevelError:
            return ()
    return tuple(out)


def levels_from_horn_event(event: Mapping[str, Any]) -> tuple[MirrorLevel, ...]:
    """Broadening (HORN) observation event with dated anchors (``horn_observations`` journal)."""

    try:
        symbol, timeframe = str(event["symbol"]), str(event["timeframe"])
        step = timeframe_ms(timeframe)
        confirmed = int(event["decision_time_ms"]) + step
        out = []
        for side in (SIDE_UPPER, SIDE_LOWER):
            line = event[f"{side}_line"]
            out.append(line_level(
                symbol=symbol, timeframe=timeframe, pattern="Broadening", side=side,
                first=(line["anchor_time_ms"], line["anchor_price"]),
                second=(line["second_time_ms"], line["second_price"]),
                confirmed_at_ms=confirmed,
                provenance={"identity": event.get("identity"), "stage": event.get("stage")},
            ))
        return tuple(out)
    except (KeyError, TypeError, ValueError, MirrorLevelError):
        return ()


def levels_from_wedge_candidate(*, candidate_id: str, symbol: str, created_at_ms: int,
                                signal_snapshot: Mapping[str, Any]) -> tuple[MirrorLevel, ...]:
    """Frozen Wedge boundaries exactly as MIRROR RETEST already derives them (RETEST-4 transform)."""

    boundaries = boundaries_from_candidate_snapshot(
        candidate_id=candidate_id, created_at_ms=created_at_ms, signal_snapshot=signal_snapshot)
    if not boundaries:
        return ()
    pattern = str(signal_snapshot.get("pattern") or "Wedge")
    out = []
    for side, boundary in zip((SIDE_UPPER, SIDE_LOWER), boundaries):
        first_time = boundary.anchor_time_ms - timeframe_ms("1")
        try:
            out.append(line_level(
                symbol=symbol, timeframe="1", pattern=pattern, side=side,
                first=(first_time, boundary.price_at(first_time)),
                second=(boundary.anchor_time_ms, boundary.anchor_price),
                confirmed_at_ms=boundary.as_of_time_ms,
                provenance={"candidate_id": candidate_id, "mirror_boundary_id": boundary.boundary_id},
            ))
        except MirrorLevelError:
            return ()
    return tuple(out)


def levels_from_ikigai_box(*, symbol: str, timeframe: str, formation: Any,
                           candle_times_ms: Sequence[int]) -> tuple[MirrorLevel, ...]:
    """Horizontal ``box_high``/``box_low`` of an Ikigai Box formation or watch."""

    try:
        step = timeframe_ms(timeframe)
        confirmed = int(candle_times_ms[int(formation.as_of_index)]) + step
        start = int(candle_times_ms[int(formation.box_start_index)])
        return tuple(
            horizontal_level(symbol=symbol, timeframe=timeframe, source=SOURCE_PATTERN_BOUNDARY,
                             pattern="IKIGAI_BOX", side=side, price=price, anchor_time_ms=start,
                             confirmed_at_ms=confirmed,
                             provenance={"direction": formation.direction,
                                         "box_start_index": int(formation.box_start_index),
                                         "box_end_index": int(formation.box_end_index)})
            for side, price in ((SIDE_UPPER, formation.box_high), (SIDE_LOWER, formation.box_low))
        )
    except (AttributeError, IndexError, TypeError, ValueError, MirrorLevelError):
        return ()


def levels_from_l_shape(*, symbol: str, timeframe: str, formation: Any,
                        candle_times_ms: Sequence[int]) -> tuple[MirrorLevel, ...]:
    """L-shape ``breakout_level`` (H for LONG, L for SHORT), known at its breakout candle."""

    try:
        step = timeframe_ms(timeframe)
        confirmed = int(candle_times_ms[int(formation.as_of_index)]) + step
        side = SIDE_UPPER if formation.direction == "LONG" else SIDE_LOWER
        return (horizontal_level(
            symbol=symbol, timeframe=timeframe, source=SOURCE_PATTERN_BOUNDARY, pattern="L-shape",
            side=side, price=formation.breakout_level,
            anchor_time_ms=int(candle_times_ms[int(formation.extreme_index)]),
            confirmed_at_ms=confirmed,
            provenance={"direction": formation.direction,
                        "breakout_index": int(formation.breakout_index)}),)
    except (AttributeError, IndexError, TypeError, ValueError, MirrorLevelError):
        return ()


# --- registry -------------------------------------------------------------------------------------

@dataclass
class LevelRegistry:
    """Deduplicated levels of one symbol/timeframe universe, stable across restarts.

    Exact duplicates (same ``level_id``) are idempotent. Two different sources
    describing the same horizontal price (within ``merge_tolerance`` price units
    at the same side) are reconciled into the earliest-confirmed level; the other
    source is kept in ``aliases`` for provenance, never silently dropped.
    """

    levels: dict[str, MirrorLevel] = field(default_factory=dict)
    aliases: dict[str, list[str]] = field(default_factory=dict)

    def get(self, level_id: str) -> MirrorLevel | None:
        if level_id in self.levels:
            return self.levels[level_id]
        for primary, others in self.aliases.items():
            if level_id in others:
                return self.levels[primary]
        return None

    def add(self, level: MirrorLevel, *, merge_tolerance: float = 0.0) -> MirrorLevel:
        if level.level_id in self.levels:
            return self.levels[level.level_id]
        known = self.get(level.level_id)
        if known is not None:
            return known
        if level.is_horizontal and merge_tolerance > 0:
            for existing in sorted(self.levels.values(), key=lambda x: (x.confirmed_at_ms, x.level_id)):
                if (existing.is_horizontal and existing.symbol == level.symbol
                        and existing.timeframe == level.timeframe and existing.side == level.side
                        and abs(existing.boundary.anchor_price - level.boundary.anchor_price)
                        <= merge_tolerance):
                    primary, other = ((existing, level)
                                      if (existing.confirmed_at_ms, existing.level_id)
                                      <= (level.confirmed_at_ms, level.level_id)
                                      else (level, existing))
                    if primary is level:
                        self.levels.pop(existing.level_id)
                        self.levels[level.level_id] = level
                        moved = self.aliases.pop(existing.level_id, [])
                        self.aliases[level.level_id] = sorted({*moved, existing.level_id})
                    else:
                        self.aliases.setdefault(existing.level_id, [])
                        self.aliases[existing.level_id] = sorted(
                            {*self.aliases[existing.level_id], level.level_id})
                    return primary
        self.levels[level.level_id] = level
        return level

    def extend(self, levels: Iterable[MirrorLevel], *, merge_tolerance: float = 0.0) -> None:
        for level in sorted(levels, key=lambda x: (x.confirmed_at_ms, x.level_id)):
            self.add(level, merge_tolerance=merge_tolerance)

    def known_at(self, time_ms: int) -> tuple[MirrorLevel, ...]:
        """Levels a live process could know at ``time_ms`` (no look-ahead)."""

        return tuple(sorted((level for level in self.levels.values()
                             if level.confirmed_at_ms <= time_ms),
                            key=lambda x: (x.confirmed_at_ms, x.level_id)))

    def to_dict(self) -> dict[str, Any]:
        return {"levels": [self.levels[key].to_dict() for key in sorted(self.levels)],
                "aliases": {key: list(value) for key, value in sorted(self.aliases.items())}}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "LevelRegistry":
        registry = cls()
        for item in raw.get("levels") or ():
            level = MirrorLevel.from_dict(item)
            registry.levels[level.level_id] = level
        registry.aliases = {str(k): [str(x) for x in v] for k, v in (raw.get("aliases") or {}).items()}
        return registry
