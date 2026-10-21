"""
Architecture Validation Report

Aggregates architecture validation results
into a single project report.

Part of:
Project Sync Framework
Architecture Intelligence Layer
"""

from collections import Counter

from ..rules.rule_result import RuleResult


class ValidationReport:
    """
    Aggregated architecture validation report.
    """

    def __init__(self, results: list[RuleResult]):
        self.results = results

    @property
    def total_rules(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(result.success for result in self.results)

    @property
    def failed(self) -> int:
        return self.total_rules - self.passed

    @property
    def success_rate(self) -> float:
        if self.total_rules == 0:
            return 100.0

        return round(
            self.passed / self.total_rules * 100,
            2,
        )

    def category_summary(self) -> dict[str, int]:
        """
        Count rules by category.
        """

        counter = Counter()

        for result in self.results:
            counter[result.category] += 1

        return dict(counter)

    def failures(self) -> list[RuleResult]:
        """
        Return failed validations.
        """

        return [
            result
            for result in self.results
            if not result.success
        ]

    def to_dict(self) -> dict:
        """
        Export report.
        """

        return {
            "total_rules": self.total_rules,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "categories": self.category_summary(),
            "failures": [
                failure.to_dict()
                for failure in self.failures()
            ],
        }