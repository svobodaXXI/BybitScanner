"""Reversible Journal inclusion controls for imported trades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from app.core.imports import JournalTradeState, JournalTradeStateRecord
from app.core.trades.enums import TradeStatus
from app.core.trades.readiness import TradeReadinessStatus, evaluate_trade_readiness


@dataclass(frozen=True, slots=True)
class BulkExclusionPreview:
    trade_ids: tuple
    older_than: datetime
    remaining_incomplete_count: int
    token: str


class ExcludeImportedTrade:
    """Exclude a CLOSED+INCOMPLETE imported trade without deleting facts."""

    def __init__(self, trades, executions, states, fields, values):
        self._trades, self._executions, self._states = trades, executions, states
        self._fields, self._values = fields, values

    async def execute(self, trade_id, *, reason="user excluded"):
        trade = await self._trades.get_by_id(trade_id)
        if trade is None:
            raise ValueError("trade not found")
        if trade.status is not TradeStatus.CLOSED:
            raise ValueError("only CLOSED trades may be excluded")
        executions = await self._executions.list_by_trade(trade.trade_id)
        if not executions:
            raise ValueError("only exchange-imported trades may be excluded")
        if not await _is_incomplete(trade, self._fields, self._values):
            raise ValueError("READY trades are not excluded by this workflow")
        await self._states.save(JournalTradeStateRecord(
            trade_id=trade.trade_id,
            account_id=trade.account_id,
            state=JournalTradeState.EXCLUDED_USER,
            reason=reason,
            excluded_at=datetime.now(timezone.utc),
        ))
        return trade


class RestoreExcludedTrade:
    def __init__(self, trades, states):
        self._trades, self._states = trades, states

    async def execute(self, trade_id):
        trade = await self._trades.get_by_id(trade_id)
        if trade is None:
            raise ValueError("trade not found")
        state = await self._states.get(trade.trade_id)
        if state is None or state.state is not JournalTradeState.EXCLUDED_USER:
            raise ValueError("trade is not user-excluded")
        await self._states.save(JournalTradeStateRecord(
            trade_id=trade.trade_id,
            account_id=trade.account_id,
            state=JournalTradeState.INCLUDED,
            reason="restored by user",
        ))
        return trade


class PreviewBulkExcludeOldIncomplete:
    def __init__(self, trades, executions, states, fields, values):
        self._trades, self._executions, self._states = trades, executions, states
        self._fields, self._values = fields, values

    async def execute(self, *, account_id, older_than: datetime) -> BulkExclusionPreview:
        older_than = _utc(older_than)
        trades = await self._trades.list_all(account_id=account_id, limit=100_000, offset=0, include_excluded=True)
        candidate_ids = []
        for trade in trades:
            if trade.status is not TradeStatus.CLOSED or trade.closed_at is None or trade.closed_at >= older_than:
                continue
            state = await self._states.get(trade.trade_id)
            if state is not None and state.state is not JournalTradeState.INCLUDED:
                # Explicit INCLUDED is still eligible; it is not a hidden
                # exclusion marker.
                pass
            elif state is not None:
                continue
            if not await self._executions.list_by_trade(trade.trade_id):
                continue
            if await _is_incomplete(trade, self._fields, self._values):
                candidate_ids.append(trade.trade_id)
        material = "|".join([older_than.isoformat(), *(str(item) for item in candidate_ids)])
        token = sha256(material.encode()).hexdigest()[:24]
        remaining = 0
        for trade in trades:
            if trade.status is TradeStatus.CLOSED and trade.closed_at is not None and trade.closed_at >= older_than:
                if await self._executions.list_by_trade(trade.trade_id) and await _is_incomplete(trade, self._fields, self._values):
                    remaining += 1
        return BulkExclusionPreview(tuple(candidate_ids), older_than, remaining, token)


class ApplyBulkExclusion:
    def __init__(self, trades, states):
        self._trades, self._states = trades, states

    async def execute(self, preview: BulkExclusionPreview, *, confirm_token: str | None = None) -> int:
        if confirm_token != preview.token:
            raise PermissionError("bulk exclusion requires explicit confirmation")
        count = 0
        for trade_id in preview.trade_ids:
            trade = await self._trades.get_by_id(trade_id)
            if trade is None:
                continue
            await self._states.save(JournalTradeStateRecord(
                trade_id=trade.trade_id,
                account_id=trade.account_id,
                state=JournalTradeState.EXCLUDED_USER,
                reason="bulk old incomplete import",
                excluded_at=datetime.now(timezone.utc),
            ))
            count += 1
        return count


async def _is_incomplete(trade, fields, values) -> bool:
    definitions = tuple(item for item in await fields.list_definitions(include_inactive=False) if item.required_for_statistics)
    filled = await values.list_by_trade(trade.trade_id)
    return evaluate_trade_readiness(trade, required_dynamic_fields=definitions, filled_dynamic_field_ids=(item.field_id for item in filled)).status is TradeReadinessStatus.INCOMPLETE


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("older_than must be timezone-aware datetime")
    return value.astimezone(timezone.utc)
