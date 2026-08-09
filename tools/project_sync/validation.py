"""
validation.py

Project Sync Framework

Version:
0.4.2

Component:
Validation Contract

Responsibility:

Defines validation result objects.

This module does NOT:

- execute validation;
- analyze architecture;
- modify files.
"""


from dataclasses import dataclass, field



@dataclass
class ValidationIssue:
    """
    Single validation issue.
    """


    component: str

    rule: str

    message: str



    def to_dict(self):

        return {

            "component": self.component,

            "rule": self.rule,

            "message": self.message

        }




class ValidationResult:
    """
    Stores validation execution result.
    """



    def __init__(self):

        self.issues = []



    def add_issue(
        self,
        issue: ValidationIssue
    ):

        self.issues.append(
            issue
        )



    def count(self):

        return len(
            self.issues
        )



    def status(self):

        if self.count() == 0:

            return "PASSED"


        return "FAILED"