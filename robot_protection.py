"""Robot v0.1 STOP/TAKE planning and protection-recovery policy.

Strategy policy lives here; exchange mutations remain owned by the shared PAPER
runtime. No mutation is blindly retried. STOP safety always has priority over
TAKE recovery.
"""

from __future__ import annotations

import robot_l_shape

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import hashlib
import os
import uuid
from typing import Any, Mapping, Protocol

from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT
from terminal.domain.models import Execution, OrderSide, TradingAccountId, Symbol
from terminal.application.command_identity import CommandIdentityFactory
from terminal.api.models import (
    ClientActionId,
    FullCloseCommandRequest,
    PaperStopMutationRequest,
)

# Maximum STOP distance from actual entry for every non-Box Robot pattern
# (Wedge and L-shape, LONG and SHORT; RM-STRUCT-2, owner 2026-10-17). A
# structural STOP that is invalid or beyond it is replaced by the fallback at
# exactly this distance; the entry is not rejected. Ikigai Box has its own policy.
MAX_STOP_DISTANCE = Decimal("0.015")
TAKE_REALIZATION = Decimal("0.90")
PROTECTION_DEADLINE_MS = 5_000
# Minimum planned take/stop ratio for a new entry (retest LIMIT and late Market entry).
MIN_ENTRY_RR = Decimal("1.5")  # Legacy non-Wedge default.
WEDGE_MIN_ENTRY_RR = Decimal("1.5")  # Owner 2026-10-09: Wedge minimum 1.5, not #419 proposed 2
MIN_ENTRY_RR_ENV = "ROBOT_MIN_ENTRY_RR"
MIN_ENTRY_RR_BOUNDS = (Decimal("0"), Decimal("10"))

RECOVERY_PROTECTED = "PROTECTED"
RECOVERY_TAKE_ONLY = "TAKE_RECOVERY"
RECOVERY_WAIT = "WAIT_PROTECTION"
RECOVERY_EMERGENCY_CLOSE = "EMERGENCY_CLOSE"
RECOVERY_EMERGENCY_CLOSE_PENDING = "EMERGENCY_CLOSE_PENDING"
RECOVERY_CLOSED = "CLOSED_EMERGENCY_PROTECTION_FAILURE"


class RobotProtectionError(RuntimeError):
    pass


class BoxActualFillRRUnsatisfied(RobotProtectionError):
    """No tick-aligned STOP beyond P4 reaches net RR >= 2 for the actual entry."""


def min_entry_rr() -> Decimal:
    """Retest-LIMIT entry threshold: ``ROBOT_MIN_ENTRY_RR`` when a valid Decimal in 0..10, else the default."""

    raw = os.environ.get(MIN_ENTRY_RR_ENV)
    if raw is None or not raw.strip():
        return MIN_ENTRY_RR
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return MIN_ENTRY_RR
    low, high = MIN_ENTRY_RR_BOUNDS
    return value if value.is_finite() and low <= value <= high else MIN_ENTRY_RR


def wedge_min_entry_rr() -> Decimal:
    """Respect the owner-approved 1.5R Wedge floor and stricter valid config.

    The rejected #419 hard 2R requirement is not authoritative.
    L-shape and Box have separate policy contracts.
    """
    return max(WEDGE_MIN_ENTRY_RR, min_entry_rr())


class ProtectionSubmitter(Protocol):
    def create_stop(self, request: PaperStopMutationRequest): ...
    def amend_stop(self, request: PaperStopMutationRequest): ...
    def create_take(self, request: PaperStopMutationRequest): ...
    def amend_take(self, request: PaperStopMutationRequest): ...
    def full_close(self, request: FullCloseCommandRequest): ...


