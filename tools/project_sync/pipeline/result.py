"""
Project Sync Framework

Pipeline Result Model

Defines standardized output of pipeline stages.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineResult:
    """
    Common result contract for pipeline execution.
    """

    stage: str

    success: bool

    data: Any = None

    message: str = ""

    errors: list[str] = field(
        default_factory=list
    )

    metadata: dict = field(
        default_factory=dict
    )

    def add_error(
        self,
        error: str,
    ):
        """
        Add execution error.
        """

        self.errors.append(
            error
        )

        self.success = False

    def add_metadata(
        self,
        key: str,
        value: Any,
    ):
        """
        Add metadata value.
        """

        self.metadata[key] = value

    def merge_metadata(
        self,
        values: dict,
    ):
        """
        Merge metadata dictionary.
        """

        self.metadata.update(
            values
        )

    def to_dict(
        self,
    ) -> dict:
        """
        Convert result to machine-readable format.
        """

        return {
            "stage": self.stage,
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    @classmethod
    def success_result(
        cls,
        stage: str,
        data: Any = None,
        message: str = "",
        metadata: dict | None = None,
    ):
        """
        Create successful pipeline result.
        """

        return cls(
            stage=stage,
            success=True,
            data=data,
            message=message,
            metadata=metadata or {},
        )

    @classmethod
    def failure_result(
        cls,
        stage: str,
        error: str,
        message: str = "",
        metadata: dict | None = None,
    ):
        """
        Create failed pipeline result.
        """

        return cls(
            stage=stage,
            success=False,
            message=message,
            errors=[error],
            metadata=metadata or {},
        )
