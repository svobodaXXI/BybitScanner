"""
BybitScanner Project Sync Framework

Compatibility Runner

Version:
3.1

Responsibility:
    Compatibility entry point for the Project Sync Pipeline.

Canonical implementation:
    tools.project_sync.pipeline.project_sync_runner

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

Important:
    This module does not define Pipeline stages,
    Pipeline registry, Pipeline executor,
    or Pipeline report generation.

    The canonical implementation is located in:
        tools.project_sync.pipeline.project_sync_runner

    This compatibility runner only:
        - invokes the canonical pipeline;
        - converts PipelineReport to its
          machine-readable dictionary representation
          for console compatibility output.
"""


from .pipeline.project_sync_runner import (
    run_pipeline,
)


def main():
    """
    Execute the canonical Project Sync Pipeline.
    """

    report = run_pipeline()

    report_data = report.to_dict()

    print(
        "PROJECT SYNC PIPELINE ENGINE"
    )

    print(
        f"Status: {report_data['status']}"
    )

    print(
        f"Stages: {report_data['stages']}"
    )


if __name__ == "__main__":

    main()