@dataclass(frozen=True, slots=True)
class ProtectionPlan:
    candidate_id: str
    symbol: str
    direction: str
    stop_price: Decimal
    take_price: Decimal
    stop_request: PaperStopMutationRequest
    take_request: PaperStopMutationRequest
    # Box only: how the STOP was chosen and the actual-fill net RR it yields.
    stop_basis: str | None = None
    actual_fill_net_rr: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ProtectionRecoveryDecision:
    action: str
    deadline_at_ms: int | None
    emergency_close_request: FullCloseCommandRequest | None = None


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotProtectionError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotProtectionError(f"{field} must be finite and positive")
    return number


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotProtectionError(f"{field} must be an integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotProtectionError(f"{field} must be an integer") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RobotProtectionError(f"{field} must be an integer")
    return int(number)



def wedge_structural_extreme(
    signal_snapshot: Mapping[str, Any], direction: str,
) -> Decimal:
    """Frozen counted Wedge touches: native Robot STOP provenance.

    LONG uses the lowest *counted* lower touch; SHORT uses the highest
    *counted* upper touch. Uncounted excursions are not structural evidence.
    Shared by PAPER Robot and local SIMULATION; never reads market/runtime.
    """
    if not isinstance(signal_snapshot, Mapping):
        raise RobotProtectionError("frozen Wedge signal snapshot is missing")
    geometry = signal_snapshot.get("geometry")
    if not isinstance(geometry, Mapping):
        raise RobotProtectionError("frozen Wedge geometry is missing")
    touches = geometry.get("touches")
    if not isinstance(touches, Mapping):
        raise RobotProtectionError("frozen Wedge touch evidence is missing")
    if direction == DIRECTION_LONG:
        key = "lower_touch_points"
    elif direction == DIRECTION_SHORT:
        key = "upper_touch_points"
    else:
        raise RobotProtectionError("unsupported Wedge direction")
    points = touches.get(key)
    if not isinstance(points, (list, tuple)):
        raise RobotProtectionError(f"no counted {key} available to compute structural_extreme")
    prices = [
        _decimal(point.get("price"), "counted Wedge touch price")
        for point in points
        if isinstance(point, Mapping) and point.get("counted")
    ]
    if not prices:
        raise RobotProtectionError(f"no counted {key} available to compute structural_extreme")
    return min(prices) if direction == DIRECTION_LONG else max(prices)


def wedge_frozen_reference_target(
    signal_snapshot: Mapping[str, Any], direction: str,
) -> tuple[Decimal, Decimal]:
    """Native Robot Wedge frozen width potential, not an inferred future high.

    The source is geometry.pair_metrics.reference_price/start_width exactly
    as in the original RobotBreakoutMonitor._frozen_prices.
    """
    if not isinstance(signal_snapshot, Mapping):
        raise RobotProtectionError("frozen Wedge signal snapshot is missing")
    geometry = signal_snapshot.get("geometry")
    pair_metrics = geometry.get("pair_metrics") if isinstance(geometry, Mapping) else None
    if not isinstance(pair_metrics, Mapping):
        raise RobotProtectionError("signal snapshot pair_metrics is missing reference_price/start_width")
    reference = _decimal(pair_metrics.get("reference_price"), "frozen Wedge reference")
    width = _decimal(pair_metrics.get("start_width"), "frozen Wedge width").copy_abs()
    if direction == DIRECTION_LONG:
        target = reference + width
    elif direction == DIRECTION_SHORT:
        target = reference - width
    else:
        raise RobotProtectionError("unsupported Wedge direction")
    if target <= 0:
        raise RobotProtectionError("frozen Wedge target is not positive")
    return reference, target


def _action_id(candidate_id: str, leg: str, price: Decimal | None = None) -> ClientActionId:
    suffix = "" if price is None else f"\0{price.normalize()}"
    digest = hashlib.sha256(
        f"{candidate_id}\0{leg}{suffix}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-{leg}-{digest}")


def stop_within_limit(direction: str, *, entry_price: Decimal, stop_price: Decimal) -> bool:
    """True when STOP is on the protective side of entry and within MAX_STOP_DISTANCE."""

    entry = _decimal(entry_price, "entry_price")
    stop = _decimal(stop_price, "stop_price")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        return stop < entry and (entry - stop) / entry <= MAX_STOP_DISTANCE
    if normalized_direction == DIRECTION_SHORT:
        return stop > entry and (stop - entry) / entry <= MAX_STOP_DISTANCE
    raise RobotProtectionError("unsupported Robot direction")


def limited_stop(direction: str, *, entry_price: Decimal, preferred_stop: Decimal) -> Decimal:
    """Preferred STOP when within MAX_STOP_DISTANCE on the protective side,
    else the fallback exactly MAX_STOP_DISTANCE from entry (LONG below, SHORT above)."""

    entry = _decimal(entry_price, "entry_price")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        fallback = entry * (Decimal("1") - MAX_STOP_DISTANCE)
    elif normalized_direction == DIRECTION_SHORT:
        fallback = entry * (Decimal("1") + MAX_STOP_DISTANCE)
    else:
        raise RobotProtectionError("unsupported Robot direction")
    if preferred_stop <= 0:
        return fallback
    if stop_within_limit(normalized_direction, entry_price=entry, stop_price=preferred_stop):
        return preferred_stop
    return fallback


def structural_stop(
    direction: str,
    *,
    average_entry: Decimal,
    structural_extreme: Decimal,
    tick_size: Decimal,
) -> Decimal:
    """Return structural STOP with the 1.5% distance fallback.

    LONG structural stop is one tick below the relevant low. SHORT is one tick
    above the relevant high. If that stop is farther than MAX_STOP_DISTANCE
    (1.5%) from the entry, use exactly the 1.5% fallback instead; the entry is
    not rejected for distance alone. The same function serves planned entries
    (RR gates) and filled positions.

    A filled Robot position must never end up with no STOP at all. The
    structural candidate is derived from the frozen signal geometry, but
    ``average_entry`` is the authoritative fill price read after entry --
    intervening price action (partial fills, top-ups, retest slippage) can
    leave the structural extreme on the wrong side of, or equal to, the
    actual entry. Rather than fail closed and leave a filled position with no
    protection at all (CR-PAPER-PROTECTION-LIFECYCLE-001 post-BATUSDT-defect
    fix), an invalid structural candidate falls back to the same fallback distance
    already used for a too-far structural stop, always on the safe side of
    entry.
    """

    entry = _decimal(average_entry, "average_entry")
    extreme = _decimal(structural_extreme, "structural_extreme")
    tick = _decimal(tick_size, "tick_size")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        candidate = extreme - tick
    elif normalized_direction == DIRECTION_SHORT:
        candidate = extreme + tick
    else:
        raise RobotProtectionError("unsupported Robot direction")
    return limited_stop(normalized_direction, entry_price=entry, preferred_stop=candidate)


def tighten_stop(direction: str, *, existing_stop: Decimal | None, proposed_stop: Decimal) -> Decimal:
    """Never widen STOP after averaging or top-up."""

    proposed = _decimal(proposed_stop, "proposed_stop")
    if existing_stop is None:
        return proposed
    existing = _decimal(existing_stop, "existing_stop")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        return max(existing, proposed)
    if normalized_direction == DIRECTION_SHORT:
        return min(existing, proposed)
    raise RobotProtectionError("unsupported Robot direction")


def plan_wedge_partial_at_two_r(
    direction: str, *,
    pattern: str,
    average_entry: Decimal,
    initial_stop: Decimal,
    active_stop: Decimal,
    active_take: Decimal,
    original_quantity: Decimal,
    remaining_quantity: Decimal,
    quantity_step: Decimal,
    entry_fill_ms: int,
    candle_open_ms: int,
    candle_end_ms: int,
    candle_high: Decimal,
    candle_low: Decimal,
    available_at_ms: int,
) -> Decimal | None:
    """Return a 25% reduce-only *quantity proposal*, never an order.

    A real entry must already be filled and protected, and this must be the
    first partial of the trade. Only a complete later M1 bar can signal +2R,
    anchored to the original admission STOP (not a tightened/replaced STOP).
    If the same bar reaches either active STOP or TAKE, the protection event
    takes priority and no partial can be planned from its ambiguous intrabar
    ordering. This assumes the caller supplied attested execution/position,
    original risk, candle source and a durable no-previous-partial fence.
    """
    direction = str(direction).strip().upper()
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("unsupported partial direction")
    if pattern not in ("Falling Wedge", "Rising Wedge"):
        raise RobotProtectionError("partial policy is only proposed for Wedge")
    prices = dict(
        average_entry=average_entry, initial_stop=initial_stop,
        active_stop=active_stop, active_take=active_take,
        original_quantity=original_quantity, remaining_quantity=remaining_quantity,
        quantity_step=quantity_step, candle_high=candle_high, candle_low=candle_low,
    )
    if any(not isinstance(x, Decimal) or not x.is_finite() for x in prices.values()):
        raise RobotProtectionError("unproven partial Decimal inputs")
    if not (
        average_entry > 0 and initial_stop > 0 and active_stop > 0
        and active_take > 0 and original_quantity > 0
        and remaining_quantity == original_quantity and quantity_step > 0
        and candle_high > 0 and candle_low > 0 and candle_high >= candle_low
    ):
        raise RobotProtectionError("invalid protected entry, volume or candle")
    if not all(type(t) is int and t >= 0 for t in (
        entry_fill_ms, candle_open_ms, candle_end_ms, available_at_ms,
    )):
        raise RobotProtectionError("unproven candle time")
    if (
        candle_open_ms % 60_000 != 0
        or candle_end_ms != candle_open_ms + 60_000
        or candle_open_ms < entry_fill_ms
        or available_at_ms < candle_end_ms
    ):
        raise RobotProtectionError("unproven closed post-fill M1 boundary")
    if direction == DIRECTION_LONG:
        if not (initial_stop <= active_stop < average_entry < active_take):
            raise RobotProtectionError("invalid protected LONG risk")
        risk = average_entry - initial_stop
        if candle_low <= active_stop or candle_high >= active_take:
            return None
        reached = candle_high >= average_entry + Decimal(2) * risk
    else:
        if not (active_take < average_entry < active_stop <= initial_stop):
            raise RobotProtectionError("invalid protected SHORT risk")
        risk = initial_stop - average_entry
        if candle_high >= active_stop or candle_low <= active_take:
            return None
        reached = candle_low <= average_entry - Decimal(2) * risk
    if not reached:
        return None
    proposed = (
        original_quantity * Decimal("0.25") / quantity_step
    ).to_integral_value(rounding=ROUND_FLOOR) * quantity_step
    return proposed if Decimal(0) < proposed < remaining_quantity else None


@dataclass(frozen=True, slots=True)
class AttestedPartialEconomics:
    """Fill arithmetic only; an owner must independently attest order ownership."""

    average_entry: Decimal
    original_quantity: Decimal
    closed_quantity: Decimal
    remaining_quantity: Decimal
    realized_gross_pnl: Decimal
    total_entry_fees: Decimal
    realized_exit_fees: Decimal
    first_entry_ms: int
    latest_partial_fill_ms: int


def summarize_attested_robot_partial(
    direction: str, *,
    trading_account_id: TradingAccountId,
    symbol: Symbol,
    entry_order_ids: tuple[str, ...],
    partial_order_id: str,
    entry_executions: tuple[Execution, ...],
    partial_executions: tuple[Execution, ...],
    actual_remaining_quantity: Decimal,
) -> AttestedPartialEconomics:
    """Strictly aggregate exact-ID fills to feed the break-even STOP planner.

    The serialized PAPER owner must FIRST attest that each entry order is
    Robot-owned by this exact trade and that partial_order_id is its one
    durable reduce-only EXIT intent; the independently observed remaining
    position must still belong solely to that trade. A foreign/ambiguous
    execution is not usable. This function submits no commands and never
    itself grants partial-close or STOP-amend authority.
    """
    direction = str(direction).strip().upper()
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("unsupported partial direction")
    if not isinstance(trading_account_id, TradingAccountId) or not isinstance(symbol, Symbol):
        raise RobotProtectionError("partial account/symbol identity unavailable")
    if (
        not isinstance(entry_order_ids, tuple) or not entry_order_ids
        or not all(isinstance(x, str) and x.strip() and x == x.strip() for x in entry_order_ids)
        or len(set(entry_order_ids)) != len(entry_order_ids)
        or not isinstance(partial_order_id, str) or not partial_order_id.strip()
        or partial_order_id in entry_order_ids
        or not isinstance(entry_executions, tuple) or not entry_executions
        or not isinstance(partial_executions, tuple) or not partial_executions
        or not isinstance(actual_remaining_quantity, Decimal)
        or not actual_remaining_quantity.is_finite()
        or actual_remaining_quantity <= 0
    ):
        raise RobotProtectionError("partial evidence or exact order identity unavailable")
    entry_side = OrderSide.BUY if direction == DIRECTION_LONG else OrderSide.SELL
    exit_side = OrderSide.SELL if direction == DIRECTION_LONG else OrderSide.BUY
    seen: set[str] = set()

    def check(fills: tuple[Execution, ...], side: OrderSide, allowed: set[str]) -> None:
        for fill in fills:
            if not isinstance(fill, Execution):
                raise RobotProtectionError("unproven execution type")
            exec_id = fill.dedup_key.exec_id.value
            if (
                fill.dedup_key.trading_account_id != trading_account_id
                or fill.symbol != symbol
                or fill.dedup_key.category.value != "linear"
                or fill.side is not side
                or fill.order_id.value not in allowed
                or exec_id in seen
                or fill.fee < 0
            ):
                raise RobotProtectionError("foreign, duplicate or invalid Robot partial fill")
            seen.add(exec_id)

    check(entry_executions, entry_side, set(entry_order_ids))
    check(partial_executions, exit_side, {partial_order_id})
    # Every asserted entry order must have an actual fill; otherwise a
    # claimed complete source order-set has no corroboration here.
    if set(entry_order_ids) != {fill.order_id.value for fill in entry_executions}:
        raise RobotProtectionError("an entry order lacks execution evidence")
    last_entry = max(fill.exchange_timestamp_ms for fill in entry_executions)
    first_partial = min(fill.exchange_timestamp_ms for fill in partial_executions)
    if first_partial <= last_entry:
        raise RobotProtectionError("partial execution precedes completed entry")
    original = sum((fill.quantity.value for fill in entry_executions), Decimal(0))
    closed = sum((fill.quantity.value for fill in partial_executions), Decimal(0))
    if closed <= 0 or closed >= original or original - closed != actual_remaining_quantity:
        raise RobotProtectionError("partial fills do not match exact remaining Robot exposure")
    notional = sum((fill.quantity.value * fill.price.value for fill in entry_executions), Decimal(0))
    average = notional / original
    sign = Decimal(1) if direction == DIRECTION_LONG else Decimal(-1)
    gross = sum(
        ((fill.price.value - average) * sign * fill.quantity.value for fill in partial_executions),
        Decimal(0),
    )
    return AttestedPartialEconomics(
        average_entry=average, original_quantity=original,
        closed_quantity=closed, remaining_quantity=actual_remaining_quantity,
        realized_gross_pnl=gross,
        total_entry_fees=sum((fill.fee for fill in entry_executions), Decimal(0)),
        realized_exit_fees=sum((fill.fee for fill in partial_executions), Decimal(0)),
        first_entry_ms=min(fill.exchange_timestamp_ms for fill in entry_executions),
        latest_partial_fill_ms=max(fill.exchange_timestamp_ms for fill in partial_executions),
    )


def build_wedge_be_partial_intent(
    *,
    account_id: str,
    trade_id: str,
    candidate_id: str,
    symbol: str,
    direction: str,
    original_quantity: Decimal,
    remaining_quantity: Decimal,
    partial_quantity: Decimal,
    executable_price: Decimal,
    trigger_candle_end_ms: int,
) -> dict[str, object]:
    """Freeze one Wedge partial-exit *intent*, without permission to execute.

    The stable action identity is keyed to the trade, not price or each tick:
    recovering an unconfirmed attempt cannot silently invent a second order.
    The caller must durably persist this exact intent before any owner-thread
    dispatch, prove the order is REDUCE-ONLY for this owned trade, and reconcile
    UNKNOWN submissions rather than replaying them. The existing generic
    MarketCommandRequest does NOT encode reduce_only and is unsafe here.
    """
    ids = (account_id, trade_id, candidate_id, symbol)
    if any(not isinstance(v, str) or not v or v.strip() != v for v in ids):
        raise RobotProtectionError("partial trade/account identity unavailable")
    if any("\x00" in v or any(ord(ch) < 32 for ch in v) for v in ids):
        raise RobotProtectionError("partial identity contains control character")
    if symbol != symbol.upper():
        raise RobotProtectionError("partial symbol must be canonical")
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("unsupported partial direction")
    q = (original_quantity, remaining_quantity, partial_quantity, executable_price)
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in q):
        raise RobotProtectionError("unproven partial volume/price")
    if not (
        original_quantity > 0 and remaining_quantity == original_quantity
        and 0 < partial_quantity < remaining_quantity
        and executable_price > 0
        and partial_quantity <= original_quantity * Decimal("0.25")
    ):
        raise RobotProtectionError("partial must be first 25% or smaller")
    if type(trigger_candle_end_ms) is not int or trigger_candle_end_ms <= 0:
        raise RobotProtectionError("unproven closed M1 trigger timestamp")
    if trigger_candle_end_ms % 60_000:
        raise RobotProtectionError("trigger timestamp is not aligned M1 close")
    digest = hashlib.sha256(
        "\x00".join(("robot-wedge-be-partial-v1", *ids)).encode("utf-8")
    ).hexdigest()[:32]
    identity = CommandIdentityFactory(lambda: uuid.UUID(hex=digest)).create()
    return {
        "version": 1,
        "account_id": account_id,
        "trade_id": trade_id,
        "candidate_id": candidate_id,
        "symbol": symbol,
        "direction": direction,
        "side": "Sell" if direction == DIRECTION_LONG else "Buy",
        "original_quantity": str(original_quantity),
        "partial_quantity": str(partial_quantity),
        "executable_price": str(executable_price),
        "trigger_candle_end_ms": trigger_candle_end_ms,
        "client_action_id": f"robot-wedge-be-{digest}",
        "command_id": identity.command_id.value,
        "order_link_id": identity.order_link_id,
        "reduce_only_required": True,
    }


