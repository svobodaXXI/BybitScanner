"""Definition of a dynamic custom statistics field."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from .codes import CustomFieldCode
from .enums import CustomFieldPhase, CustomFieldSource, CustomFieldStatus, CustomFieldValueType
from .ids import CustomFieldDefinitionId


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _enum(value: object, enum_type: type, field_name: str):
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            raise ValueError(f"invalid {field_name}: {value!r}") from error
    raise TypeError(f"{field_name} must be {enum_type.__name__}")


@dataclass(frozen=True, slots=True)
class CustomFieldDefinition:
    """Immutable field definition; lifecycle operations return a new instance."""

    id: CustomFieldDefinitionId
    code: CustomFieldCode | str
    name: str
    value_type: CustomFieldValueType
    source: CustomFieldSource
    phase: CustomFieldPhase
    required: bool
    definition_version: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: CustomFieldStatus = field(default=CustomFieldStatus.ACTIVE, kw_only=True)
    required_for_statistics: bool = field(default=False, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.id, CustomFieldDefinitionId):
            object.__setattr__(self, "id", CustomFieldDefinitionId(self.id))
        if isinstance(self.code, str):
            object.__setattr__(self, "code", CustomFieldCode(self.code))
        elif not isinstance(self.code, CustomFieldCode):
            raise TypeError("code must be CustomFieldCode or str")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must not be empty")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "value_type", _enum(self.value_type, CustomFieldValueType, "value_type"))
        object.__setattr__(self, "source", _enum(self.source, CustomFieldSource, "source"))
        object.__setattr__(self, "phase", _enum(self.phase, CustomFieldPhase, "phase"))
        object.__setattr__(self, "status", _enum(self.status, CustomFieldStatus, "status"))
        if type(self.required) is not bool:
            raise TypeError("required must be bool")
        if type(self.required_for_statistics) is not bool:
            raise TypeError("required_for_statistics must be bool")
        if type(self.definition_version) is not int or self.definition_version < 1:
            raise ValueError("definition_version must be an integer >= 1")
        object.__setattr__(self, "created_at", _as_utc(self.created_at, "created_at"))

    @classmethod
    def create(
        cls,
        code: CustomFieldCode | str,
        name: str,
        value_type: CustomFieldValueType,
        source: CustomFieldSource,
        phase: CustomFieldPhase = CustomFieldPhase.ANY,
        required: bool = False,
        definition_version: int = 1,
        created_at: datetime | None = None,
        field_id: CustomFieldDefinitionId | None = None,
        id: CustomFieldDefinitionId | None = None,
        required_for_statistics: bool = False,
    ) -> "CustomFieldDefinition":
        if field_id is not None and id is not None:
            raise TypeError("pass either field_id or id, not both")
        return cls(
            id=field_id or id or CustomFieldDefinitionId.generate(),
            code=code,
            name=name,
            value_type=value_type,
            source=source,
            phase=phase,
            required=required,
            definition_version=definition_version,
            created_at=created_at or datetime.now(timezone.utc),
            required_for_statistics=required_for_statistics,
        )

    @property
    def is_active(self) -> bool:
        return self.status is CustomFieldStatus.ACTIVE

    def activate(self) -> "CustomFieldDefinition":
        return replace(self, status=CustomFieldStatus.ACTIVE)

    def deactivate(self) -> "CustomFieldDefinition":
        return replace(self, status=CustomFieldStatus.INACTIVE)
