"""
Project Sync Framework
Pipeline Stage Model

Defines pipeline execution stage contract.
"""

from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class PipelineStage:
    """
    Single executable pipeline stage.
    """

    name: str

    handler: Callable[..., Any]

    description: str = ""

    enabled: bool = True

    metadata: dict = field(default_factory=dict)

    def execute(self, context=None):
        """
        Execute stage handler.
        """

        if not self.enabled:
            return None

        return self.handler(context)

    def to_dict(self) -> dict:
        """
        Convert stage definition to machine-readable format.
        """

        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }