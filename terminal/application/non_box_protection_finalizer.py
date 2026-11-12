"""Shared non-Box Robot STOP/TAKE finalization from durable trade evidence.

Production PAPER and isolated local SIMULATION use the same immutable Robot
entry fee attribution, realized economics, and obligation lifecycle. This
module has no exchange client or runtime process authority.
"""
from __future__ import annotations

from decimal import Decimal
import logging

from terminal.domain.models import Category, Execution, OrderSide, PositionKey, PositionSide
from terminal.persistence.sqlite_store import (
    PaperProtectionObligationRecord, RobotTradeRecord, SQLiteStore,
)

LOGGER = logging.getLogger(__name__)


def robot_entry_fees(store: SQLiteStore, trade: RobotTradeRecord) -> Decimal | None:
    """Only entry fills owned by this exact Robot candidate are fee evidence."""
    from terminal.application.robot_breakout_monitor import (
        RobotBreakoutMonitorError, robot_entry_order_ids,
    )

    candidate = store.get_robot_candidate(trade.candidate_id)
    if (candidate is None or candidate.robot_state is None
            or trade.entry_path not in {"LIMIT", "MARKET"}
            or trade.entry_quantity is None):
        return None
    try:
        order_ids = robot_entry_order_ids(
            store, trade.trading_account_id, candidate,
            candidate.robot_state.get("execution") or {},
            entry_path=trade.entry_path,
        )
    except RobotBreakoutMonitorError:
        return None
    entry_side = OrderSide.BUY if trade.direction == "LONG" else OrderSide.SELL
    fills = tuple(
        fill
        for order_id in order_ids
        for fill in store.load_executions_for_order(trade.trading_account_id, order_id)
    )
    if (not fills
            or any(fill.symbol != trade.symbol or fill.side is not entry_side for fill in fills)
            or sum((fill.quantity.value for fill in fills), Decimal("0")) != trade.entry_quantity):
        return None
    return sum((fill.fee for fill in fills), Decimal("0"))


def finalize_non_box_protection_obligation(
    store: SQLiteStore,
    obligation: PaperProtectionObligationRecord,
    trade: RobotTradeRecord,
    execution: Execution,
    *,
    now_ms: int,
    require_entry_fees: bool = False,
) -> PaperProtectionObligationRecord:
    """Close an exact non-Box Robot trade ONLY after durable, attested FLAT.

    Production preserves its existing exit-only-fee fallback if entry fees
    are unavailable; isolated SIMULATION uses require_entry_fees=True and
    refuses to claim a complete result without both sides' actual fees.
    """
    if (trade.pattern == "IKIGAI_BOX"
            or trade.trade_id != obligation.trade_id
            or trade.trading_account_id != obligation.trading_account_id
            or trade.symbol != obligation.symbol
            or obligation.winning_leg not in {"STOP", "TAKE"}
            or obligation.status != "DISPATCHING"
            or execution.dedup_key.execution_id != obligation.exec_id
            or execution.order_id != obligation.order_id
            or execution.dedup_key.trading_account_id != trade.trading_account_id
            or execution.symbol != trade.symbol):
        raise ValueError("non-Box protection evidence identity mismatch")
    position_key = PositionKey(trade.trading_account_id, Category.LINEAR, trade.symbol, 0)
    position = store.get_position_projection(position_key)
    if (position is None or position.side is not PositionSide.FLAT
            or position.quantity.value != 0):
        return obligation
    if trade.entry_quantity is None:
        LOGGER.error("Robot protection finalize lacks entry attestation: %s", trade.trade_id)
        return obligation
    if (execution.quantity.value != obligation.observed_quantity
            or (require_entry_fees and execution.quantity.value != trade.entry_quantity)):
        LOGGER.error("Robot protection close quantity is not attested: %s", trade.trade_id)
        return obligation
    exit_side = OrderSide.SELL if trade.direction == "LONG" else OrderSide.BUY
    if execution.side is not exit_side:
        raise ValueError("non-Box protection close side differs from Robot trade")
    entry_fees = robot_entry_fees(store, trade)
    if entry_fees is None:
        if require_entry_fees:
            LOGGER.error("SIMULATION Robot fees unproven: %s", trade.trade_id)
            return obligation
        LOGGER.error("Robot entry fees unproven; retaining exit-only total: %s", trade.trade_id)
        entry_fees = Decimal("0")
    exit_price = execution.price.value
    exit_quantity = execution.quantity.value
    fees = entry_fees + execution.fee
    gross = (exit_quantity * (exit_price - trade.average_entry)
             if trade.direction == "LONG"
             else exit_quantity * (trade.average_entry - exit_price))
    entry_notional = trade.entry_quantity * trade.average_entry
    if entry_notional <= 0:
        return obligation
    pnl_pct = (gross - fees) / entry_notional * Decimal("100")
    store.close_robot_trade(
        trade.trade_id, exit_time_ms=execution.exchange_timestamp_ms,
        exit_price=exit_price, exit_reason=obligation.winning_leg,
        realized_pnl_usdt=gross, realized_pnl_pct=pnl_pct,
        fees_costs_usdt=fees, updated_at_ms=now_ms,
    )
    # Production's existing non-Box finalization leaves projection clearing
    # to its protection lifecycle; do not silently widen that mutation here.
    return store.transition_paper_protection_obligation(
        obligation.obligation_id, expected_status="DISPATCHING",
        next_status="RESOLVED", expected_version=obligation.version,
        updated_at_ms=now_ms,
    )
