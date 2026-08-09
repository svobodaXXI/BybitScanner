"""
BybitScanner Project Sync Framework

Migration Pipeline Stage

Provides registry-based migration stage execution.

Responsibility:
    Evaluate canonical migration state through the
    Project Sync Pipeline.

This stage:
    - reads the canonical migration plan;
    - reads the migration decision;
    - reads the migration approval;
    - determines the current migration state;
    - exposes migration state to PipelineContext;
    - reports pending approval state;
    - preserves Approval Control boundaries.

It does not:
    - approve migration;
    - modify documents;
    - execute migration;
    - bypass Approval Control;
    - generate migration content.
"""


from __future__ import annotations

from pathlib import Path
import json

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


MIGRATION_PLAN_REPORT = (
    REPORT_DIR
    / "migration_plan.json"
)


MIGRATION_DECISION_REPORT = (
    REPORT_DIR
    / "migration_decision.json"
)


MIGRATION_APPROVAL_REPORT = (
    REPORT_DIR
    / "migration_approval.json"
)


class MigrationStage(
    PipelineStage
):
    """
    Pipeline stage responsible for
    canonical migration state evaluation.
    """

    def __init__(self):

        super().__init__(
            name="migration",
            handler=self.run,
            description=(
                "Evaluate canonical migration state "
                "and approval readiness"
            ),
        )

        self.plan_path = (
            MIGRATION_PLAN_REPORT
        )

        self.decision_path = (
            MIGRATION_DECISION_REPORT
        )

        self.approval_path = (
            MIGRATION_APPROVAL_REPORT
        )

    def load_report(
        self,
        path: Path,
    ):
        """
        Load one JSON migration artifact safely.
        """

        if not path.exists():

            return None, (
                f"Migration artifact not found: "
                f"{path.name}"
            )

        try:

            report = json.loads(
                path.read_text(
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
                f"{path.name} must contain "
                "a JSON object"
            )

        return report, None

    def load_optional_report(
        self,
        path: Path,
    ):
        """
        Load an optional migration artifact.

        Missing optional artifacts are represented
        as an empty dictionary rather than as a
        Pipeline error.
        """

        if not path.exists():

            return {}

        try:

            report = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):

            return {}

        if not isinstance(
            report,
            dict,
        ):

            return {}

        return report

    def load_plan(
        self,
    ):
        """
        Load canonical migration plan.
        """

        return self.load_report(
            self.plan_path
        )

    def load_decision(
        self,
    ):
        """
        Load migration decision when available.
        """

        return self.load_optional_report(
            self.decision_path
        )

    def load_approval(
        self,
    ):
        """
        Load migration approval when available.
        """

        return self.load_optional_report(
            self.approval_path
        )

    @staticmethod
    def normalize_list(
        value,
    ) -> list:
        """
        Normalize an artifact list field.
        """

        if isinstance(
            value,
            list,
        ):

            return value

        return []

    def evaluate_status(
        self,
        plan: dict,
        decision: dict,
        approval: dict,
    ):
        """
        Determine canonical migration state.

        State precedence:

            1. Invalid plan
            2. NOT_REQUIRED
            3. APPROVED
            4. WAITING_APPROVAL
            5. PENDING_APPROVAL
            6. READY
        """

        migration_required = plan.get(
            "migration_required",
            False,
        )

        if not isinstance(
            migration_required,
            bool,
        ):

            migration_required = False

        plan_documents = self.normalize_list(
            plan.get(
                "documents",
                [],
            )
        )

        migration_plan = self.normalize_list(
            plan.get(
                "migration_plan",
                [],
            )
        )

        plan_approval_required = bool(
            plan.get(
                "approval_required",
                False,
            )
        )

        if not migration_required:

            return (
                "NOT_REQUIRED",
                False,
                False,
                plan_documents,
                migration_plan,
            )

        approval_status = approval.get(
            "status"
        )

        approval_value = approval.get(
            "approval",
            False,
        )

        explicit_approval = approval.get(
            "explicit_approval",
            False,
        )

        automatic_approval = approval.get(
            "automatic_approval",
            False,
        )

        if (
            approval_status == "APPROVED"
            and approval_value is True
            and explicit_approval is True
            and automatic_approval is False
        ):

            return (
                "APPROVED",
                True,
                True,
                plan_documents,
                migration_plan,
            )

        decision_status = decision.get(
            "status"
        )

        decision_value = decision.get(
            "decision"
        )

        if (
            decision_status
            == "WAITING_APPROVAL"
            and
            decision_value
            == "PENDING"
        ):

            return (
                "PENDING_APPROVAL",
                True,
                True,
                plan_documents,
                migration_plan,
            )

        if (
            decision_status
            == "NOT_REQUIRED"
        ):

            return (
                "NOT_REQUIRED",
                False,
                False,
                [],
                [],
            )

        if (
            approval_status
            == "WAITING_APPROVAL"
        ):

            return (
                "WAITING_APPROVAL",
                True,
                True,
                plan_documents,
                migration_plan,
            )

        if plan_approval_required:

            return (
                "PENDING_APPROVAL",
                True,
                True,
                plan_documents,
                migration_plan,
            )

        return (
            "READY",
            True,
            False,
            plan_documents,
            migration_plan,
        )

    def run(
        self,
        context=None,
    ):
        """
        Evaluate canonical migration state.

        This stage is read-only.

        It never approves or executes migration.
        """

        plan, error = self.load_plan()

        if error is not None:

            result = {

                "stage":
                    self.name,

                "status":
                    "ERROR",

                "migration_required":
                    False,

                "approval_required":
                    False,

                "documents":
                    [],

                "actions":
                    [],

                "migration_plan":
                    [],

                "source":
                    "migration_control_chain",

                "error":
                    error,

            }

            if context is not None:

                context.add_artifact(
                    "migration",
                    result,
                )

                context.add_error(
                    error
                )

            return result

        decision = (
            self.load_decision()
        )

        approval = (
            self.load_approval()
        )

        (
            status,
            migration_required,
            approval_required,
            documents,
            migration_plan,
        ) = self.evaluate_status(
            plan,
            decision,
            approval,
        )

        actions = self.normalize_list(
            plan.get(
                "actions",
                [],
            )
        )

        updates = plan.get(
            "updates",
            {},
        )

        if not isinstance(
            updates,
            dict,
        ):

            updates = {}

        result = {

            "stage":
                self.name,

            "status":
                status,

            "migration_required":
                migration_required,

            "approval_required":
                approval_required,

            "documents":
                documents,

            "actions":
                actions,

            "migration_plan":
                migration_plan,

            "updates":
                updates,

            "updates_count":
                len(updates),

            "source":
                "migration_control_chain",

            "artifacts":
                {
                    "migration_plan":
                        str(
                            self.plan_path
                        ),

                    "migration_decision":
                        str(
                            self.decision_path
                        ),

                    "migration_approval":
                        str(
                            self.approval_path
                        ),
                },

        }

        if context is not None:

            context.add_artifact(
                "migration",
                result,
            )

            context.set(
                "migration_status",
                status,
            )

            context.set(
                "migration_required",
                migration_required,
            )

            context.set(
                "migration_approval_required",
                approval_required,
            )

            context.set(
                "migration_documents",
                documents,
            )

            context.set(
                "migration_plan",
                migration_plan,
            )

        return result