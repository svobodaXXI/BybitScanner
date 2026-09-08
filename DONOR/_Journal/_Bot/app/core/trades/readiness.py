"""Data-quality and statistics-readiness rules for journal trades."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .enums import TradeStatus


class TradeReadinessStatus(StrEnum):
    OPEN = "OPEN"
    INCOMPLETE = "INCOMPLETE"
    READY = "READY"


class TradeMissingReason(StrEnum):
    INSTRUMENT = "INSTRUMENT"
    DIRECTION = "DIRECTION"
    ENTRY_PRICE = "ENTRY_PRICE"
    QUANTITY = "QUANTITY"
    EXIT_PRICE = "EXIT_PRICE"
    NET_PNL = "NET_PNL"


@dataclass(frozen=True, slots=True)
class TradeReadiness:
    """Derived readiness result; missing facts are never represented as zero."""

    status: TradeReadinessStatus
    missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, TradeReadinessStatus):
            object.__setattr__(self, "status", TradeReadinessStatus(self.status))
        missing = tuple(str(item) for item in self.missing)
        if len(set(missing)) != len(missing):
            raise ValueError("readiness missing reasons must be unique")
        object.__setattr__(self, "missing", missing)
        if self.status is TradeReadinessStatus.OPEN and missing:
            raise ValueError("OPEN readiness cannot contain missing reasons")
        if self.status is TradeReadinessStatus.READY and missing:
            raise ValueError("READY readiness cannot contain missing reasons")

    @property
    def eligible_for_general_statistics(self) -> bool:
        return self.status is TradeReadinessStatus.READY

    @property
    def data_status(self) -> TradeReadinessStatus:
        return self.status

    @property
    def missing_reasons(self) -> tuple[str, ...]:
        return self.missing

    @property
    def is_ready(self) -> bool:
        return self.eligible_for_general_statistics

    @property
    def requires_attention(self) -> bool:
        return self.status is not TradeReadinessStatus.READY


def _field_identity(field) -> str:
    field_id = getattr(field, "id", field)
    return f"dynamic_field:{field_id}"


def evaluate_trade_readiness(
    trade,
    *,
    required_dynamic_fields: Iterable[object] = (),
    filled_dynamic_field_ids: Iterable[object] = (),
) -> TradeReadiness:
    """Evaluate lifecycle, general facts, and required dynamic values.

    The function intentionally accepts a trade-like read model. This keeps the
    rule usable for historical database rows whose close facts are incomplete,
    even when the normal manual-close command always produces complete facts.
    """
    status = getattr(trade, "status", None)
    if not isinstance(status, TradeStatus):
        status = TradeStatus(status)
    if status is TradeStatus.OPEN:
        return TradeReadiness(TradeReadinessStatus.OPEN)

    missing: list[str] = []
    facts = (
        ("instrument_id", TradeMissingReason.INSTRUMENT),
        ("direction", TradeMissingReason.DIRECTION),
        ("entry_price", TradeMissingReason.ENTRY_PRICE),
        ("quantity", TradeMissingReason.QUANTITY),
        ("exit_price", TradeMissingReason.EXIT_PRICE),
        ("net_pnl", TradeMissingReason.NET_PNL),
    )
    for attribute, reason in facts:
        if attribute == "instrument_id" and getattr(trade, "instrument_available", True) is False:
            missing.append(reason.value)
        elif getattr(trade, attribute, None) is None:
            missing.append(reason.value)

    filled = {getattr(item, "id", item) for item in filled_dynamic_field_ids}
    for field in required_dynamic_fields:
        if getattr(field, "required_for_statistics", True) is False:
            continue
        if getattr(field, "id", field) not in filled:
            missing.append(_field_identity(field))
    return TradeReadiness(
        TradeReadinessStatus.READY if not missing else TradeReadinessStatus.INCOMPLETE,
        tuple(missing),
    )


# Names used by different application layers during the handoff are kept as
# intentional aliases, not duplicate implementations.
TradeDataQuality = TradeReadiness
EvaluateTradeReadiness = evaluate_trade_readiness
