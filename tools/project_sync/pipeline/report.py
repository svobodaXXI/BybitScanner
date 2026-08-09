"""
Project Sync Framework

Pipeline Report Model

Defines the standardized report contract for
Project Sync Pipeline execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
from typing import Any


@dataclass
class PipelineReport:
    """
    Standardized final report of Pipeline execution.
    """

    pipeline: str
    version: str
    status: str
    stages: int

    results: list[dict[str, Any]] = field(
        default_factory=list
    )

    errors: list[dict[str, Any]] = field(
        default_factory=list
    )

    created: str = field(
        default_factory=lambda:
            datetime.now().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert report to machine-readable format.
        """

        return {
            "pipeline": self.pipeline,
            "version": self.version,
            "status": self.status,
            "created": self.created,
            "stages": self.stages,
            "results": self.results,
            "errors": self.errors,
        }

    def write(
        self,
        path: Path,
    ) -> None:
        """
        Persist report as JSON artifact.
        """

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                self.to_dict(),
                indent=4,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

    @classmethod
    def from_results(
        cls,
        results: list[dict[str, Any]],
        version: str = "3.2",
    ) -> "PipelineReport":
        """
        Create a standardized report from
        normalized PipelineResult dictionaries.
        """

        errors = [
            result
            for result in results
            if not result.get(
                "success",
                False,
            )
        ]

        return cls(
            pipeline="project_sync_pipeline_engine",
            version=version,
            status=(
                "HEALTHY"
                if not errors
                else "FAILED"
            ),
            stages=len(results),
            results=results,
            errors=errors,
        )
