"""Fail-closed PAPER proof of a Robot-owned non-Box manual Market close.

The Robot candidate carries the durable close intent BEFORE dispatch. A
restart can prove the exact execution identity, final FLAT projection, original
entry attestation, fee attribution and realized economics without re-sending
a Market order or inventing historical fills.

CR-ROBOT-CLOSE-ALL-MAX-QTY-001: a position whose confirmed quantity exceeds
the instrument's own maximum Market order quantity cannot close in one
order. The intent then carries an ORDERED list of chunk order_link_ids
(``order_link_ids``) instead of a single one; this proof requires every
listed chunk to have its own confirmed fill, requires their quantities to
sum to exactly ``trade.entry_quantity`` (no more, no less -- a short or
over-filled chunk sequence is never silently accepted), and requires the
position version to have advanced by exactly one durable step per chunk.
Realized economics use the quantity-weighted exit price across every chunk.
A single-chunk close (today's only shape) is the ``len(fills) == 1`` case of
the same proof, byte-identical in outcome to before this file changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from terminal.domain.models import Category, Execution, OrderSide, PositionSide


@dataclass(frozen=True, slots=True)
class RobotManualCloseEvidence:
    exit_time_ms: int
    exit_price: Decimal
    realized_pnl_usdt: Decimal
    realized_pnl_pct: Decimal
    fees_costs_usdt: Decimal


def manual_close_intent_links(intent: Mapping) -> tuple[str, ...] | None:
    """Ordered chunk order_link_ids from a durable close intent.

    Accepts either the current ordered-``chunks`` schema (CR-ROBOT-CLOSE-ALL-
    MAX-QTY-001, one dict per Market chunk) or the pre-chunking single-link
    schema (an in-flight candidate recorded by an older build), never a
    malformed mix of both.
    """
    chunks = intent.get("chunks")
    singular = intent.get("order_link_id")
    if chunks is not None:
        if singular is not None:
            return None
        if (
            not isinstance(chunks, Sequence) or isinstance(chunks, (str, bytes))
            or not chunks
        ):
            return None
        links: list[str] = []
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                return None
            link = chunk.get("order_link_id")
            if not isinstance(link, str):
                return None
            links.append(link)
        return tuple(links)
    if isinstance(singular, str):
        return (singular,)
    return None


def prove_robot_manual_close(
    *, trade, candidate, position, fills: Sequence[Execution] | None,
    entry_fees: Decimal | None,
) -> RobotManualCloseEvidence | None:
    """Return verified close economics, or None on any missing/mismatched fact.

    ``fills`` must be given in the same order as the intent's chunk links.
    """
    if trade is None or candidate is None or position is None or not fills:
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
    links = manual_close_intent_links(intent)
    if links is None or len(links) != len(fills):
        return None
    for link in links:
        if not link.startswith("tw_") or len(link) != 36:
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
        # Exactly one aggregate PAPER Market execution per registered chunk
        # must have advanced the previously attested Robot lot; any
        # intervening fill outside this exact chunk sequence is ambiguous.
        or position.version != trade.entry_position_version + len(links)
    ):
        return None
    closing_side = (
        OrderSide.SELL if trade.direction == "LONG"
        else OrderSide.BUY if trade.direction == "SHORT"
        else None
    )
    if closing_side is None:
        return None
    total_quantity = Decimal(0)
    weighted_price = Decimal(0)
    total_fill_fees = Decimal(0)
    last_timestamp = None
    previous_timestamp = trade.entry_time_ms
    for link, fill in zip(links, fills):
        if (
            fill is None
            or fill.dedup_key.trading_account_id != trade.trading_account_id
            or fill.dedup_key.category is not Category.LINEAR
            or fill.dedup_key.exec_id.value != "paper-exec-" + link
            or fill.order_id.value != "paper-order-" + link
            or fill.symbol != trade.symbol
            or fill.side is not closing_side
            or fill.quantity.value <= 0
            # Chunks close in the order they were submitted: each fill must
            # not predate the previous one (or the trade's own entry for the
            # first chunk). Equal timestamps are accepted (same matching tick).
            or fill.exchange_timestamp_ms < previous_timestamp
            or not fill.price.value.is_finite() or fill.price.value <= 0
            or not fill.fee.is_finite() or fill.fee < 0
        ):
            return None
        total_quantity += fill.quantity.value
        weighted_price += fill.quantity.value * fill.price.value
        total_fill_fees += fill.fee
        previous_timestamp = fill.exchange_timestamp_ms
        last_timestamp = fill.exchange_timestamp_ms
    # The whole chunk sequence must account for exactly the attested lot --
    # not a partial sequence (still-open risk) and never more (double fill).
    if total_quantity != trade.entry_quantity:
        return None
    if position.updated_at_ms != last_timestamp:
        return None
    if (
        entry_fees is None
        or not isinstance(entry_fees, Decimal)
        or not entry_fees.is_finite()
        or entry_fees < 0
        or trade.average_entry <= 0
        or trade.entry_quantity * trade.average_entry <= 0
    ):
        return None
    exit_price = weighted_price / total_quantity
    gross = (
        total_quantity * (exit_price - trade.average_entry)
        if trade.direction == "LONG"
        else total_quantity * (trade.average_entry - exit_price)
    )
    fees = entry_fees + total_fill_fees
    net_pct = (gross - fees) / (trade.entry_quantity * trade.average_entry) * Decimal("100")
    return RobotManualCloseEvidence(
        exit_time_ms=last_timestamp,
        exit_price=exit_price,
        realized_pnl_usdt=gross,
        realized_pnl_pct=net_pct,
        fees_costs_usdt=fees,
    )
