"""
BybitScanner Project Sync Framework

Pipeline Stage Adapter

Provides compatibility between existing Project Sync
modules and the canonical PipelineStage execution model.

Responsibility:
    Adapt specialized Project Sync modules
    to PipelineStage.

This module:
    - adapts specialized module execution to PipelineStage;
    - converts specialized module execution into PipelineResult;
    - preserves PipelineContext;
    - supports legacy module entry points without creating
      an alternative pipeline execution contour.

It does not:
    - execute PipelineStage directly;
    - perform orchestration;
    - perform business analysis;
    - make migration decisions;
    - approve migration;
    - modify documents directly.

Canonical execution owner:
    PipelineExecutor
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Callable

from .context import PipelineContext
from .result import PipelineResult
from .stage import PipelineStage


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


def execute_module(
    module: str,
    context: PipelineContext,
    artifact: Path | None = None,
) -> PipelineResult:
    """
    Execute an existing Project Sync module as an
    adapted Pipeline operation.

    The specialized module remains responsible for
    its own business logic.

    PipelineExecutor remains the sole owner of
    PipelineStage orchestration and execution.
    """

    command = [
        sys.executable,
        "-m",
        module,
    ]

    if artifact is not None:

        command.append(
            str(artifact)
        )

    try:

        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    except OSError as error:

        error_message = str(
            error
        )

        context.add_error(
            error_message
        )

        return PipelineResult.failure_result(
            stage=module,
            error=error_message,
            metadata={
                "module": module,
                "return_code": None,
            },
        )

    output = (
        result.stdout.strip()
    )

    errors = []

    stderr = (
        result.stderr.strip()
    )

    if stderr:

        errors.append(
            stderr
        )

    if result.returncode != 0:

        error = (
            stderr
            or
            f"Module '{module}' "
            f"returned exit code "
            f"{result.returncode}"
        )

        context.add_error(
            error
        )

        return PipelineResult.failure_result(
            stage=module,
            error=error,
            message=output,
            metadata={
                "module": module,
                "return_code":
                    result.returncode,
            },
        )

    return PipelineResult.success_result(
        stage=module,
        data={
            "output": output,
            "errors": errors,
        },
        metadata={
            "module": module,
            "return_code":
                result.returncode,
        },
    )


def create_module_stage(
    name: str,
    module: str,
    description: str = "",
    artifact_resolver: Callable[
        [PipelineContext],
        Path | None
    ] | None = None,
) -> type[PipelineStage]:
    """
    Create a PipelineStage class for an existing
    Project Sync module.

    The generated class is registry-compatible and
    remains inside the canonical Pipeline execution
    contour.

    PipelineExecutor executes the resulting stage.
    This adapter only translates the specialized
    module into a PipelineStage-compatible handler.
    """

    class ModuleStage(
        PipelineStage
    ):
        """
        Registry-compatible adapter for one
        specialized Project Sync module.
        """

        def __init__(self):

            super().__init__(
                name=name,
                handler=self.run,
                description=description,
                metadata={
                    "adapter": (
                        "module_stage_adapter"
                    ),
                    "module": module,
                },
            )

        def run(
            self,
            context: PipelineContext | None = None,
        ) -> PipelineResult:

            if context is None:

                context = PipelineContext(
                    project_path=str(
                        PROJECT_ROOT
                    ),
                )

            artifact = None

            if artifact_resolver is not None:

                artifact = (
                    artifact_resolver(
                        context
                    )
                )

            result = execute_module(
                module=module,
                context=context,
                artifact=artifact,
            )

            context.add_artifact(
                name,
                result.to_dict(),
            )

            return result

    ModuleStage.__name__ = (
        f"{name.title().replace('_', '')}Stage"
    )

    ModuleStage.__qualname__ = (
        ModuleStage.__name__
    )

    return ModuleStage