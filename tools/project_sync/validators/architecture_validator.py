"""
Architecture Validator

Coordinates architecture validation.

Validation execution is delegated
to RuleExecutor.
"""

from typing import Any

from ..rules.rule_executor import RuleExecutor
from ..rules.rule_registry import RuleRegistry
from ..rules.rule_result import RuleResult


class ArchitectureValidator:
    """
    Coordinates architecture validation.
    """


    def __init__(
        self,
        rule_registry: RuleRegistry,
    ):
        self.rule_registry = rule_registry
        self.executor = RuleExecutor(rule_registry)


    def validate_component(
        self,
        component: dict[str, Any],
        context: dict[str, Any],
    ) -> list[RuleResult]:
        """
        Validate a single component.
        """

        return self.executor.execute(
            component,
            context,
        )


    def validate_project(
        self,
        components: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[RuleResult]:
        """
        Validate project architecture.
        """

        return self.executor.execute_project(
            components,
            context,
        )


    def get_rule_metadata(
        self,
    ) -> list[dict]:
        """
        Return metadata
        of registered rules.
        """

        return self.rule_registry.get_metadata()