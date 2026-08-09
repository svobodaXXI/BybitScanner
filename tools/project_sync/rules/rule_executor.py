"""
Architecture Rule Executor

Executes registered architecture rules.

Part of:
Project Sync Framework
Architecture Intelligence Layer
"""


from typing import Any

from .rule_registry import RuleRegistry
from .rule_result import RuleResult


class RuleExecutor:
    """
    Executes architecture rules
    against project components.
    """


    def __init__(
        self,
        registry: RuleRegistry,
    ):
        self.registry = registry


    def execute(
        self,
        component: dict[str, Any],
        context: dict[str, Any],
    ) -> list[RuleResult]:
        """
        Execute all registered rules
        for a single component.
        """

        results: list[RuleResult] = []

        for rule in self.registry.get_rules():

            try:

                results.append(
                    rule.validate(
                        component,
                        context,
                    )
                )

            except Exception as error:

                results.append(
                    RuleResult(
                        rule_id=rule.rule_id,
                        status="ERROR",
                        message=str(error),
                        component=component.get(
                            "name",
                            "unknown",
                        ),
                    )
                )

        return results


    def execute_project(
        self,
        components: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[RuleResult]:
        """
        Execute rules
        for the whole project.
        """

        results: list[RuleResult] = []

        for component in components:

            results.extend(
                self.execute(
                    component,
                    context,
                )
            )

        return results