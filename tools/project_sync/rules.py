"""
rules.py

Project Sync Framework

Version:
0.4.0

Component:
Architecture Validation Rules

Responsibility:

Stores architecture validation rules.

This module does NOT:

- execute validation;
- scan project files;
- modify project structure.
"""


from dataclasses import dataclass
from typing import List



@dataclass
class ArchitectureRule:
    """
    Single architecture rule definition.
    """

    rule_id: str

    name: str

    description: str

    severity: str = "error"



class RuleRegistry:
    """
    Collection of architecture rules.
    """


    def __init__(self):

        self.rules: List[ArchitectureRule] = []



    def add(
        self,
        rule: ArchitectureRule
    ):
        """
        Register new rule.
        """

        self.rules.append(
            rule
        )



    def all(self):
        """
        Return all registered rules.
        """

        return self.rules



    def count(self):
        """
        Return rule count.
        """

        return len(
            self.rules
        )