def restore_wedge_be_partial_intent(
    intent: Mapping[str, object], *,
    account_id: str,
    trade_id: str,
    candidate_id: str,
    symbol: str,
    direction: str,
    original_quantity: Decimal,
    remaining_quantity: Decimal,
) -> dict[str, object]:
    """Fail closed on a conflicting or tampered durable intent after restart.

    This is *not* evidence that a pending/UNKNOWN execution may be submitted
    again. Any existing command ID requires canonical owner reconciliation.
    """
    if not isinstance(intent, Mapping):
        raise RobotProtectionError("missing durable partial intent")
    try:
        partial = Decimal(intent["partial_quantity"])
        price = Decimal(intent["executable_price"])
        time = intent["trigger_candle_end_ms"]
    except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
        raise RobotProtectionError("partial intent values are incomplete") from exc
    rebuilt = build_wedge_be_partial_intent(
        account_id=account_id, trade_id=trade_id, candidate_id=candidate_id,
        symbol=symbol, direction=direction,
        original_quantity=original_quantity, remaining_quantity=remaining_quantity,
        partial_quantity=partial, executable_price=price,
        trigger_candle_end_ms=time,
    )
    if dict(intent) != rebuilt:
        raise RobotProtectionError("durable partial intent conflicts with proven trade")
    return rebuilt


