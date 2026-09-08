"""Safe historical execution import and read-only preview workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from app.application.errors import UnsafeHistoricalBoundaryError
from app.application.ports.exchange_execution_source import ExchangeExecutionSource
from app.application.ports.repositories.instrument_repository import InstrumentRepository
from app.core.trades.execution_fact import ExecutionFact
from app.core.instruments import Instrument

from .process_execution_and_update_trade import ProcessExecutionAndUpdateTrade, TradeAction
from .process_execution_fact import ExecutionProcessingStatus


@dataclass(frozen=True, slots=True)
class HistoricalExecutionBackfillCommand:
    start_at: datetime
    end_at: datetime | None = None
    allow_unsafe_boundary: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_at", _aware_utc(self.start_at, "start_at"))
        if self.end_at is not None:
            object.__setattr__(self, "end_at", _aware_utc(self.end_at, "end_at"))
        if self.end_at is not None and self.start_at > self.end_at:
            raise ValueError("start_at must be less than or equal to end_at")
        if type(self.allow_unsafe_boundary) is not bool:
            raise TypeError("allow_unsafe_boundary must be bool")


@dataclass(frozen=True, slots=True)
class HistoricalExecutionBackfillSummary:
    fetched: int
    processed: int
    already_processed: int
    trades_created: int
    trades_updated: int
    trades_closed: int
    errors: int
    error_messages: tuple[str, ...] = ()


class HistoricalExecutionBackfill:
    """Fetch normalized facts, then feed each through the existing UoW path."""

    def __init__(self, source: ExchangeExecutionSource, processor: ProcessExecutionAndUpdateTrade) -> None:
        self._source = source
        self._processor = processor

    async def execute(self, command: HistoricalExecutionBackfillCommand) -> HistoricalExecutionBackfillSummary:
        if not isinstance(command, HistoricalExecutionBackfillCommand):
            raise TypeError("command must be HistoricalExecutionBackfillCommand")
        if not command.allow_unsafe_boundary:
            raise UnsafeHistoricalBoundaryError(
                "historical import requires explicit allow_unsafe_boundary acknowledgement; preview first"
            )
        facts = await _historical_facts(self._source, command.start_at, command.end_at)
        processed = already_processed = created = updated = closed = errors = 0
        messages = []
        for fact in facts:
            try:
                identity = next((item for item in getattr(self._source, "historical_instrument_identities", ()) if item.instrument_id == fact.instrument_id), None)
                historical_instrument = None if identity is None else Instrument(
                    identity.instrument_id, identity.symbol, f"{identity.symbol} (historical)", "BYBIT", "LINEAR", False
                )
                try:
                    result = await self._processor.execute(fact, historical_instrument=historical_instrument)
                except TypeError as error:
                    if "historical_instrument" not in str(error):
                        raise
                    result = await self._processor.execute(fact)
            except Exception as error:  # one malformed/mismatched fact must not hide the rest of a backfill
                errors += 1
                safe_message = _safe_error_message(error)
                messages.append(f"{fact.external_execution_id}: {type(error).__name__}: {safe_message}")
                continue
            if result.execution_status is ExecutionProcessingStatus.ALREADY_PROCESSED:
                already_processed += 1
                continue
            processed += 1
            if result.trade_action is TradeAction.CREATED:
                created += 1
            elif result.trade_action is TradeAction.UPDATED:
                updated += 1
            elif result.trade_action is TradeAction.CLOSED:
                closed += 1
            elif result.trade_action is TradeAction.REVERSED:
                # One source fill closed the old lifecycle and opened the
                # residual opposite lifecycle.  Count both resulting changes.
                created += 1
                closed += 1
        return HistoricalExecutionBackfillSummary(
            fetched=len(facts),
            processed=processed,
            already_processed=already_processed,
            trades_created=created,
            trades_updated=updated,
            trades_closed=closed,
            errors=errors,
            error_messages=tuple(messages),
        )


@dataclass(frozen=True, slots=True)
class PreviewExecutionRow:
    external_execution_id: str
    instrument_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    fee: str
    fee_currency: str
    executed_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalExecutionPreview:
    execution_count: int
    symbol_count: int
    first_executed_at: datetime | None
    last_executed_at: datetime | None
    counts_by_symbol: tuple[tuple[str, int], ...]
    sample: tuple[PreviewExecutionRow, ...] = ()


class PreviewHistoricalExecutionImport:
    """Read-only preview; it has no UnitOfWork or persistence dependency."""

    def __init__(self, source: ExchangeExecutionSource, instruments: InstrumentRepository) -> None:
        self._source = source
        self._instruments = instruments

    async def execute(
        self,
        *,
        start_at: datetime,
        end_at: datetime | None = None,
        sample_limit: int = 0,
    ) -> HistoricalExecutionPreview:
        start = _aware_utc(start_at, "start_at")
        end = None if end_at is None else _aware_utc(end_at, "end_at")
        if end is not None and start > end:
            raise ValueError("start_at must be less than or equal to end_at")
        if type(sample_limit) is not int or not 0 <= sample_limit <= 100:
            raise ValueError("sample_limit must be between 0 and 100")
        facts = await _historical_facts(self._source, start, end)
        symbols = {}
        for fact in facts:
            if fact.instrument_id not in symbols:
                instrument = await self._instruments.get_by_id(fact.instrument_id)
                if instrument is not None:
                    symbols[fact.instrument_id] = instrument.symbol
                else:
                    identity = next((item for item in getattr(self._source, "historical_instrument_identities", ()) if item.instrument_id == fact.instrument_id), None)
                    symbols[fact.instrument_id] = identity.symbol if identity is not None else str(fact.instrument_id)
        counts: dict[str, int] = {}
        for fact in facts:
            symbol = symbols[fact.instrument_id]
            counts[symbol] = counts.get(symbol, 0) + 1
        sample = tuple(
            PreviewExecutionRow(
                external_execution_id=fact.external_execution_id or "",
                instrument_id=str(fact.instrument_id),
                symbol=symbols[fact.instrument_id],
                side=fact.side.value,
                quantity=str(fact.quantity.value),
                price=str(fact.price.value),
                fee=str(fact.fee.amount),
                fee_currency=fact.fee.currency,
                executed_at=fact.executed_at,
            )
            for fact in facts[:sample_limit]
        )
        return HistoricalExecutionPreview(
            execution_count=len(facts),
            symbol_count=len(counts),
            first_executed_at=None if not facts else facts[0].executed_at,
            last_executed_at=None if not facts else facts[-1].executed_at,
            counts_by_symbol=tuple(sorted(counts.items())),
            sample=sample,
        )


async def _historical_facts(source, start_at: datetime, end_at: datetime | None) -> tuple[ExecutionFact, ...]:
    fetcher = getattr(source, "fetch_historical_executions", None)
    if fetcher is None:
        raise TypeError("execution source must implement fetch_historical_executions")
    facts = tuple(await fetcher(start_at=start_at, end_at=end_at))
    if any(not isinstance(fact, ExecutionFact) for fact in facts):
        raise TypeError("execution source must return ExecutionFact values")
    return tuple(sorted(facts, key=lambda item: (item.executed_at, item.external_execution_id or "")))


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


_SENSITIVE_ERROR_RE = re.compile(
    r"(?i)\b(api[_ -]?key|api[_ -]?secret|authorization|signed[_ -]?headers?|signature)\b"
)


def _safe_error_message(error: Exception) -> str:
    """Keep operational detail while preventing authentication data leakage."""
    message = " ".join(str(error).split())
    if not message:
        return "empty exception message"
    if _SENSITIVE_ERROR_RE.search(message):
        return "exception message redacted because it contained sensitive authentication data"
    return message[:500]
