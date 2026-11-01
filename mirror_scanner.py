"""Scanner -> MIRROR level observation (#613 integration of ``mirror_levels``).

One Scanner pass, per symbol and timeframe, on the snapshot the Scanner already
fetched (its newest, possibly open candle excluded):

    pattern boundaries of this snapshot (Wedge / Triangle geometry, HORN, Ikigai Box, L-shape)
  + confirmed swing zones (``mirror_levels.swing``)
  -> one deduplicated ``LevelRegistry`` per symbol/timeframe (repeated scans and
     several sources of one real level reconcile into the first registered level)
  -> ``mirror_levels.tracker`` over the closed candles not yet consumed
     (``geometry.naked_retest`` breakout / first retest, 5m ambiguity settled by
     ``retest_calibration.fine_resolver`` on the same pass's 1m candles)
  -> MIRROR candidate = fresh, confident naked breakout of an untested level
  -> durable state file + append-only journal + one Telegram card per event.

FVG / iFVG are recorded quality attributes only; they never create, admit or
reject a candidate. Nothing here trades: every candidate carries the existing
``mirror_retest_robot_bridge.observe_for_robot`` result (``executable=False``,
``admission_allowed=False``) and the common ``prepare_robot_handoff`` capability
answer. The PAPER Robot reads these candidates (``mirror_retest_robot.scanner_level_sources``)
as RETEST campaigns for its own Box attempts in the campaign direction.

Standalone MIRROR entry (``BYBITSCANNER_MIRROR_STANDALONE_ROBOT=1`` only;
owner decisions 2026-10-25): a 5m untested horizontal-level campaign watches
closed 5m and 1m candles independently. A Nison-style Hammer after a decline,
Hanging Man after a rise, or the existing directional Engulfing becomes
eligible only when its *immediately following* closed candle closes beyond
the pattern's real-body boundary (not its wick). Entry reference = that next
close; structural STOP = pattern extreme; TAKE = 100 % at first level retest.
The common Robot still owns the one-tick STOP buffer, the 1.5% limit, net RR
>=2 with fees/slippage, R0, admission and all executions. Doji/Inverted Hammer
are not standalone entry triggers. No look-ahead or cross-TF agreement.

Durability: the state (registry, tracker records, pending notifications) is
replaced atomically before any Telegram send; a pending card is re-sent after a
crash (at least once), a delivered one never. An unreadable state file is never
overwritten: the symbol/timeframe is skipped and the error journaled, so a
tested level can never be rediscovered as a new untested one.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import hashlib
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence

from geometry.naked_retest import NakedRetestError, PHASE_CAMPAIGN_ACTIVE
from mirror_levels.imbalance import detect_fvgs, replay as replay_fvg
from mirror_levels.levels import (
    LevelRegistry, MirrorLevel, MirrorLevelError, SOURCE_SWING_ZONE, horizontal_level,
    levels_from_geometry, levels_from_horn_event,
    levels_from_ikigai_box, levels_from_l_shape, timeframe_ms,
)
from mirror_levels.swing import confirmed_pivots, swing_levels
from mirror_levels.tracker import (
    STATUS_DATA_BLOCKED, STATUS_RETESTED, STATUS_UNPROVEN, STATUS_UNTESTED, STATUS_WAITING,
    new_record, track,
)
from retest_calibration import causal_atr_series, fine_resolver

ENV_FLAG = "BYBITSCANNER_MIRROR_OBSERVATION"
ROOT_ENV = "BYBITSCANNER_MIRROR_EVIDENCE_DIR"
DEFAULT_ROOT = Path(__file__).resolve().parent / "runtime" / "terminal" / "mirror_levels"  # gitignored
STATE_DIR = "state"
EVENTS_FILE = "events.jsonl"
STATE_VERSION = "mirror-scanner-1"
PATTERN = "MIRROR"

ATR_PERIOD = 14
MERGE_TOLERANCE_ATR = 0.25          # same real level: within 0.25 ATR (the swing-zone tolerance)
FRESH_BREAKOUT_CANDLES = 2          # a live breakout closed at most 2 closed candles ago
MIN_BREAKOUT_BODY_ATR = 0.5         # provisional observation threshold; not a trading rule
MIN_MIRROR_RETEST_POTENTIAL_PERCENT = Decimal("0.7")  # owner: minimum gross distance to first retest
WAITING_EXPIRY_CANDLES = 400        # an unbroken level whose last anchor left two Scanner windows
RETENTION_MS = 3 * 86_400_000       # finished records are kept 3 days for the Terminal

LIFECYCLE_TRACKING = "TRACKING"
LIFECYCLE_DONE = "DONE"
LIFECYCLE_REJECTED = "REJECTED"

WEDGE_ENGINE_PATTERNS = frozenset({"Rising Wedge", "Falling Wedge", "Triangle Compression"})

# Why a detected MIRROR candidate cannot reach PAPER on its own (shown in Terminal, never bypassed here).
PAPER_BLOCKERS = (
    "standalone_mirror_entry_off_until_owner_enables_BYBITSCANNER_MIRROR_STANDALONE_ROBOT",
)

STANDALONE_LEVEL_TIMEFRAME = "5"      # its breakout identity equals the Robot's own 5m campaign replay
CONFIRMATION_TIMEFRAMES = ("5", "1")
CONFIRMATION_ENGULFING = "ENGULFING"
CONFIRMATION_HAMMER = "HAMMER"
CONFIRMATION_HANGING_MAN = "HANGING_MAN"
# Engineering interpretation of Nison's "very little or no" upper shadow.
# The book does NOT give this numerical cut-off; not a profitability claim.
HAMMER_MAX_UPPER_TO_BODY = "0.50"
ENTRY_STOP_KIND = "REVERSAL_FORMATION_EXTREME"
ENTRY_MIN_NET_RR = 2                  # owner: Net RR >= 2:1 with fees and slippage

_SAFE_SYMBOL = re.compile(r"^[A-Z0-9]+$")


class MirrorStateError(RuntimeError):
    """The durable state cannot be trusted; it is left untouched."""


def mirror_observation_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """On by default (observation only); BYBITSCANNER_MIRROR_OBSERVATION=0 switches it off."""
    return (os.environ if environ is None else environ).get(ENV_FLAG, "1") != "0"


def evidence_root(root=None) -> Path:
    if root is not None:
        return Path(root)
    override = os.environ.get(ROOT_ENV, "").strip()
    return Path(override) if override else DEFAULT_ROOT


def append_event(record: Mapping[str, Any], root=None) -> None:
    """Append one fsynced JSON line, the Scanner observation-journal format (``horn_scanner``)."""
    directory = evidence_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"recorded_at_ms": int(time.time() * 1000), **record}, ensure_ascii=False, default=str)
    with open(directory / EVENTS_FILE, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


# --- candles and sources ------------------------------------------------------------------------

def closed_rows(frame, timeframe: str) -> list[dict[str, Any]]:
    """Scanner OHLC frame (``time`` = open ms) as closed-candle mappings."""

    step = timeframe_ms(timeframe)
    return [{"open_time_ms": int(t), "close_time_ms": int(t) + step, "open": float(o),
             "high": float(h), "low": float(lo), "close": float(c), "closed": True}
            for t, o, h, lo, c in zip(frame["time"], frame["open"], frame["high"],
                                      frame["low"], frame["close"])]


def _with_parent(levels, parent: Mapping[str, Any]):
    return [replace(level, provenance={**level.provenance, **parent}) for level in levels]


def box_source_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Ikigai Box boundaries are a MIRROR source exactly when the Scanner scans Box signals."""
    return (os.environ if environ is None else environ).get("BYBITSCANNER_IKIGAI_BOX_SIGNALS") == "1"


