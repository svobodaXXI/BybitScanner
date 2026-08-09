"""
validator.py

Project Sync Framework

Version:
0.4.2

Component:
Architecture Validator Engine

Responsibility:

Validates architecture registry
against architecture rules.

This module does NOT:

- scan filesystem;
- build registries;
- modify project files;
- update documentation.
"""


from .validation import (
    ValidationResult,
    ValidationIssue,
)


class ArchitectureValidator:
    """
    Executes architecture validation.
    """


    def __init__(
        self,
        rules
    ):
        """
        Initialize validator.

        rules:
            RuleRegistry instance
        """

        self.rules = rules



    def validate(
        self,
        architecture_registry
    ):
        """
        Validate architecture registry.

        Current version:
        Contract implementation only.

        Detailed rule execution
        will be added incrementally.
        """

        result = ValidationResult()


        for rule in self.rules.all():

            if not self._check_rule(
                rule,
                architecture_registry
            ):

                result.add_issue(
                    ValidationIssue(
                        component="architecture",
                        rule=rule.rule_id,
                        message=rule.description
                    )
                )


        return result



    def _check_rule(
        self,
        rule,
        architecture_registry
    ):
        """
        Rule execution placeholder.

        Specific validators will be
        implemented in separate layers.
        """

        return True