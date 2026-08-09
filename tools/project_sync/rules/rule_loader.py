"""
Architecture Rule Loader

Automatically loads architecture rules.

Part of:
Project Sync Framework
Architecture Intelligence Layer
"""

from .handlers.architecture_first_rule import (
    ArchitectureFirstRule,
)
from .handlers.dependency_direction_rule import (
    DependencyDirectionRule,
)
from .rule_registry import RuleRegistry


class RuleLoader:
    """
    Loads architecture rules
    into the registry.
    """

    def __init__(
        self,
        registry: RuleRegistry,
    ):
        self.registry = registry

    def load(self) -> RuleRegistry:
        """
        Register all available rules.
        """

        self.registry.register(
            ArchitectureFirstRule()
        )

        self.registry.register(
            DependencyDirectionRule()
        )

        return self.registry