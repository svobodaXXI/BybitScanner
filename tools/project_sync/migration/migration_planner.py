"""
BybitScanner Project Sync Framework

Migration Planner

Responsibility:
    Analyze synchronization context and create
    a controlled migration plan artifact.

Input:
    synchronization_plan.json

Output:
    migration_plan.json

This module:
    - transfers documents from synchronization planning;
    - transfers migration actions;
    - transfers explicitly prepared document updates;
    - preserves migration_required state from the source plan;
    - creates a canonical migration_plan structure;
    - does not modify documents.

It does not:
    - modify documents;
    - generate document content;
    - execute migration;
    - approve migration automatically;
    - bypass Approval Control.
"""

from pathlib import Path
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


SYNC_PLAN = (
    REPORT_DIR
    /
    "synchronization_plan.json"
)


MIGRATION_PLAN = (
    REPORT_DIR
    /
    "migration_plan.json"
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

    if not isinstance(
        data,
        dict
    ):

        return {}

    return data


def load_context(
    context_path: str | None = None
) -> dict:
    """
    Load migration context.

    If an explicit path is supplied,
    it is used.

    Otherwise the canonical
    synchronization_plan.json is used.
    """

    if context_path:

        context = load_json(
            Path(
                context_path
            )
        )

        if context:

            return context

    return load_json(
        SYNC_PLAN
    )


def extract_documents(
    context: dict
) -> list:
    """
    Extract documents from synchronization context.
    """

    documents = []

    source_documents = context.get(
        "documents_to_review",
        []
    )

    if isinstance(
        source_documents,
        list
    ):

        documents.extend(
            source_documents
        )

    source_documents = context.get(
        "documents",
        []
    )

    if isinstance(
        source_documents,
        list
    ):

        documents.extend(
            source_documents
        )

    migration_items = context.get(
        "migration_plan",
        []
    )

    if isinstance(
        migration_items,
        list
    ):

        for item in migration_items:

            if isinstance(
                item,
                dict
            ):

                document = item.get(
                    "document"
                )

                if isinstance(
                    document,
                    str
                ) and document:

                    documents.append(
                        document
                    )

            elif isinstance(
                item,
                str
            ) and item:

                documents.append(
                    item
                )

    return list(
        dict.fromkeys(
            document
            for document in documents
            if isinstance(
                document,
                str
            )
            and document
        )
    )


def extract_actions(
    context: dict
) -> list:
    """
    Extract migration actions.
    """

    actions = []

    source_actions = context.get(
        "actions",
        []
    )

    if isinstance(
        source_actions,
        list
    ):

        actions.extend(
            source_actions
        )

    migration_items = context.get(
        "migration_plan",
        []
    )

    if isinstance(
        migration_items,
        list
    ):

        for item in migration_items:

            if not isinstance(
                item,
                dict
            ):

                continue

            item_actions = item.get(
                "actions",
                []
            )

            if isinstance(
                item_actions,
                list
            ):

                actions.extend(
                    item_actions
                )

    if not actions:

        actions = [
            "validate_structure",
            "preserve_document_content"
        ]

    return list(
        dict.fromkeys(
            action
            for action in actions
            if isinstance(
                action,
                str
            )
            and action
        )
    )


def extract_updates(
    context: dict
) -> dict:
    """
    Extract explicitly prepared document updates.

    Supported fields:

        updates

        document_updates
    """

    updates = context.get(
        "updates"
    )

    if updates is None:

        updates = context.get(
            "document_updates"
        )

    if updates is None:

        return {}

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
        ):

            continue

        if isinstance(
            update,
            str
        ):

            normalized[document] = {
                "content": update
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
                    "content": content
                }

    return normalized


def merge_update_documents(
    documents: list,
    updates: dict
) -> list:
    """
    Add explicitly updated documents to
    the migration document list.
    """

    result = list(
        documents
    )

    for document in updates:

        if document not in result:

            result.append(
                document
            )

    return result


