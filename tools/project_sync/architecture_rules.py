"""
architecture_rules.py

Project Sync Framework

Version:
0.3.1

Component:
Architecture Rules

Responsibility:

Contains classification rules
for architecture analysis.

This module does NOT:

- scan project;
- modify files;
- generate reports;
- update documentation.

It only contains rules.
"""


from dataclasses import dataclass



@dataclass
class ArchitectureRule:
    """
    Single classification rule.
    """

    keyword: str

    layer: str

    responsibility: str



DEFAULT_RULES = [

    ArchitectureRule(
        keyword="geometry",
        layer="Geometry Engine",
        responsibility="Geometric market structure analysis"
    ),


    ArchitectureRule(
        keyword="validation",
        layer="Validation Engine",
        responsibility="Structure validation"
    ),


    ArchitectureRule(
        keyword="confirmation",
        layer="Validation Engine",
        responsibility="Signal confirmation"
    ),


    ArchitectureRule(
        keyword="telegram",
        layer="Notification Layer",
        responsibility="External notifications"
    ),


    ArchitectureRule(
        keyword="signal",
        layer="Signal Layer",
        responsibility="Signal processing"
    ),

]



def get_default_rules():
    """
    Return default architecture rules.
    """

    return DEFAULT_RULES