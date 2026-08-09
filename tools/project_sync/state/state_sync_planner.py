"""
BybitScanner Project Sync Framework

State Synchronization Planner

Responsibility:
    Build controlled synchronization plan
    from State Intelligence data.

Input:
    state_intelligence_report.json
    synchronization_plan.json (optional)

Output:
    state_synchronization_plan.json

This module:
    - analyzes current state intelligence;
    - detects state inconsistencies;
    - prepares synchronization recommendations;
    - creates controlled state synchronization artifact.

It does not:
    - modify documents;
    - execute migrations;
    - approve synchronization;
    - generate document content autonomously.
"""


from pathlib import Path
import json


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


STATE_INTELLIGENCE_REPORT = (
    REPORT_DIR
    /
    "state_intelligence_report.json"
)


SYNCHRONIZATION_PLAN = (
    REPORT_DIR
    /
    "synchronization_plan.json"
)


STATE_SYNC_PLAN = (
    REPORT_DIR
    /
    "state_synchronization_plan.json"
)


def load_json(
    path: Path
) -> dict:
    """
    Load JSON safely.
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


def analyze_state_health(
    intelligence: dict
) -> dict:
    """
    Analyze unified state health.
    """

    state_health = intelligence.get(
        "state_health",
        {}
    )

    if not isinstance(
        state_health,
        dict
    ):
        state_health = {}

    status = state_health.get(
        "status",
        "UNKNOWN"
    )

    missing_documents = state_health.get(
        "missing_documents",
        []
    )

    if not isinstance(
        missing_documents,
        list
    ):
        missing_documents = []

    return {
        "status": status,
        "missing_documents": missing_documents,
    }


def collect_state_documents(
    intelligence: dict
) -> list:
    """
    Collect analyzed state documents.
    """

    states = intelligence.get(
        "states",
        []
    )

    if not isinstance(
        states,
        list
    ):
        return []

    documents = []

    for state in states:

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


def detect_actions(
    intelligence: dict
) -> list:
    """
    Determine controlled synchronization actions.
    """

    health = analyze_state_health(
        intelligence
    )

    actions = []

    if health["status"] == "WARNING":

        if health["missing_documents"]:
            actions.append(
                "review_missing_state_documents"
            )

    elif health["status"] == "HEALTHY":

        actions.append(
            "validate_state_consistency"
        )

    else:

        actions.append(
            "review_state_intelligence"
        )

    actions.append(
        "preserve_state_document_content"
    )

    return list(
        dict.fromkeys(
            actions
        )
    )


def create_sync_plan(
    intelligence: dict
) -> dict:
    """
    Create state synchronization plan.
    """

    health = analyze_state_health(
        intelligence
    )

    documents = collect_state_documents(
        intelligence
    )

    actions = detect_actions(
        intelligence
    )

    synchronization_required = (
        health["status"] != "HEALTHY"
        or bool(
            health["missing_documents"]
        )
    )

    plan = {

        "component":
            "state_synchronization_planner",

        "version":
            "1.0",

        "status":
            "READY",

        "synchronization_required":
            synchronization_required,

        "state_health":
            health,

        "documents":
            documents,

        "actions":
            actions,

        "approval_required":
            True,

        "automatic_synchronization":
            False,

        "source":
            "state_intelligence_report",

    }

    return plan


def save_plan(
    plan: dict
):
    """
    Save state synchronization plan.
    """

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    STATE_SYNC_PLAN.write_text(
        json.dumps(
            plan,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def run():
    """
    Build and save state synchronization plan.
    """

    intelligence = load_json(
        STATE_INTELLIGENCE_REPORT
    )

    if not intelligence:

        plan = {

            "component":
                "state_synchronization_planner",

            "version":
                "1.0",

            "status":
                "ERROR",

            "synchronization_required":
                False,

            "state_health":
                {
                    "status": "UNKNOWN",
                    "missing_documents": [],
                },

            "documents":
                [],

            "actions":
                [
                    "generate_state_intelligence_report"
                ],

            "approval_required":
                True,

            "automatic_synchronization":
                False,

            "source":
                "state_intelligence_report",

        }

        save_plan(
            plan
        )

        return plan

    plan = create_sync_plan(
        intelligence
    )

    save_plan(
        plan
    )

    return plan


if __name__ == "__main__":

    result = run()

    print(
        "STATE SYNCHRONIZATION PLANNER"
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