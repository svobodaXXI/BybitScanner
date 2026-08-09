"""
BybitScanner Project Sync Framework

Migration Executor

Responsibility:
    Execute explicitly approved document migrations.

Flow:

    migration_approval.json
            ↓
    Current Migration Decision
            ↓
    Approval Consistency Validation
            ↓
    Document Update Engine
            ↓
    Migration Execution Report

Post Migration Validation is performed
by the dedicated validation component.

This module:
    - validates explicit approval;
    - validates approval against the current migration decision;
    - validates cryptographic decision binding;
    - rejects stale or mismatched approval;
    - executes the approved document update workflow;
    - distinguishes real execution from NO_UPDATES;
    - preserves WAITING_APPROVAL state;
    - collects execution results;
    - creates a machine-readable execution report.

It does not:
    - bypass Approval Control;
    - modify documents directly;
    - generate document content;
    - change migration rules;
    - perform post-migration validation itself.
"""


from pathlib import Path
from datetime import datetime
import hashlib
import json
import sys


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


REPORT_PATH = (
    REPORT_DIR
    /
    "migration_execution_report.json"
)


APPROVAL_REPORT = (
    REPORT_DIR
    /
    "migration_approval.json"
)


DECISION_REPORT = (
    REPORT_DIR
    /
    "migration_decision.json"
)


DECISION_BINDING_FIELDS = (
    "documents",
    "actions",
    "updates",
    "migration_plan",
    "approval_required",
    "migration_required"
)


