"""Robot v0.1 confirmation Market-entry policy over frozen Scanner geometry.

This module owns strategy gating only. It never retries exchange mutations and
never overlaps a Market entry with an active or ambiguous LIMIT. Execution stays
owned by the shared Terminal PAPER Market capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any, Mapping, Protocol

from robot_partial_fill import MIN_RR, TARGET_WV, missing_wv
from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT, boundary_price
from terminal.api.models import ClientActionId, MarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.domain.models import OrderSide

MIN_EXPECTED_REWARD = Decimal("0.01")

DECISION_WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
DECISION_MARKET_ENTRY = "MARKET_ENTRY"
DECISION_SKIPPED_POOR_RR = "SKIPPED_POOR_RR"
DECISION_SKIPPED_LOW_REWARD = "SKIPPED_LOW_REWARD"
DECISION_BLOCKED_LIMIT_ACTIVE = "BLOCKED_LIMIT_ACTIVE"
DECISION_BLOCKED_LIMIT_AMBIGUOUS = "BLOCKED_LIMIT_AMBIGUOUS"
DECISION_APEX_REACHED = "APEX_REACHED"
DECISION_FULL = "FULL"


class RobotMarketConfirmationError(RuntimeError):
    pass


class PaperMarketSubmitter(Protocol):
    def market(self, request: MarketCommandRequest): ...


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    action: str
    missing_wv: Decimal
    boundary_price: Decimal
    expected_reward: Decimal
    rr: Decimal


@dataclass(frozen=True, slots=True)
class ConfirmationMarketPlan:
    candidate_id: str
    geometry_index: int
    missing_wv: Decimal
    request: MarketCommandRequest


def _decimal(value: Any, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotMarketConfirmationError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise RobotMarketConfirmationError(
            f"{field} must be finite and {'non-negative' if allow_zero else 'positive'}"
        )
    return number


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotMarketConfirmationError(f"{field} must be an integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotMarketConfirmationError(f"{field} must be an integer") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RobotMarketConfirmationError(f"{field} must be an integer")
    return int(number)


def expected_reward_ratio(direction: str, *, entry_price: Decimal, take_price: Decimal) -> Decimal:
    entry = _decimal(entry_price, "entry_price")
    take = _decimal(take_price, "take_price")
    normalized = direction.strip().upper()
    if normalized == DIRECTION_LONG:
        return (take - entry) / entry
    if normalized == DIRECTION_SHORT:
        return (entry - take) / entry
    raise RobotMarketConfirmationError("unsupported Robot direction")


def risk_reward_ratio(
    direction: str,
    *,
    entry_price: Decimal,
    stop_price: Decimal,
    take_price: Decimal,
) -> Decimal:
    entry = _decimal(entry_price, "entry_price")
    stop = _decimal(stop_price, "stop_price")
    reward = expected_reward_ratio(direction, entry_price=entry, take_price=take_price)
    normalized = direction.strip().upper()
    if normalized == DIRECTION_LONG:
        risk = (entry - stop) / entry
    elif normalized == DIRECTION_SHORT:
        risk = (stop - entry) / entry
    else:
        raise RobotMarketConfirmationError("unsupported Robot direction")
    if risk <= 0:
        raise RobotMarketConfirmationError("STOP must define positive risk")
    if reward <= 0:
        return Decimal("0")
    return reward / risk


def evaluate_confirmation(
    signal_snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    candle: Mapping[str, Any],
    *,
    filled_wv: Decimal,
    sizing_reference_price: Decimal,
    stop_price: Decimal,
    take_price: Decimal,
    limit_active: bool,
    limit_state_authoritative: bool,
) -> ConfirmationDecision:
    """Evaluate one authoritative closed 1m candle after retest."""

    if not isinstance(signal_snapshot, Mapping) or not isinstance(state, Mapping):
        raise RobotMarketConfirmationError("snapshot and state must be mappings")
    if not isinstance(candle, Mapping) or candle.get("closed") is not True:
        raise RobotMarketConfirmationError("authoritative closed candle is required")
    if str(candle.get("timeframe", "")).strip() != "1":
        raise RobotMarketConfirmationError("confirmation requires 1m candle")

    direction = str(state.get("direction", "")).strip().upper()
    index = _integer(candle.get("geometry_index"), "geometry_index")
    apex_index = _integer(state.get("apex_index"), "apex_index")
    remainder = missing_wv(_decimal(filled_wv, "filled_wv", allow_zero=True))
    entry = _decimal(sizing_reference_price, "sizing_reference_price")

    if direction == DIRECTION_LONG:
        boundary_side = "upper"
    elif direction == DIRECTION_SHORT:
        boundary_side = "lower"
    else:
        raise RobotMarketConfirmationError("unsupported Robot direction")

    frozen_boundary = _decimal(
        boundary_price(signal_snapshot, side=boundary_side, geometry_index=index),
        "frozen boundary price",
    )
    reward = expected_reward_ratio(direction, entry_price=entry, take_price=take_price)
    rr = risk_reward_ratio(
        direction,
        entry_price=entry,
        stop_price=stop_price,
        take_price=take_price,
    )

    if remainder == 0:
        return ConfirmationDecision(DECISION_FULL, remainder, frozen_boundary, reward, rr)
    if index >= apex_index:
        return ConfirmationDecision(DECISION_APEX_REACHED, remainder, frozen_boundary, reward, rr)

    close = _decimal(candle.get("close"), "candle.close")
    confirmed = close > frozen_boundary if direction == DIRECTION_LONG else close < frozen_boundary
    if not confirmed:
        return ConfirmationDecision(
            DECISION_WAIT_CONFIRMATION, remainder, frozen_boundary, reward, rr
        )
    if not limit_state_authoritative:
        return ConfirmationDecision(
            DECISION_BLOCKED_LIMIT_AMBIGUOUS, remainder, frozen_boundary, reward, rr
        )
    if limit_active:
        return ConfirmationDecision(
            DECISION_BLOCKED_LIMIT_ACTIVE, remainder, frozen_boundary, reward, rr
        )
    if rr < MIN_RR:
        return ConfirmationDecision(
            DECISION_SKIPPED_POOR_RR, remainder, frozen_boundary, reward, rr
        )
    if reward < MIN_EXPECTED_REWARD:
        return ConfirmationDecision(
            DECISION_SKIPPED_LOW_REWARD, remainder, frozen_boundary, reward, rr
        )
    return ConfirmationDecision(DECISION_MARKET_ENTRY, remainder, frozen_boundary, reward, rr)


def _action_id(candidate_id: str, geometry_index: int, missing: Decimal) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0confirmation-market\0{geometry_index}\0{missing.normalize()}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-confirm-market-{digest}")


def build_confirmation_market(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    decision: ConfirmationDecision,
    *,
    geometry_index: int,
    sizing_reference_price: Decimal,
    slippage_type: str,
    slippage_value: Decimal,
) -> ConfirmationMarketPlan:
    if decision.action != DECISION_MARKET_ENTRY:
        raise RobotMarketConfirmationError("Market plan requires MARKET_ENTRY decision")
    if candidate.get("status") != "APPROVED":
        raise RobotMarketConfirmationError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotMarketConfirmationError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotMarketConfirmationError("candidate identity and symbol are required")

    direction = str(state.get("direction", "")).strip().upper()
    if direction == DIRECTION_LONG:
        side = OrderSide.BUY
    elif direction == DIRECTION_SHORT:
        side = OrderSide.SELL
    else:
        raise RobotMarketConfirmationError("unsupported Robot direction")

    missing = _decimal(decision.missing_wv, "missing_wv")
    if missing > TARGET_WV:
        raise RobotMarketConfirmationError("Market volume exceeds 1 WV invariant")
    index = _integer(geometry_index, "geometry_index")
    request = MarketCommandRequest(
        client_action_id=_action_id(candidate_id, index, missing),
        symbol=symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, missing),
        sizing_reference_price=_decimal(sizing_reference_price, "sizing_reference_price"),
        slippage_type=str(slippage_type),
        slippage_value=_decimal(slippage_value, "slippage_value", allow_zero=True),
    )
    return ConfirmationMarketPlan(candidate_id, index, missing, request)


def submit_confirmation_market(submitter: PaperMarketSubmitter, plan: ConfirmationMarketPlan):
    """Submit once through the shared PAPER Market capability; never retry here."""

    return submitter.market(plan.request)