def collect_levels(symbol: str, timeframe: str, candles, *, wedge_result=None,
                   horn_observation=None, l_shape_observation=None,
                   box_source: bool | None = None) -> list[MirrorLevel]:
    """Every level this snapshot can know at its latest closed candle (no look-ahead).

    ``candles`` is the Scanner frame including its newest, possibly open candle.
    Wedge/Triangle geometry indexes that frame; every other detector reads the
    closed prefix. Detector failures drop only that source.
    """

    closed = candles.iloc[:-1].reset_index(drop=True)
    times = [int(t) for t in candles["time"]]
    closed_times = times[:-1]
    out: list[MirrorLevel] = []

    if isinstance(wedge_result, Mapping) and wedge_result.get("pattern") in WEDGE_ENGINE_PATTERNS:
        pattern = str(wedge_result["pattern"])
        out += _with_parent(
            levels_from_geometry(symbol=symbol, timeframe=timeframe, pattern=pattern,
                                 geometry=wedge_result.get("geometry") or {},
                                 candle_times_ms=times, decision_index=len(candles) - 2),
            {"parent_pattern": pattern,
             "parent_formation_id": wedge_result.get("scanner_formation_id")})

    if isinstance(horn_observation, Mapping):
        out += _with_parent(levels_from_horn_event(horn_observation),
                            {"parent_pattern": "Broadening",
                             "parent_formation_id": horn_observation.get("identity")})

    try:
        formation = (l_shape_observation or {}).get("formation")
        if formation is None:
            from geometry.l_shape import detect_l_shape
            formation = detect_l_shape(closed)
        if formation is not None:
            out += _with_parent(
                levels_from_l_shape(symbol=symbol, timeframe=timeframe, formation=formation,
                                    candle_times_ms=closed_times, known_at_breakout_open=True),
                {"parent_pattern": "L-shape",
                 "parent_formation_id": f"l_shape:{formation.direction}:"
                                        f"{closed_times[int(formation.extreme_index)]}"})
    except Exception as error:
        print(f"{symbol:<15} {timeframe}m MIRROR L-shape source skipped: {type(error).__name__}")

    try:
        from geometry.ikigai_box import detect_ikigai_box
        box = detect_ikigai_box(closed) if (box_source_enabled() if box_source is None else box_source) else None
        if box is not None:
            out += _with_parent(
                levels_from_ikigai_box(symbol=symbol, timeframe=timeframe, formation=box,
                                       candle_times_ms=closed_times),
                {"parent_pattern": "IKIGAI_BOX",
                 "parent_formation_id": f"ikigai_box:{box.direction}:"
                                        f"{closed_times[int(box.box_start_index)]}"})
    except Exception as error:
        print(f"{symbol:<15} {timeframe}m MIRROR Box source skipped: {type(error).__name__}")

    out += list(swing_levels(closed_rows(closed, timeframe), symbol=symbol, timeframe=timeframe))
    return out


def _source_entry(level: MirrorLevel) -> dict[str, Any]:
    return {"level_id": level.level_id, "source": level.source, "pattern": level.pattern,
            "parent_pattern": level.provenance.get("parent_pattern"),
            "parent_formation_id": level.provenance.get("parent_formation_id"),
            "confirmed_at_ms": level.confirmed_at_ms}


# --- durable state ------------------------------------------------------------------------------

def state_path(symbol: str, timeframe: str, root=None) -> Path:
    return evidence_root(root) / STATE_DIR / f"{symbol}_{timeframe}.json"


def empty_state(symbol: str, timeframe: str) -> dict[str, Any]:
    return {"state_version": STATE_VERSION, "symbol": symbol, "timeframe": timeframe,
            "registry": LevelRegistry().to_dict(), "records": {}, "pending_notifications": [],
            "updated_at_ms": None}


def load_state(symbol: str, timeframe: str, root=None) -> dict[str, Any]:
    path = state_path(symbol, timeframe, root)
    if not path.exists():
        return empty_state(symbol, timeframe)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if (state.get("state_version") != STATE_VERSION or state.get("symbol") != symbol
                or state.get("timeframe") != timeframe):
            raise ValueError("state identity mismatch")
        LevelRegistry.from_dict(state["registry"])
        if not isinstance(state["records"], dict) or not isinstance(state["pending_notifications"], list):
            raise ValueError("state structure")
        return state
    except (OSError, ValueError, KeyError, TypeError, MirrorLevelError) as exc:
        raise MirrorStateError(f"{path.name}: {type(exc).__name__}: {exc}") from exc


