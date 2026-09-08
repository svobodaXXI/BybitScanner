import asyncio
from dataclasses import replace

from app.application import BootstrapStatisticalFields
from app.core.statistics import CustomFieldDefinition, CustomFieldOption
from app.core.statistics.custom_field_resolver import CustomFieldResolver
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.statistics.enums import CustomFieldPhase, CustomFieldSource, CustomFieldStatus, CustomFieldValueType


class FieldCatalogFake:
    def __init__(self):
        self.definitions = []
        self.options = []

    async def list_definitions(self, *, include_inactive=False):
        return tuple(item for item in self.definitions if include_inactive or item.is_active)

    async def save_definition(self, definition):
        current = next((index for index, item in enumerate(self.definitions) if item.id == definition.id), None)
        if current is None:
            self.definitions.append(definition)
        else:
            self.definitions[current] = definition

    async def list_options(self, field_id, *, include_inactive=False):
        return tuple(item for item in self.options if item.field_id == field_id and (include_inactive or item.active))

    async def save_option(self, option):
        current = next((index for index, item in enumerate(self.options) if item.id == option.id), None)
        if current is None:
            self.options.append(option)
        else:
            self.options[current] = option


def test_default_statistical_fields_bootstrap_is_idempotent_and_preserves_deactivation():
    catalog = FieldCatalogFake()
    bootstrap = BootstrapStatisticalFields(catalog)

    first = asyncio.run(bootstrap.execute())
    strategy = next(item for item in first if str(item.code) == "strategy")
    strategy_option = next(item for item in catalog.options if item.field_id == strategy.id)
    strategy_option_id = strategy_option.id
    catalog.definitions[0] = strategy.deactivate()
    catalog.options[0] = replace(strategy_option.deactivate(), label="Trend Continuation")
    catalog.options[1] = replace(catalog.options[1], label="Consolidation")

    asyncio.run(bootstrap.execute())

    assert len(catalog.definitions) == 5
    assert {str(item.code) for item in catalog.definitions} == {"strategy", "setup", "followed_plan", "error", "comment"}
    assert "Тип входа" not in {item.name for item in catalog.definitions}
    assert len(catalog.options) == 14
    assert catalog.definitions[0].status is CustomFieldStatus.INACTIVE
    assert catalog.options[0].active is False
    assert catalog.options[0].id == strategy_option_id
    assert {item.label for item in catalog.options if item.field_id == strategy.id} == {"Продолжение тренда", "Консолидация", "Другое"}
    assert {item.name for item in catalog.definitions if item.required_for_statistics} == {"Стратегия", "Сетап", "По плану?"}
    assert all(item.value_type in (CustomFieldValueType.CHOICE, CustomFieldValueType.YES_NO, CustomFieldValueType.TEXT) for item in catalog.definitions)
    assert all(item.phase is CustomFieldPhase.ANY for item in catalog.definitions)


def test_bootstrap_repairs_legacy_builtin_phase_for_open_editing():
    catalog = FieldCatalogFake()
    legacy = CustomFieldDefinition.create(
        "strategy", "Стратегия", CustomFieldValueType.CHOICE,
        CustomFieldSource.MANUAL,
        CustomFieldPhase.POST_TRADE,
        required_for_statistics=True,
    )
    catalog.definitions.append(legacy)

    result = asyncio.run(BootstrapStatisticalFields(catalog).execute())

    repaired = next(item for item in result if str(item.code) == "strategy")
    assert repaired.id == legacy.id
    assert repaired.phase is CustomFieldPhase.ANY
    assert catalog.definitions[0].phase is CustomFieldPhase.ANY


def test_all_builtin_context_fields_resolve_for_open_trade():
    catalog = FieldCatalogFake()
    definitions = asyncio.run(BootstrapStatisticalFields(catalog).execute())

    resolved = CustomFieldResolver().resolve(
        definitions,
        (),
        CustomFieldResolutionContext(CustomFieldPhase.OPEN, exchange="BYBIT", market="LINEAR"),
    )

    assert {str(item.code) for item in resolved} == {
        "strategy", "setup", "followed_plan", "error", "comment",
    }
