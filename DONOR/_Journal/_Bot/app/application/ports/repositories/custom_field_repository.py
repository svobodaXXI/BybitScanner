"""Repository port for the Dynamic Statistics catalog."""

from typing import Protocol, runtime_checkable

from app.core.statistics.custom_field_definition import CustomFieldDefinition
from app.core.statistics.custom_field_option import CustomFieldOption
from app.core.statistics.custom_field_scope import CustomFieldScope
from app.core.statistics.ids import CustomFieldDefinitionId


@runtime_checkable
class CustomFieldRepository(Protocol):
    """Async catalog contract; inactive records remain readable on request."""

    async def get_definition(self, field_id: CustomFieldDefinitionId) -> CustomFieldDefinition | None:
        ...

    async def list_definitions(
        self,
        *,
        include_inactive: bool = False,
    ) -> tuple[CustomFieldDefinition, ...]:
        """Return definitions ordered by code, then definition ID."""
        ...

    async def list_options(
        self,
        field_id: CustomFieldDefinitionId,
        *,
        include_inactive: bool = False,
    ) -> tuple[CustomFieldOption, ...]:
        """Return options ordered by sort_order, then option ID."""
        ...

    async def list_scopes(
        self,
        field_id: CustomFieldDefinitionId | None = None,
    ) -> tuple[CustomFieldScope, ...]:
        """Return scopes ordered deterministically by field ID and dimensions."""
        ...

    async def save_definition(self, definition: CustomFieldDefinition) -> None:
        """Upsert by immutable definition ID; no hard delete is exposed."""
        ...

    async def save_option(self, option: CustomFieldOption) -> None:
        """Upsert by immutable option ID; inactive options are retained."""
        ...

    async def save_scope(self, scope: CustomFieldScope) -> None:
        """Persist one scope record; no delete operation is exposed."""
        ...
