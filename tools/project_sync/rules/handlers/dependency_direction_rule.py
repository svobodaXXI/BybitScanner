"""
Dependency Direction Rule

Validates architecture dependency direction.

Implements:

ARCH-004

Dependency Direction
"""

from typing import Any

from ..rule_base import ArchitectureRule
from ..rule_result import RuleResult


class DependencyDirectionRule(ArchitectureRule):
    """
    Validates allowed architecture dependency flow.
    """

    rule_id = "ARCH-004"

    name = "Dependency Direction"

    description = (
        "Checks that architecture dependencies "
        "follow defined layer direction."
    )

    category = "architecture"

    severity = "high"


    allowed_layers = [
        "DATA_LAYER",
        "GEOMETRY_LAYER",
        "VALIDATION_LAYER",
        "PATTERN_LAYER",
        "SIGNAL_LAYER",
        "NOTIFICATION_LAYER",
    ]


    forbidden_dependencies = [
        (
            "NOTIFICATION_LAYER",
            "GEOMETRY_LAYER",
        ),
        (
            "SIGNAL_LAYER",
            "NOTIFICATION_LAYER",
        ),
        (
            "GEOMETRY_LAYER",
            "SIGNAL_LAYER",
        ),
        (
            "DATA_LAYER",
            "SIGNAL_LAYER",
        ),
    ]


    def validate(
        self,
        component: dict[str, Any],
        context: dict[str, Any],
    ) -> RuleResult:
        """
        Validate dependency direction.
        """

        component_layer = component.get(
            "layer"
        )

        dependencies = component.get(
            "dependencies",
            [],
        )


        for dependency in dependencies:

            dependency_layer = dependency.get(
                "layer"
            )

            pair = (
                component_layer,
                dependency_layer,
            )

            if pair in self.forbidden_dependencies:

                return RuleResult(
                    rule_id=self.rule_id,
                    status="FAILED",
                    message=(
                        f"Forbidden dependency: "
                        f"{component_layer} -> "
                        f"{dependency_layer}"
                    ),
                    component=component.get(
                        "name"
                    ),
                )


        return RuleResult(
            rule_id=self.rule_id,
            status="PASSED",
            message=(
                "Dependency direction is valid."
            ),
            component=component.get(
                "name"
            ),
        )