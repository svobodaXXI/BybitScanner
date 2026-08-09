"""
BybitScanner Project Sync Framework

Approval Controller

Responsibility:
    Validate migration decision
    and explicitly authorize controlled
    migration execution.

Input:
    migration_decision.json

Output:
    migration_approval.json

This module:
    - validates the canonical migration decision;
    - distinguishes NOT_REQUIRED from REJECTED;
    - requires explicit approval when migration is required;
    - preserves prepared document updates;
    - validates migration scope;
    - creates the approval artifact;
    - creates a cryptographic binding to the current decision;
    - controls migration permission.

It does not:
    - modify documents;
    - execute migration;
    - approve pending migrations automatically;
    - bypass Approval Control.
"""


from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime


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


def load_decision() -> dict:
    """
    Load migration decision artifact.
    """

    return load_json(
        DECISION_REPORT
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

    Only valid string document targets
    and string contents are preserved.
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


def build_decision_binding(
    decision: dict
) -> dict:
    """
    Build the canonical migration scope used
    for approval binding.
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

    return binding


def calculate_decision_binding(
    decision: dict
) -> str:
    """
    Calculate deterministic SHA-256 binding
    for the migration decision scope.
    """

    binding = build_decision_binding(
        decision
    )

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


def validate_update_scope(
    decision: dict
) -> bool:
    """
    Validate that every prepared update targets
    a document included in the migration decision.
    """

    documents = decision.get(
        "documents",
        []
    )

    updates = normalize_updates(
        decision.get(
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


def validate_decision(
    decision: dict
) -> bool:
    """
    Validate canonical migration decision.

    A valid decision may be either:

        NOT_REQUIRED

    or:

        WAITING_APPROVAL / PENDING

    Existing APPROVED state is never accepted
    as a substitute for a new explicit approval.
    """

    if not decision:

        return False

    if decision.get(
        "plan_valid"
    ) is not True:

        return False

    automatic_approval = decision.get(
        "automatic_approval",
        False
    )

    if automatic_approval:

        return False

    migration_required = decision.get(
        "migration_required",
        False
    )

    if not isinstance(
        migration_required,
        bool
    ):

        return False

    decision_value = decision.get(
        "decision"
    )

    status = decision.get(
        "status"
    )

    if not migration_required:

        return (
            status == "NOT_REQUIRED"
            and
            decision_value == "NOT_REQUIRED"
            and
            decision.get(
                "approval_required",
                False
            ) is False
            and
            decision.get(
                "documents",
                []
            ) == []
            and
            decision.get(
                "migration_plan",
                []
            ) == []
            and
            decision.get(
                "updates",
                {}
            ) == {}
        )

    if migration_required:

        if status != "WAITING_APPROVAL":

            return False

        if decision_value != "PENDING":

            return False

        if decision.get(
            "approval_required"
        ) is not True:

            return False

        documents = decision.get(
            "documents",
            []
        )

        actions = decision.get(
            "actions",
            []
        )

        migration_plan = decision.get(
            "migration_plan",
            []
        )

        updates = decision.get(
            "updates",
            {}
        )

        if not isinstance(
            documents,
            list
        ):

            return False

        if not documents:

            return False

        if not isinstance(
            actions,
            list
        ):

            return False

        if not isinstance(
            migration_plan,
            list
        ):

            return False

        if not migration_plan:

            return False

        if not isinstance(
            updates,
            dict
        ):

            return False

        if not validate_update_scope(
            decision
        ):

            return False

        return True

    return False


def create_not_required_approval(
    decision: dict
) -> dict:
    """
    Create terminal approval artifact when
    no migration is required.
    """

    return {

        "component":
            "approval_controller",

        "version":
            "2.5",

        "status":
            "NOT_REQUIRED",

        "decision":
            "NOT_REQUIRED",

        "approval":
            False,

        "plan_valid":
            True,

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
            "migration_decision",

        "explicit_approval":
            False,

        "automatic_approval":
            False,

        "migration_required":
            False,

        "decision_binding":
            calculate_decision_binding(
                decision
            ),

        "created_at":
            datetime.now().isoformat()
    }


def create_waiting_approval(
    decision: dict
) -> dict:
    """
    Create approval artifact for a valid
    migration awaiting explicit approval.
    """

    return {

        "component":
            "approval_controller",

        "version":
            "2.5",

        "status":
            "WAITING_APPROVAL",

        "decision":
            "PENDING",

        "approval":
            False,

        "plan_valid":
            True,

        "approved_at":
            None,

        "documents":
            decision.get(
                "documents",
                []
            ),

        "actions":
            decision.get(
                "actions",
                []
            ),

        "updates":
            normalize_updates(
                decision.get(
                    "updates",
                    {}
                )
            ),

        "migration_plan":
            decision.get(
                "migration_plan",
                []
            ),

        "approval_required":
            True,

        "source":
            "migration_decision",

        "explicit_approval":
            False,

        "automatic_approval":
            False,

        "migration_required":
            True,

        "decision_binding":
            calculate_decision_binding(
                decision
            ),

        "created_at":
            datetime.now().isoformat()
    }


def create_approved(
    decision: dict
) -> dict:
    """
    Create explicitly approved migration artifact.

    Approval is granted only when approve=True
    is explicitly supplied by the caller.
    """

    return {

        "component":
            "approval_controller",

        "version":
            "2.5",

        "status":
            "APPROVED",

        "decision":
            "APPROVED",

        "approval":
            True,

        "plan_valid":
            True,

        "approved_at":
            datetime.now().isoformat(),

        "documents":
            decision.get(
                "documents",
                []
            ),

        "actions":
            decision.get(
                "actions",
                []
            ),

        "updates":
            normalize_updates(
                decision.get(
                    "updates",
                    {}
                )
            ),

        "migration_plan":
            decision.get(
                "migration_plan",
                []
            ),

        "approval_required":
            True,

        "source":
            "migration_decision",

        "explicit_approval":
            True,

        "automatic_approval":
            False,

        "migration_required":
            True,

        "decision_binding":
            calculate_decision_binding(
                decision
            ),

        "created_at":
            datetime.now().isoformat()
    }


def create_rejected(
    decision: dict
) -> dict:
    """
    Create rejection artifact for an invalid
    migration decision.
    """

    return {

        "component":
            "approval_controller",

        "version":
            "2.5",

        "status":
            "REJECTED",

        "decision":
            "REJECTED",

        "approval":
            False,

        "plan_valid":
            decision.get(
                "plan_valid",
                False
            ),

        "approved_at":
            None,

        "documents":
            decision.get(
                "documents",
                []
            ),

        "actions":
            decision.get(
                "actions",
                []
            ),

        "updates":
            normalize_updates(
                decision.get(
                    "updates",
                    {}
                )
            ),

        "migration_plan":
            decision.get(
                "migration_plan",
                []
            ),

        "approval_required":
            decision.get(
                "approval_required",
                True
            ),

        "source":
            "migration_decision",

        "explicit_approval":
            False,

        "automatic_approval":
            False,

        "migration_required":
            decision.get(
                "migration_required",
                False
            ),

        "decision_binding":
            calculate_decision_binding(
                decision
            ),

        "created_at":
            datetime.now().isoformat()
    }


def create_approval(
    approve: bool = False
):
    """
    Create controlled approval artifact.

    Decision flow:

        NOT_REQUIRED
            ->
        NOT_REQUIRED

        WAITING_APPROVAL / PENDING
            ->
        WAITING_APPROVAL
        or
        APPROVED when approve=True

        invalid decision
            ->
        REJECTED

    No migration is executed here.
    """

    decision = load_decision()

    if not validate_decision(
        decision
    ):

        approval_report = create_rejected(
            decision
        )

    elif (
        decision.get(
            "migration_required",
            False
        )
        is False
    ):

        approval_report = (
            create_not_required_approval(
                decision
            )
        )

    elif approve:

        approval_report = create_approved(
            decision
        )

    else:

        approval_report = create_waiting_approval(
            decision
        )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    APPROVAL_REPORT.write_text(
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
        and sys.argv[1].lower()
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