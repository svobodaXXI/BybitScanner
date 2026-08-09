"""
architecture_analyzer.py

Project Sync Framework

Version:
0.3.2

Component:
Architecture Analyzer

Responsibility:

Analyzes module registry
using architecture rules.

This module does NOT:

- modify source code;
- update documentation;
- generate reports.

It only creates architecture representation.
"""


from pathlib import Path

from .architecture import (
    ArchitectureComponent,
    ArchitectureRegistry,
)

from .architecture_rules import (
    get_default_rules,
)



class ArchitectureAnalyzer:
    """
    Converts module registry
    into architecture registry.
    """


    def __init__(self):
        self.rules = get_default_rules()


    def analyze(
        self,
        module_registry
    ) -> ArchitectureRegistry:
        """
        Build architecture registry.
        """

        registry = ArchitectureRegistry()


        for module in module_registry.modules:

            component = ArchitectureComponent(
                name=module.name,
                path=module.path,
                component_type=module.module_type,
                status=module.status
            )


            self._apply_rules(
                component
            )


            registry.add(
                component
            )


        return registry


    def _apply_rules(
        self,
        component
    ):
        """
        Apply architecture rules.
        """

        name = component.name.lower()


        for rule in self.rules:

            if rule.keyword in name:

                component.layer = rule.layer

                component.responsibility = (
                    rule.responsibility
                )

                break