def fee_aware_break_even_stop(
    direction: str, *,
    average_entry: Decimal,
    original_quantity: Decimal,
    closed_quantity: Decimal,
    remaining_quantity: Decimal,
    realized_gross_pnl: Decimal,
    total_entry_fees: Decimal,
    realized_exit_fees: Decimal,
    stop_exit_fee_rate: Decimal,
    tick_size: Decimal,
    current_stop: Decimal,
    executable_price: Decimal,
    worst_case_slippage_ticks: int,
) -> Decimal:
    """Plan a tighten-only fee-aware STOP after an *already proven* partial fill.

    This pure calculation is NOT a trigger, partial-close command, or permission
    to amend protection. The caller must independently prove the +2R event,
    the exact 25% partial execution/identity and fees, authoritative position,
    idempotent state, admission/protection coverage, and the current executable
    quote. A later owner-thread executor must preserve the old armed STOP until
    a correlated amendment is accepted. Unknown evidence must not call here.

    `realized_gross_pnl` is gross from the closed portion; entry fees cover the
    ORIGINAL position, while exit fees cover the ALREADY closed portion.
    Remaining-stop exit fees and worst-case adverse price slippage are reserved
    separately. Future price gaps beyond the reserve can still cause a loss.
    """
    direction = str(direction).strip().upper()
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("unsupported break-even direction")
    numbers = {
        "average_entry": average_entry,
        "original_quantity": original_quantity,
        "closed_quantity": closed_quantity,
        "remaining_quantity": remaining_quantity,
        "realized_gross_pnl": realized_gross_pnl,
        "total_entry_fees": total_entry_fees,
        "realized_exit_fees": realized_exit_fees,
        "stop_exit_fee_rate": stop_exit_fee_rate,
        "tick_size": tick_size,
        "current_stop": current_stop,
        "executable_price": executable_price,
    }
    for name, value in numbers.items():
        if not isinstance(value, Decimal) or not value.is_finite():
            raise RobotProtectionError(f"{name} must be finite Decimal")
    if not (
        average_entry > 0 and original_quantity > 0
        and closed_quantity > 0 and remaining_quantity > 0
        and closed_quantity + remaining_quantity == original_quantity
        and tick_size > 0 and current_stop > 0 and executable_price > 0
        and realized_exit_fees >= 0 and total_entry_fees >= 0
        and Decimal(0) <= stop_exit_fee_rate < Decimal(1)
    ):
        raise RobotProtectionError("unproven break-even quantity, fee or price")
    if type(worst_case_slippage_ticks) is not int or worst_case_slippage_ticks < 0:
        raise RobotProtectionError("invalid break-even slippage reserve")
    if (
        direction == DIRECTION_LONG and current_stop >= executable_price
    ) or (
        direction == DIRECTION_SHORT and current_stop <= executable_price
    ):
        raise RobotProtectionError("existing STOP not safely behind executable quote")

    fees_paid = total_entry_fees + realized_exit_fees
    slip = tick_size * worst_case_slippage_ticks
    if direction == DIRECTION_LONG:
        # Net = closed-gross + (stop-fill - entry)*remaining
        #       - paid-fees - stop-fill*remaining*fee-rate.
        minimum_fill = (
            remaining_quantity * average_entry - realized_gross_pnl + fees_paid
        ) / (remaining_quantity * (Decimal(1) - stop_exit_fee_rate))
        proposed = (
            (minimum_fill + slip) / tick_size
        ).to_integral_value(rounding=ROUND_CEILING) * tick_size
        if proposed >= executable_price:
            raise RobotProtectionError("cannot safely arm break-even STOP below bid")
    else:
        maximum_fill = (
            remaining_quantity * average_entry + realized_gross_pnl - fees_paid
        ) / (remaining_quantity * (Decimal(1) + stop_exit_fee_rate))
        proposed = (
            (maximum_fill - slip) / tick_size
        ).to_integral_value(rounding=ROUND_FLOOR) * tick_size
        if proposed <= 0 or proposed <= executable_price:
            raise RobotProtectionError("cannot safely arm break-even STOP above ask")
    return tighten_stop(direction, existing_stop=current_stop, proposed_stop=proposed)