def build_migration_items(
    documents: list,
    actions: list,
    updates: dict,
    source_migration_plan: list
) -> list:
    """
    Build canonical migration plan items.

    Existing migration-plan metadata from the
    synchronization planner is preserved where possible.
    """

    source_items = {}

    if isinstance(
        source_migration_plan,
        list
    ):

        for item in source_migration_plan:

            if not isinstance(
                item,
                dict
            ):

                continue

            document = item.get(
                "document"
            )

            if isinstance(
                document,
                str
            ) and document:

                source_items[
                    document
                ] = item

    migration_items = []

    for document in documents:

        source_item = source_items.get(
            document,
            {}
        )

        item = {
            "document":
                document,

            "actions":
                list(
                    source_item.get(
                        "actions",
                        actions
                    )
                ),

            "approval_required":
                bool(
                    source_item.get(
                        "approval_required",
                        True
                    )
                )
        }

        if "changes" in source_item:

            item["changes"] = (
                source_item["changes"]
            )

        if "risk" in source_item:

            item["risk"] = (
                source_item["risk"]
            )

        if document in updates:

            item["update"] = updates[
                document
            ]

        migration_items.append(
            item
        )

    return migration_items


def determine_migration_required(
    context: dict,
    documents: list,
    migration_items: list,
    updates: dict
) -> bool:
    """
    Determine whether migration is required.

    Priority:

        1. Explicit synchronization-plan
           migration_required value.

        2. Explicit synchronization requirement.

        3. Prepared updates.

        4. Migration items/documents.

    This prevents a valid synchronization plan
    from being accidentally reduced to
    migration_required=False merely because
    updates are empty.
    """

    source_value = context.get(
        "migration_required"
    )

    if isinstance(
        source_value,
        bool
    ):

        return source_value

    synchronization_required = context.get(
        "synchronization_required"
    )

    if isinstance(
        synchronization_required,
        bool
    ) and synchronization_required:

        return True

    if updates:

        return True

    if migration_items:

        return True

    if documents:

        return True

    return False


def create_plan(
    context_path: str | None = None
):
    """
    Create controlled migration plan.
    """

    context = load_context(
        context_path
    )

    if not context:

        plan = {

            "component":
                "migration_planner",

            "version":
                "2.4",

            "status":
                "ERROR",

            "migration_required":
                False,

            "documents":
                [],

            "actions":
                [],

            "updates":
                {},

            "updates_count":
                0,

            "migration_plan":
                [],

            "approval_required":
                False,

            "source":
                "synchronization_plan",

            "error":
                "Synchronization plan not found or invalid"
        }

        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        MIGRATION_PLAN.write_text(
            json.dumps(
                plan,
                indent=4,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        return plan

    documents = extract_documents(
        context
    )

    actions = extract_actions(
        context
    )

    updates = extract_updates(
        context
    )

    documents = merge_update_documents(
        documents,
        updates
    )

    source_migration_plan = context.get(
        "migration_plan",
        []
    )

    migration_items = build_migration_items(
        documents,
        actions,
        updates,
        source_migration_plan
    )

    migration_required = (
        determine_migration_required(
            context,
            documents,
            migration_items,
            updates
        )
    )

    approval_required = (
        bool(
            context.get(
                "approval_required",
                False
            )
        )
        or
        any(
            item.get(
                "approval_required",
                True
            )
            for item in migration_items
        )
    )

    if not migration_required:

        approval_required = False

    plan = {

        "component":
            "migration_planner",

        "version":
            "2.4",

        "status":
            "READY",

        "migration_required":
            migration_required,

        "documents":
            documents,

        "actions":
            actions,

        "updates":
            updates,

        "updates_count":
            len(updates),

        "migration_plan":
            migration_items,

        "approval_required":
            approval_required,

        "source":
            "synchronization_plan"
    }

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    MIGRATION_PLAN.write_text(
        json.dumps(
            plan,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    return plan


if __name__ == "__main__":

    context_argument = (
        sys.argv[1]
        if len(sys.argv) > 1
        else None
    )

    result = create_plan(
        context_argument
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )