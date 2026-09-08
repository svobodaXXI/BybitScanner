"""Stable option identity for CHOICE custom fields."""

from dataclasses import dataclass, field, replace

from .codes import _normalize
from .ids import CustomFieldDefinitionId, CustomFieldOptionId


@dataclass(frozen=True, slots=True)
class CustomFieldOption:
    id: CustomFieldOptionId
    field_id: CustomFieldDefinitionId
    code: str
    label: str
    sort_order: int = 0
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, CustomFieldOptionId):
            object.__setattr__(self, "id", CustomFieldOptionId(self.id))
        if not isinstance(self.field_id, CustomFieldDefinitionId):
            object.__setattr__(self, "field_id", CustomFieldDefinitionId(self.field_id))
        object.__setattr__(self, "code", _normalize(self.code, name="CustomFieldOption code", uppercase=False))
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("label must not be empty")
        object.__setattr__(self, "label", self.label.strip())
        if type(self.sort_order) is not int or self.sort_order < 0:
            raise ValueError("sort_order must be an integer >= 0")
        if type(self.active) is not bool:
            raise TypeError("active must be bool")

    @classmethod
    def create(
        cls,
        field_id: CustomFieldDefinitionId,
        code: str,
        label: str,
        sort_order: int = 0,
        option_id: CustomFieldOptionId | None = None,
        id: CustomFieldOptionId | None = None,
        active: bool = True,
    ) -> "CustomFieldOption":
        if option_id is not None and id is not None:
            raise TypeError("pass either option_id or id, not both")
        return cls(
            id=option_id or id or CustomFieldOptionId.generate(),
            field_id=field_id,
            code=code,
            label=label,
            sort_order=sort_order,
            active=active,
        )

    def activate(self) -> "CustomFieldOption":
        return replace(self, active=True)

    def deactivate(self) -> "CustomFieldOption":
        return replace(self, active=False)
