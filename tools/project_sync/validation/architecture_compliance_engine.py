"""
Architecture Compliance Engine

Runs architecture validation
against the entire project.

Part of:
Project Sync Framework
Architecture Intelligence Layer
"""


from typing import Any

from ..registry.architecture.architecture_registry import (
    ArchitectureRegistry,
)

from ..reports.validation_report import (
    ValidationReport,
)

from ..rules.rule_registry import (
    RuleRegistry,
)

from ..validators.architecture_validator import (
    ArchitectureValidator,
)


class ArchitectureComplianceEngine:
    """
    Executes architecture compliance validation.
    """


    def __init__(
        self,
        rule_registry: RuleRegistry,
    ):
        self.validator = ArchitectureValidator(
            rule_registry,
        )


    def validate(
        self,
        architecture_registry: ArchitectureRegistry,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute full architecture validation.
        """


        components = (
            architecture_registry.get_components()
        )


        results = self.validator.validate_project(
            components,
            context,
        )


        report = ValidationReport(
            results,
        )


        return {
            "summary": {
                "components": len(
                    components
                ),
                "rules": len(
                    self.validator.get_rule_metadata()
                ),
                "passed": report.passed,
                "failed": report.failed,
                "success_rate": report.success_rate,
            },
            "categories": (
                report.category_summary()
            ),
            "failures": [
                failure.to_dict()
                for failure in report.failures()
            ],
        }