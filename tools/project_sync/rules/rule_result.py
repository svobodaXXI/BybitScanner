"""
Architecture Rule Engine

Rule execution result model.

Defines standardized output
for architecture validation rules.
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuleStatus(Enum):
    """
    Result status of rule execution.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"


@dataclass
class RuleResult:
    """
    Standard architecture rule execution result.

    Used by:
    - Rule Handlers
    - Architecture Validator
    - Compliance Reports
    """

    rule_id: str

    status: RuleStatus

    message: str = ""

    component: str | None = None

    details: dict[str, Any] = field(default_factory=dict)

    def is_success(self) -> bool:
        """
        Returns True when rule passed.
        """

        return self.status == RuleStatus.PASS


    def to_dict(self) -> dict[str, Any]:
        """
        Converts result into report-compatible format.
        """

        return {
            "rule_id": self.rule_id,
            "status": self.status.value,
            "message": self.message,
            "component": self.component,
            "details": self.details,
        }