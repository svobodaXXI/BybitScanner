"""Pure deterministic resolution of relevant custom field definitions."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .custom_field_definition import CustomFieldDefinition
from .custom_field_scope import CustomFieldScope
from .enums import CustomFieldPhase, CustomFieldStatus
from .resolution_context import CustomFieldResolutionContext


def _same_dimension(scope_value: object, context_value: object) -> bool:
    return scope_value == context_value


@dataclass(frozen=True, slots=True)
class CustomFieldResolver:
    """Resolve future collection relevance only; it never reads or mutates values."""

    def resolve(
        self,
        definitions: Iterable[CustomFieldDefinition],
        scopes: Iterable[CustomFieldScope],
        context: CustomFieldResolutionContext,
    ) -> tuple[CustomFieldDefinition, ...]:
        definitions_tuple = tuple(definitions)
        scopes_tuple = tuple(scopes)
        if not isinstance(context, CustomFieldResolutionContext):
            raise TypeError("context must be CustomFieldResolutionContext")

        by_id: dict[object, CustomFieldDefinition] = {}
        for definition in definitions_tuple:
            if not isinstance(definition, CustomFieldDefinition):
                raise TypeError("definitions must contain CustomFieldDefinition values")
            if definition.id in by_id:
                raise ValueError(f"duplicate custom field definition id: {definition.id}")
            by_id[definition.id] = definition

        scopes_by_field: dict[object, list[CustomFieldScope]] = defaultdict(list)
        for scope in scopes_tuple:
            if not isinstance(scope, CustomFieldScope):
                raise TypeError("scopes must contain CustomFieldScope values")
            if scope.field_id in by_id:
                scopes_by_field[scope.field_id].append(scope)
            # Unknown scope IDs are ignored because callers may load a scope superset.

        resolved = [
            definition
            for definition in definitions_tuple
            if definition.status is CustomFieldStatus.ACTIVE
            and self._phase_matches(definition.phase, context.phase)
            and self._scope_matches(definition.id, scopes_by_field, context)
        ]
        return tuple(sorted(resolved, key=lambda item: (str(item.code), str(item.id))))

    @staticmethod
    def _phase_matches(field_phase: CustomFieldPhase, context_phase: CustomFieldPhase) -> bool:
        # ANY is a valid resolution request and intentionally accepts every field phase.
        if context_phase is CustomFieldPhase.ANY:
            return True
        return field_phase in (context_phase, CustomFieldPhase.ANY)

    @classmethod
    def _scope_matches(
        cls,
        field_id: object,
        scopes_by_field: dict[object, list[CustomFieldScope]],
        context: CustomFieldResolutionContext,
    ) -> bool:
        field_scopes = scopes_by_field.get(field_id)
        if not field_scopes:
            return True  # No scope records means GLOBAL.
        return any(cls._single_scope_matches(scope, context) for scope in field_scopes)

    @staticmethod
    def _single_scope_matches(
        scope: CustomFieldScope,
        context: CustomFieldResolutionContext,
    ) -> bool:
        dimensions = (
            (scope.exchange, context.exchange),
            (scope.market, context.market),
            (scope.strategy_code, context.strategy_code),
            (scope.setup_code, context.setup_code),
        )
        return all(scope_value is None or _same_dimension(scope_value, context_value) for scope_value, context_value in dimensions)
