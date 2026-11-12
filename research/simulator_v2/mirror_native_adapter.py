"""Read-only ORIGINAL standalone MIRROR confirmation -> unsubmitted VirtualExchange plan.

No mirror_scanner.observe_mirror_levels: that route writes durable state and can
hand off to PAPER. This pure boundary reuses its original confirmation and
snapshot functions, robot_l_shape transitions, protection and risk adapters.
It does NOT create a candidate in production or authorize trading; the caller
must own a verified, committed local M1/M5 timeline and the native level state.
Box-attached MIRROR/RETEST remains a separate native execution family.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

import mirror_scanner
import robot_l_shape
from mirror_levels.levels import MirrorLevel
from research.simulator_v2.frozen_level_adapter import (
    FrozenLevelSimulationBlocked, FrozenLevelSimulationPreview,
    preview_native_frozen_level,
)
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings


@dataclass(frozen=True)
class NativeMirrorPreview:
    """A non-executable, same-run local simulation proposal, never PAPER facts."""
    level_id: str
    confirmed_at_ms: int
    candidate_id: str
    source_timeframe: str
    preview: FrozenLevelSimulationPreview


def _closed_frames(
    rows: object, *, step_ms: int, latest_ms: int, label: str,
) -> Sequence[Mapping[str, Any]]:
    if not isinstance(rows, (list, tuple)) or not 4 <= len(rows) <= 5000:
        raise FrozenLevelSimulationBlocked(f"missing bounded closed {label} history")
    previous = None
    for row in rows:
        if not isinstance(row, Mapping) or row.get("closed") is not True:
            raise FrozenLevelSimulationBlocked(f"unverified {label} closed candle")
        op, close = row.get("open_time_ms"), row.get("close_time_ms")
        if (type(op) is not int or type(close) is not int
                or op < 0 or op % step_ms or close != op + step_ms
                or close > latest_ms or (previous is not None and op != previous)):
            raise FrozenLevelSimulationBlocked(f"gap, future or unclosed {label} candle")
        previous = close
    if previous != latest_ms:
        raise FrozenLevelSimulationBlocked(f"{label} source stops before local virtual clock")
    return rows


def preview_confirmed_standalone_mirror(
    *, symbol: str, simulation_run_id: str, level: MirrorLevel,
    native_record: Mapping[str, Any], frames: Mapping[str, Sequence[Mapping[str, Any]]],
    virtual_time_ms: int, settings: SimWedgeRiskSettings,
) -> NativeMirrorPreview:
    """Only the ORIGINAL 5m-level + 1m/5m CLOSED confirmation is eligible.

    This accepts native in-memory level/tracker state, never a JSON candidate
    from the user or a VPS trade. It does not discover levels or submit orders.
    A caller must prove the actual local source before invoking this boundary.
    """
    if not isinstance(settings, SimWedgeRiskSettings):
        raise FrozenLevelSimulationBlocked("explicit virtual instrument/risk proof required")
    if (not isinstance(level, MirrorLevel) or not level.is_horizontal
            or level.timeframe != "5" or level.symbol != symbol
            or not isinstance(simulation_run_id, str) or not simulation_run_id
            or type(virtual_time_ms) is not int or virtual_time_ms <= 0
            or virtual_time_ms % 300_000 or level.confirmed_at_ms >= virtual_time_ms):
        raise FrozenLevelSimulationBlocked("standalone MIRROR requires a known closed M5 level")
    if (not isinstance(native_record, Mapping)
            or native_record.get("level_id") != level.level_id
            or native_record.get("candidate") is not True
            or native_record.get("status") != mirror_scanner.STATUS_UNTESTED
            or native_record.get("lifecycle") != mirror_scanner.LIFECYCLE_TRACKING
            or native_record.get("rejection") is not None):
        raise FrozenLevelSimulationBlocked("original MIRROR untested candidate unavailable")
    if not isinstance(frames, Mapping):
        raise FrozenLevelSimulationBlocked("closed M1/M5 confirmation required")
    m5 = _closed_frames(frames.get("5"), step_ms=300_000,
                        latest_ms=virtual_time_ms, label="M5")
    m1 = _closed_frames(frames.get("1"), step_ms=60_000,
                        latest_ms=virtual_time_ms, label="M1")
    if (m1[-5]["open_time_ms"] != virtual_time_ms - 300_000
            or m1[-1]["close"] != m5[-1]["close"]):
        raise FrozenLevelSimulationBlocked("M1/M5 sources disagree at confirmed boundary")
    # Do not mutate the original native tracker. The source itself owns its
    # candidate/cursor lifecycle and de-duplicates this frozen confirmation.
    offered = mirror_scanner._standalone_confirmations(
        level, deepcopy(dict(native_record)), {"1": m1, "5": m5}, virtual_time_ms,
    )
    ready = [item for item in offered
             if item.get("terms") is not None
             and virtual_time_ms - 300_000 < item.get("confirmation_close_ms", 0) <= virtual_time_ms]
    if len(ready) != 1:
        raise FrozenLevelSimulationBlocked(
            "no single original closed standalone MIRROR confirmation at this M5 boundary"
        )
    item = ready[0]
    snapshot = mirror_scanner._standalone_snapshot(symbol, item["terms"])
    snapshot_text = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    candidate_id = "sim_mirror_" + hashlib.sha256(
        (simulation_run_id + "\0" + level.level_id + "\0" + snapshot_text).encode("utf-8")
    ).hexdigest()[:32]
    candidate = {
        "candidate_id": candidate_id, "status": "APPROVED",
        "symbol": symbol, "timeframe": item["timeframe"],
        "signal_snapshot": snapshot,
    }
    try:
        native_state, event = robot_l_shape.initialize_state(candidate)
        if event != robot_l_shape.EVENT_MIRROR_CONFIRMATION_READY:
            raise FrozenLevelSimulationBlocked("native MIRROR Robot did not confirm")
        preview = preview_native_frozen_level(
            candidate, native_state, settings=settings,
            virtual_time_ms=virtual_time_ms,
            _native_mirror_confirmation_proven=True,
        )
    except robot_l_shape.RobotLShapeError as exc:
        raise FrozenLevelSimulationBlocked("original MIRROR Robot rejected confirmation") from exc
    return NativeMirrorPreview(
        level_id=level.level_id, confirmed_at_ms=item["confirmation_close_ms"],
        candidate_id=candidate_id, source_timeframe=item["timeframe"],
        preview=preview,
    )