def frozen_take_90(
    direction: str,
    *,
    frozen_signal_reference_price: Decimal,
    frozen_scanner_target_price: Decimal,
) -> Decimal:
    """Freeze TAKE at 90% realization of Scanner's immutable signal potential."""

    reference = _decimal(frozen_signal_reference_price, "frozen_signal_reference_price")
    target = _decimal(frozen_scanner_target_price, "frozen_scanner_target_price")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        if target <= reference:
            raise RobotProtectionError("LONG Scanner target must be above signal reference")
        return reference + (target - reference) * TAKE_REALIZATION
    if normalized_direction == DIRECTION_SHORT:
        if target >= reference:
            raise RobotProtectionError("SHORT Scanner target must be below signal reference")
        return reference - (reference - target) * TAKE_REALIZATION
    raise RobotProtectionError("unsupported Robot direction")


def build_protection_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
    structural_extreme: Decimal,
    tick_size: Decimal,
    frozen_signal_reference_price: Decimal,
    frozen_scanner_target_price: Decimal,
    existing_stop: Decimal | None = None,
) -> ProtectionPlan:
    if candidate.get("status") != "APPROVED":
        raise RobotProtectionError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")

    proposed_stop = structural_stop(
        direction,
        average_entry=average_entry,
        structural_extreme=structural_extreme,
        tick_size=tick_size,
    )
    stop = tighten_stop(direction, existing_stop=existing_stop, proposed_stop=proposed_stop)
    take = frozen_take_90(
        direction,
        frozen_signal_reference_price=frozen_signal_reference_price,
        frozen_scanner_target_price=frozen_scanner_target_price,
    )
    entry = _decimal(average_entry, "average_entry")
    if direction == DIRECTION_LONG and not (stop < entry < take):
        raise RobotProtectionError("LONG protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop):
        raise RobotProtectionError("SHORT protection geometry is invalid")

    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop,
        take_price=take,
        stop_request=PaperStopMutationRequest(_action_id(candidate_id, "stop", stop), symbol, stop),
        take_request=PaperStopMutationRequest(_action_id(candidate_id, "take", take), symbol, take),
    )


