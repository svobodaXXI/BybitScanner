"""PAPER-only IMPULSE_FLOW terms for the existing Scanner -> Robot owner path.

This module neither subscribes to market data nor executes orders. Source
completeness is limited to two independently certified closed M1 minutes:
live publicTrade continuity remains UNPROVEN outside that bounded window.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import hashlib
import os
from typing import Any, Mapping

from robot_entry_flow_evidence import IMPULSE_RESEARCH_TARGET_R
from terminal.api.models import (
    ClientActionId, LimitCommandRequest, PaperStopMutationRequest,
    TimeInForce, VolumeRequest, VolumeUnit,
)
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import OrderSide

PATTERN = "IMPULSE_FLOW"
PAPER_OPT_IN = "BYBITSCANNER_ROBOT_IMPULSE_PAPER_AUTO"
ENTRY_PHASE = "IMPULSE_ENTRY_READY"
STATE_VERSION = 1
MAX_SIGNAL_AGE_MS = 90_000
MAX_RESTING_MS = 120_000


class ImpulseRobotError(ValueError):
    pass


def paper_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Explicit PAPER opt-in. Never enabled by the general Autopilot switch."""
    values = os.environ if environ is None else environ
    return values.get(PAPER_OPT_IN) == "1"


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ImpulseRobotError(f"{name} must be a positive Decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as error:
        raise ImpulseRobotError(f"{name} must be a positive Decimal") from error
    if not result.is_finite() or result <= 0:
        raise ImpulseRobotError(f"{name} must be a positive Decimal")
    return result


@dataclass(frozen=True, slots=True)
class FrozenImpulseTerms:
    symbol: str
    direction: str
    closed_at_ms: int
    closed_price: Decimal
    structural_extreme: Decimal


def frozen_terms(snapshot: Mapping[str, Any]) -> FrozenImpulseTerms:
    """Validate the frozen output of the trusted two-minute Scanner producer.

    Source claims alone grant no authority: the in-process producer must
    certify BOTH closed minutes against recent-trade and official kline
    identities, then record the true post-fetch decision time. Bybit seq
    does not prove continuous feed delivery.
    """
    if not isinstance(snapshot, Mapping) or snapshot.get("pattern") != PATTERN:
        raise ImpulseRobotError("frozen IMPULSE_FLOW snapshot required")
    if (snapshot.get("timeframe") != "1"
            or snapshot.get("robot_handoff_ready") is not True
            or snapshot.get("scanner_observational_only") is True):
        raise ImpulseRobotError("closed M1 Robot handoff is unavailable")
    source = snapshot.get("impulse_source")
    if (not isinstance(source, Mapping)
            or source.get("kind") != "BYBIT_TRIPLE_CLOSED_M1_CERTIFIED"
            or source.get("scope") != "TWO_CLOSED_M1"
            or source.get("source_complete") is not True
            or source.get("receipt_cutoff_proven") is not True
            or source.get("transport_generation_proven") is not True):
        raise ImpulseRobotError("source-complete causal impulse tape is unproven")
    data = snapshot.get("impulse")
    if not isinstance(data, Mapping):
        raise ImpulseRobotError("frozen impulse signal is missing")
    symbol = snapshot.get("symbol")
    direction = data.get("direction")
    close_ms = source.get("closed_at_ms")
    decided_ms = data.get("known_at_ms")
    if (not isinstance(symbol, str) or not symbol.endswith("USDT")
            or symbol != symbol.upper()
            or direction not in ("LONG", "SHORT")
            or type(close_ms) is not int or close_ms <= 0 or close_ms % 60_000
            or type(decided_ms) is not int or not
            close_ms <= decided_ms <= close_ms + MAX_SIGNAL_AGE_MS):
        raise ImpulseRobotError("impulse identity, direction or M1 close is invalid")
    price = _decimal(data.get("closed_price"), "closed_price")
    extreme = _decimal(data.get("structural_extreme"), "structural_extreme")
    if ((direction == "LONG" and extreme >= price)
            or (direction == "SHORT" and extreme <= price)):
        raise ImpulseRobotError("frozen structural STOP is not adverse to entry")
    if source.get("decision_ms") != decided_ms:
        raise ImpulseRobotError("source proof/decision time differs")
    return FrozenImpulseTerms(symbol, direction, close_ms, price, extreme)


def initialize_state(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping) or candidate.get("status") != "APPROVED":
        raise ImpulseRobotError("candidate must be APPROVED")
    if not isinstance(candidate.get("signal_snapshot"), Mapping):
        raise ImpulseRobotError("candidate snapshot missing")
    terms = frozen_terms(candidate["signal_snapshot"])
    return {
        "state_version": STATE_VERSION,
        "phase": ENTRY_PHASE,
        "pattern": PATTERN,
        "direction": terms.direction,
        "signal_close_ms": terms.closed_at_ms,
        "execution": {},
    }


def frozen_entry_request(
    candidate_id: str, snapshot: Mapping[str, Any], *, tick_size: Decimal,
) -> LimitCommandRequest:
    """One canonical 1 WV GTC LIMIT; existing PAPER owner handles sizing/market."""
    terms = frozen_terms(snapshot)
    tick = _decimal(tick_size, "tick_size")
    side = OrderSide.BUY if terms.direction == "LONG" else OrderSide.SELL
    mode = ROUND_FLOOR if terms.direction == "LONG" else ROUND_CEILING
    raw = (terms.closed_price / tick).to_integral_value(rounding=mode) * tick
    price = normalize_limit_price(raw, tick, side)
    if price <= 0 or not isinstance(candidate_id, str) or not candidate_id:
        raise ImpulseRobotError("invalid candidate identity or entry price")
    token = hashlib.sha256(
        f"{candidate_id}\\0impulse-limit\\0{terms.closed_at_ms}".encode("utf-8")
    ).hexdigest()[:32]
    return LimitCommandRequest(
        client_action_id=ClientActionId("robot-impulse-limit-" + token),
        symbol=terms.symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        sizing_reference_price=price,
        limit_price=price,
        time_in_force=TimeInForce.GTC,
    )


def protection_after_fill(
    candidate_id: str, snapshot: Mapping[str, Any], *,
    average_entry: Decimal, tick_size: Decimal,
):
    """Reuse the canonical STOP/TAKE request types using ACTUAL filled entry."""
    import robot_protection

    terms = frozen_terms(snapshot)
    entry = _decimal(average_entry, "actual average_entry")
    tick = _decimal(tick_size, "tick_size")
    stop = robot_protection.structural_stop(
        terms.direction, average_entry=entry,
        structural_extreme=terms.structural_extreme, tick_size=tick,
    )
    distance = abs(entry - stop)
    target = (entry + distance * IMPULSE_RESEARCH_TARGET_R
              if terms.direction == "LONG"
              else entry - distance * IMPULSE_RESEARCH_TARGET_R)
    mode = ROUND_CEILING if terms.direction == "LONG" else ROUND_FLOOR
    take = (target / tick).to_integral_value(rounding=mode) * tick
    if (take <= 0 or
            (terms.direction == "LONG" and not stop < entry < take) or
            (terms.direction == "SHORT" and not take < entry < stop)):
        raise ImpulseRobotError("actual impulse fill has invalid STOP/TAKE")
    return robot_protection.ProtectionPlan(
        candidate_id=candidate_id, symbol=terms.symbol,
        direction=terms.direction, stop_price=stop, take_price=take,
        stop_request=PaperStopMutationRequest(
            robot_protection._action_id(candidate_id, "stop", stop), terms.symbol, stop,
        ),
        take_request=PaperStopMutationRequest(
            robot_protection._action_id(candidate_id, "take", take), terms.symbol, take,
        ),
    )