def save_state(state: Mapping[str, Any], root=None) -> None:
    path = state_path(state["symbol"], state["timeframe"], root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


# --- lifecycle ----------------------------------------------------------------------------------

def _robot_handoff(level: MirrorLevel, record: Mapping[str, Any]) -> dict[str, Any]:
    """The existing Robot boundary's answer for this candidate: observation, never admission."""

    from mirror_retest_robot_bridge import observe_for_robot
    from pattern_robot_integration import is_robot_executable_signal

    observation = observe_for_robot(boundary_id=level.level_id, state=record["naked_retest"])
    snapshot = {"pattern": PATTERN, "symbol": level.symbol, "scanner_observational_only": True,
                "mirror_level_id": level.level_id}
    return {**observation.__dict__,
            "robot_handoff_executable": is_robot_executable_signal(snapshot, timeframe=level.timeframe),
            "paper_admission": "NOT_AUTHORIZED", "paper_blockers": list(PAPER_BLOCKERS)}


def _retest_potential_percent(target: float | Decimal, reference: float | Decimal) -> Decimal:
    """Gross retest distance relative to the confirmed close, in percent.

    The target is the frozen boundary at the relevant candle CLOSE. This
    measures geometry only; Robot net RR / fees / slippage still gate entries.
    """
    price = Decimal(str(reference))
    level = Decimal(str(target))
    if not price.is_finite() or not level.is_finite() or price <= 0 or level <= 0:
        return Decimal("0")
    return abs(level - price) * Decimal("100") / price


def _judge_breakout(level: MirrorLevel, record: Mapping[str, Any], latest_close_ms: int, step: int) -> str | None:
    """Rejection reason of a naked breakout as a live MIRROR candidate, or None (candidate)."""

    breakout = record["naked_retest"]["breakout"]
    age = (latest_close_ms - int(breakout["close_time_ms"])) // step
    if age > FRESH_BREAKOUT_CANDLES:
        return f"stale_breakout:{age}_candles_before_latest_close"
    evidence = record.get("breakout_evidence") or {}
    body_atr = evidence.get("body_atr")
    if body_atr is None:
        return "breakout_atr_unavailable"
    if body_atr < MIN_BREAKOUT_BODY_ATR:
        return f"weak_breakout_body:{body_atr:.2f}_atr"
    # The first MIRROR retest is the target, not the wick excursion.
    # Compare the CLOSED breakout candle with the frozen level at its close.
    # Keep rejected breakouts in durable history, but do not publish a weak
    # campaign as a candidate or hand it to PAPER.
    potential = _retest_potential_percent(
        level.boundary.price_at(int(breakout["close_time_ms"])),
        breakout["close"],
    )
    if potential < MIN_MIRROR_RETEST_POTENTIAL_PERCENT:
        return "retest_potential_below_0_7_percent"
    return None


def _duplicate_breakout(level_id, level, record, records, registry) -> str | None:
    """One naked candle through two adjacent levels of one side is one MIRROR event, not two."""

    breakout = record["naked_retest"]["breakout"]
    for other_id, other in records.items():
        other_level = registry.levels.get(other_id)
        other_breakout = other["naked_retest"].get("breakout")
        if (other_id != level_id and other.get("candidate") and other_level is not None
                and other_level.side == level.side and other_breakout is not None
                and other_breakout["open_time_ms"] == breakout["open_time_ms"]
                and other_breakout["direction"] == breakout["direction"]):
            return f"duplicate_breakout_of:{other_id}"
    return None


def _engulfing(previous: Mapping[str, Any], current: Mapping[str, Any], direction: str) -> bool:
    """The repository's Engulfing rule; SHORT is the same rule on price-negated candles."""

    import pandas as pd
    from geometry.reversal_patterns import is_bullish_engulfing

    def view(row):
        if direction == "LONG":
            return {"open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]}
        return {"open": -row["open"], "high": -row["low"], "low": -row["high"], "close": -row["close"]}

    return bool(is_bullish_engulfing(pd.DataFrame([view(previous), view(current)]), 1))


def _candle_numbers(row: Mapping[str, Any]):
    """Positive finite OHLC of an explicitly closed, physically valid candle."""
    from decimal import Decimal, InvalidOperation

    if row.get("closed") is not True:
        return None
    try:
        o, h, lo, c = (Decimal(str(row[k])) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if (not all(x.is_finite() and x > 0 for x in (o, h, lo, c))
            or lo > min(o, c) or h < max(o, c) or h <= lo):
        return None
    return o, h, lo, c


def _nison_hammer(candle: Mapping[str, Any], direction: str,
                  preceding: Sequence[Mapping[str, Any]]) -> bool:
    """Hammer LONG or Hanging Man SHORT: identical lower-wick shape, different context.

    Nison: small real body at upper end, lower wick at least 2x the body,
    very little/no upper wick. For the otherwise qualitative upper-wick phrase
    we use an explicit <= 1/2-body implementation tolerance. Previous two
    consecutive closes must fall (LONG) or rise (SHORT), a causal conservative
    proxy for the prior trend rather than a number ascribed to Nison.
    Doji remains observational, not an entry trigger.
    """
    from decimal import Decimal

    if direction not in ("LONG", "SHORT") or len(preceding) < 2:
        return False
    values = _candle_numbers(candle)
    before = [_candle_numbers(x) for x in preceding[-2:]]
    if values is None or any(x is None for x in before):
        return False
    older, newer = before
    try:
        duration = int(candle["close_time_ms"]) - int(candle["open_time_ms"])
        if (duration <= 0
                or any(int(row["close_time_ms"]) - int(row["open_time_ms"]) != duration
                       for row in preceding[-2:])
                or int(preceding[-2]["close_time_ms"]) != int(preceding[-1]["open_time_ms"])
                or int(preceding[-1]["close_time_ms"]) != int(candle["open_time_ms"])):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    if direction == "LONG" and not older[3] > newer[3]:
        return False
    if direction == "SHORT" and not older[3] < newer[3]:
        return False
    o, h, lo, c = values
    body = abs(c - o)
    if body == 0:  # doji requires its own independently reviewed context/rule
        return False
    lower_wick = min(o, c) - lo
    upper_wick = h - max(o, c)
    return (lower_wick >= 2 * body
            and upper_wick <= Decimal(HAMMER_MAX_UPPER_TO_BODY) * body)


def _next_close_confirms(formation: Sequence[Mapping[str, Any]],
                         following: Mapping[str, Any], direction: str, step: int) -> bool:
    """The *next* closed same-TF candle confirms beyond the pattern BODY, not wick."""
    candles = [*formation, following]
    values = [_candle_numbers(x) for x in candles]
    if direction not in ("LONG", "SHORT") or not formation or any(x is None for x in values):
        return False
    try:
        if any(int(right["open_time_ms"]) != int(left["close_time_ms"])
               or int(left["close_time_ms"]) - int(left["open_time_ms"]) != step
               for left, right in zip(candles, candles[1:])):
            return False
        if int(following["close_time_ms"]) - int(following["open_time_ms"]) != step:
            return False
    except (KeyError, ValueError, TypeError):
        return False
    real_body_top = max(max(o, c) for o, _, _, c in values[:-1])
    real_body_bottom = min(min(o, c) for o, _, _, c in values[:-1])
    return (values[-1][3] > real_body_top if direction == "LONG"
            else values[-1][3] < real_body_bottom)


def _entry_terms(level: MirrorLevel, record: Mapping[str, Any], candle: Mapping[str, Any],
                 timeframe: str, *, confirmation_kind: str,
                 formation: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    """Frozen standalone entry terms: following close, preceding formation STOP."""
    from decimal import Decimal
    import robot_l_shape
    from mirror_retest_robot import PAPER_FEE_RATE, STOP_SLIPPAGE_FRACTION

    direction = record["naked_retest"]["breakout"]["campaign_direction"]
    reference = Decimal(str(candle["close"]))
    stop = (min(Decimal(str(x["low"])) for x in formation) if direction == "LONG"
            else max(Decimal(str(x["high"])) for x in formation))
    target = Decimal(str(level.boundary.price_at(int(candle["close_time_ms"]))))
    sign = 1 if direction == "LONG" else -1
    if not ((reference - stop) * sign > 0 and (target - reference) * sign > 0):
        return None, "entry_geometry_invalid"
    # Price may approach the retest boundary after the breakout; recheck
    # the actual confirmation close, not only the campaign's original signal.
    if _retest_potential_percent(target, reference) < MIN_MIRROR_RETEST_POTENTIAL_PERCENT:
        return None, "entry_retest_potential_below_0_7_percent"
    try:
        rr = robot_l_shape.net_reward_risk(direction, entry_price=reference, stop_price=stop,
                                           target_price=target, fee_rate=PAPER_FEE_RATE,
                                           exit_slippage_fraction=STOP_SLIPPAGE_FRACTION)
    except robot_l_shape.RobotLShapeError:
        return None, "entry_net_rr_unavailable"
    if rr < ENTRY_MIN_NET_RR:
        return None, f"entry_net_rr_below_2:{rr:.2f}"
    breakout = record["naked_retest"]["breakout"]
    return {
        "direction": direction, "source_timeframe": timeframe,
        "breakout_time_ms": int(candle["open_time_ms"]),
        "reference": str(reference), "target": str(target), "stop": str(stop), "structural_stop": str(stop),
        "stop_kind": ENTRY_STOP_KIND,
        "potential_percent": str(abs(target - reference) / reference * 100),
        "reward_risk": str(rr),
        "level_id": level.level_id, "level_timeframe": level.timeframe, "level_source": level.source,
        "level_pattern": level.pattern, "level_breakout_close_ms": int(breakout["close_time_ms"]),
        "confirmation": {"kind": confirmation_kind, "timeframe": timeframe,
                         **{key: candle[key] for key in ("open_time_ms", "close_time_ms", "open", "high", "low",
                                                         "close")},
                         "formation": [{key: source[key] for key in
                                        ("open_time_ms", "close_time_ms", "open", "high", "low", "close")}
                                       for source in formation]},
    }, None


def _standalone_confirmations(level: MirrorLevel, record: dict[str, Any], frames: Mapping[str, Sequence],
                              latest_close: int) -> list[dict[str, Any]]:
    """Closed 5m/1m separately: pattern first, immediately following close second.

    No trade from the formation candle alone, no later/missing confirmation,
    and nothing after the first retest of the horizontal MIRROR level.
    """
    if (level.timeframe != STANDALONE_LEVEL_TIMEFRAME or not level.is_horizontal
            or record.get("candidate") is not True or record.get("lifecycle") != LIFECYCLE_TRACKING
            or record.get("status") != STATUS_UNTESTED):
        return []
    breakout = record["naked_retest"]["breakout"]
    direction = breakout["campaign_direction"]
    price = level.boundary.price_at(int(breakout["close_time_ms"]))
    cursors = record.setdefault("entry_cursors", {})
    found = []
    for timeframe in CONFIRMATION_TIMEFRAMES:
        step = timeframe_ms(timeframe)
        rows = [row for row in frames.get(timeframe) or ()
                if int(row["open_time_ms"]) >= int(breakout["open_time_ms"])
                and int(row["close_time_ms"]) <= latest_close
                and row.get("closed") is True]
        cursor = int(cursors.get(timeframe) or breakout["close_time_ms"])
        # i is the confirmation candle. A Hammer/Hanging Man needs two candles
        # *before* the formation for its local directional context.
        for i in range(2, len(rows)):
            current, previous = rows[i], rows[i - 1]
            if int(current["close_time_ms"]) <= cursor or int(current["open_time_ms"]) < int(breakout["close_time_ms"]):
                continue
            cursor = int(current["close_time_ms"])
            # No entry if the target was touched by any candle in this formation.
            # The 5m tracker also guards historical first retests outside this window.
            engulf_formation = rows[i - 2:i]
            pattern = None
            kind = None
            if (_engulfing(engulf_formation[0], engulf_formation[1], direction)
                    and _next_close_confirms(engulf_formation, current, direction, step)):
                pattern, kind = engulf_formation, CONFIRMATION_ENGULFING
            elif (i >= 3
                  and _nison_hammer(previous, direction, rows[i - 3:i - 1])
                  and _next_close_confirms([previous], current, direction, step)):
                pattern = [previous]
                kind = CONFIRMATION_HAMMER if direction == "LONG" else CONFIRMATION_HANGING_MAN
            if pattern is None:
                continue
            involved = [*pattern, current]
            if any((x["high"] >= price if direction == "LONG" else x["low"] <= price)
                   for x in involved):
                continue
            # The following candle must not invalidate the original formation
            # before we have even observed its confirmation close. Its low/high
            # may be beyond the eventual buffered STOP; a close-only check
            # would otherwise admit a reversal that has already failed.
            formation_extreme = (min(x["low"] for x in pattern) if direction == "LONG"
                                 else max(x["high"] for x in pattern))
            invalidated = (current["low"] <= formation_extreme if direction == "LONG"
                           else current["high"] >= formation_extreme)
            if invalidated:
                continue
            terms, rejection = _entry_terms(
                level, record, current, timeframe, confirmation_kind=kind, formation=pattern)
            found.append({"timeframe": timeframe, "confirmation_close_ms": int(current["close_time_ms"]),
                          "kind": kind, "terms": terms, "rejection": rejection})
        cursors[timeframe] = cursor
    return found


def _standalone_snapshot(symbol: str, terms: Mapping[str, Any]) -> dict[str, Any]:
    timeframe = terms["source_timeframe"]
    return {"pattern": PATTERN, "symbol": symbol, "timeframe": timeframe, "scanner_source_timeframe": timeframe,
            "robot_handoff_ready": True, "mirror_entry": dict(terms)}


def _imbalance_quality(record: Mapping[str, Any], gaps, rows) -> list[dict[str, Any]]:
    """Linked FVGs with their current fill / inversion (iFVG) phase -- attributes only."""

    by_id = {gap.fvg_id: gap for gap in gaps}
    out = []
    for item in record.get("imbalance") or ():
        gap = by_id.get(item["fvg_id"])
        if gap is None:
            out.append(dict(item))
            continue
        lifecycle = replay_fvg(gap, rows)
        out.append({**item, "phase": lifecycle["phase"], "inverted": lifecycle["inverted_ms"] is not None,
                    "inverted_ms": lifecycle["inverted_ms"], "ifvg_retest_ms": lifecycle["ifvg_retest_ms"]})
    return out


def _advance(level: MirrorLevel, record: dict[str, Any], rows, *, atr_at, gaps, tolerance,
             fine_candles, confirmed_extrema=()) -> tuple[dict[str, Any], list[str]]:
    """Feed unconsumed closed candles one at a time; returns the record and its status transitions."""

    cursor = record["naked_retest"].get("cursor_close_time_ms")
    transitions = []
    for row in rows:
        if cursor is not None and row["close_time_ms"] <= cursor:
            continue
        # A subsequently CONFIRMED higher high / lower low invalidates an
        # unbroken horizontal mirror ray, even when only its wick crosses.
        # Wait until the right-hand pivot candles CLOSE: never look ahead.
        # A breakout already proven before confirmation remains historical;
        # it must not be rewritten using future pivot evidence.
        if level.is_horizontal and record["status"] == STATUS_WAITING:
            for pivot in confirmed_extrema:
                if (int(pivot["confirmed_at_ms"]) != int(row["close_time_ms"])
                        or int(pivot["pivot_at_ms"]) < level.confirmed_at_ms):
                    continue
                new_price = float(pivot["price"])
                old_price = level.price_at(int(pivot["pivot_at_ms"]))
                superseded = ((level.side == "upper" and new_price > old_price)
                              or (level.side == "lower" and new_price < old_price))
                if superseded:
                    record.update(lifecycle=LIFECYCLE_REJECTED,
                                  rejection="superseded_by_confirmed_extremum",
                                  superseding_extremum={"pivot_at_ms": int(pivot["pivot_at_ms"]),
                                                        "confirmed_at_ms": int(pivot["confirmed_at_ms"]),
                                                        "price": new_price})
                    transitions.append("SUPERSEDED_EXTREMUM")
                    return record, transitions
        resolver = None
        state = record["naked_retest"]
        if fine_candles and state["phase"] == PHASE_CAMPAIGN_ACTIVE:
            resolver = fine_resolver(level.boundary, state["breakout"]["direction"], fine_candles)
        before = record["status"]
        record = track(level, [row], record=record, atr_at=atr_at, gaps=gaps,
                       edge_tolerance=tolerance, ambiguity_resolver=resolver)
        if record["status"] != before:
            transitions.append(record["status"])
        if record["status"] in (STATUS_RETESTED, STATUS_UNPROVEN, STATUS_DATA_BLOCKED):
            break
    return record, transitions


def observe_mirror_levels(symbol, candles, *, timeframe, wedge_result=None, horn_observation=None,
                          l_shape_observation=None, fine_candles=None, box_source: bool | None = None,
                          root=None, now_ms: int | None = None) -> dict[str, Any] | None:
    """Advance the durable MIRROR state of one symbol/timeframe by this Scanner snapshot.

    ``fine_candles``: closed 1m candles of the same pass, used only to settle an
    ambiguous 5m retest contact. Returns a summary with the notifications that
    are now pending (``send_mirror_notifications`` delivers them).
    """

    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not _SAFE_SYMBOL.fullmatch(symbol):
        raise ValueError("invalid MIRROR symbol")
    step = timeframe_ms(timeframe)
    if candles is None or len(candles) < 3:
        return None
    try:
        state = load_state(symbol, timeframe, root)
    except MirrorStateError as error:
        append_event({"event": "mirror_state_unreadable", "symbol": symbol, "timeframe": timeframe,
                      "error": str(error)[:300]}, root)
        print(f"{symbol:<15} {timeframe}m MIRROR state unreadable, skipped: {error}", flush=True)
        return None

    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    rows = closed_rows(candles.iloc[:-1], timeframe)
    latest_close = rows[-1]["close_time_ms"]
    atr_series = causal_atr_series(rows, ATR_PERIOD)
    atr_by_close = {row["close_time_ms"]: value for row, value in zip(rows, atr_series)}
    tolerance = MERGE_TOLERANCE_ATR * (atr_series[-1] or 0.0)
    highs, lows = confirmed_pivots(rows)
    registry = LevelRegistry.from_dict(state["registry"])
    records: dict[str, dict[str, Any]] = state["records"]
    journal: list[dict[str, Any]] = []
    base = {"symbol": symbol, "timeframe": timeframe}

    for level in sorted(collect_levels(symbol, timeframe, candles, wedge_result=wedge_result,
                                       horn_observation=horn_observation,
                                       l_shape_observation=l_shape_observation,
                                       box_source=box_source),
                        key=lambda x: (x.confirmed_at_ms, x.level_id)):
        # Do not alias a newly confirmed replacement to an invalidated
        # historical ray merely because both prices fit the ATR merge zone.
        excluded = any(
            previous.get("rejection") == "superseded_by_confirmed_extremum"
            and registered.side == level.side
            and registered.is_horizontal and level.is_horizontal
            and abs(registered.boundary.anchor_price - level.boundary.anchor_price) <= tolerance
            for old_id, previous in records.items()
            for registered in (registry.levels.get(old_id),)
            if registered is not None
        )
        primary = registry.add(level, merge_tolerance=0.0 if excluded else tolerance,
                               prefer_existing=True)
        record = records.get(primary.level_id)
        if record is None:
            records[primary.level_id] = {
                **new_record(primary), "registered_at_ms": latest_close, "sources": [_source_entry(primary)],
                "lifecycle": LIFECYCLE_TRACKING, "candidate": None, "rejection": None,
                "freshness": None, "robot": None, "last_event_ms": latest_close, "notified": [],
            }
            journal.append({"event": "mirror_level_registered", **base, "level_id": primary.level_id,
                            "source": primary.source, "pattern": primary.pattern,
                            "side": primary.side, "anchors": [list(a) for a in primary.anchors],
                            "confirmed_at_ms": primary.confirmed_at_ms})
        elif all(item["level_id"] != level.level_id for item in record["sources"]):
            record["sources"].append(_source_entry(level))
            journal.append({"event": "mirror_level_source_merged", **base, "level_id": primary.level_id,
                            "merged_level_id": level.level_id, "source": level.source,
                            "pattern": level.pattern})

    gaps = detect_fvgs(rows, symbol=symbol, timeframe=timeframe)
    pending = state["pending_notifications"]
    entries = state.setdefault("standalone_entries", [])
    frames = {timeframe: rows, **({"1": list(fine_candles)} if fine_candles and timeframe != "1" else {})}
    for level_id, record in list(records.items()):
        level = registry.levels.get(level_id)
        if level is None or record["lifecycle"] != LIFECYCLE_TRACKING:
            continue
        try:
            record, transitions = _advance(level, record, rows, atr_at=atr_by_close.get, gaps=gaps,
                                           tolerance=tolerance, fine_candles=fine_candles,
                                           confirmed_extrema=(highs if level.side == "upper" else lows))
        except (NakedRetestError, ValueError) as error:
            record.update(lifecycle=LIFECYCLE_REJECTED, rejection=f"invalid_history:{error}"[:200],
                          last_event_ms=latest_close)
            records[level_id] = record
            journal.append({"event": "mirror_level_rejected", **base, "level_id": level_id,
                            "reason": record["rejection"]})
            continue
        record["imbalance"] = _imbalance_quality(record, gaps, rows)
        for status in transitions:
            record["last_event_ms"] = latest_close
            if status == "SUPERSEDED_EXTREMUM":
                # Candidate/Telegram/Robot eligibility is never granted to
                # the superseded, still-unbroken level. Keep its evidence.
                record["candidate"] = False
                pending[:] = [item for item in pending if item["level_id"] != level_id]
                pivot = record["superseding_extremum"]
                # This is a NEW confirmed swing-extremum ray, not a retroactive
                # mutation of the pattern boundary or its campaign. Preserve
                # the historical source and derive a new independent identity
                # from the exact price/time of the wick extremum.
                replacement = horizontal_level(
                    symbol=symbol, timeframe=timeframe, source=SOURCE_SWING_ZONE,
                    pattern=None, side=level.side, price=float(pivot["price"]),
                    anchor_time_ms=int(pivot["pivot_at_ms"]),
                    confirmed_at_ms=int(pivot["confirmed_at_ms"]), touches=1,
                    provenance={"supersedes_level_id": level_id,
                                "source": "confirmed_wick_extremum"},
                )
                registry.add(replacement, merge_tolerance=0.0)
                if replacement.level_id not in records:
                    records[replacement.level_id] = {
                        **new_record(replacement), "registered_at_ms": latest_close,
                        "sources": [_source_entry(replacement)],
                        "lifecycle": LIFECYCLE_TRACKING, "candidate": None,
                        "rejection": None, "freshness": None, "robot": None,
                        "last_event_ms": latest_close, "notified": [],
                    }
                    journal.append({"event": "mirror_level_registered", **base,
                                    "level_id": replacement.level_id,
                                    "source": replacement.source, "pattern": replacement.pattern,
                                    "side": replacement.side,
                                    "anchors": [list(a) for a in replacement.anchors],
                                    "confirmed_at_ms": replacement.confirmed_at_ms,
                                    "supersedes_level_id": level_id})
                record["superseded_by_level_id"] = replacement.level_id
                journal.append({"event": "mirror_level_rejected", **base, "level_id": level_id,
                                "reason": record["rejection"],
                                "superseded_by_level_id": replacement.level_id,
                                "superseding_extremum": pivot})
            elif status == STATUS_UNTESTED:
                rejection = _judge_breakout(level, record, latest_close, step) \
                    or _duplicate_breakout(level_id, level, record, records, registry)
                record["candidate"] = rejection is None
                record["rejection"] = rejection
                record["freshness"] = "STALE" if rejection and rejection.startswith("stale") else "FRESH"
                if record["candidate"]:
                    record["robot"] = _robot_handoff(level, record)
                    pending.append({"level_id": level_id, "kind": "breakout",
                                    "chart": _frozen_event_chart(symbol, timeframe, rows, registry,
                                                                 level_id, record, "breakout")})
                journal.append({"event": "mirror_breakout", **base, "level_id": level_id,
                                "breakout": record["naked_retest"]["breakout"],
                                "evidence": record["breakout_evidence"], "candidate": record["candidate"],
                                "rejection": rejection, "imbalance": record["imbalance"]})
            elif status in (STATUS_RETESTED, STATUS_UNPROVEN):
                record["lifecycle"] = LIFECYCLE_DONE
                if record.get("candidate"):
                    record["robot"] = _robot_handoff(level, record)
                    # Retest is durable for Robot/Terminal, but never a second
                    # Telegram observation for the same MIRROR level campaign.
                journal.append({"event": "mirror_first_retest", **base, "level_id": level_id,
                                "status": status, "retest": record["naked_retest"]["retest"],
                                "candidate": record.get("candidate")})
            elif status == STATUS_DATA_BLOCKED:
                record.update(lifecycle=LIFECYCLE_REJECTED, rejection="history_gap")
                journal.append({"event": "mirror_level_rejected", **base, "level_id": level_id,
                                "reason": "history_gap"})
        for item in _standalone_confirmations(level, record, frames, latest_close):
            entry_id = f"{level_id}@{item['timeframe']}@{item['confirmation_close_ms']}"
            journal.append({"event": "mirror_entry_confirmation", **base, "level_id": level_id,
                            "entry_id": entry_id, "confirmation_timeframe": item["timeframe"],
                            "kind": item["kind"], "rejection": item["rejection"],
                            "terms": item["terms"]})
            if item["terms"] is not None and all(e["entry_id"] != entry_id for e in entries):
                entries.append({"entry_id": entry_id, "terms": item["terms"], "handoff": "PENDING",
                                "candidate_id": None})
        if (record["lifecycle"] == LIFECYCLE_TRACKING and record["status"] == STATUS_WAITING
                and level.anchors[-1][0] < latest_close - WAITING_EXPIRY_CANDLES * step):
            record.update(lifecycle=LIFECYCLE_REJECTED, rejection="expired_before_breakout",
                          last_event_ms=latest_close)
            journal.append({"event": "mirror_level_rejected", **base, "level_id": level_id,
                            "reason": "expired_before_breakout"})
        records[level_id] = record

    # Finished records stay visible for RETENTION_MS; the registry keeps every identity it still
    # needs, so a re-scan inside the window maps a known level back onto it instead of a new one.
    window_start = rows[0]["open_time_ms"]
    for level_id in [key for key, rec in records.items()
                     if rec["lifecycle"] != LIFECYCLE_TRACKING
                     and int(rec.get("last_event_ms") or 0) < now_ms - RETENTION_MS
                     and key in registry.levels
                     and all(t < window_start for t, _ in registry.levels[key].anchors)
                     and not any(item["level_id"] == key for item in pending)]:
        records.pop(level_id)
        registry.levels.pop(level_id, None)
        registry.aliases.pop(level_id, None)

    state.update(registry=registry.to_dict(), records=records, pending_notifications=pending,
                 updated_at_ms=now_ms)
    save_state(state, root)                      # durable before anything leaves the process
    for item in journal:
        append_event(item, root)
    handed = _hand_off_standalone_entries(symbol, state, root)
    for item in journal:
        if item["event"] in ("mirror_breakout", "mirror_first_retest") and item.get("candidate"):
            print(f"{symbol:<15} {timeframe}m MIRROR {item['event']} level={item['level_id']} "
                  f"candidate={item.get('candidate')} {item.get('rejection') or item.get('status') or ''}",
                  flush=True)
    return {"symbol": symbol, "timeframe": timeframe, "levels": len(registry.levels),
            "new_candidates": sum(1 for item in journal
                                  if item["event"] == "mirror_breakout" and item["candidate"]),
            "tracking": sum(1 for r in records.values() if r["lifecycle"] == LIFECYCLE_TRACKING),
            "candidates": sum(1 for r in records.values() if r.get("candidate")),
            "events": [item["event"] for item in journal], "pending": list(pending),
            "standalone_handoffs": handed}


def _hand_off_standalone_entries(symbol: str, state: dict[str, Any], root=None) -> list[str]:
    """Hand each new standalone entry to the common Robot handoff at most once.

    The attempt is made durable (``SENT``) before the handoff; an entry left ``SENT`` by a crash is never
    handed again (a duplicate candidate could spend the campaign twice). Flag off -> ``OFF`` (observation).
    """

    from pattern_robot_integration import is_robot_executable_signal, prepare_robot_handoff

    handed = []
    for entry in state.get("standalone_entries") or ():
        if entry.get("handoff") != "PENDING":
            continue
        snapshot = _standalone_snapshot(symbol, entry["terms"])
        timeframe = entry["terms"]["source_timeframe"]
        if not is_robot_executable_signal(snapshot, timeframe=timeframe):
            entry["handoff"] = "OFF"
            save_state(state, root)
            continue
        entry["handoff"] = "SENT"
        save_state(state, root)
        result = prepare_robot_handoff(snapshot, timeframe=timeframe, enabled=True)
        entry["handoff"] = "HANDED" if result.candidate_id else "FAILED"
        entry["candidate_id"] = result.candidate_id
        save_state(state, root)
        append_event({"event": "mirror_entry_handoff", "symbol": symbol, "entry_id": entry["entry_id"],
                      "handoff": entry["handoff"], "candidate_id": result.candidate_id}, root)
        if result.candidate_id:
            handed.append(result.candidate_id)
    return handed


def mirror_source_token(symbol: str, timeframe: str, level_id: str,
                        kind: str, event_open_time_ms: int) -> str:
    """Opaque callback for the exact breakout/retest event, not just the level."""
    key = f"{symbol}|{timeframe}|{level_id}|{kind}|{int(event_open_time_ms)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def mirror_first_card_archive_id(symbol: str, timeframe: str, level_id: str) -> str:
    """Stable first-card key for this exact level campaign, never its ticker."""
    key = f"{symbol}|{timeframe}|{level_id}"
    return "mirror-first:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _frozen_event_chart(symbol: str, timeframe: str, rows: Sequence[Mapping[str, Any]],
                        registry: LevelRegistry, level_id: str,
                        record: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Freeze the event OHLC and provably related boundaries before Telegram delivery."""
    event = ((record.get("naked_retest") or {}).get("retest") if kind == "first_retest"
             else (record.get("naked_retest") or {}).get("breakout")) or {}
    event_open_ms = int(event["open_time_ms"])
    event_close_ms = event_open_ms + timeframe_ms(timeframe)
    # A delayed delivery must never show bars that closed after this event.
    event_rows = [row for row in rows if int(row["close_time_ms"]) <= event_close_ms]
    selected = registry.levels[level_id]
    origin_ids = {s.get("parent_formation_id") for s in record.get("sources", ())
                  if s.get("parent_formation_id")}
    levels = []
    # Some older pattern snapshots lack a formation ID. A paired boundary
    # still belongs to the same frozen geometry only when its engine decision
    # index, confirmation time, pattern and source all agree. Never pair levels
    # merely because they share a symbol or pattern name.
    selected_decision = selected.provenance.get("decision_index")
    for level in registry.levels.values():
        is_selected = level.level_id == level_id
        same_origin = bool(origin_ids and level.provenance.get("parent_formation_id") in origin_ids)
        same_frozen_geometry = bool(
            not origin_ids and selected_decision is not None
            and level.provenance.get("decision_index") == selected_decision
            and level.confirmed_at_ms == selected.confirmed_at_ms
            and level.source == selected.source and level.pattern == selected.pattern
        )
        if not (is_selected or same_origin or same_frozen_geometry):
            continue
        # Never draw a later pattern boundary on a historical MIRROR event.
        if int(level.confirmed_at_ms) > event_close_ms:
            continue
        item = level.to_dict()
        item["selected"] = is_selected
        levels.append(item)
    source_start_ms = min(
        (int(anchor[0]) for level in levels
         for anchor in level.get("anchors", ())
         if int(anchor[0]) <= event_close_ms),
        default=int(event_rows[max(0, len(event_rows) - 120)]["open_time_ms"]),
    )
    geometry_candles = [
        {k: row[k] for k in ("open_time_ms", "open", "high", "low", "close")}
        for row in event_rows
        if int(row["open_time_ms"]) >= source_start_ms
    ][-2000:]
    return {
        "symbol": symbol, "timeframe": timeframe, "level_id": level_id,
        # Source identity is frozen from the selected detector level, never
        # inferred from the shape of a plotted line or merged source aliases.
        "source": selected.source, "pattern": selected.pattern,
        "retest_confirmed": record.get("status") == STATUS_RETESTED,
        "event_kind": kind,
        "source_formation_ids": sorted({
            f"origin:{symbol}:{timeframe}:{source['parent_formation_id']}"
            for source in record.get("sources", ())
            if source.get("parent_formation_id")
            and int(source.get("confirmed_at_ms") or 0) <= event_close_ms
        }),
        "candles": [{k: row[k] for k in ("open_time_ms", "open", "high", "low", "close")}
                    for row in event_rows[-120:]],
        # The Telegram PNG keeps its 120-candle framing. The Editor evidence
        # separately preserves available bars from the detector's earliest
        # original source anchor, without reconstructing older OHLC or shifting
        # the anchor to the beginning of the chart.
        "geometry_candles": geometry_candles,
        "levels": levels,
        "event_open_time_ms": event.get("open_time_ms"),
        # The breakout OHLC and level are frozen at event time: do not infer
        # the visual label from current market data during delayed delivery.
        "breakout_close": event.get("close") if kind == "breakout" else None,
        "breakout_boundary_at_close": (
            event.get("boundary_at_close") if kind == "breakout" else None
        ),
    }


# --- Telegram -----------------------------------------------------------------------------------

def _utc(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _price(value) -> str:
    return f"{float(value):.10g}"


def level_geometry_text(level: Mapping[str, Any]) -> str:
    anchors = level["anchors"]
    if len(anchors) == 1 or level["boundary"]["slope_per_ms"] == 0:
        return f"горизонталь {_price(level['boundary']['anchor_price'])}"
    (t1, p1), (t2, p2) = anchors[0], anchors[-1]
    return f"наклонная A1 {_utc(t1)} {_price(p1)} → A2 {_utc(t2)} {_price(p2)}"


def mirror_subtype(source: str | None, pattern: str | None, kind: str,
                   *, retest_confirmed: bool = False) -> str:
    """Name only the selected detector's proven source, not its visual slope."""
    from mirror_levels.levels import SOURCE_PATTERN_BOUNDARY, SOURCE_SWING_ZONE

    if source == SOURCE_PATTERN_BOUNDARY:
        return "Граница паттерна · " + (str(pattern) if pattern else "тип не установлен")
    if source == SOURCE_SWING_ZONE:
        # A breakout is not yet proof that support/resistance switched roles.
        return ("Зеркальный уровень" if kind == "first_retest" and retest_confirmed
                else "Горизонтальный уровень · смена роли не подтверждена")
    return "Источник уровня не подтверждён"


def mirror_caption(row: Mapping[str, Any], kind: str) -> str:
    """Owner card from selected level provenance; no guessed MIRROR subtype."""

    level = row.get("level") or {}
    return "\n".join((
        f"🪞 MIRROR · {row['symbol']} · {row['timeframe']}m",
        mirror_subtype(level.get("source"), level.get("pattern"), kind,
                       retest_confirmed=row.get("status") == STATUS_RETESTED),
    ))


# Observation-delivery backpressure: Scanner coverage takes precedence over
# retrying a Telegram Gateway outage. Pending events remain durable.
_MIRROR_SEND_NEXT_AT = 0.0
_MIRROR_SEND_MIN_GAP_SEC = 10.0
_MIRROR_SEND_FAILURE_COOLDOWN_SEC = 300.0


def send_mirror_notifications(symbol: str, timeframe: str, *, test_mode: bool = False, root=None) -> int:
    """Deliver immutable event charts; never substitute a newer symbol chart.

    Legacy cards without frozen evidence are retired without text-only spam.
    Only image-backed cards count as delivered; failed uploads stay pending.
    """

    import config
    from notification import (
        build_tradingview_keyboard, get_telegram_chat_ids,
        get_telegram_owner_chat_id, send_message_to_recipients,
    )
    from telegram_bot import send_photo
    from signal_archive import record_original_signal
    from signal_mirror_geometry_producer import build_mirror_geometry_snapshot
    from mirror_event_chart import render_mirror_chart
    import tempfile

    global _MIRROR_SEND_NEXT_AT
    if not test_mode and time.monotonic() < _MIRROR_SEND_NEXT_AT:
        return 0
    try:
        state = load_state(symbol, timeframe, root)
    except MirrorStateError:
        return 0
    if not state["pending_notifications"]:
        return 0
    rows = {row["level_id"]: row for row in project_state(state)}
    sent = 0
    for item in list(state["pending_notifications"]):
        if item.get("kind") == "first_retest":
            # Retire old pending retest observations without sending or
            # reclassifying a historical event. No retroactive Telegram spam.
            state["pending_notifications"].remove(item)
            save_state(state, root)
            continue
        # At most one network delivery per (symbol, timeframe) call; an outage
        # must not hold the Scanner behind thousands of old MIRROR cards.
        if not test_mode:
            _MIRROR_SEND_NEXT_AT = time.monotonic() + _MIRROR_SEND_MIN_GAP_SEC
        row = rows.get(item["level_id"])
        delivered: bool | str
        if row is None:
            delivered = "level_missing"
        elif not getattr(config, "TELEGRAM_ENABLED", False):
            delivered = "telegram_disabled"
        else:
            text = mirror_caption(row, item["kind"]) + ("\n🧪 TEST MODE" if test_mode else "")
            frozen = item.get("chart")
            if frozen:
                try:
                    with tempfile.TemporaryDirectory(prefix="mirror_event_") as directory:
                        chart_path = Path(directory) / "event.png"
                        render_mirror_chart(frozen, chart_path)
                        owner_id = get_telegram_owner_chat_id()
                        source_token = mirror_source_token(
                            symbol, timeframe, item["level_id"], item["kind"],
                            frozen["event_open_time_ms"])
                        source_ids = frozen.get("source_formation_ids") or []
                        if len(source_ids) != 1:
                            # Ambiguous or absent parent: show the exact level
                            # chart, never attribute it to an arbitrary pattern.
                            source_ids = []
                        source_id = f"mirror-origin:{source_token}"
                        first_id = mirror_first_card_archive_id(symbol, timeframe, item["level_id"])
                        image_bytes = chart_path.read_bytes()
                        if not test_mode and item["kind"] == "breakout":
                            # Preserve the immutable first campaign card; retries
                            # never overwrite it with a retest or later chart.
                            record_original_signal(
                                first_id, symbol=symbol, timeframe=timeframe,
                                pattern=row.get("level_label", "MIRROR"), text=text,
                                image_bytes=image_bytes,
                                geometry_snapshot=build_mirror_geometry_snapshot(first_id, frozen))
                        source_ready = False if test_mode else record_original_signal(
                            source_id, symbol=symbol, timeframe=timeframe,
                            pattern=row.get("level_label", "MIRROR"), text=text,
                            image_bytes=image_bytes, source_formation_ids=source_ids,
                            source_campaign_first_id=first_id,
                            geometry_snapshot=build_mirror_geometry_snapshot(source_id, frozen))
                        delivered = True
                        for chat_id in get_telegram_chat_ids():
                            is_owner = bool(owner_id and chat_id == owner_id)
                            markup = build_tradingview_keyboard(
                                symbol, timeframe, include_review_actions=is_owner,
                                signal_id=source_id if is_owner and source_ready else None)
                            if is_owner and source_ready:
                                markup["inline_keyboard"].insert(0, [{
                                    "text": "↩️ К сигналу",
                                    "callback_data": f"mirror:source:{source_token}",
                                }])
                            response = send_photo(config.TELEGRAM_TOKEN, chat_id, chart_path,
                                                  caption=text[:1024], reply_markup=markup)
                            if not (isinstance(response, dict) and response.get("ok")):
                                delivered = False
                except (ValueError, KeyError, TypeError) as exc:
                    # Invalid frozen evidence cannot be repaired with current
                    # candles; never disguise a text message as a delivered card.
                    print(f"[MIRROR CHART EVIDENCE ERROR] {symbol} {timeframe}m {type(exc).__name__}: {exc}",
                          flush=True)
                    delivered = "invalid_frozen_chart"
                except Exception as exc:
                    print(f"[MIRROR CHART DELIVERY ERROR] {symbol} {timeframe}m {type(exc).__name__}: {exc}",
                          flush=True)
                    delivered = False
            else:
                # Old pending records predate frozen chart snapshots. Retire
                # them without sending misleading text-only notifications.
                delivered = "legacy_chart_unavailable"
        append_event({"event": "mirror_delivery", "symbol": symbol, "timeframe": timeframe,
                      "level_id": item["level_id"], "kind": item["kind"],
                      "chart_frozen": bool(item.get("chart")),
                      "delivered": delivered, "test_mode": bool(test_mode)}, root)
        if delivered is False:
            if not test_mode:
                _MIRROR_SEND_NEXT_AT = time.monotonic() + _MIRROR_SEND_FAILURE_COOLDOWN_SEC
            break
        sent += delivered is True
        state["pending_notifications"].remove(item)
        record = state["records"].get(item["level_id"])
        if record is not None:
            record["notified"] = [*record.get("notified", []), {"kind": item["kind"], "result": delivered}]
        save_state(state, root)
        if not test_mode:
            break
    return sent

# --- Terminal projection (read-only) ------------------------------------------------------------

def _level_label(level: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    parents = sorted({s.get("parent_pattern") or "swing" for s in record.get("sources", ())})
    return f"{' + '.join(parents)} {level['side']}"


def _first_retest_text(record: Mapping[str, Any]) -> str:
    status = record["status"]
    retest = record["naked_retest"].get("retest")
    if status == STATUS_RETESTED:
        return f"первый ретест подтверждён {_utc(retest['open_time_ms'])}"
    if status == STATUS_UNPROVEN:
        return f"касание не доказано {_utc(retest['open_time_ms'])} (fail-closed)"
    if status == STATUS_UNTESTED:
        return "ещё не было (уровень свежий)"
    return "—"


def _imbalance_text(record: Mapping[str, Any]) -> str:
    items = record.get("imbalance") or ()
    if not items:
        return "нет (на допуск не влияет)"
    return "; ".join(f"{i['direction']} {_price(i['bottom'])}–{_price(i['top'])} {i['position']}"
                     + (f" {i['phase']}" if i.get("phase") else "")
                     + (" iFVG" if i.get("inverted") else "") for i in items) + " (атрибут качества)"


def project_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    registry = LevelRegistry.from_dict(state["registry"])
    rows = []
    for level_id, record in state["records"].items():
        level = registry.levels.get(level_id)
        if level is None:
            continue
        level_dict = level.to_dict()
        parents = [s for s in record.get("sources", ()) if s.get("parent_pattern")]
        rows.append({
            "symbol": state["symbol"], "timeframe": state["timeframe"], "level_id": level_id,
            "status": record["status"], "lifecycle": record["lifecycle"],
            "candidate": record.get("candidate"), "freshness": record.get("freshness"),
            "rejection_reason": record.get("rejection"),
            "breakout": record["naked_retest"].get("breakout"),
            "breakout_evidence": record.get("breakout_evidence"),
            "first_retest": record["naked_retest"].get("retest"),
            "level": level_dict, "level_label": _level_label(level_dict, record),
            "level_geometry_text": level_geometry_text(level_dict),
            "imbalance": record.get("imbalance") or [],
            "sources": record.get("sources", []),
            "parent_patterns": [{"pattern": s["parent_pattern"], "formation_id": s.get("parent_formation_id")}
                                for s in parents],
            "aliases": registry.aliases.get(level_id, []),
            "robot": record.get("robot"),
            "registered_at_ms": record.get("registered_at_ms"),
            "last_event_ms": record.get("last_event_ms"),
            "notified": record.get("notified", []),
            "first_retest_text": _first_retest_text(record),
            "imbalance_text": _imbalance_text(record),
            "sources_text": ", ".join(f"{s.get('parent_pattern') or s['source']}" for s in record.get("sources", ())),
        })
    return rows


def project_mirror_levels(root=None, *, limit: int = 200, include_waiting: bool = False) -> dict[str, Any]:
    """Terminal read model over every state file; never writes, never blocks the PAPER owner."""

    directory = evidence_root(root) / STATE_DIR
    rows, unreadable, counts = [], [], {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else ():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            projected = project_state(state)
        except (OSError, ValueError, KeyError, TypeError, MirrorLevelError):
            unreadable.append(path.name)
            continue
        for row in projected:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
            if include_waiting or row["status"] != STATUS_WAITING:
                rows.append(row)
    rows.sort(key=lambda r: (bool(r["candidate"]), int(r["last_event_ms"] or 0)), reverse=True)
    return {"levels": rows[:limit], "counts": counts, "total": len(rows), "unreadable": unreadable,
            "paper_admission": "NOT_AUTHORIZED", "paper_blockers": list(PAPER_BLOCKERS)}
