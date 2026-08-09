# tools/project_sync/pipeline/context.py

"""
Project Sync Framework
Pipeline Context Model

Shared execution context for pipeline stages.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """
    Runtime context passed between pipeline stages.
    """

    project_path: str

    data: dict[str, Any] = field(default_factory=dict)

    artifacts: dict[str, Any] = field(default_factory=dict)

    metadata: dict[str, Any] = field(default_factory=dict)

    errors: list[str] = field(default_factory=list)

    def set(self, key: str, value: Any):
        """
        Store context data.
        """

        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve context data.
        """

        return self.data.get(key, default)

    def add_artifact(self, name: str, artifact: Any):
        """
        Register generated artifact.
        """

        self.artifacts[name] = artifact

    def add_error(self, error: str):
        """
        Register execution error.
        """

        self.errors.append(error)

    def has_errors(self) -> bool:
        """
        Check execution errors.
        """

        return len(self.errors) > 0

    def to_dict(self) -> dict:
        """
        Convert context to machine-readable format.
        """

        return {
            "project_path": self.project_path,
            "data": self.data,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "errors": self.errors,
        }