def post_fill_net_rr(
    direction: str, *, average_entry: Decimal, quantity: Decimal,
    entry_fee: Decimal, stop_price: Decimal, take_price: Decimal,
    exit_fee_rate: Decimal = Decimal("0.0006"),
) -> Decimal:
    """Fee-aware RR on durable entry fills and final executable protection.

    Conservative PAPER exit fees use the taker rate; negative/unknown entry
    costs and invalid geometry fail closed rather than admitting a trade.
    """
    entry = _decimal(average_entry, "actual average entry")
    size = _decimal(quantity, "actual filled quantity")
    stop = _decimal(stop_price, "final STOP")
    take = _decimal(take_price, "final TAKE")
    if not entry_fee.is_finite() or entry_fee < 0:
        raise RobotProtectionError("actual entry fee is invalid")
    if not exit_fee_rate.is_finite() or not Decimal(0) <= exit_fee_rate < 1:
        raise RobotProtectionError("PAPER exit fee rate is invalid")
    if direction == DIRECTION_LONG and not (stop < entry < take):
        raise RobotProtectionError("actual LONG protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop):
        raise RobotProtectionError("actual SHORT protection geometry is invalid")
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("actual entry direction is invalid")
    sign = Decimal(1 if direction == DIRECTION_LONG else -1)
    reward = sign * (take - entry) * size - entry_fee - take * size * exit_fee_rate
    risk = sign * (entry - stop) * size + entry_fee + stop * size * exit_fee_rate
    if risk <= 0:
        raise RobotProtectionError("actual STOP carries no positive risk")
    return reward / risk


@dataclass(frozen=True, slots=True)
class BoxStopTerms:
    """Pure terms only; not an order, a fill proof, or execution approval."""

    price: Decimal
    quantity: Decimal


def prepare_box_stop_terms(
    snapshot: Mapping[str, Any], *,
    confirmed_position_quantity: Decimal,
    confirmed_average_entry: Decimal,
) -> BoxStopTerms:
    """Read the frozen Box STOP and size it to externally confirmed exposure.

    The caller must independently prove fill, position ownership and protection
    authorization. This function cannot submit orders or promote BOX_PLAN_ONLY.
    """
    if (snapshot.get("pattern") != "IKIGAI_BOX"
            or snapshot.get("environment") != "PAPER"
            or snapshot.get("execution_authorized") is not False
            or snapshot.get("attempt") != 1):
        raise RobotProtectionError("a non-executable first-attempt PAPER Box snapshot is required")
    plan = snapshot.get("plan")
    if not isinstance(plan, Mapping):
        raise RobotProtectionError("Box plan is missing")
    direction = plan.get("direction")
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("Box direction is invalid")
    prices = plan.get("limit_prices")
    quantities = plan.get("limit_quantities")
    if (not isinstance(prices, (tuple, list)) or len(prices) != 4
            or not isinstance(quantities, (tuple, list)) or len(quantities) != 4):
        raise RobotProtectionError("Box grid must contain four entries")
    levels = tuple(_decimal(price, "Box LIMIT price") for price in prices)
    sizes = tuple(_decimal(qty, "Box LIMIT quantity") for qty in quantities)
    if any(size != sizes[0] for size in sizes):
        raise RobotProtectionError("Box entry quantities must be equal")
    stop = _decimal(plan.get("stop_price"), "frozen Box STOP")
    quantity = _decimal(confirmed_position_quantity, "confirmed position quantity")
    entry = _decimal(confirmed_average_entry, "confirmed average entry")
    if quantity > sum(sizes):
        raise RobotProtectionError("confirmed exposure exceeds the approved Box grid")
    if direction == DIRECTION_LONG:
        if not (stop < levels[3] < levels[2] < levels[1] < levels[0] and stop < entry):
            raise RobotProtectionError("LONG Box STOP is not beyond P4 and actual entry")
    elif not (stop > levels[3] > levels[2] > levels[1] > levels[0] and stop > entry):
        raise RobotProtectionError("SHORT Box STOP is not beyond P4 and actual entry")
    return BoxStopTerms(stop, quantity)



def box_stop_for_actual_entry(
    snapshot: Mapping[str, Any],
    *,
    average_entry: Decimal,
    existing_stop: Decimal | None = None,
) -> Decimal:
    """Return the minimally tightened Box STOP preserving frozen TAKE and net RR>=2.

    The frozen STOP remains preferred. If actual execution makes it fail the
    approved fee-aware 2:1 contract, move it only toward entry, tick by tick in
    effect, to the first ratio-compliant price that is still strictly beyond P4.
    Once an active STOP exists it can never widen.
    """
    if snapshot.get("pattern") != "IKIGAI_BOX":
        raise RobotProtectionError("Ikigai Box snapshot is required")
    plan = snapshot.get("plan")
    inputs = snapshot.get("inputs")
    if not isinstance(plan, Mapping) or not isinstance(inputs, Mapping):
        raise RobotProtectionError("Box plan/inputs are missing")
    direction = str(plan.get("direction", "")).strip().upper()
    if direction not in {DIRECTION_LONG, DIRECTION_SHORT}:
        raise RobotProtectionError("Box direction is invalid")

    levels = plan.get("limit_prices")
    if not isinstance(levels, (tuple, list)) or len(levels) != 4:
        raise RobotProtectionError("Box grid must contain four entries")
    p4 = _decimal(levels[3], "Box P4")
    take = _decimal(plan.get("take_price"), "frozen Box TAKE")
    frozen_stop = _decimal(plan.get("stop_price"), "frozen Box STOP")
    entry = _decimal(average_entry, "actual Box average entry")
    tick = _decimal(inputs.get("tick_size"), "Box tick size")
    def fee(value: object, name: str) -> Decimal:
        try:
            rate = value if isinstance(value, Decimal) else Decimal(str(value))
        except Exception as exc:
            raise RobotProtectionError(f"{name} must be decimal-compatible") from exc
        if not rate.is_finite() or not Decimal(0) <= rate < Decimal(1):
            raise RobotProtectionError(f"{name} must be finite in [0, 1)")
        return rate

    entry_fee = fee(inputs.get("entry_fee_rate"), "Box entry fee")
    target_fee = fee(inputs.get("target_fee_rate"), "Box target fee")
    stop_fee = fee(inputs.get("stop_fee_rate"), "Box STOP fee")

    sign = Decimal(1 if direction == DIRECTION_LONG else -1)
    if sign * (take - entry) <= 0:
        raise RobotProtectionError("actual Box entry is not on the loss side of frozen TAKE")

    current = frozen_stop if existing_stop is None else _decimal(existing_stop, "existing Box STOP")
    if direction == DIRECTION_LONG:
        if not current < p4 < entry:
            raise RobotProtectionError("LONG Box STOP/P4/entry geometry is invalid")
        if existing_stop is not None and current < frozen_stop:
            raise RobotProtectionError("existing LONG Box STOP widens frozen risk")
    else:
        if not current > p4 > entry:
            raise RobotProtectionError("SHORT Box STOP/P4/entry geometry is invalid")
        if existing_stop is not None and current > frozen_stop:
            raise RobotProtectionError("existing SHORT Box STOP widens frozen risk")

    # Price of an armed Box STOP is frozen for the whole attempt. Top-ups
    # change quantity/VWAP, never STOP price (AAVE incident). Actual-fill
    # net RR remains recorded separately and may be below the full-grid RR.
    if existing_stop is not None:
        if current % tick != 0:
            raise RobotProtectionError("existing Box STOP is not tick-aligned")
        return current

    reward = sign * (take - entry) - entry * entry_fee - take * target_fee
    if reward <= 0:
        raise RobotProtectionError("actual Box entry leaves no positive net reward")

    def risk(stop: Decimal) -> Decimal:
        return sign * (entry - stop) + entry * entry_fee + stop * stop_fee

    def acceptable(stop: Decimal) -> bool:
        return (
            stop > 0
            and stop % tick == 0
            and sign * (p4 - stop) > 0
            and risk(stop) > 0
            and Decimal(2) * risk(stop) <= reward
        )

    if acceptable(current):
        return current

    denominator = stop_fee - sign
    if denominator == 0:
        raise RobotProtectionError("Box STOP RR bound is undefined")
    bound = (reward / Decimal(2) - entry * (sign + entry_fee)) / denominator
    if bound <= 0:
        raise BoxActualFillRRUnsatisfied("no positive Box STOP satisfies actual-fill RR")

    from decimal import ROUND_CEILING, ROUND_FLOOR
    rounding = ROUND_CEILING if direction == DIRECTION_LONG else ROUND_FLOOR
    tightened = (bound / tick).to_integral_value(rounding=rounding) * tick

    # Never widen from already-active/frozen protection.
    if direction == DIRECTION_LONG:
        tightened = max(tightened, current)
    else:
        tightened = min(tightened, current)

    if not acceptable(tightened):
        raise BoxActualFillRRUnsatisfied(
            "no tick-aligned Box STOP beyond P4 satisfies actual-fill net RR >= 2"
        )
    return tightened


def box_actual_fill_net_rr(
    snapshot: Mapping[str, Any], *, average_entry: Decimal, stop: Decimal,
) -> Decimal:
    """Fee-aware net RR of the actual entry against ``stop`` and the frozen TAKE."""
    plan = snapshot.get("plan")
    inputs = snapshot.get("inputs")
    if not isinstance(plan, Mapping) or not isinstance(inputs, Mapping):
        raise RobotProtectionError("Box plan/inputs are missing")
    sign = Decimal(1 if str(plan.get("direction", "")).strip().upper() == DIRECTION_LONG else -1)
    take = _decimal(plan.get("take_price"), "frozen Box TAKE")
    entry = _decimal(average_entry, "actual Box average entry")
    stop = _decimal(stop, "Box STOP")

    def fee(value: object, name: str) -> Decimal:
        # Same contract as box_stop_for_actual_entry: a finite rate in [0, 1).
        try:
            rate = value if isinstance(value, Decimal) else Decimal(str(value))
        except Exception as exc:
            raise RobotProtectionError(f"{name} must be decimal-compatible") from exc
        if not rate.is_finite() or not Decimal(0) <= rate < Decimal(1):
            raise RobotProtectionError(f"{name} must be finite in [0, 1)")
        return rate

    entry_fee = fee(inputs.get("entry_fee_rate"), "Box entry fee")
    target_fee = fee(inputs.get("target_fee_rate"), "Box target fee")
    stop_fee = fee(inputs.get("stop_fee_rate"), "Box STOP fee")
    reward = sign * (take - entry) - entry * entry_fee - take * target_fee
    risk = sign * (entry - stop) + entry * entry_fee + stop * stop_fee
    if risk <= 0:
        raise RobotProtectionError("Box STOP carries no positive risk")
    return reward / risk


def _box_full_grid_average(snapshot: Mapping[str, Any]) -> Decimal:
    plan = snapshot.get("plan") or {}
    prices = tuple(_decimal(item, "Box LIMIT price") for item in plan.get("limit_prices") or ())
    sizes = tuple(_decimal(item, "Box LIMIT quantity") for item in plan.get("limit_quantities") or ())
    if len(prices) != 4 or len(sizes) != 4 or sum(sizes) <= 0:
        raise RobotProtectionError("Box grid must contain four entries")
    return sum((p * q for p, q in zip(prices, sizes)), Decimal(0)) / sum(sizes)


def build_box_protection_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
    confirmed_position_quantity: Decimal,
) -> ProtectionPlan:
    """Build shared Robot protection requests from immutable Box terms."""
    if candidate.get("status") != "APPROVED":
        raise RobotProtectionError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("identity", {}).get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")
    if direction != str(snapshot.get("plan", {}).get("direction", "")).strip().upper():
        raise RobotProtectionError("Box direction conflicts with frozen plan")

    stop_terms = prepare_box_stop_terms(
        snapshot,
        confirmed_position_quantity=confirmed_position_quantity,
        confirmed_average_entry=average_entry,
    )
    take = _decimal(snapshot["plan"].get("take_price"), "frozen Box TAKE")
    entry = _decimal(average_entry, "average_entry")
    if direction == DIRECTION_LONG and not (stop_terms.price < entry < take):
        raise RobotProtectionError("LONG Box protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop_terms.price):
        raise RobotProtectionError("SHORT Box protection geometry is invalid")

    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop_terms.price,
        take_price=take,
        stop_request=PaperStopMutationRequest(
            _action_id(candidate_id, "stop", stop_terms.price), symbol, stop_terms.price,
        ),
        take_request=PaperStopMutationRequest(
            _action_id(candidate_id, "take", take), symbol, take,
        ),
    )




