"""Small, persistence-agnostic contracts for safe first history import."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from app.core.accounts.account_id import AccountId
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.trade_aggregate import TradeAggregate
from app.core.trades.trade_id import TradeId


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class HistoricalImportMode(StrEnum):
    NEW_ONLY = "NEW_ONLY"
    LAST_30_DAYS = "LAST_30_DAYS"
    ALL_AVAILABLE = "ALL_AVAILABLE"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True, slots=True)
class HistoryProgress:
    stage: str
    windows_total: int
    windows_completed: int
    executions_found: int


@dataclass(frozen=True, slots=True)
class BybitHistorySnapshot:
    account_id: AccountId
    fetched_from: datetime
    fetched_to: datetime
    created_at: datetime
    raw_executions: tuple[dict, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        for name in ("fetched_from", "fetched_to", "created_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if self.fetched_from >= self.fetched_to:
            raise ValueError("snapshot fetched_from must precede fetched_to")


@dataclass(frozen=True, slots=True)
class HistoricalInstrumentIdentity:
    instrument_id: object
    symbol: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("historical instrument symbol is required")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())


class JournalTradeState(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED_USER = "EXCLUDED_USER"
    BASELINE_PRE_TRACKING = "BASELINE_PRE_TRACKING"


@dataclass(frozen=True, slots=True)
class JournalTradeStateRecord:
    trade_id: TradeId
    account_id: AccountId
    state: JournalTradeState = JournalTradeState.INCLUDED
    reason: str | None = None
    excluded_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.trade_id, TradeId) or not isinstance(self.account_id, AccountId):
            raise TypeError("trade_id and account_id must be domain identifiers")
        if not isinstance(self.state, JournalTradeState):
            object.__setattr__(self, "state", JournalTradeState(self.state))
        for name in ("excluded_at", "updated_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, name))


@dataclass(frozen=True, slots=True)
class ExchangeImportSettings:
    account_id: AccountId
    exchange: str
    history_available_from: datetime | None = None
    tracking_start_at: datetime | None = None
    initial_import_mode: HistoricalImportMode = HistoricalImportMode.NEW_ONLY
    initial_import_completed_at: datetime | None = None
    last_sync_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError("exchange must be a non-empty string")
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        mode = self.initial_import_mode
        if not isinstance(mode, HistoricalImportMode):
            object.__setattr__(self, "initial_import_mode", HistoricalImportMode(mode))
        for name in ("history_available_from", "tracking_start_at", "initial_import_completed_at", "last_sync_at", "created_at", "updated_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, name))
        if self.history_available_from and self.tracking_start_at and self.tracking_start_at < self.history_available_from:
            raise ValueError("tracking_start_at cannot precede history_available_from")


@dataclass(frozen=True, slots=True)
class SupportedHistoryDiscovery:
    status: str
    history_available_from: datetime | None
    first_executed_at: datetime | None
    last_executed_at: datetime | None
    execution_count: int
    incompatible_count: int
    last_incompatible_at: datetime | None
    external_execution_ids: tuple[str, ...] = ()
    incompatibilities: tuple["HistoryIncompatibility", ...] = ()
    incompatibilities: tuple["HistoryIncompatibility", ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"SUPPORTED", "NO_HISTORY", "NO_SUPPORTED_HISTORY"}:
            raise ValueError("unknown discovery status")
        for name in ("history_available_from", "first_executed_at", "last_executed_at", "last_incompatible_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, name))


@dataclass(frozen=True, slots=True)
class HistoryIncompatibility:
    exec_time: datetime | None
    symbol: str | None
    side: str | None
    exec_id: str | None
    reason_incompatible: str

    def __post_init__(self) -> None:
        if self.exec_time is not None:
            object.__setattr__(self, "exec_time", _utc(self.exec_time, "exec_time"))
        if not self.reason_incompatible:
            raise ValueError("reason_incompatible is required")


@dataclass(frozen=True, slots=True)
class HistoryIncompatibility:
    exec_time: datetime | None
    symbol: str | None
    side: str | None
    exec_id: str | None
    reason_incompatible: str

    def __post_init__(self) -> None:
        if self.exec_time is not None:
            object.__setattr__(self, "exec_time", _utc(self.exec_time, "exec_time"))
        if not self.reason_incompatible:
            raise ValueError("reason_incompatible is required")


@dataclass(frozen=True, slots=True)
class LogicalTradePreview:
    trade_id: TradeId
    account_id: AccountId
    instrument_id: object
    opened_at: datetime
    closed_at: datetime | None
    status: str
    execution_count: int
    symbol: str | None = None
    boundary_crossing: bool = False
    baseline: bool = False
    external_execution_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", _utc(self.opened_at, "opened_at"))
        if self.closed_at is not None:
            object.__setattr__(self, "closed_at", _utc(self.closed_at, "closed_at"))


@dataclass(frozen=True, slots=True)
class HistoricalImportPreview:
    selected_start: datetime
    selected_end: datetime
    supported_history_from: datetime
    execution_count: int
    logical_trade_count: int
    symbol_count: int
    already_imported_execution_count: int
    already_imported_trade_count: int
    would_import_trade_count: int
    boundary_crossing_trade_count: int
    first_executed_at: datetime | None
    last_executed_at: datetime | None
    counts_by_symbol: tuple[tuple[str, int], ...] = ()
    logical_trades: tuple[LogicalTradePreview, ...] = ()
    baseline_open_trades: tuple[LogicalTradePreview, ...] = ()
    # ``execution_count`` is the canonical exchange-fact count.  Reconstruction
    # may transiently create more legs, but those are deliberately separate.
    raw_exchange_execution_count: int | None = None
    reconstruction_leg_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_start", _utc(self.selected_start, "selected_start"))
        object.__setattr__(self, "selected_end", _utc(self.selected_end, "selected_end"))
        object.__setattr__(self, "supported_history_from", _utc(self.supported_history_from, "supported_history_from"))
        if self.selected_start > self.selected_end:
            raise ValueError("selected_start must be <= selected_end")
        for name in ("first_executed_at", "last_executed_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, name))


@dataclass(frozen=True, slots=True)
class HistoricalImportPlan:
    """Immutable preview output; import requires this exact confirmation token."""

    selected_start: datetime
    selected_end: datetime
    supported_history_from: datetime
    executions: tuple[ExecutionFact, ...]
    logical_trades: tuple[LogicalTradePreview, ...]
    boundary_crossing: tuple[LogicalTradePreview, ...]
    baseline_open_trades: tuple[LogicalTradePreview, ...]
    already_imported_execution_ids: tuple[str, ...] = ()
    token: str = ""
    mode: HistoricalImportMode = HistoricalImportMode.CUSTOM
    already_imported_trade_count: int = 0
    historical_instruments: tuple[HistoricalInstrumentIdentity, ...] = ()
    planned_journal_trade_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_start", _utc(self.selected_start, "selected_start"))
        object.__setattr__(self, "selected_end", _utc(self.selected_end, "selected_end"))
        object.__setattr__(self, "supported_history_from", _utc(self.supported_history_from, "supported_history_from"))
        if self.selected_start > self.selected_end:
            raise ValueError("selected_start must be <= selected_end")
        if self.selected_start < self.supported_history_from:
            raise ValueError("selected period precedes supported history")
        if not isinstance(self.mode, HistoricalImportMode):
            object.__setattr__(self, "mode", HistoricalImportMode(self.mode))
        if not self.token:
            material = "|".join(
                [self.selected_start.isoformat(), self.selected_end.isoformat(), *(
                    str(item.external_execution_id) for item in self.executions
                )]
            )
            object.__setattr__(self, "token", sha256(material.encode()).hexdigest()[:24])

    @property
    def execution_count(self) -> int:
        return len(self.executions)

    @property
    def logical_trade_count(self) -> int:
        return len(self.logical_trades)
