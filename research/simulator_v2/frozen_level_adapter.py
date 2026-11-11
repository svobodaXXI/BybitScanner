"""Shared native frozen-level Robot policy -> isolated protected virtual LIMIT.

Only transforms the exact ORIGINAL robot_l_shape decision and 1-WV LIMIT into
an unsubmitted SIMULATION request. No geometry, admission, strategy, account,
exchange/venue, PAPER/LIVE or Robot-monitor implementation is duplicated.
MIRROR remains separately gated until its native campaign authority is wired.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

import robot_l_shape
from retest_account_risk import position_worst_case_loss_usdt
from terminal.api.models import VolumeUnit
from research.simulator_v2.virtual_exchange import LimitRequest, ProtectedLimitRequest
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings


class FrozenLevelSimulationBlocked(ValueError):
    """Native Robot facts or isolated execution/risk proof are incomplete."""


@dataclass(frozen=True)
class FrozenLevelSimulationPreview:
    candidate_id: str
    pattern: str
    direction: str
    source_timeframe: str
    available_at_ms: int
    protected: ProtectedLimitRequest
    worst_case_loss_usdt: Decimal
    native_net_reward_risk: Decimal


def preview_native_frozen_level(
    candidate: Mapping[str, Any], state: Mapping[str, Any], *,
    settings: SimWedgeRiskSettings, virtual_time_ms: int,
) -> FrozenLevelSimulationPreview:
    """Reuse native frozen-level Robot entry/STOP/TAKE/RR, never submit it.

    The caller must supply an ORIGINAL closed-candle Scanner snapshot and
    original robot_l_shape state on the SAME completed virtual M1. This
    boundary does not approve a candidate, synthesize a signal or bypass
    the production Robot/Autopilot/PAPER admission gates.
    """
    if not isinstance(candidate, Mapping) or candidate.get("status") != "APPROVED":
        raise FrozenLevelSimulationBlocked("no approved native frozen-level candidate")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping) or not isinstance(state, Mapping):
        raise FrozenLevelSimulationBlocked("original Scanner snapshot/Robot state required")
    pattern = robot_l_shape.snapshot_pattern(snapshot)
    if pattern not in ("L-shape", "Double Top", "Double Bottom"):
        raise FrozenLevelSimulationBlocked("frozen-level strategy has no local execution adapter")
    if snapshot.get("robot_handoff_ready") is not True:
        raise FrozenLevelSimulationBlocked("original Scanner handoff not proven")
    if not isinstance(settings, SimWedgeRiskSettings):
        raise FrozenLevelSimulationBlocked("explicit local SIMULATION risk terms required")
    if type(virtual_time_ms) is not int or virtual_time_ms < 0 or virtual_time_ms % 60_000:
        raise FrozenLevelSimulationBlocked("uncommitted virtual M1 clock")
    terms = robot_l_shape.frozen_terms(snapshot)
    if snapshot.get("timeframe") != terms.source_timeframe:
        raise FrozenLevelSimulationBlocked("Scanner/Robot source timeframe differs")
    if snapshot.get("symbol") != candidate.get("symbol"):
        raise FrozenLevelSimulationBlocked("candidate symbol does not match Scanner identity")
    if state.get("phase") != robot_l_shape.PHASE_RETEST_DETECTED:
        raise FrozenLevelSimulationBlocked("original Robot has no completed entry transition")
    retest_ms = state.get("retest_time_ms")
    if type(retest_ms) is not int or retest_ms > virtual_time_ms or retest_ms < terms.breakout_time_ms:
        raise FrozenLevelSimulationBlocked("entry confirmation is not a closed past candle")
    if terms.source_timeframe == "5" and retest_ms % 300_000:
        raise FrozenLevelSimulationBlocked("unclosed five-minute confirmation")
    plan = robot_l_shape.build_initial_retest_limit(
        candidate, state, tick_size=settings.tick_size,
    )
    request = plan.request
    if (plan.candidate_id != candidate.get("candidate_id")
            or request.symbol != snapshot["symbol"]
            or request.volume.unit != VolumeUnit.WORKING_VOLUME
            or request.volume.amount != Decimal("1")
            or request.side.value != ("Buy" if terms.direction == "LONG" else "Sell")):
        raise FrozenLevelSimulationBlocked("native Robot LIMIT identity or one-WV unit changed")
    entry = request.limit_price
    if entry % settings.tick_size:
        raise FrozenLevelSimulationBlocked("native LIMIT violates instrument tick")
    quantity = settings.contracts_per_working_volume
    if (quantity < settings.minimum_quantity
            or quantity % settings.quantity_step
            or quantity * entry > settings.max_notional_usdt):
        raise FrozenLevelSimulationBlocked("virtual quantity/notional gate denied 1 WV")

    stop = robot_l_shape.preferred_stop(
        snapshot, terms, tick_size=settings.tick_size,
    )
    take = terms.target
    if not (stop < entry < take if terms.direction == "LONG" else take < entry < stop):
        raise FrozenLevelSimulationBlocked("original STOP/TAKE do not straddle entry")
    worst_loss = position_worst_case_loss_usdt(
        direction=terms.direction, quantity=quantity, entry_price=entry,
        stop_price=stop, fee_rate=max(settings.entry_fee_rate, settings.exit_fee_rate),
    )
    if worst_loss is None or worst_loss > settings.max_risk_usdt:
        raise FrozenLevelSimulationBlocked("native STOP risk exceeds explicit local budget")
    try:
        rr = robot_l_shape.net_reward_risk(
            terms.direction, entry_price=entry, stop_price=stop,
            target_price=take,
            fee_rate=max(settings.entry_fee_rate, settings.exit_fee_rate),
        )
    except robot_l_shape.RobotLShapeError as exc:
        raise FrozenLevelSimulationBlocked("native Robot net RR is unavailable") from exc
    if rr < robot_l_shape.MIN_REWARD_RISK:
        raise FrozenLevelSimulationBlocked("native Robot net RR below required 2:1")
    return FrozenLevelSimulationPreview(
        candidate_id=plan.candidate_id, pattern=pattern,
        direction=terms.direction, source_timeframe=terms.source_timeframe,
        available_at_ms=retest_ms,
        protected=ProtectedLimitRequest(
            entry=LimitRequest(
                order_id=request.client_action_id.value,
                side="BUY" if terms.direction == "LONG" else "SELL",
                quantity=quantity, limit_price=entry,
            ),
            stop_price=stop, take_price=take,
        ),
        worst_case_loss_usdt=worst_loss,
        native_net_reward_risk=rr,
    )
