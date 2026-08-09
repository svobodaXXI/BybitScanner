"""
BybitScanner Project Sync Framework

Post Migration Validation Pipeline Stage

Responsibility:
    Execute the canonical Post Migration Validator
    as the final stage of the Project Sync Pipeline.

This stage:
    - executes the existing post-migration validator;
    - reads the canonical validation report;
    - exposes validation state to PipelineContext;
    - preserves NO_UPDATES as a valid terminal state;
    - reports validation errors through the Pipeline.

It does not:
    - approve migration;
    - execute migration itself;
    - modify project documents directly;
    - bypass Migration Control.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from .stage import PipelineStage


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)

REPORT_DIR = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
)

VALIDATION_REPORT = (
    REPORT_DIR
    / "post_migration_validation_report.json"
)

VALIDATOR_MODULE = (
    "tools.project_sync.migration."
    "post_migration_validator"
)


class PostMigrationValidationStage(
    PipelineStage
):
    """
    Final Pipeline stage responsible for
    post-migration validation.
    """

    def __init__(self):
        super().__init__(
            name="post_migration_validation",
            handler=self.run,
            description=(
                "Execute canonical post-migration "
                "validation and expose its result."
            ),
        )

        self.report_path = (
            VALIDATION_REPORT
        )

    def load_report(self):
        """
        Load the canonical post-migration
        validation report.
        """

        if not self.report_path.exists():

            return None, (
                "Post-migration validation report "
                "not found."
            )

        try:

            report = json.loads(
                self.report_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:

            return None, str(error)

        if not isinstance(
            report,
            dict,
        ):

            return None, (
                "Post-migration validation report "
                "must contain a JSON object."
            )

        return report, None

    def execute_validator(self):
        """
        Execute the canonical
        Post Migration Validator.
        """

        try:

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    VALIDATOR_MODULE,
                ],
                cwd=str(
                    PROJECT_ROOT
                ),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        except OSError as error:

            return {
                "return_code": None,
                "stdout": "",
                "stderr": str(error),
            }

        return {
            "return_code":
                completed.returncode,
            "stdout":
                completed.stdout,
            "stderr":
                completed.stderr,
        }

    def run(
        self,
        context=None,
    ):
        """
        Execute post-migration validation.

        The validator remains the canonical owner
        of post-migration validation logic.

        This Pipeline stage only executes the validator,
        reads its canonical artifact, and exposes the
        result to PipelineContext.
        """

        execution = (
            self.execute_validator()
        )

        if execution["return_code"] is None:

            result = {
                "stage":
                    self.name,

                "status":
                    "ERROR",

                "migration_required":
                    True,

                "documents":
                    [],

                "checks":
                    {},

                "errors":
                    [
                        "post_migration_validator_execution_failed"
                    ],

                "return_code":
                    None,

                "artifact":
                    str(
                        self.report_path
                    ),
            }

            if execution["stderr"]:

                result["validator_error"] = (
                    execution["stderr"]
                )

            if context is not None:

                context.add_artifact(
                    "post_migration_validation",
                    result,
                )

                for error in result["errors"]:

                    context.add_error(
                        str(error)
                    )

            return result

        if execution["return_code"] != 0:

            errors = [
                "post_migration_validator_returned_nonzero"
            ]

            if execution["stderr"]:

                errors.append(
                    execution["stderr"].strip()
                )

            result = {
                "stage":
                    self.name,

                "status":
                    "ERROR",

                "migration_required":
                    True,

                "documents":
                    [],

                "checks":
                    {},

                "errors":
                    errors,

                "return_code":
                    execution["return_code"],

                "artifact":
                    str(
                        self.report_path
                    ),
            }

            if context is not None:

                context.add_artifact(
                    "post_migration_validation",
                    result,
                )

                for error in result["errors"]:

                    context.add_error(
                        str(error)
                    )

            return result

        report, report_error = (
            self.load_report()
        )

        if report_error is not None:

            result = {
                "stage":
                    self.name,

                "status":
                    "ERROR",

                "migration_required":
                    True,

                "documents":
                    [],

                "checks":
                    {},

                "errors":
                    [report_error],

                "return_code":
                    execution["return_code"],

                "artifact":
                    str(
                        self.report_path
                    ),
            }

            if context is not None:

                context.add_artifact(
                    "post_migration_validation",
                    result,
                )

                context.add_error(
                    report_error
                )

            return result

        errors = report.get(
            "errors",
            [],
        )

        if not isinstance(
            errors,
            list,
        ):

            errors = [
                str(errors)
            ]

        status = report.get(
            "status",
            "UNKNOWN",
        )

        result = {
            "stage":
                self.name,

            "status":
                status,

            "migration_required":
                report.get(
                    "migration_required"
                ),

            "documents":
                report.get(
                    "documents",
                    [],
                ),

            "checks":
                report.get(
                    "checks",
                    {},
                ),

            "errors":
                errors,

            "return_code":
                execution["return_code"],

            "artifact":
                str(
                    self.report_path
                ),
        }

        if context is not None:

            context.add_artifact(
                "post_migration_validation",
                result,
            )

            context.set(
                "post_migration_validation_status",
                status,
            )

            context.set(
                "post_migration_validation_report",
                result,
            )

            for error in errors:

                context.add_error(
                    str(error)
                )

        return result
