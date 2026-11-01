"""Fail-closed proof of a Robot lot closed by a verified non-Robot PAPER command.

No inferred intent, synthetic execution, external I/O, or order dispatch.
A confirmed FLAT net position alone never closes an immutable Robot trade.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from terminal.application.robot_manual_close_proof import RobotManualCloseEvidence
from terminal.domain.models import Category, CommandState, Controller, OrderSide, PositionSide


def prove_nonrobot_robot_close(
    *, trade, candidate, position, executions: Sequence,
    command, entry_order_ids: Sequence[str], entry_fees: Decimal | None,
    unique_open_owner: bool, has_competing_work: bool,
) -> RobotManualCloseEvidence | None:
    if (
        trade is None or candidate is None or position is None
        or command is None or not executions or not entry_order_ids
        or not unique_open_owner or has_competing_work
        or trade.pattern == "IKIGAI_BOX" or trade.exit_time_ms is not None
        or trade.entry_quantity is None or trade.entry_quantity <= 0
        or trade.entry_position_version is None
        or candidate.status != "OPEN"
        or candidate.candidate_id != trade.candidate_id
        or candidate.symbol != trade.symbol
        or position.position_key.trading_account_id != trade.trading_account_id
        or position.position_key.category is not Category.LINEAR
        or position.position_key.symbol != trade.symbol
        or position.position_key.position_idx != 0
        or position.side is not PositionSide.FLAT
        or position.quantity.value != 0
        or str(position.sync_state).lower() != "synced"
        or position.version != trade.entry_position_version + 1
        or command.trading_account_id != trade.trading_account_id
        or command.category is not Category.LINEAR
        or command.symbol != trade.symbol
        or command.position_idx != 0
        or command.controller is not Controller.MANUAL
        or command.command_kind != "create_market"
        or command.current_state is not CommandState.FILLED
        or command.exchange_order_id is None
        or command.normalized_quantity is None
        or command.normalized_quantity.value != trade.entry_quantity
        or not isinstance(command.order_link_id, str)
        or not command.order_link_id.startswith("tw_")
        or len(command.order_link_id) != 36
        or entry_fees is None or not entry_fees.is_finite()
        or entry_fees < 0 or trade.average_entry <= 0
    ):
        return None

    entry_side = (
        OrderSide.BUY if trade.direction == "LONG"
        else OrderSide.SELL if trade.direction == "SHORT" else None
    )
    if entry_side is None:
        return None
    exit_side = OrderSide.SELL if entry_side is OrderSide.BUY else OrderSide.BUY
    if command.side is not exit_side:
        return None
    close = executions[-1]
    if (
        close.dedup_key.trading_account_id != trade.trading_account_id
        or close.dedup_key.category is not Category.LINEAR
        or close.dedup_key.exec_id.value != "paper-exec-" + command.order_link_id
        or close.order_id.value != "paper-order-" + command.order_link_id
        or command.exchange_order_id != close.order_id
        or close.symbol != trade.symbol or close.side is not exit_side
        or close.quantity.value != trade.entry_quantity
        or close.price.value <= 0 or not close.price.value.is_finite()
        or not close.fee.is_finite() or close.fee < 0
        or close.exchange_timestamp_ms != position.updated_at_ms
        or close.exchange_timestamp_ms < trade.entry_time_ms
    ):
        return None

    order_ids = set(entry_order_ids)
    if len(order_ids) != len(entry_order_ids):
        return None
    entry_indices = [i for i, fill in enumerate(executions[:-1])
                     if fill.order_id.value in order_ids]
    if not entry_indices:
        return None
    # From the first attested Robot entry until the Market exit, every
    # execution must be an entry owned by this exact Robot lot. This refuses
    # mixed manual lots, intervening partial closes, overlapping Robot owners
    # and ambiguous equal timestamps, not just mismatched final net quantity.
    window = executions[entry_indices[0]:]
    entry_fills = window[:-1]
    if not entry_fills or any(
        fill.order_id.value not in order_ids
        or fill.symbol != trade.symbol
        or fill.dedup_key.trading_account_id != trade.trading_account_id
        or fill.side is not entry_side
        or fill.quantity.value <= 0
        or not fill.fee.is_finite() or fill.fee < 0
        for fill in entry_fills
    ):
        return None
    if len(entry_indices) != len(entry_fills):
        return None
    if sum((fill.quantity.value for fill in entry_fills), Decimal("0")) != trade.entry_quantity:
        return None
    if sum((fill.fee for fill in entry_fills), Decimal("0")) != entry_fees:
        return None
    timestamps = [fill.exchange_timestamp_ms for fill in window]
    if any(left >= right for left, right in zip(timestamps, timestamps[1:])):
        return None

    gross = trade.entry_quantity * (
        close.price.value - trade.average_entry if trade.direction == "LONG"
        else trade.average_entry - close.price.value
    )
    fees = entry_fees + close.fee
    pct = (gross - fees) / (trade.entry_quantity * trade.average_entry) * Decimal("100")
    return RobotManualCloseEvidence(
        exit_time_ms=close.exchange_timestamp_ms,
        exit_price=close.price.value,
        realized_pnl_usdt=gross,
        realized_pnl_pct=pct,
        fees_costs_usdt=fees,
    )
