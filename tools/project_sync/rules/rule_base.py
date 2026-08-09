"""
Architecture Rule Engine

Base architecture rule definition.

All architecture validation rules
must inherit from ArchitectureRule.
"""


from abc import ABC, abstractmethod
from typing import Any

from .rule_result import RuleResult


class ArchitectureRule(ABC):
    """
    Base class for architecture validation rules.
    """


    rule_id: str = ""

    name: str = ""

    description: str = ""

    category: str = "architecture"

    severity: str = "normal"


    def metadata(self) -> dict[str, Any]:
        """
        Returns rule metadata.

        Used by:
        - Rule Registry
        - Validation Reports
        - Architecture Compliance Engine
        """

        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
        }


    @abstractmethod
    def validate(
        self,
        component: dict[str, Any],
        context: dict[str, Any],
    ) -> RuleResult:
        """
        Execute architecture validation.

        Parameters:

        component:
            Component information
            from Architecture Registry.

        context:
            Project architecture context.

        Returns:

        RuleResult
            Standardized validation result.
        """

        raise NotImplementedError