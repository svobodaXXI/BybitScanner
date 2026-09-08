"""Idempotent default manual fields for the daily Telegram journal."""

from dataclasses import dataclass
from dataclasses import replace

from app.application.ports.repositories import CustomFieldRepository
from app.core.statistics import CustomFieldDefinition, CustomFieldOption
from app.core.statistics.enums import CustomFieldPhase, CustomFieldSource, CustomFieldValueType


@dataclass(frozen=True, slots=True)
class DefaultFieldSpec:
    code: str
    name: str
    value_type: CustomFieldValueType
    required_for_statistics: bool
    options: tuple[tuple[str, str], ...] = ()


DEFAULT_STATISTICAL_FIELD_SPECS = (
    DefaultFieldSpec(
        "strategy", "Стратегия", CustomFieldValueType.CHOICE, True,
        (("trend_continuation", "Продолжение тренда"), ("consolidation", "Консолидация"), ("other", "Другое")),
    ),
    DefaultFieldSpec(
        "setup", "Сетап", CustomFieldValueType.CHOICE, True,
        (("breakout", "Пробой"), ("retest", "Ретест"), ("compression", "Поджатие"), ("pullback", "Откат"), ("other", "Другое")),
    ),
    DefaultFieldSpec("followed_plan", "По плану?", CustomFieldValueType.YES_NO, True),
    DefaultFieldSpec(
        "error", "Ошибка", CustomFieldValueType.CHOICE, False,
        (("none", "Другое"), ("early_entry", "Ранний вход"), ("late_entry", "Поздний вход"), ("stop_violation", "Нарушение стопа"), ("overrisk", "Перериск"), ("fomo", "FOMO")),
    ),
    DefaultFieldSpec("comment", "Комментарий", CustomFieldValueType.TEXT, False),
)


class BootstrapStatisticalFields:
    """Create defaults and repair the legacy phase of built-in manual fields."""

    def __init__(self, fields: CustomFieldRepository) -> None:
        self._fields = fields

    async def execute(self) -> tuple[CustomFieldDefinition, ...]:
        existing = {str(item.code): item for item in await self._fields.list_definitions(include_inactive=True)}
        result = []
        for spec in DEFAULT_STATISTICAL_FIELD_SPECS:
            definition = existing.get(spec.code)
            if definition is None:
                definition = CustomFieldDefinition.create(
                    spec.code,
                    spec.name,
                    spec.value_type,
                    CustomFieldSource.MANUAL,
                    phase=CustomFieldPhase.ANY,
                    required_for_statistics=spec.required_for_statistics,
                )
                await self._fields.save_definition(definition)
                existing[spec.code] = definition
            elif definition.phase is not CustomFieldPhase.ANY:
                # Older installations persisted the built-ins as POST_TRADE,
                # which made the same editor unusable for OPEN trades.  Keep
                # user-created fields immutable and patch only known defaults.
                updated = replace(definition, phase=CustomFieldPhase.ANY)
                phase_updater = getattr(self._fields, "update_definition_phase", None)
                if phase_updater is None:
                    # Lightweight fakes and alternate adapters can still use
                    # their regular upsert path for this controlled correction.
                    await self._fields.save_definition(updated)
                else:
                    await phase_updater(definition.id, CustomFieldPhase.ANY)
                definition = updated
                existing[spec.code] = definition
            result.append(definition)
            if spec.options:
                current = {item.code: item for item in await self._fields.list_options(definition.id, include_inactive=True)}
                for sort_order, (code, label) in enumerate(spec.options):
                    option = current.get(code)
                    if option is None:
                        await self._fields.save_option(CustomFieldOption.create(definition.id, code, label, sort_order=sort_order))
                    elif option.label != label:
                        # The stable option code/ID is the historical identity;
                        # changing only its display label is history-safe.
                        await self._fields.save_option(replace(option, label=label))
        return tuple(result)
