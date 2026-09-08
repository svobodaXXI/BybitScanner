"""GetTradeDetails application use case."""

from app.application.dtos import CustomValueView, GetTradeDetailsCommand, GetTradeDetailsResult, InstrumentView
from app.application.automatic_data import resolve_current_observations
from app.application.ports.repositories import (
    AutomaticFactorObservationRepository,
    CustomFieldRepository,
    ExecutionRepository,
    InstrumentRepository,
    TradeCustomValueRepository,
    TradeRepository,
    TradeJournalStateRepository,
)
from app.application.use_cases._common import require_trade, view
from app.core.statistics.enums import CustomFieldValueType
from app.core.trades.readiness import evaluate_trade_readiness


class GetTradeDetails:
    def __init__(
        self,
        trade_repository: TradeRepository,
        custom_field_repository: CustomFieldRepository,
        trade_custom_value_repository: TradeCustomValueRepository,
        instrument_repository: InstrumentRepository | None = None,
        execution_repository: ExecutionRepository | None = None,
        journal_state_repository: TradeJournalStateRepository | None = None,
        automatic_observation_repository: AutomaticFactorObservationRepository | None = None,
    ) -> None:
        self._trades = trade_repository
        self._fields = custom_field_repository
        self._values = trade_custom_value_repository
        self._instruments = instrument_repository
        self._executions = execution_repository
        self._journal_states = journal_state_repository
        self._automatic_observations = automatic_observation_repository

    async def execute(self, command: GetTradeDetailsCommand) -> GetTradeDetailsResult:
        if not isinstance(command, GetTradeDetailsCommand):
            raise TypeError("command must be GetTradeDetailsCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        values = await self._values.list_by_trade(trade.trade_id)
        definitions = await self._fields.list_definitions(include_inactive=True)
        definitions_by_key = {(item.id, item.definition_version): item for item in definitions}
        option_cache = {}
        details = []
        for value in sorted(values, key=lambda item: (item.recorded_at, str(item.field_id), item.definition_version)):
            definition = definitions_by_key.get((value.field_id, value.definition_version))
            option = None
            if definition is not None and definition.value_type is CustomFieldValueType.CHOICE:
                if definition.id not in option_cache:
                    option_cache[definition.id] = await self._fields.list_options(definition.id, include_inactive=True)
                option = next((item for item in option_cache[definition.id] if item.id == value.value), None)
            details.append(CustomValueView(value=value, definition=definition, option=option))
        instrument = None
        if self._instruments is not None:
            found = await self._instruments.get_by_id(trade.instrument_id)
            if found is not None:
                instrument = InstrumentView.from_instrument(found)
        required = tuple(item for item in definitions if item.required_for_statistics)
        readiness = evaluate_trade_readiness(
            trade,
            required_dynamic_fields=required,
            filled_dynamic_field_ids=(item.field_id for item in values),
        )
        has_exchange_executions = False
        if self._executions is not None:
            has_exchange_executions = bool(await self._executions.list_by_trade(trade.trade_id))
        journal_state = None
        if self._journal_states is not None:
            state = await self._journal_states.get(trade.trade_id)
            journal_state = None if state is None else state.state
        automatic_observations = ()
        if self._automatic_observations is not None:
            automatic_observations = resolve_current_observations(
                await self._automatic_observations.list_for_trade(trade.trade_id)
            )
        return GetTradeDetailsResult(
            view(trade), tuple(details), instrument, readiness, definitions,
            has_exchange_executions, journal_state, automatic_observations,
        )
