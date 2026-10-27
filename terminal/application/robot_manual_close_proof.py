"""Fail-closed PAPER proof of a Robot-owned non-Box manual Market close.

The Robot candidate carries the durable close intent BEFORE dispatch. A
restart can prove the exact execution identity, final FLAT projection, original
entry attestation, fee attribution and realized economics without re-sending
a Market order or inventing historical fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from terminal.domain.models import Category, Execution, OrderSide, PositionSide


@dataclass(frozen=True, slots=True)
class RobotManualCloseEvidence:
    exit_time_ms: int
    exit_price: Decimal
    realized_pnl_usdt: Decimal
    realized_pnl_pct: Decimal
    fees_costs_usdt: Decimal


def prove_robot_manual_close(
    *, trade, candidate, position, fill: Execution | None,
    entry_fees: Decimal | None,
) -> RobotManualCloseEvidence | None:
    """Return verified close economics, or None on any missing/mismatched fact."""
    if trade is None or candidate is None or position is None or fill is None:
        return None
    if trade.exit_time_ms is not None or trade.pattern == "IKIGAI_BOX":
        return None
    state = candidate.robot_state
    if not isinstance(state, Mapping):
        return None
    execution = state.get("execution")
    if not isinstance(execution, Mapping):
        return None
    intent = execution.get("robot_close_all_manual_intent")
    if not isinstance(intent, Mapping):
        return None
    link = intent.get("order_link_id")
    if not isinstance(link, str) or not link.startswith("tw_") or len(link) != 36:
        return None
    if (
        intent.get("trade_id") != trade.trade_id
        or intent.get("candidate_id") != candidate.candidate_id
        or intent.get("symbol") != trade.symbol.value
        or candidate.symbol != trade.symbol
        or candidate.status != "OPEN"
        or trade.candidate_id != candidate.candidate_id
        or trade.entry_quantity is None
        or trade.entry_quantity <= 0
        or trade.entry_position_version is None
        or intent.get("entry_position_version") != trade.entry_position_version
    ):
        return None
    try:
        frozen_quantity = Decimal(str(intent.get("entry_quantity")))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if frozen_quantity != trade.entry_quantity:
        return None
    if (
        position.position_key.trading_account_id != trade.trading_account_id
        or position.position_key.symbol != trade.symbol
        or position.position_key.category is not Category.LINEAR
        or position.position_key.position_idx != 0
        or position.side is not PositionSide.FLAT
        or position.quantity.value != 0
        # Exactly one aggregate PAPER Market execution must have flattened
        # the previously attested Robot lot; any intervening fill is ambiguous.
        or position.version != trade.entry_position_version + 1
        or fill.dedup_key.trading_account_id != trade.trading_account_id
        or fill.dedup_key.category is not Category.LINEAR
        or fill.dedup_key.exec_id.value != "paper-exec-" + link
        or fill.order_id.value != "paper-order-" + link
        or fill.symbol != trade.symbol
        or fill.quantity.value != trade.entry_quantity
        or fill.exchange_timestamp_ms < trade.entry_time_ms
        or position.updated_at_ms != fill.exchange_timestamp_ms
    ):
        return None
    closing_side = (
        OrderSide.SELL if trade.direction == "LONG"
        else OrderSide.BUY if trade.direction == "SHORT"
        else None
    )
    if fill.side is not closing_side:
        return None
    if (
        entry_fees is None
        or not isinstance(entry_fees, Decimal)
        or not entry_fees.is_finite()
        or entry_fees < 0
        or not fill.fee.is_finite()
        or fill.fee < 0
        or trade.average_entry <= 0
        or trade.entry_quantity * trade.average_entry <= 0
    ):
        return None
    price = fill.price.value
    qty = fill.quantity.value
    gross = (
        qty * (price - trade.average_entry)
        if trade.direction == "LONG"
        else qty * (trade.average_entry - price)
    )
    fees = entry_fees + fill.fee
    net_pct = (gross - fees) / (trade.entry_quantity * trade.average_entry) * Decimal("100")
    return RobotManualCloseEvidence(
        exit_time_ms=fill.exchange_timestamp_ms,
        exit_price=price,
        realized_pnl_usdt=gross,
        realized_pnl_pct=net_pct,
        fees_costs_usdt=fees,
    )
