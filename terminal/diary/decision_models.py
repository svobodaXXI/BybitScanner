"""Trading Diary D2 setup, decision and linkage models.

These records are observational/research data. They do not dispatch orders and do
not replace Terminal execution identities or exchange authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from terminal.domain.models import Controller, Origin, PositionSide, Symbol, TradingAccountId

from .models import TradeEpisodeId


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True, order=True)
class SetupInstanceId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "setup instance id"))


@dataclass(frozen=True, slots=True, order=True)
class DecisionEventId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "decision event id"))


@dataclass(frozen=True, slots=True, order=True)
class OrderPlanId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "order plan id"))


class DecisionEventKind(str, Enum):
    STRATEGY = "STRATEGY"
    RISK = "RISK"
    SETUP_OUTCOME = "SETUP_OUTCOME"


class SetupTerminalOutcome(str, Enum):
    SKIPPED = "SKIPPED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class SetupInstanceRecord:
    setup_instance_id: SetupInstanceId
    symbol: Symbol
    timeframe: str
    pattern: str
    direction: PositionSide
    strategy_version: str
    setup_id: str
    hypothesis_id: str | None
    entry_mode: str
    origin: Origin
    created_at_ms: int

    def __post_init__(self) -> None:
        if self.direction is PositionSide.FLAT:
            raise ValueError("setup direction cannot be FLAT")
        for value, name in (
            (self.timeframe, "timeframe"),
            (self.pattern, "pattern"),
            (self.strategy_version, "strategy version"),
            (self.setup_id, "setup id"),
            (self.entry_mode, "entry mode"),
        ):
            _non_empty(value, name)
        if self.hypothesis_id is not None:
            _non_empty(self.hypothesis_id, "hypothesis id")
        if self.created_at_ms < 0:
            raise ValueError("setup timestamp must not be negative")


@dataclass(frozen=True, slots=True)
class DecisionEventRecord:
    decision_event_id: DecisionEventId
    setup_instance_id: SetupInstanceId
    kind: DecisionEventKind
    previous_state: str | None
    next_state: str
    reason_code: str
    origin: Origin
    controller: Controller
    strategy_version: str
    hypothesis_id: str | None
    setup_id: str
    entry_mode: str
    feature_snapshot_ref: str | None
    risk_snapshot_ref: str | None
    order_plan_id: OrderPlanId | None
    occurred_at_ms: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.previous_state is not None:
            _non_empty(self.previous_state, "previous state")
        _non_empty(self.next_state, "next state")
        _non_empty(self.reason_code, "reason code")
        _non_empty(self.strategy_version, "strategy version")
        _non_empty(self.setup_id, "setup id")
        _non_empty(self.entry_mode, "entry mode")
        if self.hypothesis_id is not None:
            _non_empty(self.hypothesis_id, "hypothesis id")
        if self.feature_snapshot_ref is not None:
            _non_empty(self.feature_snapshot_ref, "feature snapshot ref")
        if self.risk_snapshot_ref is not None:
            _non_empty(self.risk_snapshot_ref, "risk snapshot ref")
        if self.occurred_at_ms < 0:
            raise ValueError("decision timestamp must not be negative")
        if self.schema_version < 1:
            raise ValueError("decision schema version must be positive")
        if self.kind is DecisionEventKind.SETUP_OUTCOME:
            SetupTerminalOutcome(self.next_state)


@dataclass(frozen=True, slots=True)
class OrderPlanRecord:
    order_plan_id: OrderPlanId
    setup_instance_id: SetupInstanceId
    strategy_decision_event_id: DecisionEventId
    risk_decision_event_id: DecisionEventId
    trading_account_id: TradingAccountId
    symbol: Symbol
    side: PositionSide
    created_at_ms: int

    def __post_init__(self) -> None:
        if self.side is PositionSide.FLAT:
            raise ValueError("order-plan side cannot be FLAT")
        if self.created_at_ms < 0:
            raise ValueError("order-plan timestamp must not be negative")


@dataclass(frozen=True, slots=True)
class TradeEpisodeSetupLink:
    trade_episode_id: TradeEpisodeId
    setup_instance_id: SetupInstanceId
    order_plan_id: OrderPlanId
    linked_at_ms: int

    def __post_init__(self) -> None:
        if self.linked_at_ms < 0:
            raise ValueError("episode-link timestamp must not be negative")
