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
answer; PAPER admission of a standalone MIRROR candidate is not authorised. The
PAPER Robot reads these candidates (``mirror_retest_robot.scanner_level_sources``)
only as RETEST campaigns for its own Box attempts in the campaign direction.

Durability: the state (registry, tracker records, pending notifications) is
replaced atomically before any Telegram send; a pending card is re-sent after a
crash (at least once), a delivered one never. An unreadable state file is never
overwritten: the symbol/timeframe is skipped and the error journaled, so a
tested level can never be rediscovered as a new untested one.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence

from geometry.naked_retest import NakedRetestError, PHASE_CAMPAIGN_ACTIVE
from mirror_levels.imbalance import detect_fvgs, replay as replay_fvg
from mirror_levels.levels import (
    LevelRegistry, MirrorLevel, MirrorLevelError, levels_from_geometry, levels_from_horn_event,
    levels_from_ikigai_box, levels_from_l_shape, timeframe_ms,
)
from mirror_levels.swing import swing_levels
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
WAITING_EXPIRY_CANDLES = 400        # an unbroken level whose last anchor left two Scanner windows
RETENTION_MS = 3 * 86_400_000       # finished records are kept 3 days for the Terminal

LIFECYCLE_TRACKING = "TRACKING"
LIFECYCLE_DONE = "DONE"
LIFECYCLE_REJECTED = "REJECTED"

WEDGE_ENGINE_PATTERNS = frozenset({"Rising Wedge", "Falling Wedge", "Triangle Compression"})

# Why a detected MIRROR candidate cannot reach PAPER on its own (shown in Terminal, never bypassed here).
PAPER_BLOCKERS = (
    "standalone_mirror_trading_rules_not_owner_accepted",
    "mirror_not_in_robot_supported_patterns",
    "paper_mirror_execution_only_as_box_attempt_overlay",
)

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


def _judge_breakout(record: Mapping[str, Any], latest_close_ms: int, step: int) -> str | None:
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
             fine_candles) -> tuple[dict[str, Any], list[str]]:
    """Feed unconsumed closed candles one at a time; returns the record and its status transitions."""

    cursor = record["naked_retest"].get("cursor_close_time_ms")
    transitions = []
    for row in rows:
        if cursor is not None and row["close_time_ms"] <= cursor:
            continue
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
    registry = LevelRegistry.from_dict(state["registry"])
    records: dict[str, dict[str, Any]] = state["records"]
    journal: list[dict[str, Any]] = []
    base = {"symbol": symbol, "timeframe": timeframe}

    for level in sorted(collect_levels(symbol, timeframe, candles, wedge_result=wedge_result,
                                       horn_observation=horn_observation,
                                       l_shape_observation=l_shape_observation,
                                       box_source=box_source),
                        key=lambda x: (x.confirmed_at_ms, x.level_id)):
        primary = registry.add(level, merge_tolerance=tolerance, prefer_existing=True)
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
    for level_id, record in list(records.items()):
        level = registry.levels.get(level_id)
        if level is None or record["lifecycle"] != LIFECYCLE_TRACKING:
            continue
        try:
            record, transitions = _advance(level, record, rows, atr_at=atr_by_close.get, gaps=gaps,
                                           tolerance=tolerance, fine_candles=fine_candles)
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
            if status == STATUS_UNTESTED:
                rejection = _judge_breakout(record, latest_close, step) \
                    or _duplicate_breakout(level_id, level, record, records, registry)
                record["candidate"] = rejection is None
                record["rejection"] = rejection
                record["freshness"] = "STALE" if rejection and rejection.startswith("stale") else "FRESH"
                if record["candidate"]:
                    record["robot"] = _robot_handoff(level, record)
                    pending.append({"level_id": level_id, "kind": "breakout"})
                journal.append({"event": "mirror_breakout", **base, "level_id": level_id,
                                "breakout": record["naked_retest"]["breakout"],
                                "evidence": record["breakout_evidence"], "candidate": record["candidate"],
                                "rejection": rejection, "imbalance": record["imbalance"]})
            elif status in (STATUS_RETESTED, STATUS_UNPROVEN):
                record["lifecycle"] = LIFECYCLE_DONE
                if record.get("candidate"):
                    record["robot"] = _robot_handoff(level, record)
                    pending.append({"level_id": level_id, "kind": "first_retest"})
                journal.append({"event": "mirror_first_retest", **base, "level_id": level_id,
                                "status": status, "retest": record["naked_retest"]["retest"],
                                "candidate": record.get("candidate")})
            elif status == STATUS_DATA_BLOCKED:
                record.update(lifecycle=LIFECYCLE_REJECTED, rejection="history_gap")
                journal.append({"event": "mirror_level_rejected", **base, "level_id": level_id,
                                "reason": "history_gap"})
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
            "events": [item["event"] for item in journal], "pending": list(pending)}


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