def build_box_stop_only_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
    confirmed_position_quantity: Decimal,
    existing_stop: Decimal | None = None,
) -> ProtectionPlan:
    """Build Box aggregate STOP while TAKE is owned by per-slot EXIT LIMITs."""
    if candidate.get("status") not in {"APPROVED", "OPEN"}:
        raise RobotProtectionError("Box candidate must be APPROVED or OPEN")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("identity", {}).get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")
    if direction != str(snapshot.get("plan", {}).get("direction", "")).strip().upper():
        raise RobotProtectionError("Box direction conflicts with frozen plan")
    quantity = _decimal(confirmed_position_quantity, "confirmed position quantity")
    entry = _decimal(average_entry, "average_entry")
    try:
        stop = box_stop_for_actual_entry(
            snapshot, average_entry=entry, existing_stop=existing_stop,
        )
        basis = "ACTUAL_FILL_RR"
    except BoxActualFillRRUnsatisfied as shortfall:
        # PAPER option B (owner, 2026-10-08): a partial first fill may sit below
        # net 2:1. Keep the frozen (or already active, never wider) STOP, but only
        # while the full planned grid itself still proves net RR >= 2.
        try:
            box_stop_for_actual_entry(snapshot, average_entry=_box_full_grid_average(snapshot))
        except RobotProtectionError as error:
            raise RobotProtectionError(
                f"Box full grid does not satisfy net RR >= 2: {error}"
            ) from shortfall
        frozen = snapshot["plan"]
        stop = _decimal(
            existing_stop if existing_stop is not None else frozen.get("stop_price"),
            "Box STOP",
        )
        tick = _decimal((snapshot.get("inputs") or {}).get("tick_size"), "Box tick size")
        p4 = _decimal(frozen["limit_prices"][3], "Box P4")
        beyond_p4 = stop < p4 if direction == DIRECTION_LONG else stop > p4
        if stop <= 0 or stop % tick != 0 or not beyond_p4:
            raise RobotProtectionError(
                "frozen Box STOP is not tick-aligned strictly beyond P4"
            ) from shortfall
        basis = "FROZEN_FIRST_FILL"
    # Preserving an armed STOP can leave a partial/top-up position below net
    # 2:1. Record the truthful basis; do not represent it as RR-compliant.
    if (existing_stop is not None and box_actual_fill_net_rr(
        snapshot, average_entry=entry, stop=stop,
    ) < Decimal("2")):
        basis = "FROZEN_FIRST_FILL"
    take = _decimal(snapshot["plan"].get("take_price"), "frozen Box TAKE")
    if direction == DIRECTION_LONG and not (stop < entry < take):
        raise RobotProtectionError("LONG Box protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop):
        raise RobotProtectionError("SHORT Box protection geometry is invalid")
    # quantity is intentionally validated here even though the shared stop
    # request is position-scoped: callers must prove real exposure first.
    if quantity <= 0:
        raise RobotProtectionError("confirmed Box exposure must be positive")
    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop,
        take_price=take,
        stop_request=PaperStopMutationRequest(
            _action_id(candidate_id, "stop", stop), symbol, stop,
        ),
        # Kept structurally for ProtectionPlan compatibility; OFR-5 callers
        # MUST NOT submit this aggregate TAKE. Slot EXIT LIMITs own TAKE.
        take_request=PaperStopMutationRequest(
            _action_id(candidate_id, "take", take), symbol, take,
        ),
        stop_basis=basis,
        actual_fill_net_rr=box_actual_fill_net_rr(snapshot, average_entry=entry, stop=stop),
    )


