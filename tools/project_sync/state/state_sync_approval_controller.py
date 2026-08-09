"""
BybitScanner Project Sync Framework

State Synchronization Approval Controller

Responsibility:
    Validate the State Synchronization Plan
    and explicitly authorize controlled
    State Synchronization execution.

Input:
    state_synchronization_plan.json

Output:
    state_sync_approval.json

This module:
    - validates the canonical state synchronization plan;
    - requires explicit approval;
    - creates the State Synchronization approval artifact;
    - controls synchronization permission.

It does not:
    - modify documents;
    - execute synchronization;
    - approve synchronization automatically;
    - generate document content;
    - bypass Governance Control.
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
        if isinstance(
            data,
            dict
        )
        else {}
    )


def load_plan() -> dict:
    """
    Load canonical State Synchronization Plan.
    """

    return load_json(
        STATE_SYNC_PLAN
    )


def validate_plan(
    plan: dict
) -> bool:
    """
    Validate State Synchronization Plan.

    A valid plan must:

        - exist;
        - belong to the State Synchronization Planner;
        - have READY status;
        - contain document list;
        - contain action list.
    """

    if not plan:
        return False

    if plan.get(
        "component"
    ) != "state_synchronization_planner":

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


def create_approval(
    approve: bool = False
) -> dict:
    """
    Create controlled State Synchronization
    approval artifact.

    Default:

        WAITING_APPROVAL

    Explicit approval:

        approve=True

    If synchronization is not required:

        NOT_REQUIRED

    Invalid plan:

        REJECTED

    No synchronization is executed here.
    """

    plan = load_plan()

    plan_valid = validate_plan(
        plan
    )

    synchronization_required = bool(
        plan.get(
            "synchronization_required",
            False
        )
    )

    if not plan_valid:

        status = "REJECTED"

        decision = "REJECTED"

        approval = False

        explicit_approval = False

    elif not synchronization_required:

        status = "NOT_REQUIRED"

        decision = "NOT_REQUIRED"

        approval = False

        explicit_approval = False

    elif approve:

        status = "APPROVED"

        decision = "APPROVED"

        approval = True

        explicit_approval = True

    else:

        status = "WAITING_APPROVAL"

        decision = "PENDING"

        approval = False

        explicit_approval = False

    approval_report = {

        "component":
            "state_sync_approval_controller",

        "version":
            "1.0",

        "status":
            status,

        "decision":
            decision,

        "approval":
            approval,

        "plan_valid":
            plan_valid,

        "synchronization_required":
            synchronization_required,

        "approved_at":
            (
                datetime.now().isoformat()
                if explicit_approval
                else None
            ),

        "documents":
            plan.get(
                "documents",
                []
            ),

        "actions":
            plan.get(
                "actions",
                []
            ),

        "approval_required":
            True,

        "explicit_approval":
            explicit_approval,

        "automatic_approval":
            False,

        "source":
            "state_synchronization_plan",

        "source_plan":
            str(
                STATE_SYNC_PLAN
            ),

        "created_at":
            datetime.now().isoformat(),
    }

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    STATE_SYNC_APPROVAL.write_text(
        json.dumps(
            approval_report,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    return approval_report


if __name__ == "__main__":

    approve = (
        len(sys.argv) > 1
        and
        sys.argv[1].lower()
        in {
            "approve",
            "--approve",
            "approved"
        }
    )

    result = create_approval(
        approve=approve
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )