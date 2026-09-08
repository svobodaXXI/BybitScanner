"""Application query for the Data Quality / Attention Center."""

from dataclasses import dataclass

from app.application.dtos import InstrumentView, TradeView
from app.application.ports.repositories import (
    CustomFieldRepository,
    InstrumentRepository,
    TradeCustomValueRepository,
    TradeRepository,
)
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.readiness import TradeReadiness, TradeReadinessStatus, evaluate_trade_readiness
from app.core.trades.trade_id import TradeId


@dataclass(frozen=True, slots=True)
class AttentionItem:
    trade: TradeView
    readiness: TradeReadiness
    instrument: InstrumentView | None = None
    missing_labels: tuple[str, ...] = ()

    @property
    def trade_id(self) -> TradeId:
        return self.trade.trade_id

    @property
    def instrument_label(self) -> str | None:
        return None if self.instrument is None else self.instrument.symbol


@dataclass(frozen=True, slots=True)
class AttentionSummary:
    total_attention: int
    open_count: int
    incomplete_count: int


@dataclass(frozen=True, slots=True)
class AttentionResult:
    summary: AttentionSummary
    items: tuple[AttentionItem, ...]


class GetAttentionCenter:
    """Read all attention-worthy trades once and classify each trade once."""

    def __init__(
        self,
        trade_repository: TradeRepository,
        custom_field_repository: CustomFieldRepository,
        trade_custom_value_repository: TradeCustomValueRepository,
        instrument_repository: InstrumentRepository | None = None,
    ) -> None:
        self._trades = trade_repository
        self._fields = custom_field_repository
        self._values = trade_custom_value_repository
        self._instruments = instrument_repository

    async def execute(self, *, account_id=None, instrument_id=None) -> AttentionResult:
        trades = await self._trades.list_all(
            account_id=account_id,
            instrument_id=instrument_id,
            limit=100_000,
            offset=0,
        )
        definitions = tuple(
            item for item in await self._fields.list_definitions(include_inactive=False)
            if item.required_for_statistics
        )
        definition_labels = {str(item.id): item.name for item in definitions}
        items = []
        for trade in trades:
            values = await self._values.list_by_trade(trade.trade_id)
            readiness = evaluate_trade_readiness(
                trade,
                required_dynamic_fields=definitions,
                filled_dynamic_field_ids=(item.field_id for item in values),
            )
            if readiness.status is TradeReadinessStatus.READY:
                continue
            instrument = None
            if self._instruments is not None:
                found = await self._instruments.get_by_id(trade.instrument_id)
                instrument = None if found is None else InstrumentView.from_instrument(found)
            labels = tuple(
                definition_labels.get(reason.removeprefix("dynamic_field:"), reason)
                for reason in readiness.missing
            )
            items.append(AttentionItem(TradeView.from_trade(trade), readiness, instrument, labels))

        # A repository should not return duplicates, but de-duplicate here at
        # the use-case boundary so multiple missing reasons never inflate N.
        unique = {item.trade_id: item for item in items}
        ordered = tuple(sorted(unique.values(), key=lambda item: (item.trade.opened_at, str(item.trade_id)), reverse=True))
        open_count = sum(1 for item in ordered if item.trade.status is TradeStatus.OPEN)
        return AttentionResult(
            AttentionSummary(len(ordered), open_count, len(ordered) - open_count),
            ordered,
        )
