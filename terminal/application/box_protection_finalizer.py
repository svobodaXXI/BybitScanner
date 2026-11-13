"""Shared durable finalizer for an executed Ikigai Box protection leg.

The function is deliberately store-only: production PAPER and the isolated
SIMULATION adapter reuse the same evidence gate without importing a runtime,
exchange adapter, credentials, services, or private API surface.
"""
from __future__ import annotations

from decimal import Decimal
import logging

from terminal.domain.models import Category, PositionKey, PositionSide
from terminal.persistence.sqlite_store import (
    PaperProtectionObligationRecord,
    RobotTradeRecord,
    SQLiteStore,
)

LOGGER = logging.getLogger(__name__)


def finalize_box_protection_obligation(
    store: SQLiteStore,
    obligation: PaperProtectionObligationRecord,
    trade: RobotTradeRecord,
    *,
    now_ms: int,
) -> PaperProtectionObligationRecord:
    """Finalize one Box STOP/TAKE only from durable zero-exposure proof."""
    if trade.pattern != "IKIGAI_BOX":
        raise ValueError("Ikigai Box trade required")
    position_key = PositionKey(
        trade.trading_account_id, Category.LINEAR, trade.symbol, 0,
    )
    position = store.get_position_projection(position_key)
    if position is None or position.side is not PositionSide.FLAT:
        return obligation
    candidate = store.get_robot_candidate(trade.candidate_id)
    source_id = (
        candidate.signal_snapshot.get("source_box_candidate_id")
        if candidate is not None else None
    )
    if not isinstance(source_id, str) or not source_id.strip():
        return obligation
    try:
        proof = store.prove_box_owned_position(source_id.strip())
    except Exception:
        return obligation
    if (
        proof.remaining_quantity != 0
        or proof.average_exit is None
        or proof.last_execution_at_ms is None
        or proof.entry_notional <= 0
    ):
        return obligation
    realized_pct = (
        (proof.realized_pnl - proof.accumulated_fee)
        / proof.entry_notional
        * Decimal("100")
    )
    if trade.exit_time_ms is not None and trade.exit_reason != obligation.winning_leg:
        corrected = store.correct_box_take_race_from_proven_stop(
            trade_id=trade.trade_id,
            obligation_id=obligation.obligation_id,
            exit_time_ms=proof.last_execution_at_ms,
            exit_price=proof.average_exit,
            realized_pnl_usdt=proof.realized_pnl,
            realized_pnl_pct=realized_pct,
            fees_costs_usdt=proof.accumulated_fee,
            updated_at_ms=now_ms,
        )
        if not corrected:
            LOGGER.error(
                "Box STOP/TAKE race cannot be proved; reconciliation required: obligation=%s",
                obligation.obligation_id,
            )
            return obligation
        LOGGER.warning(
            "Corrected proven Box STOP/TAKE reason race: obligation=%s trade=%s",
            obligation.obligation_id,
            trade.trade_id,
        )
    else:
        store.close_robot_trade(
            trade.trade_id,
            exit_time_ms=proof.last_execution_at_ms,
            exit_price=proof.average_exit,
            exit_reason=obligation.winning_leg,
            realized_pnl_usdt=proof.realized_pnl,
            realized_pnl_pct=realized_pct,
            fees_costs_usdt=proof.accumulated_fee,
            updated_at_ms=now_ms,
        )
    store.clear_paper_protection_for_flat(position_key)
    if obligation.status == "DISPATCHING":
        obligation = store.transition_paper_protection_obligation(
            obligation.obligation_id,
            expected_status="DISPATCHING",
            next_status="RESOLVED",
            expected_version=obligation.version,
            updated_at_ms=now_ms,
        )
    return obligation
