import inspect
from datetime import datetime, timezone
from typing import get_type_hints

from app.application.ports.repositories import (
    AccountRepository,
    CustomFieldRepository,
    ExecutionRepository,
    InstrumentRepository,
    TradeCustomValueRepository,
    TradeRepository,
)
from app.application.ports import ExchangeExecutionSource
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


def test_public_repository_ports_are_importable_protocols():
    for port in (
        TradeRepository,
        ExecutionRepository,
        CustomFieldRepository,
        TradeCustomValueRepository,
        AccountRepository,
        InstrumentRepository,
    ):
        assert getattr(port, "_is_protocol", False) is True


def test_all_repository_methods_are_async_and_use_domain_types():
    expected = {
        TradeRepository: ("get_by_id", "save", "list_open", "list_all"),
        ExecutionRepository: ("save", "get_by_id", "get_by_external_id", "list_by_trade"),
        CustomFieldRepository: (
            "get_definition",
            "list_definitions",
            "list_options",
            "list_scopes",
            "save_definition",
            "save_option",
            "save_scope",
        ),
        TradeCustomValueRepository: ("add", "list_by_trade", "get_for_field"),
        AccountRepository: ("exists", "list_active", "list_for_owner", "belongs_to_owner"),
        InstrumentRepository: ("search", "get_by_id", "get_by_exchange_symbol"),
    }
    for port, method_names in expected.items():
        for method_name in method_names:
            method = getattr(port, method_name)
            assert inspect.iscoroutinefunction(method)
            assert "dict" not in str(inspect.signature(method))


def test_representative_port_annotations_use_domain_value_objects():
    assert get_type_hints(TradeRepository.get_by_id)["trade_id"] is TradeId
    assert get_type_hints(ExecutionRepository.get_by_id)["execution_id"] is ExecutionId
    assert get_type_hints(CustomFieldRepository.get_definition)["field_id"].__name__ == "CustomFieldDefinitionId"
    assert get_type_hints(TradeCustomValueRepository.list_by_trade)["trade_id"] is TradeId
    assert get_type_hints(AccountRepository.exists)["account_id"].__name__ == "AccountId"
    assert get_type_hints(AccountRepository.list_for_owner)["owner_id"].__name__ == "OwnerId"
    assert get_type_hints(AccountRepository.belongs_to_owner)["owner_id"].__name__ == "OwnerId"
    assert get_type_hints(InstrumentRepository.get_by_id)["instrument_id"].__name__ == "InstrumentId"


class FakeTradeRepository:
    async def get_by_id(self, trade_id: TradeId) -> Trade | None:
        return None

    async def save(self, trade: Trade) -> None:
        return None

    async def list_open(self, *, account_id=None, instrument_id=None) -> tuple[Trade, ...]:
        return ()

    async def list_all(self, *, account_id=None, instrument_id=None, limit=100, offset=0) -> tuple[Trade, ...]:
        return ()


class FakeExecutionRepository:
    async def save(self, execution: Execution) -> None:
        return None

    async def get_by_id(self, execution_id: ExecutionId) -> Execution | None:
        return None

    async def get_by_external_id(self, *, exchange, account_id, external_execution_id):
        return None

    async def list_by_trade(self, trade_id: TradeId) -> tuple[Execution, ...]:
        return ()


class FakeCustomFieldRepository:
    async def get_definition(self, field_id):
        return None

    async def list_definitions(self, *, include_inactive=False):
        return ()

    async def list_options(self, field_id, *, include_inactive=False):
        return ()

    async def list_scopes(self, field_id=None):
        return ()

    async def save_definition(self, definition):
        return None

    async def save_option(self, option):
        return None

    async def save_scope(self, scope):
        return None


class FakeTradeCustomValueRepository:
    async def add(self, value):
        return None

    async def upsert(self, value):
        return None

    async def list_by_trade(self, trade_id):
        return ()

    async def get_for_field(self, *, trade_id, field_id, definition_version):
        return None


class FakeAccountRepository:
    async def exists(self, account_id):
        return True

    async def list_active(self):
        return ()

    async def list_for_owner(self, owner_id):
        return ()

    async def belongs_to_owner(self, account_id, owner_id):
        return False


class FakeInstrumentRepository:
    async def search(self, query, *, limit=20):
        return ()

    async def get_by_id(self, instrument_id):
        return None

    async def get_by_exchange_symbol(self, exchange, symbol, *, active_only=True):
        return ()


def test_tiny_async_fakes_satisfy_protocols_structurally():
    assert isinstance(FakeTradeRepository(), TradeRepository)
    assert isinstance(FakeExecutionRepository(), ExecutionRepository)
    assert isinstance(FakeCustomFieldRepository(), CustomFieldRepository)
    assert isinstance(FakeTradeCustomValueRepository(), TradeCustomValueRepository)
    assert isinstance(FakeAccountRepository(), AccountRepository)
    assert isinstance(FakeInstrumentRepository(), InstrumentRepository)


class FakeExchangeExecutionSource:
    async def fetch_executions(self, *, cursor=None, since=None):
        return ()


def test_exchange_execution_source_is_small_and_async():
    assert isinstance(FakeExchangeExecutionSource(), ExchangeExecutionSource)
    assert inspect.iscoroutinefunction(ExchangeExecutionSource.fetch_executions)


def test_protocol_surface_uses_current_domain_entities_without_infrastructure_imports():
    definitions = CustomFieldDefinition.create(
        "quality",
        "Quality",
        CustomFieldValueType.TEXT,
        CustomFieldSource.MANUAL,
        created_at=datetime.now(timezone.utc),
    )
    option = CustomFieldOption.create(definitions.id, "good", "Good")
    scope = CustomFieldScope.global_scope(definitions.id)
    value = TradeCustomValue.create(TradeId.generate(), definitions, "good", datetime.now(timezone.utc))
    assert all(item is not None for item in (definitions, option, scope, value))
