"""Robot v0.1 PAPER flat-closure evidence policy.

A Robot entry can be liquidated by an *aggregate* emergency close that was
dispatched for a different, colliding candidate: PAPER ``full_close`` sizes its
market order on the whole confirmed symbol position, so one SELL can flatten
several Robot lots while only the candidate that triggered it records the
emergency outcome. The untouched trade then stays OPEN against an authoritative
FLAT position and blocks ``reconcile_robot`` forever.

This module proves -- or refuses to prove -- that such a stale trade was in fact
closed by that aggregate execution, using only durable rows. It never invents an
exit price, time or reason. It is pure: no I/O, no store, no clock, no logging.
Every guard is fail-closed; ambiguity returns ``None`` rather than a guess.

The proof deliberately requires the emergency marker itself. Robot fills plus an
aggregate closing execution plus a FLAT position are *not* sufficient to emit
``EMERGENCY_CLOSE``: without a durable emergency candidate the closure has no
proven cause and must stay unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT
from terminal.domain.models import Execution, OrderSide, PositionSide

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module store-free
    from terminal.persistence.sqlite_store import (
        PositionProjectionRecord,
        RobotTradeRecord,
    )


EMERGENCY_OUTCOME_CLOSED = "CLOSED_EMERGENCY_PROTECTION_FAILURE"
EMERGENCY_CANDIDATE_STATUS = "INVALIDATED"
EXIT_REASON_EMERGENCY_CLOSE = "EMERGENCY_CLOSE"

_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class CandidateOwnership:
    """Durable per-candidate facts, read by the caller so this module stays pure.

    Covers every candidate of the symbol regardless of lifecycle status: the
    emergency candidate is INVALIDATED and would be invisible to the admission
    layer's owner view, yet its entry fill is part of the closed lot.
    """

    candidate_id: str
    status: str
    limit_order_id: str | None
    emergency_attempted_at_ms: int | None
    emergency_closed_at_ms: int | None
    emergency_outcome: str | None
    has_open_trade: bool


@dataclass(frozen=True, slots=True)
class LotContribution:
    """One reconstructed open-lot entry fill and its proven Robot owner."""

    exec_id: str
    order_id: str
    quantity: Decimal
    candidate_id: str
    candidate_status: str


@dataclass(frozen=True, slots=True)
class EmergencyAttribution:
    """Durable emergency-close marker proving why the aggregate close happened."""

    candidate_id: str
    attempted_at_ms: int
    closed_at_ms: int
    outcome: str
    lot_quantity: Decimal


@dataclass(frozen=True, slots=True)
class FlatClosureEvidence:
    trade_id: str
    candidate_id: str
    closing_exec_id: str
    closing_order_id: str
    closing_quantity: Decimal
    exit_time_ms: int
    exit_price: Decimal
    exit_reason: str
    realized_pnl_usdt: Decimal
    realized_pnl_pct: Decimal
    fees_costs_usdt: Decimal
    open_lot: tuple[LotContribution, ...]
    emergency: EmergencyAttribution


def _sides(direction: str) -> tuple[OrderSide, OrderSide] | None:
    """Return ``(entry_side, exit_side)`` for a Robot direction."""

    if direction == DIRECTION_LONG:
        return OrderSide.BUY, OrderSide.SELL
    if direction == DIRECTION_SHORT:
        return OrderSide.SELL, OrderSide.BUY
    return None


def _order_owner_map(
    candidates: Sequence[CandidateOwnership],
) -> tuple[dict[str, str], dict[str, str]] | None:
    """Map entry ``order_id -> candidate_id`` and ``candidate_id -> status``.

    Duplicate candidate ids, or one entry order claimed by two candidates, make
    ownership ambiguous and fail closed.
    """

    owners: dict[str, str] = {}
    statuses: dict[str, str] = {}
    for candidate in candidates:
        if candidate.candidate_id in statuses:
            return None
        statuses[candidate.candidate_id] = candidate.status
        order_id = candidate.limit_order_id
        if order_id is None:
            continue
        if order_id in owners:
            return None
        owners[order_id] = candidate.candidate_id
    return owners, statuses


def _emergency_candidate(
    candidates: Sequence[CandidateOwnership],
) -> CandidateOwnership | None:
    """Return the single candidate carrying a complete emergency-close marker.

    A partially written marker, an unexpected outcome, or more than one marked
    candidate is ambiguous evidence and fails closed.
    """

    marked: list[CandidateOwnership] = []
    for candidate in candidates:
        fields = (
            candidate.emergency_attempted_at_ms,
            candidate.emergency_closed_at_ms,
            candidate.emergency_outcome,
        )
        if all(field is None for field in fields):
            continue
        if any(field is None for field in fields):
            return None
        if candidate.emergency_outcome != EMERGENCY_OUTCOME_CLOSED:
            return None
        marked.append(candidate)
    if len(marked) != 1:
        return None
    return marked[0]


def prove_flat_closure(
    *,
    trade: "RobotTradeRecord",
    position: "PositionProjectionRecord | None",
    executions: Sequence[Execution],
    candidates: Sequence[CandidateOwnership],
    open_trade_candidate_ids: frozenset[str],
    has_unresolved_obligation: bool,
) -> FlatClosureEvidence | None:
    """Prove that ``trade`` was closed by the symbol's last, aggregate execution.

    ``executions`` must be every execution of this account/symbol. The store's
    SQL orders them by ``exchange_timestamp_ms`` then ``exec_id`` for a
    deterministic read, but ``exec_id`` is only that tie-breaker, never causal
    evidence of execution order. This proof requires the timestamps themselves
    to be strictly increasing; any tie between two ``exchange_timestamp_ms``
    values is ambiguous and rejected rather than resolved lexically.
    ``candidates`` must cover every candidate of the symbol, any status.
    Returns ``None`` unless every guard is proven from those rows.
    """

    # --- trade ownership attestation ------------------------------------
    if has_unresolved_obligation:
        return None
    entry_quantity = trade.entry_quantity
    entry_position_version = trade.entry_position_version
    if entry_quantity is None or entry_position_version is None:
        return None
    if entry_quantity <= 0:
        return None
    if trade.exit_time_ms is not None:
        return None
    sides = _sides(trade.direction)
    if sides is None:
        return None
    entry_side, exit_side = sides

    # Only this trade may own the symbol, and the caller's two ownership views
    # must agree before either is trusted.
    if open_trade_candidate_ids != frozenset({trade.candidate_id}):
        return None
    for candidate in candidates:
        if candidate.has_open_trade != (candidate.candidate_id in open_trade_candidate_ids):
            return None

    # --- authoritative FLAT position bound to the closing execution ------
    if position is None:
        return None
    if position.side is not PositionSide.FLAT or position.quantity.value != 0:
        return None
    if position.version <= entry_position_version:
        return None

    if not executions:
        return None
    # exec_id is a deterministic tie-breaker for the SQL ORDER BY only -- it is
    # never causal proof of execution order. Two executions sharing the same
    # exchange_timestamp_ms are ambiguous for lot reconstruction (and for
    # binding PositionProjection.updated_at_ms to a single execution), so any
    # duplicate timestamp in this history fails closed rather than trusting
    # lexical exec_id ordering.
    previous_timestamp: int | None = None
    for execution in executions:
        if execution.symbol != trade.symbol:
            return None
        if previous_timestamp is not None and execution.exchange_timestamp_ms <= previous_timestamp:
            return None
        previous_timestamp = execution.exchange_timestamp_ms

    closing = executions[-1]
    if closing.side is not exit_side:
        return None
    if position.updated_at_ms != closing.exchange_timestamp_ms:
        return None
    closing_quantity = closing.quantity.value

    # --- open-lot reconstruction ----------------------------------------
    # Walk every earlier execution as a signed net. The last moment the symbol
    # was exactly flat opens the lot that the closing execution liquidated;
    # everything before it is already-settled history (manual or Robot).
    net = Decimal(0)
    last_flat_index = -1
    prefix = executions[:-1]
    for index, execution in enumerate(prefix):
        if execution.side is entry_side:
            net += execution.quantity.value
        elif execution.side is exit_side:
            net -= execution.quantity.value
        else:  # pragma: no cover - OrderSide has exactly two members
            return None
        if net == 0:
            last_flat_index = index
    if net <= 0 or net != closing_quantity:
        return None

    window = prefix[last_flat_index + 1:]
    if not window:
        return None
    # An intermediate closing-side execution inside the open lot means some of
    # the exposure was already reduced by something else; attribution of the
    # final aggregate close is then ambiguous.
    if any(execution.side is not entry_side for execution in window):
        return None

    mapped = _order_owner_map(candidates)
    if mapped is None:
        return None
    order_owner, candidate_status = mapped

    open_lot: list[LotContribution] = []
    attributed: dict[str, Decimal] = {}
    lot_total = Decimal(0)
    for execution in window:
        order_id = execution.order_id.value
        owner = order_owner.get(order_id)
        if owner is None:
            # Manual or otherwise unattributable contribution: fail closed.
            return None
        quantity = execution.quantity.value
        open_lot.append(LotContribution(
            exec_id=execution.dedup_key.exec_id.value,
            order_id=order_id,
            quantity=quantity,
            candidate_id=owner,
            candidate_status=candidate_status[owner],
        ))
        attributed[owner] = attributed.get(owner, Decimal(0)) + quantity
        lot_total += quantity
    if lot_total != closing_quantity:
        return None

    # The stale trade's own entry may have arrived as several PAPER partial
    # fills; what must hold is that they aggregate to its attested quantity.
    trade_quantity = attributed.get(trade.candidate_id)
    if trade_quantity is None or trade_quantity != entry_quantity:
        return None
    # A competing open Robot owner is already excluded: the symbol proved
    # exactly one open trade candidate above, and it is this trade's.

    # --- mandatory emergency attribution --------------------------------
    emergency = _emergency_candidate(candidates)
    if emergency is None:
        return None
    if emergency.status != EMERGENCY_CANDIDATE_STATUS:
        return None
    if emergency.candidate_id == trade.candidate_id:
        return None
    emergency_quantity = attributed.get(emergency.candidate_id)
    if emergency_quantity is None or emergency_quantity <= 0:
        return None
    attempted_at_ms = emergency.emergency_attempted_at_ms
    closed_at_ms = emergency.emergency_closed_at_ms
    if attempted_at_ms is None or closed_at_ms is None:
        return None
    if attempted_at_ms > closed_at_ms:
        return None
    if not attempted_at_ms <= closing.exchange_timestamp_ms <= closed_at_ms:
        return None

    # --- economics, read from the closing execution ----------------------
    # The closing execution is the aggregate, so the trade's own share is taken
    # from its attested entry quantity -- never from closing.quantity, which
    # covers every lot the emergency close flattened.
    entry_notional = entry_quantity * trade.average_entry
    if entry_notional <= 0:
        return None
    exit_price = closing.price.value
    fees_costs_usdt = closing.fee * entry_quantity / closing_quantity
    if trade.direction == DIRECTION_LONG:
        price_delta = exit_price - trade.average_entry
    else:
        price_delta = trade.average_entry - exit_price
    realized_pnl_usdt = entry_quantity * price_delta
    realized_pnl_pct = (realized_pnl_usdt - fees_costs_usdt) / entry_notional * _HUNDRED

    return FlatClosureEvidence(
        trade_id=trade.trade_id,
        candidate_id=trade.candidate_id,
        closing_exec_id=closing.dedup_key.exec_id.value,
        closing_order_id=closing.order_id.value,
        closing_quantity=closing_quantity,
        exit_time_ms=closing.exchange_timestamp_ms,
        exit_price=exit_price,
        exit_reason=EXIT_REASON_EMERGENCY_CLOSE,
        realized_pnl_usdt=realized_pnl_usdt,
        realized_pnl_pct=realized_pnl_pct,
        fees_costs_usdt=fees_costs_usdt,
        open_lot=tuple(open_lot),
        emergency=EmergencyAttribution(
            candidate_id=emergency.candidate_id,
            attempted_at_ms=attempted_at_ms,
            closed_at_ms=closed_at_ms,
            outcome=EMERGENCY_OUTCOME_CLOSED,
            lot_quantity=emergency_quantity,
        ),
    )
