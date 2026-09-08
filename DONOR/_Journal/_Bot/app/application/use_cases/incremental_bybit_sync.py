"""Restart-safe incremental Bybit execution synchronization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import logging

from .historical_execution_backfill import _safe_error_message
from .process_execution_and_update_trade import TradeAction
from .process_execution_fact import ExecutionProcessingStatus
from app.core.trades.trade_id import TradeId


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncrementalBybitSyncSummary:
    fetched: int = 0
    processed: int = 0
    already_processed: int = 0
    trades_created: int = 0
    trades_updated: int = 0
    trades_closed: int = 0
    errors: int = 0
    cursor: datetime | None = None
    error_messages: tuple[str, ...] = ()
    created_trade_ids: tuple[TradeId, ...] = ()


class IncrementalBybitSync:
    """Fetch one overlap window and advance the durable time watermark safely.

    ``last_sync_at`` is intentionally reused from exchange_import_settings.
    The overlap makes the timestamp watermark safe for same-millisecond fills;
    canonical external execution IDs make replays idempotent.
    """

    def __init__(self, source, processor, settings_repository, *, account_id, overlap_seconds: float = 60):
        self._source = source
        self._processor = processor
        self._settings = settings_repository
        self._account_id = account_id
        if overlap_seconds < 0:
            raise ValueError("overlap_seconds must be non-negative")
        self._overlap = timedelta(seconds=overlap_seconds)

    async def execute(self, *, now: datetime | None = None) -> IncrementalBybitSyncSummary:
        current = await self._settings.get(account_id=self._account_id, exchange="BYBIT")
        if current is None:
            logger.warning("BYBIT_SYNC_DISABLED reason=no_exchange_import_settings")
            return IncrementalBybitSyncSummary()

        end = _utc(now or datetime.now(timezone.utc), "now")
        watermark = current.last_sync_at
        start = (watermark - self._overlap) if watermark is not None else end - self._overlap
        if start >= end:
            return IncrementalBybitSyncSummary(cursor=watermark)

        facts = tuple(await self._source.fetch_executions(since=start, end_at=end, include_inactive=False))
        facts = tuple(sorted(facts, key=lambda item: (item.executed_at, item.external_execution_id or "")))
        logger.info("BYBIT_SYNC_FETCHED count=%s", len(facts))
        processed = already_processed = created = updated = closed = errors = 0
        messages: list[str] = []
        created_trade_ids: list[TradeId] = []
        candidate_cursor = watermark

        for fact in facts:
            try:
                result = await self._processor.execute(fact)
            except Exception as error:  # keep the bot alive; retry from the safe watermark next tick
                errors += 1
                message = f"{fact.external_execution_id}: {type(error).__name__}: {_safe_error_message(error)}"
                messages.append(message)
                logger.error(
                    "BYBIT_SYNC_ERRORS count=%s execution_id=%s executed_at=%s error_type=%s error=%s",
                    errors, fact.external_execution_id, fact.executed_at,
                    type(error).__name__, _safe_error_message(error),
                )
                # Stop at the first failed item. Later facts must not move the
                # durable cursor past an execution that still needs retry.
                break

            if result.execution_status is ExecutionProcessingStatus.ALREADY_PROCESSED:
                already_processed += 1
            else:
                processed += 1
                if result.trade_action is TradeAction.CREATED:
                    created += 1
                    if result.trade_id is not None and result.trade_id not in created_trade_ids:
                        created_trade_ids.append(result.trade_id)
                elif result.trade_action is TradeAction.UPDATED:
                    updated += 1
                elif result.trade_action is TradeAction.CLOSED:
                    closed += 1
                elif result.trade_action is TradeAction.REVERSED:
                    created += 1
                    closed += 1
                    if result.trade_id is not None and result.trade_id not in created_trade_ids:
                        created_trade_ids.append(result.trade_id)
            if candidate_cursor is None or fact.executed_at > candidate_cursor:
                candidate_cursor = fact.executed_at

        if candidate_cursor is not None and (watermark is None or candidate_cursor > watermark):
            await self._settings.save(replace(current, last_sync_at=candidate_cursor, updated_at=end))
            logger.info("BYBIT_SYNC_CURSOR advanced_to=%s", candidate_cursor.isoformat())

        logger.info(
            "BYBIT_SYNC_PROCESSED count=%s", processed,
        )
        logger.info("BYBIT_SYNC_ALREADY_PROCESSED count=%s", already_processed)
        logger.info("BYBIT_SYNC_TRADES_CREATED count=%s", created)
        logger.info("BYBIT_SYNC_TRADES_UPDATED count=%s", updated)
        logger.info("BYBIT_SYNC_TRADES_CLOSED count=%s", closed)
        logger.info("BYBIT_SYNC_ERRORS count=%s", errors)
        return IncrementalBybitSyncSummary(
            fetched=len(facts), processed=processed,
            already_processed=already_processed, trades_created=created,
            trades_updated=updated, trades_closed=closed, errors=errors,
            cursor=candidate_cursor, error_messages=tuple(messages),
            created_trade_ids=tuple(created_trade_ids),
        )


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)
