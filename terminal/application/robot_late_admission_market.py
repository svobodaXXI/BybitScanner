"""Deterministic shared-Market plan for Robot v0.1 late admission.

This module builds command identity and request data only. It performs no
persistence, no market-data fetch, and no order submission. RobotBreakoutMonitor
owns durable intent ordering; TerminalCommandApi owns normalization/execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import uuid
from typing import Any, Mapping

import robot_state_machine
from terminal.api.models import (
    ClientActionId,
    MarketCommandRequest,
    VolumeRequest,
    VolumeUnit,
)
from terminal.application.command_identity import (
    CommandIdentityCandidate,
    CommandIdentityFactory,
)
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.domain.models import OrderSide, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook


LATE_ADMISSION_MARKET_WV = Decimal("1")
LATE_ADMISSION_SLIPPAGE_TYPE = "Percent"
LATE_ADMISSION_SLIPPAGE_PERCENT = Decimal("0.5")


class RobotLateAdmissionMarketError(RuntimeError):
    """Raised when a deterministic late-admission Market plan is invalid."""


@dataclass(frozen=True, slots=True)
class LateAdmissionMarketPlan:
    candidate_id: str
    direction: str
    best_price: Decimal
    request: MarketCommandRequest
    identity: CommandIdentityCandidate


def _stable_digest(candidate_id: str) -> str:
    return hashlib.sha256(
        f"{candidate_id}\0late-admission-market".encode("utf-8")
    ).hexdigest()[:32]


def _stable_action_id(candidate_id: str) -> ClientActionId:
    return ClientActionId(f"robot-late-market-{_stable_digest(candidate_id)}")


def _stable_command_identity(candidate_id: str) -> CommandIdentityCandidate:
    deterministic_uuid = uuid.UUID(hex=_stable_digest(candidate_id))
    return CommandIdentityFactory(lambda: deterministic_uuid).create()


def build_late_admission_market_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    book: NormalizedOrderBook,
) -> LateAdmissionMarketPlan:
    """Build the single 1-WV MARKET intent for a replay-discovered retest.

    The sizing reference is the current executable best price on the same side
    that the shared PAPER Market path will consume. Canonical quantity remains
    owned by TerminalCommandApi.market_preflight(); this builder never duplicates
    instrument normalization.
    """

    if not isinstance(candidate, Mapping) or not isinstance(state, Mapping):
        raise RobotLateAdmissionMarketError("candidate and state must be mappings")
    if candidate.get("status") != "APPROVED":
        raise RobotLateAdmissionMarketError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotLateAdmissionMarketError("late admission requires 1m candidate")
    if state.get("phase") != robot_state_machine.PHASE_RETEST_DETECTED:
        raise RobotLateAdmissionMarketError("late admission requires RETEST_DETECTED")

    execution = state.get("execution")
    if not isinstance(execution, Mapping) or execution.get("entry_mode") != LATE_ADMISSION_MARKET:
        raise RobotLateAdmissionMarketError("late admission marker is missing")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    snapshot = candidate.get("signal_snapshot")
    if not candidate_id or not isinstance(snapshot, Mapping):
        raise RobotLateAdmissionMarketError("candidate identity and snapshot are required")
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    if not symbol:
        raise RobotLateAdmissionMarketError("signal snapshot symbol is missing")

    direction = str(state.get("direction", "")).strip().upper()
    if direction == robot_state_machine.DIRECTION_LONG:
        side = OrderSide.BUY
        levels = book.asks
    elif direction == robot_state_machine.DIRECTION_SHORT:
        side = OrderSide.SELL
        levels = book.bids
    else:
        raise RobotLateAdmissionMarketError("unsupported Robot direction")

    if book.symbol != Symbol(symbol) or book.health is not BookHealth.READY:
        raise RobotLateAdmissionMarketError("normalized book is not READY for candidate symbol")
    if not levels:
        raise RobotLateAdmissionMarketError("executable book side is empty")

    best_price = levels[0].price.value
    if not isinstance(best_price, Decimal) or not best_price.is_finite() or best_price <= 0:
        raise RobotLateAdmissionMarketError("best executable price is invalid")

    request = MarketCommandRequest(
        client_action_id=_stable_action_id(candidate_id),
        symbol=symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, LATE_ADMISSION_MARKET_WV),
        sizing_reference_price=best_price,
        slippage_type=LATE_ADMISSION_SLIPPAGE_TYPE,
        slippage_value=LATE_ADMISSION_SLIPPAGE_PERCENT,
    )
    return LateAdmissionMarketPlan(
        candidate_id=candidate_id,
        direction=direction,
        best_price=best_price,
        request=request,
        identity=_stable_command_identity(candidate_id),
    )
