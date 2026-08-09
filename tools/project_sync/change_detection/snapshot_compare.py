"""
BybitScanner Project Sync Framework

Snapshot Compare Engine

Responsibility:
    Compare previous project snapshot
    with current document registry.

This module:
    - loads document registry snapshots;
    - detects changed documents;
    - generates change report.

It does not:
    - modify documents;
    - analyze impact;
    - update documentation.
"""

from pathlib import Path
import json


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


CURRENT_REGISTRY = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_registry.json"
)


PREVIOUS_SNAPSHOT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "snapshots"
    / "previous_document_registry.json"
)


CHANGE_REPORT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "change_report.json"
)


def load_json(
    path: Path
) -> dict:
    """
    Load JSON file.
    """

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def index_documents(
    data: dict
) -> dict:
    """
    Convert document list into indexed structure.
    """

    result = {}

    for document in data.get(
        "documents",
        []
    ):

        name = document.get(
            "name"
        )

        if not name:
            continue

        result[name] = document

    return result


def compare_documents(
    previous: dict,
    current: dict
) -> list:
    """
    Detect changed documents.
    """

    changes = []

    names = (
        set(previous)
        | set(current)
    )

    for name in sorted(
        names
    ):

        old = previous.get(
            name
        )

        new = current.get(
            name
        )

        if old != new:

            if old and new:
                change_type = "MODIFIED"

            elif new:
                change_type = "ADDED"

            else:
                change_type = "REMOVED"

            changes.append(
                {
                    "document": name,
                    "change_type": change_type,
                }
            )

    return changes


def create_report(
    changes: list
):
    """
    Create machine-readable change report.
    """

    report = {
        "detector":
            "snapshot_compare",

        "changed_documents":
            changes,

        "change_count":
            len(changes),
    }

    CHANGE_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    CHANGE_REPORT.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    return report


def run_detection():
    """
    Compare current registry
    with previous snapshot.
    """

    if not PREVIOUS_SNAPSHOT.exists():

        print(
            "Previous snapshot not found."
        )

        return None

    if not CURRENT_REGISTRY.exists():

        print(
            "Current document registry not found."
        )

        return None

    previous = index_documents(
        load_json(
            PREVIOUS_SNAPSHOT
        )
    )

    current = index_documents(
        load_json(
            CURRENT_REGISTRY
        )
    )

    changes = compare_documents(
        previous,
        current
    )

    return create_report(
        changes
    )


if __name__ == "__main__":

    result = run_detection()

    if result:

        print(
            f"Detected changes: "
            f"{result['change_count']}"
        )