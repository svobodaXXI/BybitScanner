"""
Project Sync Framework

Pipeline Executor

Executes pipeline stages and collects results.

Responsibility:
    Provide the single canonical execution contour
    for registered PipelineStage instances.

The Executor:
    - executes one stage;
    - executes all enabled stages;
    - converts raw stage output into PipelineResult;
    - records execution errors in PipelineContext.

It does not:
    - define pipeline composition;
    - register stages;
    - implement business logic;
    - make migration decisions;
    - modify documents directly.
"""

from __future__ import annotations

from .context import PipelineContext
from .result import PipelineResult
from .stage import PipelineStage


class PipelineExecutor:
    """
    Canonical executor of PipelineStage instances.
    """

    def __init__(
        self,
        stages: list[PipelineStage],
    ):
        self.stages = stages

    def execute_stage(
        self,
        stage: PipelineStage,
        context: PipelineContext,
    ) -> PipelineResult:
        """
        Execute one PipelineStage.

        This is the single canonical execution method
        for individual pipeline stages.
        """

        if stage is None:

            return PipelineResult.failure_result(
                stage="unknown",
                error="Pipeline stage is None.",
            )

        if not stage.enabled:

            return PipelineResult.success_result(
                stage=stage.name,
                message=(
                    "Pipeline stage is disabled."
                ),
                metadata={
                    "enabled": False,
                    "skipped": True,
                },
            )

        try:

            result = stage.execute(
                context
            )

            if isinstance(
                result,
                PipelineResult,
            ):

                return result

            return PipelineResult.success_result(
                stage=stage.name,
                data=result,
            )

        except Exception as error:

            error_message = str(
                error
            )

            context.add_error(
                error_message
            )

            return PipelineResult.failure_result(
                stage=stage.name,
                error=error_message,
            )

    def execute(
        self,
        context: PipelineContext,
    ) -> list[PipelineResult]:
        """
        Execute all registered and enabled stages
        in their canonical registry order.
        """

        results = []

        for stage in self.stages:

            result = self.execute_stage(
                stage,
                context,
            )

            results.append(
                result
            )

        return results