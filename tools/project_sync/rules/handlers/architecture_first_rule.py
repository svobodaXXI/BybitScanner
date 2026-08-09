"""
ARCH-001

Architecture First Rule.

Checks that every registered component
has required architectural information.
"""


from typing import Any

from ..rule_base import ArchitectureRule
from ..rule_result import RuleResult


class ArchitectureFirstRule(ArchitectureRule):
    """
    ARCH-001:
    Architecture First
    """

    rule_id = "ARCH-001"

    name = "Architecture First"

    description = (
        "Component must define architecture responsibility "
        "before implementation."
    )

    category = "architecture"

    severity = "high"


    def validate(
        self,
        component: dict[str, Any],
        context: dict[str, Any],
    ) -> RuleResult:
        """
        Validate architecture metadata.
        """

        required_fields = [
            "name",
            "layer",
            "responsibility",
        ]

        missing = [
            field
            for field in required_fields
            if field not in component
        ]

        if missing:
            return RuleResult(
                rule_id=self.rule_id,
                status="FAILED",
                message=(
                    "Missing architecture fields: "
                    + ", ".join(missing)
                ),
                component=component.get(
                    "name",
                    "unknown",
                ),
            )

        return RuleResult(
            rule_id=self.rule_id,
            status="PASSED",
            message="Architecture definition exists.",
            component=component.get(
                "name",
                "unknown",
            ),
        )