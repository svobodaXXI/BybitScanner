"""
BybitScanner Project Sync Framework

State Synchronization Engine

Responsibility:
    Execute controlled State Synchronization
    workflow using an approved state
    synchronization plan.

Input:
    state_synchronization_plan.json

Output:
    state_sync_execution_report.json

This module:
    - validates synchronization approval;
    - validates synchronization plan;
    - prepares controlled synchronization execution;
    - records execution state.

It does not:
    - modify documents directly;
    - generate document content;
    - approve synchronization automatically;
    - bypass Approval Control.
"""

from pathlib import Path
from datetime import datetime
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


STATE_SYNC_PLAN = (
    REPORT_DIR
    /
    "state_synchronization_plan.json"
)


STATE_SYNC_APPROVAL = (
    REPORT_DIR
    /
    "state_sync_approval.json"
)


EXECUTION_REPORT = (
    REPORT_DIR
    /
    "state_sync_execution_report.json"
)


def load_json(
    path: Path
) -> dict:
    """
    Load JSON artifact safely.
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
        json.JSONDecodeError,
        OSError
    ):
        return {}

    return (
        data
        if isinstance(data, dict)
        else {}
    )


def load_plan() -> dict:
    """
    Load state synchronization plan.
    """

    return load_json(
        STATE_SYNC_PLAN
    )


def load_approval() -> dict:
    """
    Load optional explicit state synchronization
    approval artifact.
    """

    return load_json(
        STATE_SYNC_APPROVAL
    )


def validate_plan(
    plan: dict
) -> bool:
    """
    Validate state synchronization plan.
    """

    if not plan:
        return False

    if plan.get(
        "status"
    ) != "READY":
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

    return True


def validate_approval(
    approval: dict
) -> bool:
    """
    Validate explicit synchronization approval.
    """

    if not approval:
        return False

    if approval.get(
        "status"
    ) != "APPROVED":
        return False

    if approval.get(
        "approval"
    ) is not True:
        return False

    if approval.get(
        "automatic_approval"
    ) is True:
        return False

    return True


def build_execution_result(
    plan: dict,
    approval: dict,
    approved: bool
) -> dict:
    """
    Build controlled synchronization execution result.
    """

    documents = plan.get(
        "documents",
        []
    )

    actions = plan.get(
        "actions",
        []
    )

    synchronization_required = plan.get(
        "synchronization_required",
        False
    )

    if not validate_plan(
        plan
    ):

        status = "FAILED"

        message = (
            "State synchronization plan "
            "is invalid or unavailable."
        )

    elif not synchronization_required:

        status = "NOT_REQUIRED"

        message = (
            "State synchronization is "
            "not required."
        )

    elif not approved:

        status = "WAITING_APPROVAL"

        message = (
            "Explicit state synchronization "
            "approval is required."
        )

    else:

        status = "READY_FOR_EXECUTION"

        message = (
            "State synchronization is approved "
            "and ready for controlled execution."
        )

    return {

        "component":
            "state_sync_engine",

        "version":
            "1.0",

        "status":
            status,

        "message":
            message,

        "synchronization_required":
            synchronization_required,

        "approval_required":
            True,

        "approved":
            approved,

        "documents":
            documents,

        "actions":
            actions,

        "executed":
            False,

        "executed_at":
            None,

        "source_plan":
            str(
                STATE_SYNC_PLAN
            ),

        "source_approval":
            (
                str(
                    STATE_SYNC_APPROVAL
                )
                if approval
                else None
            ),

    }


def save_report(
    report: dict
):
    """
    Save state synchronization execution report.
    """

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    EXECUTION_REPORT.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def run(
    approval_path: str | None = None
):
    """
    Execute controlled state synchronization workflow.

    No document modification is performed here.
    """

    plan = load_plan()

    if approval_path:

        approval = load_json(
            Path(
                approval_path
            )
        )

    else:

        approval = load_approval()

    approved = validate_approval(
        approval
    )

    result = build_execution_result(
        plan,
        approval,
        approved
    )

    if (
        result["status"]
        ==
        "READY_FOR_EXECUTION"
    ):

        result["executed"] = False

        result["message"] = (
            "Approval validated. "
            "State synchronization execution "
            "is authorized but no document "
            "modification is performed by "
            "this engine."
        )

        result["approved_at"] = (
            approval.get(
                "approved_at"
            )
        )

    result["created_at"] = (
        datetime.now().isoformat()
    )

    save_report(
        result
    )

    return result


if __name__ == "__main__":

    approval_argument = (
        sys.argv[1]
        if len(sys.argv) > 1
        else None
    )

    result = run(
        approval_argument
    )

    print(
        "STATE SYNCHRONIZATION ENGINE"
    )

    print(
        f"Status: {result['status']}"
    )

    print(
        "Synchronization required: "
        f"{result['synchronization_required']}"
    )

    print(
        f"Documents: {len(result['documents'])}"
    )

    print(
        f"Actions: {len(result['actions'])}"
    )