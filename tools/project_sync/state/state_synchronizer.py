"""
BybitScanner Project Sync Framework

State Synchronizer

Responsibility:
    Prepare controlled synchronization state
    from State Intelligence and synchronization
    planning artifacts.

Input:
    state_intelligence_report.json
    state_synchronization_plan.json

Output:
    state_synchronization_result.json
"""

from pathlib import Path
import json
from datetime import datetime


PROJECT_ROOT = Path("C:/BybitScanner")

REPORT_DIR = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
)

STATE_INTELLIGENCE_REPORT = (
    REPORT_DIR
    / "state_intelligence_report.json"
)

STATE_SYNC_PLAN = (
    REPORT_DIR
    / "state_synchronization_plan.json"
)

STATE_SYNC_RESULT = (
    REPORT_DIR
    / "state_synchronization_result.json"
)


def load_json(path: Path) -> dict:
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

    return data if isinstance(data, dict) else {}


def load_intelligence() -> dict:
    return load_json(
        STATE_INTELLIGENCE_REPORT
    )


def load_plan() -> dict:
    return load_json(
        STATE_SYNC_PLAN
    )


def validate_intelligence(
    intelligence: dict
) -> bool:

    if not intelligence:
        return False

    if intelligence.get(
        "component"
    ) != "state_intelligence":
        return False

    states = intelligence.get(
        "states",
        []
    )

    return isinstance(
        states,
        list
    )


def validate_plan(
    plan: dict
) -> bool:

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

    actions = plan.get(
        "actions",
        []
    )

    return (
        isinstance(documents, list)
        and isinstance(actions, list)
    )


def collect_state_documents(
    intelligence: dict
) -> list:

    documents = []

    for state in intelligence.get(
        "states",
        []
    ):

        if not isinstance(
            state,
            dict
        ):
            continue

        document = state.get(
            "document"
        )

        if document:
            documents.append(
                document
            )

    return list(
        dict.fromkeys(
            documents
        )
    )


def evaluate_state_health(
    intelligence: dict
) -> dict:

    health = intelligence.get(
        "state_health",
        {}
    )

    if not isinstance(
        health,
        dict
    ):
        health = {}

    missing = health.get(
        "missing_documents",
        []
    )

    if not isinstance(
        missing,
        list
    ):
        missing = []

    return {
        "status": health.get(
            "status",
            "UNKNOWN"
        ),
        "missing_documents": missing,
    }


def build_result(
    intelligence: dict,
    plan: dict
) -> dict:

    intelligence_valid = (
        validate_intelligence(
            intelligence
        )
    )

    plan_valid = (
        validate_plan(
            plan
        )
    )

    state_health = (
        evaluate_state_health(
            intelligence
        )
    )

    documents = []

    actions = []

    synchronization_required = False

    if plan_valid:

        documents = plan.get(
            "documents",
            []
        )

        actions = plan.get(
            "actions",
            []
        )

        synchronization_required = bool(
            plan.get(
                "synchronization_required",
                False
            )
        )

    if not documents and intelligence_valid:

        documents = collect_state_documents(
            intelligence
        )

    if not intelligence_valid:

        status = "FAILED"

        message = (
            "State Intelligence report "
            "is invalid or unavailable."
        )

    elif not plan_valid:

        status = "FAILED"

        message = (
            "State Synchronization plan "
            "is invalid or unavailable."
        )

    elif synchronization_required:

        status = "READY"

        message = (
            "State synchronization is "
            "prepared and requires "
            "controlled approval."
        )

    else:

        status = "NOT_REQUIRED"

        message = (
            "State synchronization "
            "is not required."
        )

    return {
        "component":
            "state_synchronizer",

        "version":
            "1.0",

        "status":
            status,

        "message":
            message,

        "intelligence_valid":
            intelligence_valid,

        "plan_valid":
            plan_valid,

        "synchronization_required":
            synchronization_required,

        "approval_required":
            True,

        "automatic_synchronization":
            False,

        "state_health":
            state_health,

        "documents":
            documents,

        "actions":
            actions,

        "executed":
            False,

        "created_at":
            datetime.now().isoformat(),

        "source_intelligence":
            str(
                STATE_INTELLIGENCE_REPORT
            ),

        "source_plan":
            str(
                STATE_SYNC_PLAN
            ),
    }


def save_result(
    result: dict
):

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    STATE_SYNC_RESULT.write_text(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def run():

    intelligence = load_intelligence()

    plan = load_plan()

    result = build_result(
        intelligence,
        plan
    )

    save_result(
        result
    )

    return result


if __name__ == "__main__":

    result = run()

    print(
        "STATE SYNCHRONIZER"
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
