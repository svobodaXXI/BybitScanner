"""Pure Robot v0.1 late-admission MARKET viability policy.

This module evaluates a catch-up-restored RETEST_DETECTED candidate against the
current authoritative normalized L2 book.  It performs no persistence and no
order submission.  Execution remains owned by the existing shared PAPER Market
path; this module only reuses its deterministic matching semantics to preview
VWAP and current trade economics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

import robot_protection
import robot_state_machine
from robot_market_confirmation import (
    MIN_EXPECTED_REWARD,
    expected_reward_ratio,
    risk_reward_ratio,
)
from robot_partial_fill import MAX_ADVERSE_MOVE
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.domain.models import OrderSide, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook
from terminal.paper.matching import (
    PaperBookUnavailable,
    PaperInsufficientLiquidity,
    match_market_order,
)


MIN_LATE_ADMISSION_RR = Decimal("1.5")
MIN_LATE_ADMISSION_REWARD = MIN_EXPECTED_REWARD
MAX_LATE_ADMISSION_SLIPPAGE = MAX_ADVERSE_MOVE

DECISION_MARKET_ENTRY = "MARKET_ENTRY"
DECISION_BLOCKED_ADMISSION = "BLOCKED_ADMISSION"
DECISION_BLOCKED_OWNERSHIP = "BLOCKED_OWNERSHIP"
DECISION_APEX_REACHED = "APEX_REACHED"
DECISION_BLOCKED_BOOK_UNAVAILABLE = "BLOCKED_BOOK_UNAVAILABLE"
DECISION_BLOCKED_BOOK_STALE = "BLOCKED_BOOK_STALE"
DECISION_BLOCKED_INSUFFICIENT_LIQUIDITY = "BLOCKED_INSUFFICIENT_LIQUIDITY"
DECISION_SKIPPED_POOR_RR = "SKIPPED_POOR_RR"
DECISION_SKIPPED_LOW_REWARD = "SKIPPED_LOW_REWARD"
DECISION_SKIPPED_EXCESS_SLIPPAGE = "SKIPPED_EXCESS_SLIPPAGE"


class RobotLateAdmissionError(RuntimeError):
    """Raised when pure late-admission policy input is internally invalid."""


@dataclass(frozen=True, slots=True)
class LateAdmissionDecision:
    action: str
    projected_vwap: Decimal | None = None
    best_price: Decimal | None = None
    adverse_slippage: Decimal | None = None
    stop_price: Decimal | None = None
    take_price: Decimal | None = None
    expected_reward: Decimal | None = None
    rr: Decimal | None = None


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotLateAdmissionError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotLateAdmissionError(f"{field} must be finite and positive")
    return number


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotLateAdmissionError(f"{field} must be a non-negative integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotLateAdmissionError(f"{field} must be a non-negative integer") from exc
    if (
        not number.is_finite()
        or number < 0
        or number != number.to_integral_value()
    ):
        raise RobotLateAdmissionError(f"{field} must be a non-negative integer")
    return int(number)


def _frozen_apex_index(signal_snapshot: Mapping[str, Any]) -> Decimal:
    geometry = signal_snapshot.get("geometry")
    apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
    if not isinstance(apex, Mapping):
        raise RobotLateAdmissionError("frozen apex is missing")
    return _positive_decimal(apex.get("index"), "frozen apex index")


def _direction_and_side(state: Mapping[str, Any]) -> tuple[str, OrderSide]:
    direction = str(state.get("direction", "")).strip().upper()
    if direction == robot_state_machine.DIRECTION_LONG:
        return direction, OrderSide.BUY
    if direction == robot_state_machine.DIRECTION_SHORT:
        return direction, OrderSide.SELL
    raise RobotLateAdmissionError("unsupported Robot direction")


def _require_late_retest_state(state: Mapping[str, Any]) -> None:
    if state.get("phase") != robot_state_machine.PHASE_RETEST_DETECTED:
        raise RobotLateAdmissionError("late admission requires RETEST_DETECTED state")
    execution = state.get("execution")
    if not isinstance(execution, Mapping) or execution.get("entry_mode") != LATE_ADMISSION_MARKET:
        raise RobotLateAdmissionError("late admission marker is missing")


def _metrics_decision(
    action: str,
    *,
    vwap: Decimal,
    best_price: Decimal,
    adverse_slippage: Decimal,
    stop_price: Decimal,
    take_price: Decimal,
    expected_reward: Decimal,
    rr: Decimal,
) -> LateAdmissionDecision:
    return LateAdmissionDecision(
        action=action,
        projected_vwap=vwap,
        best_price=best_price,
        adverse_slippage=adverse_slippage,
        stop_price=stop_price,
        take_price=take_price,
        expected_reward=expected_reward,
        rr=rr,
    )


def evaluate_late_admission(
    signal_snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    book: NormalizedOrderBook | None,
    *,
    quantity: Quantity,
    current_geometry_index: int,
    now_ms: int,
    max_book_age_ms: int,
    structural_extreme: Decimal,
    tick_size: Decimal,
    frozen_signal_reference_price: Decimal,
    frozen_scanner_target_price: Decimal,
    admission_ready: bool,
    ownership_clear: bool,
) -> LateAdmissionDecision:
    """Evaluate whether a catch-up-restored retest is viable for MARKET entry.

    The caller supplies already-authoritative admission/ownership facts and the
    intended normalized quantity.  This keeps the policy pure while allowing
    RobotBreakoutMonitor to reuse its existing durable gates in the later
    integration slice.
    """

    if not isinstance(signal_snapshot, Mapping) or not isinstance(state, Mapping):
        raise RobotLateAdmissionError("snapshot and state must be mappings")
    _require_late_retest_state(state)
    direction, side = _direction_and_side(state)

    index = _non_negative_int(current_geometry_index, "current_geometry_index")
    now = _non_negative_int(now_ms, "now_ms")
    max_age = _non_negative_int(max_book_age_ms, "max_book_age_ms")
    apex_index = _frozen_apex_index(signal_snapshot)

    if not isinstance(admission_ready, bool):
        raise RobotLateAdmissionError("admission_ready must be boolean")
    if not isinstance(ownership_clear, bool):
        raise RobotLateAdmissionError("ownership_clear must be boolean")
    if not admission_ready:
        return LateAdmissionDecision(DECISION_BLOCKED_ADMISSION)
    if not ownership_clear:
        return LateAdmissionDecision(DECISION_BLOCKED_OWNERSHIP)
    if Decimal(index) >= apex_index:
        return LateAdmissionDecision(DECISION_APEX_REACHED)

    if not isinstance(quantity, Quantity) or quantity.value <= 0:
        raise RobotLateAdmissionError("quantity must be a positive Quantity")
    if book is None:
        return LateAdmissionDecision(DECISION_BLOCKED_BOOK_UNAVAILABLE)

    symbol = str(signal_snapshot.get("symbol", "")).strip().upper()
    if not symbol:
        raise RobotLateAdmissionError("signal snapshot symbol is missing")
    if book.symbol != Symbol(symbol) or book.health is not BookHealth.READY:
        return LateAdmissionDecision(DECISION_BLOCKED_BOOK_UNAVAILABLE)

    age_ms = now - book.received_at_ms
    if age_ms < 0 or age_ms > max_age:
        return LateAdmissionDecision(DECISION_BLOCKED_BOOK_STALE)

    levels = book.asks if side is OrderSide.BUY else book.bids
    if not levels:
        return LateAdmissionDecision(DECISION_BLOCKED_INSUFFICIENT_LIQUIDITY)
    best_price = levels[0].price.value

    try:
        matched = match_market_order(book, side=side, quantity=quantity)
    except PaperBookUnavailable:
        return LateAdmissionDecision(DECISION_BLOCKED_BOOK_UNAVAILABLE)
    except PaperInsufficientLiquidity:
        return LateAdmissionDecision(DECISION_BLOCKED_INSUFFICIENT_LIQUIDITY)

    vwap = matched.vwap.value
    if direction == robot_state_machine.DIRECTION_LONG:
        adverse_slippage = max(Decimal("0"), (vwap - best_price) / best_price)
    else:
        adverse_slippage = max(Decimal("0"), (best_price - vwap) / best_price)

    stop_price = robot_protection.structural_stop(
        direction,
        average_entry=vwap,
        structural_extreme=structural_extreme,
        tick_size=tick_size,
    )
    take_price = robot_protection.frozen_take_90(
        direction,
        frozen_signal_reference_price=frozen_signal_reference_price,
        frozen_scanner_target_price=frozen_scanner_target_price,
    )
    expected_reward = expected_reward_ratio(
        direction,
        entry_price=vwap,
        take_price=take_price,
    )
    rr = risk_reward_ratio(
        direction,
        entry_price=vwap,
        stop_price=stop_price,
        take_price=take_price,
    )

    metrics = {
        "vwap": vwap,
        "best_price": best_price,
        "adverse_slippage": adverse_slippage,
        "stop_price": stop_price,
        "take_price": take_price,
        "expected_reward": expected_reward,
        "rr": rr,
    }
    if rr < MIN_LATE_ADMISSION_RR:
        return _metrics_decision(DECISION_SKIPPED_POOR_RR, **metrics)
    if expected_reward < MIN_LATE_ADMISSION_REWARD:
        return _metrics_decision(DECISION_SKIPPED_LOW_REWARD, **metrics)
    if adverse_slippage > MAX_LATE_ADMISSION_SLIPPAGE:
        return _metrics_decision(DECISION_SKIPPED_EXCESS_SLIPPAGE, **metrics)
    return _metrics_decision(DECISION_MARKET_ENTRY, **metrics)