def mirror_caption(row: Mapping[str, Any], kind: str) -> str:
    """Owner card for one MIRROR event, from the Terminal projection row."""

    breakout = row.get("breakout") or {}
    evidence = row.get("breakout_evidence") or {}
    direction = {"UP": "вверх", "DOWN": "вниз"}.get(breakout.get("direction"), "—")
    lines = [
        f"🪞 MIRROR · {row['symbol']} {row['timeframe']}m"
        + (" · первый ретест" if kind == "first_retest" else " · пробой"),
        f"Пробой {direction} (ретест-кампания {breakout.get('campaign_direction', '—')}), "
        f"{evidence.get('kind', '—')}"
        + (f", тело {evidence['body_atr']:.2f} ATR" if evidence.get("body_atr") is not None else ""),
        f"Уровень: {row['level_label']} — {level_geometry_text(row['level'])}",
        f"Свеча пробоя: {_utc(breakout['open_time_ms'])} O {_price(breakout['open'])} "
        f"C {_price(breakout['close'])}" if breakout else "Свеча пробоя: —",
        f"Ретест: {row['first_retest_text']}",
        f"FVG: {row['imbalance_text']}",
        f"Источники: {row['sources_text']}",
        "Робот: только наблюдение — PAPER-допуск MIRROR не авторизован",
    ]
    return "\n".join(lines)


def send_mirror_notifications(symbol: str, timeframe: str, *, test_mode: bool = False, root=None) -> int:
    """Deliver pending MIRROR cards through the Scanner's Telegram interface; returns cards sent.

    A card leaves the pending list only after delivery to every recipient (or when
    Telegram is disabled), and the state is saved after each one.
    """

    import config
    from notification import build_tradingview_keyboard, send_message_to_recipients

    try:
        state = load_state(symbol, timeframe, root)
    except MirrorStateError:
        return 0
    if not state["pending_notifications"]:
        return 0
    rows = {row["level_id"]: row for row in project_state(state)}
    sent = 0
    for item in list(state["pending_notifications"]):
        row = rows.get(item["level_id"])
        delivered: bool | str
        if row is None:
            delivered = "level_missing"
        elif not getattr(config, "TELEGRAM_ENABLED", False):
            delivered = "telegram_disabled"
        else:
            text = mirror_caption(row, item["kind"]) + ("\n🧪 TEST MODE" if test_mode else "")
            markup = build_tradingview_keyboard(symbol, timeframe, include_review_actions=False)
            delivered = bool(send_message_to_recipients(text, reply_markup=markup))
        append_event({"event": "mirror_delivery", "symbol": symbol, "timeframe": timeframe, **item,
                      "delivered": delivered, "test_mode": bool(test_mode)}, root)
        if delivered is False:
            continue                              # stays pending; retried on the next pass
        sent += delivered is True
        state["pending_notifications"].remove(item)
        record = state["records"].get(item["level_id"])
        if record is not None:
            record["notified"] = [*record.get("notified", []), {"kind": item["kind"], "result": delivered}]
        save_state(state, root)
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
