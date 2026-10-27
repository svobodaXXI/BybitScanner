"""Read-only verified economics for a coordinated account-wide PAPER Close-All.

Never infer missing fill, cost basis, fee or remaining-position evidence.
The Robot path consumes its exact closed trade ledger; manual positions
require a single full PAPER Market exit and a reproducible unmodified entry
lot from this account's immutable fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Iterable

from terminal.domain.models import Category, OrderSide, PositionSide


@dataclass(frozen=True, slots=True)
class PaperCloseAllSymbolReport:
    symbol: str
    owner: str
    evidence_status: str
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    quantity: Decimal | None = None
    gross_pnl_usdt: Decimal | None = None
    fees_costs_usdt: Decimal | None = None
    net_pnl_usdt: Decimal | None = None
    reason: str | None = None


def paper_close_all_market_link(action_id: str, symbol: str) -> str:
    digest = hashlib.sha256(
        ("paper-account-close-all" + chr(0) + action_id + chr(0) + symbol)
        .encode("utf-8")
    ).hexdigest()[:32]
    return f"tw_{digest}{sum(bytes.fromhex(digest)) & 0xF:x}"


def unproven(symbol: str, owner: str, reason: str) -> PaperCloseAllSymbolReport:
    return PaperCloseAllSymbolReport(symbol, owner, "UNPROVEN", reason=reason)


def verified_robot_close(symbol: str, trade, after) -> PaperCloseAllSymbolReport:
    if trade is None or after is None:
        return unproven(symbol, "ROBOT", "robot_close_evidence_missing")
    if (
        trade.symbol.value != symbol
        or trade.exit_time_ms is None
        or trade.exit_reason != "MANUAL"
        or trade.exit_price is None or trade.exit_price <= 0
        or trade.average_entry <= 0
        or trade.entry_quantity is None or trade.entry_quantity <= 0
        or trade.realized_pnl_usdt is None
        or trade.fees_costs_usdt is None
        or not trade.realized_pnl_usdt.is_finite()
        or not trade.fees_costs_usdt.is_finite()
        or trade.fees_costs_usdt < 0
        or after.position_key.symbol.value != symbol
        or after.side is not PositionSide.FLAT
        or after.quantity.value != 0
    ):
        return unproven(symbol, "ROBOT", "robot_closed_trade_unproven")
    return PaperCloseAllSymbolReport(
        symbol, "ROBOT", "VERIFIED", trade.average_entry, trade.exit_price,
        trade.entry_quantity, trade.realized_pnl_usdt, trade.fees_costs_usdt,
        trade.realized_pnl_usdt - trade.fees_costs_usdt,
    )


def verified_manual_close(
    *, symbol: str, before, after, exit_fill, fills: Iterable,
    expected_link: str, account_id,
) -> PaperCloseAllSymbolReport:
    bad = lambda why: unproven(symbol, "MANUAL", why)
    if before is None or after is None or exit_fill is None:
        return bad("paper_market_exit_evidence_missing")
    if (
        before.position_key.trading_account_id != account_id
        or after.position_key.trading_account_id != account_id
        or before.position_key.symbol.value != symbol
        or after.position_key.symbol.value != symbol
        or before.position_key.category is not Category.LINEAR
        or before.position_key.position_idx != 0
        or before.side not in (PositionSide.LONG, PositionSide.SHORT)
        or before.quantity.value <= 0
        or before.average_entry is None
        or before.average_entry.value <= 0
        or after.side is not PositionSide.FLAT
        or after.quantity.value != 0
        or after.version != before.version + 1
        or after.updated_at_ms != exit_fill.exchange_timestamp_ms
        or exit_fill.exchange_timestamp_ms < before.updated_at_ms
        or exit_fill.dedup_key.trading_account_id != account_id
        or exit_fill.dedup_key.category is not Category.LINEAR
        or exit_fill.symbol.value != symbol
        or exit_fill.dedup_key.exec_id.value != "paper-exec-" + expected_link
        or exit_fill.order_id.value != "paper-order-" + expected_link
        or exit_fill.quantity.value != before.quantity.value
    ):
        return bad("paper_flat_or_exit_identity_unproven")
    opening_side = OrderSide.BUY if before.side is PositionSide.LONG else OrderSide.SELL
    closing_side = OrderSide.SELL if before.side is PositionSide.LONG else OrderSide.BUY
    if exit_fill.side is not closing_side:
        return bad("paper_exit_side_unproven")
    rows = tuple(fills)
    if not rows or rows[-1].dedup_key != exit_fill.dedup_key:
        return bad("paper_exit_history_incomplete")
    # Reconstruct the latest lot from every ordered fill, resetting at FLAT.
    # A partial exit inside the current lot makes entry-fee allocation
    # ambiguous; do not claim NET in that case.
    outstanding = Decimal("0")
    entry_notional = Decimal("0")
    entry_fees = Decimal("0")
    entry_side = None
    modified = False
    previous_ms = -1
    last_start_quantity = None
    last_entry_notional = None
    last_entry_fees = None
    for item in rows:
        if (
            item.symbol.value != symbol
            or item.dedup_key.trading_account_id != account_id
            or item.dedup_key.category is not Category.LINEAR
            or item.exchange_timestamp_ms <= previous_ms
            or item.quantity.value <= 0
            or not item.fee.is_finite()
            or item.fee < 0
        ):
            return bad("paper_fill_history_ambiguous")
        previous_ms = item.exchange_timestamp_ms
        qty = item.quantity.value
        if outstanding == 0:
            entry_side = item.side
            entry_notional = Decimal("0")
            entry_fees = Decimal("0")
            modified = False
        if item.side is entry_side:
            outstanding += qty
            entry_notional += qty * item.price.value
            entry_fees += item.fee
        else:
            if qty > outstanding:
                return bad("paper_crossed_net_position")
            if item.dedup_key == exit_fill.dedup_key:
                last_start_quantity = outstanding
                last_entry_notional = entry_notional
                last_entry_fees = entry_fees
                if modified:
                    return bad("paper_partial_exit_cost_basis_unproven")
            else:
                modified = True
            outstanding -= qty
    if (
        outstanding != 0
        or entry_side is not opening_side
        or last_start_quantity != before.quantity.value
        or last_entry_notional is None
        or last_entry_fees is None
        or last_entry_notional / before.quantity.value != before.average_entry.value
    ):
        return bad("paper_entry_cost_basis_unproven")
    gross = (
        before.quantity.value * (exit_fill.price.value - before.average_entry.value)
        if before.side is PositionSide.LONG
        else before.quantity.value * (before.average_entry.value - exit_fill.price.value)
    )
    fees = last_entry_fees + exit_fill.fee
    return PaperCloseAllSymbolReport(
        symbol, "MANUAL", "VERIFIED", before.average_entry.value,
        exit_fill.price.value, before.quantity.value, gross, fees, gross - fees,
    )
