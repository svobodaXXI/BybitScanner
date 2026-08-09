"""
default_rules.py

Project Sync Framework

Version:
0.4.1

Component:
Default Architecture Rules

Responsibility:

Provides built-in architecture rules.

This module does NOT:

- validate components;
- analyze modules;
- modify files.
"""


from .rules import (
    ArchitectureRule,
    RuleRegistry,
)



def create_default_rules():

    registry = RuleRegistry()


    registry.add(
        ArchitectureRule(
            rule_id="RULE-012",
            name="Geometry Responsibility",
            description=(
                "Geometry Engine must contain only "
                "geometric analysis responsibilities "
                "and must not contain signals, "
                "telegram or trading decisions."
            )
        )
    )


    registry.add(
        ArchitectureRule(
            rule_id="RULE-013",
            name="Validation Responsibility",
            description=(
                "Validation Engine must validate "
                "geometry only and must not contain "
                "trading logic, notifications "
                "or execution."
            )
        )
    )


    registry.add(
        ArchitectureRule(
            rule_id="RULE-014",
            name="Signal Responsibility",
            description=(
                "Signal Layer handles signal quality "
                "and interpretation only and must not "
                "contain geometry generation."
            )
        )
    )


    return registry