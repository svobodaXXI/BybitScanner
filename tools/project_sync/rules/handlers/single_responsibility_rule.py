"""
Single Responsibility Rule

Implements:

ARCH-002

Single Responsibility
"""

from typing import Any

from ..rule_base import ArchitectureRule
from ..rule_result import RuleResult


class SingleResponsibilityRule(ArchitectureRule):
    """
    Validates that a component
    has exactly one responsibility.
    """

    rule_id = "ARCH-002"

    name = "Single Responsibility"

    description = (
        "Checks that every component "
        "has one defined responsibility."
    )

    category = "architecture"

    severity = "high"


    def validate(
        self,
        component: dict[str, Any],
        context: dict[str, Any],
    ) -> RuleResult:
        """
        Validate component responsibility.
        """

        responsibility = component.get(
            "responsibility"
        )

        if responsibility is None:

            return RuleResult(
                rule_id=self.rule_id,
                status="FAILED",
                message="Responsibility is missing.",
                component=component.get(
                    "name",
                    "unknown",
                ),
            )

        if isinstance(
            responsibility,
            list,
        ):

            if len(responsibility) != 1:

                return RuleResult(
                    rule_id=self.rule_id,
                    status="FAILED",
                    message=(
                        "Component has multiple "
                        "responsibilities."
                    ),
                    component=component.get(
                        "name",
                        "unknown",
                    ),
                )

        return RuleResult(
            rule_id=self.rule_id,
            status="PASSED",
            message=(
                "Single responsibility confirmed."
            ),
            component=component.get(
                "name",
                "unknown",
            ),
        )