def normalize_updates(
    updates
) -> dict:
    """
    Normalize explicitly prepared updates.

    Supported forms:

        {
            "DOCUMENTS/example.md": "content"
        }

    or:

        {
            "DOCUMENTS/example.md": {
                "content": "content"
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


def calculate_decision_binding(
    decision: dict
) -> str:
    """
    Calculate deterministic SHA-256 binding
    for the canonical migration decision scope.

    The binding must match the binding created
    by Approval Controller.

    Any change to the migration scope,
    prepared updates, migration plan,
    approval requirement or migration
    requirement invalidates the approval.
    """

    binding = {}

    for field in DECISION_BINDING_FIELDS:

        if field == "documents":

            default = []

        elif field == "actions":

            default = []

        elif field == "updates":

            default = {}

        elif field == "migration_plan":

            default = []

        else:

            default = None

        value = decision.get(
            field,
            default
        )

        if field == "updates":

            value = normalize_updates(
                value
            )

        binding[field] = value

    canonical = json.dumps(
        binding,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":"
        )
    )

    return hashlib.sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest()


from tools.project_sync.migration.document_updater import (
    update_document,
)


class MigrationExecutor:
    """
    Execute approved migration workflow.
    """

    def __init__(
        self,
        migration_report: dict,
        migration_decision: dict | None = None
    ):

        self.report = (
            migration_report
            if isinstance(
                migration_report,
                dict
            )
            else {}
        )

        self.decision = (
            migration_decision
            if isinstance(
                migration_decision,
                dict
            )
            else {}
        )

        self.result = {

            "component":
                "migration_executor",

            "version":
                "2.5",

            "status":
                "INITIALIZED",

            "migration_required":
                True,

            "executed_at":
                None,

            "documents":
                [],

            "actions":
                [],

            "updates":
                {},

            "backups":
                [],

            "updated":
                [],

            "errors":
                []
        }

    def validate_approval(
        self
    ) -> bool:
        """
        Validate explicit approval.

        Approval is accepted only when the
        Approval Controller has explicitly
        authorized the migration.
        """

        return (

            self.report.get(
                "status"
            )
            ==
            "APPROVED"

            and

            self.report.get(
                "decision"
            )
            ==
            "APPROVED"

            and

            self.report.get(
                "approval"
            )
            is True

            and

            self.report.get(
                "explicit_approval"
            )
            is True

            and

            self.report.get(
                "automatic_approval",
                False
            )
            is False

            and

            self.report.get(
                "migration_required"
            )
            is True

        )

    def validate_decision(
        self
    ) -> bool:
        """
        Validate the current migration decision.

        The current decision must remain a valid
        WAITING_APPROVAL / PENDING decision.

        The executor never treats an APPROVED value
        inside migration_decision.json as valid.
        Approval exists only in migration_approval.json.
        """

        if not self.decision:

            self.result["errors"].append(
                "migration_decision_missing"
            )

            return False

        if self.decision.get(
            "plan_valid"
        ) is not True:

            self.result["errors"].append(
                "migration_decision_invalid"
            )

            return False

        if self.decision.get(
            "migration_required"
        ) is not True:

            self.result["errors"].append(
                "migration_required_not_true"
            )

            return False

        if self.decision.get(
            "status"
        ) != "WAITING_APPROVAL":

            self.result["errors"].append(
                "migration_decision_not_waiting_approval"
            )

            return False

        if self.decision.get(
            "decision"
        ) != "PENDING":

            self.result["errors"].append(
                "migration_decision_not_pending"
            )

            return False

        if self.decision.get(
            "approval_required"
        ) is not True:

            self.result["errors"].append(
                "approval_required_not_true"
            )

            return False

        return True

    def validate_approval_consistency(
        self
    ) -> bool:
        """
        Verify that the approval artifact matches
        the current migration decision.

        Both:

        1. cryptographic decision binding;
        2. explicit migration-scope fields

        are validated.

        This prevents stale approval reuse.
        """

        approval_binding = self.report.get(
            "decision_binding"
        )

        current_binding = calculate_decision_binding(
            self.decision
        )

        if (
            not isinstance(
                approval_binding,
                str
            )
            or
            approval_binding != current_binding
        ):

            self.result["errors"].append(
                "approval_decision_binding_mismatch"
            )

            return False

        fields = (
            "documents",
            "actions",
            "updates",
            "migration_plan",
            "approval_required",
            "migration_required"
        )

        for field in fields:

            if field == "updates":

                approval_value = normalize_updates(
                    self.report.get(
                        field,
                        {}
                    )
                )

                decision_value = normalize_updates(
                    self.decision.get(
                        field,
                        {}
                    )
                )

            else:

                if field in {
                    "documents",
                    "actions",
                    "migration_plan"
                }:

                    default = []

                else:

                    default = None

                approval_value = self.report.get(
                    field,
                    default
                )

                decision_value = self.decision.get(
                    field,
                    default
                )

            if approval_value != decision_value:

                self.result["errors"].append(
                    f"approval_mismatch:{field}"
                )

                return False

        return True

    def validate_report_structure(
        self
    ) -> bool:
        """
        Validate basic approval report structure.
        """

        documents = self.report.get(
            "documents",
            []
        )

        actions = self.report.get(
            "actions",
            []
        )

        updates = self.report.get(
            "updates",
            {}
        )

        migration_plan = self.report.get(
            "migration_plan",
            []
        )

        if not isinstance(
            documents,
            list
        ):

            self.result["errors"].append(
                "invalid_documents_format"
            )

            return False

        if not isinstance(
            actions,
            list
        ):

            self.result["errors"].append(
                "invalid_actions_format"
            )

            return False

        if not isinstance(
            updates,
            dict
        ):

            self.result["errors"].append(
                "invalid_updates_format"
            )

            return False

        if not isinstance(
            migration_plan,
            list
        ):

            self.result["errors"].append(
                "invalid_migration_plan_format"
            )

            return False

        if not documents:

            self.result["errors"].append(
                "migration_documents_empty"
            )

            return False

        if not migration_plan:

            self.result["errors"].append(
                "migration_plan_empty"
            )

            return False

        return True

    def execute(
        self
    ):
        """
        Execute approved migration.

        A migration that has not received explicit
        approval remains in WAITING_APPROVAL.

        A stale or mismatched approval is rejected
        and never reaches the Document Update Engine.

        An explicitly approved migration with no
        prepared document updates is reported as
        NO_UPDATES.

        NO_UPDATES is not equivalent to
        NOT_REQUIRED.
        """

        if not self.validate_approval():

            self.result["status"] = (
                "WAITING_APPROVAL"
            )

            self.result["migration_required"] = (
                True
            )

            self.result["documents"] = (
                self.report.get(
                    "documents",
                    []
                )
                if isinstance(
                    self.report.get(
                        "documents",
                        []
                    ),
                    list
                )
                else []
            )

            self.result["actions"] = (
                self.report.get(
                    "actions",
                    []
                )
                if isinstance(
                    self.report.get(
                        "actions",
                        []
                    ),
                    list
                )
                else []
            )

            self.result["errors"].append(
                "explicit_approval_required"
            )

            return self.result

        if not self.validate_decision():

            self.result["status"] = (
                "REJECTED"
            )

            self.result["migration_required"] = (
                True
            )

            return self.result

        if not self.validate_approval_consistency():

            self.result["status"] = (
                "REJECTED"
            )

            self.result["migration_required"] = (
                True
            )

            return self.result

        if not self.validate_report_structure():

            self.result["status"] = (
                "FAILED"
            )

            self.result["migration_required"] = (
                True
            )

            return self.result

        self.result["documents"] = (
            self.report.get(
                "documents",
                []
            )
        )

        self.result["actions"] = (
            self.report.get(
                "actions",
                []
            )
        )

        self.result["updates"] = (
            self.report.get(
                "updates",
                {}
            )
        )

        update_result = update_document(
            self.report
        )

        self.result["updates"] = (
            update_result.get(
                "updates",
                self.result["updates"]
            )
        )

        self.result["backups"] = (
            update_result.get(
                "backups",
                []
            )
        )

        self.result["updated"] = (
            update_result.get(
                "updated",
                []
            )
        )

        self.result["errors"] = (
            update_result.get(
                "errors",
                []
            )
        )

        update_status = update_result.get(
            "status"
        )

        if update_status == "NO_UPDATES":

            self.result["status"] = (
                "NO_UPDATES"
            )

            self.result["migration_required"] = (
                True
            )

            self.result["executed_at"] = (
                datetime.now().isoformat()
            )

            return self.result

        if update_status == "UPDATED":

            self.result["status"] = (
                "EXECUTED"
            )

            self.result["migration_required"] = (
                True
            )

            self.result["executed_at"] = (
                datetime.now().isoformat()
            )

            return self.result

        self.result["status"] = (
            update_status
            or
            "FAILED"
        )

        self.result["migration_required"] = (
            True
        )

        self.result["executed_at"] = (
            datetime.now().isoformat()
        )

        return self.result


def save_report(
    result: dict
):
    """
    Save machine-readable execution report.
    """

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    REPORT_PATH.write_text(

        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        ),

        encoding="utf-8"
    )


def load_migration_report(
    path: Path
) -> dict:
    """
    Load migration approval artifact safely.
    """

    if not path.exists():

        return {}

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return {}

    return (
        data
        if isinstance(
            data,
            dict
        )
        else {}
    )


if __name__ == "__main__":

    approval_argument = (
        sys.argv[1]
        if len(sys.argv) > 1
        else None
    )

    decision_argument = (
        sys.argv[2]
        if len(sys.argv) > 2
        else None
    )

    approval_path = (
        Path(
            approval_argument
        )
        if approval_argument
        else APPROVAL_REPORT
    )

    decision_path = (
        Path(
            decision_argument
        )
        if decision_argument
        else DECISION_REPORT
    )

    migration_report = load_migration_report(
        approval_path
    )

    migration_decision = load_migration_report(
        decision_path
    )

    executor = MigrationExecutor(
        migration_report,
        migration_decision
    )

    result = executor.execute()

    save_report(
        result
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )