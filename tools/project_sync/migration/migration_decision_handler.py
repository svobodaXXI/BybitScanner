"""
BybitScanner Project Sync Framework

Migration Decision Handler

Responsibility:
    - read migration plans;
    - validate migration readiness;
    - determine approval state;
    - create migration decision artifact.

Input:
    migration_plan.json

Output:
    migration_decision.json

This module:
    - validates migration plan structure;
    - distinguishes "no migration required"
      from an invalid migration plan;
    - determines whether explicit approval is required;
    - preserves migration actions and prepared updates;
    - validates prepared update targets against
      the migration scope;
    - creates a controlled decision artifact.

It does not:
    - modify documents;
    - execute migration;
    - grant approval automatically;
    - bypass Approval Control.
"""


from pathlib import Path
import json
import sys
from datetime import datetime
from typing import Any


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


REPORT_DIR = (
    PROJECT_ROOT
    /
    "tools"
    /
    "project_sync"
    /
    "reports"
)


MIGRATION_PLAN = (
    REPORT_DIR
    /
    "migration_plan.json"
)


DECISION_REPORT = (
    REPORT_DIR
    /
    "migration_decision.json"
)


class MigrationDecisionHandler:
    """
    Handles controlled migration decisions.
    """

    def __init__(
        self,
        plan_path: str | None = None
    ):
        self.plan_path = (
            Path(plan_path)
            if plan_path
            else MIGRATION_PLAN
        )

    def load_plan(
        self
    ) -> dict[str, Any]:
        """
        Load migration plan safely.
        """

        if not self.plan_path.exists():

            return {
                "status":
                    "ERROR",

                "error":
                    "Migration plan not found",

                "source":
                    str(
                        self.plan_path
                    )
            }

        try:

            data = json.loads(
                self.plan_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            json.JSONDecodeError,
            OSError
        ) as error:

            return {
                "status":
                    "ERROR",

                "error":
                    str(error),

                "source":
                    str(
                        self.plan_path
                    )
            }

        if not isinstance(
            data,
            dict
        ):

            return {
                "status":
                    "ERROR",

                "error":
                    "Migration plan must be a JSON object",

                "source":
                    str(
                        self.plan_path
                    )
            }

        return data

    def normalize_updates(
        self,
        updates
    ) -> dict:
        """
        Normalize explicitly prepared document updates.

        Supported forms:

            {
                "DOCUMENTS/example.md":
                    "content"
            }

        or:

            {
                "DOCUMENTS/example.md":
                    {
                        "content":
                            "content"
                    }
            }
        """

        if not isinstance(
            updates,
            dict
        ):

            return {}

        normalized = {}

        for document, update in updates.items():

            if not isinstance(
                document,
                str
            ) or not document:

                continue

            if isinstance(
                update,
                str
            ):

                normalized[document] = {
                    "content":
                        update
                }

                continue

            if isinstance(
                update,
                dict
            ):

                content = update.get(
                    "content"
                )

                if isinstance(
                    content,
                    str
                ):

                    normalized[document] = {
                        "content":
                            content
                    }

        return normalized

    def validate_plan_structure(
        self,
        plan: dict[str, Any]
    ) -> bool:
        """
        Validate basic migration plan structure.

        A plan with migration_required=False and
        an empty migration_plan is valid and means
        that no migration is required.
        """

        if not plan:

            return False

        if plan.get(
            "status"
        ) != "READY":

            return False

        migration_required = plan.get(
            "migration_required"
        )

        if not isinstance(
            migration_required,
            bool
        ):

            return False

        migration_plan = plan.get(
            "migration_plan",
            []
        )

        if not isinstance(
            migration_plan,
            list
        ):

            return False

        documents = plan.get(
            "documents",
            []
        )

        if not isinstance(
            documents,
            list
        ):

            return False

        actions = plan.get(
            "actions",
            []
        )

        if not isinstance(
            actions,
            list
        ):

            return False

        updates = plan.get(
            "updates",
            {}
        )

        if not isinstance(
            updates,
            dict
        ):

            return False

        return True

    def validate_update_scope(
        self,
        plan: dict[str, Any]
    ) -> bool:
        """
        Validate that every prepared update targets
        a document explicitly included in the
        migration scope.
        """

        documents = plan.get(
            "documents",
            []
        )

        updates = self.normalize_updates(
            plan.get(
                "updates",
                {}
            )
        )

        if not isinstance(
            documents,
            list
        ):

            return False

        approved_documents = set(
            document
            for document in documents
            if isinstance(
                document,
                str
            )
            and document
        )

        return all(
            document in approved_documents
            for document in updates
        )

    def validate_required_migration(
        self,
        plan: dict[str, Any]
    ) -> bool:
        """
        Validate a plan that actually requires migration.

        When migration_required=True, the plan must contain
        at least one migration item and valid document
        targets.
        """

        migration_plan = plan.get(
            "migration_plan",
            []
        )

        if not migration_plan:

            return False

        documents = plan.get(
            "documents",
            []
        )

        if not documents:

            return False

        for item in migration_plan:

            if not isinstance(
                item,
                dict
            ):

                return False

            document = item.get(
                "document"
            )

            if not isinstance(
                document,
                str
            ) or not document:

                return False

            if document not in documents:

                return False

            item_actions = item.get(
                "actions",
                []
            )

            if not isinstance(
                item_actions,
                list
            ):

                return False

            approval_required = item.get(
                "approval_required",
                True
            )

            if not isinstance(
                approval_required,
                bool
            ):

                return False

        if not self.validate_update_scope(
            plan
        ):

            return False

        return True

    def validate_plan(
        self,
        plan: dict[str, Any]
    ) -> bool:
        """
        Validate complete migration plan.

        Two valid states exist:

            1. migration_required=False
               migration_plan=[]
               documents=[]
               updates={}

            2. migration_required=True
               migration_plan contains valid items.
        """

        if not self.validate_plan_structure(
            plan
        ):

            return False

        migration_required = plan.get(
            "migration_required",
            False
        )

        migration_plan = plan.get(
            "migration_plan",
            []
        )

        documents = plan.get(
            "documents",
            []
        )

        updates = self.normalize_updates(
            plan.get(
                "updates",
                {}
            )
        )

        if not migration_required:

            return (
                migration_plan == []
                and
                documents == []
                and
                updates == {}
            )

        return self.validate_required_migration(
            plan
        )

    def collect_documents(
        self,
        migration_plan: list
    ) -> list:

        documents = []

        for item in migration_plan:

            if not isinstance(
                item,
                dict
            ):

                continue

            document = item.get(
                "document"
            )

            if (
                isinstance(
                    document,
                    str
                )
                and document
            ):

                documents.append(
                    document
                )

        return list(
            dict.fromkeys(
                documents
            )
        )

    def collect_actions(
        self,
        migration_plan: list
    ) -> list:

        actions = []

        for item in migration_plan:

            if not isinstance(
                item,
                dict
            ):

                continue

            item_actions = item.get(
                "actions",
                []
            )

            if not isinstance(
                item_actions,
                list
            ):

                continue

            actions.extend(
                action
                for action in item_actions
                if isinstance(
                    action,
                    str
                )
                and action
            )

        return list(
            dict.fromkeys(
                actions
            )
        )

    def collect_updates(
        self,
        plan: dict[str, Any]
    ) -> dict:
        """
        Preserve explicitly prepared updates.
        """

        return self.normalize_updates(
            plan.get(
                "updates",
                {}
            )
        )

    def create_not_required_decision(
        self,
        plan: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Create a valid no-migration decision.

        This is not a rejection.
        It is a terminal non-migration state.
        """

        return {

            "component":
                "migration_decision_handler",

            "version":
                "2.3",

            "status":
                "NOT_REQUIRED",

            "decision":
                "NOT_REQUIRED",

            "approved_at":
                None,

            "documents":
                [],

            "actions":
                [],

            "updates":
                {},

            "migration_plan":
                [],

            "approval_required":
                False,

            "source":
                "migration_plan",

            "created_at":
                datetime.now().isoformat(),

            "plan_valid":
                True,

            "migration_required":
                False,

            "automatic_approval":
                False
        }

    def create_rejected_decision(
        self,
        plan: dict[str, Any],
        error: str | None = None
    ) -> dict[str, Any]:
        """
        Create controlled rejection artifact.
        """

        decision = {

            "component":
                "migration_decision_handler",

            "version":
                "2.3",

            "status":
                "REJECTED",

            "decision":
                "REJECTED",

            "approved_at":
                None,

            "documents":
                [],

            "actions":
                [],

            "updates":
                {},

            "migration_plan":
                [],

            "approval_required":
                True,

            "source":
                "migration_plan",

            "created_at":
                datetime.now().isoformat(),

            "plan_valid":
                False,

            "migration_required":
                plan.get(
                    "migration_required",
                    False
                )
                if isinstance(
                    plan,
                    dict
                )
                else False,

            "automatic_approval":
                False
        }

        if error:

            decision["error"] = error

        return decision

    def create_pending_decision(
        self,
        plan: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Create explicit approval-gate decision.

        No approval is granted here.
        """

        migration_plan = plan.get(
            "migration_plan",
            []
        )

        documents = self.collect_documents(
            migration_plan
        )

        actions = self.collect_actions(
            migration_plan
        )

        updates = self.collect_updates(
            plan
        )

        return {

            "component":
                "migration_decision_handler",

            "version":
                "2.3",

            "status":
                "WAITING_APPROVAL",

            "decision":
                "PENDING",

            "approved_at":
                None,

            "documents":
                documents,

            "actions":
                actions,

            "updates":
                updates,

            "migration_plan":
                migration_plan,

            "approval_required":
                True,

            "source":
                "migration_plan",

            "created_at":
                datetime.now().isoformat(),

            "plan_valid":
                True,

            "migration_required":
                True,

            "automatic_approval":
                False
        }

    def analyze(
        self
    ) -> dict[str, Any]:
        """
        Create migration decision.

        Decision flow:

            no migration required
                ->
            NOT_REQUIRED

            valid migration required
                ->
            WAITING_APPROVAL / PENDING

            invalid migration plan
                ->
            REJECTED

        No automatic approval is granted.
        """

        plan = self.load_plan()

        if plan.get(
            "status"
        ) == "ERROR":

            decision = self.create_rejected_decision(
                plan,
                plan.get(
                    "error",
                    "Invalid migration plan"
                )
            )

            self.save_decision(
                decision
            )

            return decision

        if not self.validate_plan_structure(
            plan
        ):

            decision = self.create_rejected_decision(
                plan,
                "Invalid migration plan structure"
            )

            self.save_decision(
                decision
            )

            return decision

        migration_required = plan.get(
            "migration_required",
            False
        )

        if not migration_required:

            if self.validate_plan(
                plan
            ):

                decision = (
                    self.create_not_required_decision(
                        plan
                    )
                )

            else:

                decision = self.create_rejected_decision(
                    plan,
                    "No-migration plan contains unexpected migration data"
                )

            self.save_decision(
                decision
            )

            return decision

        if not self.validate_plan(
            plan
        ):

            decision = self.create_rejected_decision(
                plan,
                "Migration plan validation failed"
            )

            self.save_decision(
                decision
            )

            return decision

        decision = self.create_pending_decision(
            plan
        )

        self.save_decision(
            decision
        )

        return decision

    def save_decision(
        self,
        decision: dict[str, Any]
    ):
        """
        Save migration decision artifact.
        """

        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        DECISION_REPORT.write_text(
            json.dumps(
                decision,
                indent=4,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )


def create_decision(
    plan_path: str | None = None
):
    """
    Create migration decision artifact.
    """

    handler = MigrationDecisionHandler(
        plan_path
    )

    return handler.analyze()


if __name__ == "__main__":

    plan_argument = (
        sys.argv[1]
        if len(sys.argv) > 1
        else None
    )

    result = create_decision(
        plan_argument
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )