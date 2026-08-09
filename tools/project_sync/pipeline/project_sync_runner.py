"""
BybitScanner Project Sync Framework

Project Sync Pipeline Runner v3.3

Responsibility:
    Execute the canonical Project Sync Pipeline.

Architecture:
    PipelineRegistry
            ↓
    PipelineExecutor
            ↓
    PipelineStage
            ↓
    PipelineContext
            ↓
    PipelineResult
            ↓
    PipelineReport
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import sys

from tools.project_sync.pipeline.context import (
    PipelineContext,
)

from tools.project_sync.pipeline.executor import (
    PipelineExecutor,
)

from tools.project_sync.pipeline.registry import (
    PipelineRegistry,
)

from tools.project_sync.pipeline.report import (
    PipelineReport,
)


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


PROJECT_SYNC_ROOT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
)

REPORT_DIR = (
    PROJECT_SYNC_ROOT
    / "reports"
)

REPORT_PATH = (
    REPORT_DIR
    / "pipeline_report.json"
)

CONTEXT_PATH = (
    PROJECT_SYNC_ROOT
    / "context"
    / "pipeline_context.json"
)


def create_pipeline_context() -> PipelineContext:
    """
    Create the canonical shared PipelineContext.
    """

    CONTEXT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    context = PipelineContext(
        project_path=str(
            PROJECT_ROOT
        )
    )

    context.metadata.update(
        {
            "project":
                "BybitScanner",

            "created":
                datetime.now().isoformat(),

            "project_root":
                str(PROJECT_ROOT),
        }
    )

    persist_context(
        context
    )

    return context


def persist_context(
    context: PipelineContext,
) -> None:
    """
    Persist the canonical PipelineContext artifact.
    """

    CONTEXT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    CONTEXT_PATH.write_text(
        json.dumps(
            context.to_dict(),
            indent=4,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )


def build_registry() -> PipelineRegistry:
    """
    Build the canonical PipelineRegistry.
    """

    registry = PipelineRegistry()

    registry.register_default_stages()

    return registry


def build_executor(
    registry: PipelineRegistry,
) -> PipelineExecutor:
    """
    Create the canonical PipelineExecutor
    from the registered Pipeline stages.
    """

    stages = []

    for stage_name in (
        registry.list_stages()
    ):

        stage = registry.create(
            stage_name
        )

        if stage is not None:
            stages.append(
                stage
            )

    return PipelineExecutor(
        stages
    )


def run_pipeline() -> PipelineReport:
    """
    Execute the canonical Project Sync Pipeline.

    Returns:
        PipelineReport:
            The canonical final Pipeline Report model.

    The report remains a PipelineReport object
    throughout the execution flow.

    Serialization to dictionary/JSON occurs only
    at the persistence boundary.
    """

    context = (
        create_pipeline_context()
    )

    registry = (
        build_registry()
    )

    executor = (
        build_executor(
            registry
        )
    )

    results = (
        executor.execute(
            context
        )
    )

    persist_context(
        context
    )

    normalized_results = [
        result.to_dict()
        for result in results
    ]

    report = PipelineReport.from_results(
        normalized_results,
        version="3.3",
    )

    report.write(
        REPORT_PATH
    )

    return report


if __name__ == "__main__":

    report = run_pipeline()

    print(
        "PROJECT SYNC PIPELINE ENGINE"
    )

    print(
        f"Status: {report.status}"
    )

    print(
        f"Stages: {report.stages}"
    )

    if report.errors:

        print(
            "Errors:"
        )

        for error in report.errors:

            print(
                json.dumps(
                    error,
                    ensure_ascii=False,
                )
            )