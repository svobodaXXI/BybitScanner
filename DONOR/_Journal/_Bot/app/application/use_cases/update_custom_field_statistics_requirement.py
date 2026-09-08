"""Change only the eligibility policy of an existing dynamic field."""

from dataclasses import replace

from app.application.dtos import _id
from app.application.ports.repositories import CustomFieldRepository
from app.core.statistics.ids import CustomFieldDefinitionId


class UpdateCustomFieldStatisticsRequirement:
    def __init__(self, fields: CustomFieldRepository) -> None:
        self._fields = fields

    async def execute(self, field_id, required_for_statistics: bool):
        field_id = _id(field_id, CustomFieldDefinitionId, "field_id")
        if type(required_for_statistics) is not bool:
            raise TypeError("required_for_statistics must be bool")
        definition = await self._fields.get_definition(field_id)
        if definition is None:
            raise ValueError("custom field was not found")
        updated = replace(definition, required_for_statistics=required_for_statistics)
        await self._fields.save_definition(updated)
        return updated