def submit_box_stop_only(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    """Submit only the shared Box STOP; paired slot LIMITs own the TAKE side."""
    return submitter.create_stop(plan.stop_request)


def build_l_shape_protection_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
    tick_size: Decimal | None = None,
) -> ProtectionPlan:
    """Build shared protection requests from immutable L-shape STOP/target terms.

    ``tick_size`` is required for a standalone MIRROR entry (one-tick STOP buffer).
    """
    if candidate.get("status") != "APPROVED":
        raise RobotProtectionError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    try:
        terms = robot_l_shape.frozen_terms(snapshot)
    except robot_l_shape.RobotLShapeError as exc:
        raise RobotProtectionError(str(exc)) from exc

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")
    if direction != terms.direction:
        raise RobotProtectionError("L-shape direction conflicts with frozen terms")

    entry = _decimal(average_entry, "average_entry")
    # Frozen L-shape STOP within 1.5% of the actual entry, else the 1.5% fallback.
    try:
        preferred = robot_l_shape.preferred_stop(snapshot, terms, tick_size=tick_size)
    except robot_l_shape.RobotLShapeError as exc:
        raise RobotProtectionError(str(exc)) from exc
    stop = limited_stop(direction, entry_price=entry, preferred_stop=preferred)
    take = terms.target
    if direction == DIRECTION_LONG and not (stop < entry < take):
        raise RobotProtectionError("LONG L-shape protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop):
        raise RobotProtectionError("SHORT L-shape protection geometry is invalid")

    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop,
        take_price=take,
        stop_request=PaperStopMutationRequest(
            _action_id(candidate_id, "stop", stop), symbol, stop,
        ),
        take_request=PaperStopMutationRequest(
            _action_id(candidate_id, "take", take), symbol, take,
        ),
    )

def protection_recovery(
    candidate_id: str,
    symbol: str,
    *,
    position_open: bool,
    stop_proven: bool,
    take_proven: bool,
    protection_started_at_ms: int,
    now_ms: int,
    market_data_authoritative: bool,
    intended_stop_crossed: bool,
    emergency_close_in_flight: bool = False,
    authoritative_flat: bool = False,
) -> ProtectionRecoveryDecision:
    """Fail closed while a filled Robot position lacks proven STOP protection."""

    started = _integer(protection_started_at_ms, "protection_started_at_ms")
    now = _integer(now_ms, "now_ms")
    if now < started:
        raise RobotProtectionError("now_ms precedes protection start")
    deadline = started + PROTECTION_DEADLINE_MS

    if authoritative_flat:
        return ProtectionRecoveryDecision(RECOVERY_CLOSED, None)
    if not position_open:
        raise RobotProtectionError("non-flat recovery state requires open position")
    if stop_proven:
        return ProtectionRecoveryDecision(
            RECOVERY_PROTECTED if take_proven else RECOVERY_TAKE_ONLY,
            None,
        )
    if emergency_close_in_flight:
        return ProtectionRecoveryDecision(RECOVERY_EMERGENCY_CLOSE_PENDING, deadline)

    must_close = (
        not market_data_authoritative
        or intended_stop_crossed
        or now >= deadline
    )
    if must_close:
        request = FullCloseCommandRequest(
            _action_id(candidate_id, "emergency-protection-close"),
            symbol.strip().upper(),
        )
        return ProtectionRecoveryDecision(RECOVERY_EMERGENCY_CLOSE, deadline, request)
    return ProtectionRecoveryDecision(RECOVERY_WAIT, deadline)


def submit_initial_protection(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    """Submit STOP first, then TAKE once each; caller reconciles ambiguous results."""

    stop_result = submitter.create_stop(plan.stop_request)
    take_result = submitter.create_take(plan.take_request)
    return stop_result, take_result


def submit_stop_amend(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    return submitter.amend_stop(plan.stop_request)


def submit_take_amend(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    return submitter.amend_take(plan.take_request)


def submit_emergency_close(submitter: ProtectionSubmitter, decision: ProtectionRecoveryDecision):
    if decision.action != RECOVERY_EMERGENCY_CLOSE or decision.emergency_close_request is None:
        raise RobotProtectionError("decision does not authorize emergency close")
    return submitter.full_close(decision.emergency_close_request)


def emergency_close_request(candidate_id: str, symbol: str) -> FullCloseCommandRequest:
    """Build the emergency full-close request for a filled Robot position whose
    initial protection could not be built, validated, or submitted.

    Uses the exact same deterministic action-id scheme as
    ``protection_recovery()``'s own emergency close, so a later recovery-path
    close attempt for the same candidate is idempotent with this one rather
    than a distinct action.
    """

    return FullCloseCommandRequest(
        _action_id(candidate_id, "emergency-protection-close"), symbol.strip().upper(),
    )
