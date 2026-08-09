"""
BybitScanner Project Sync Framework

Snapshot Creator

Responsibility:
    Create baseline project snapshots.

This module:
    - validates the current document registry;
    - creates the snapshot directory;
    - copies current registry state;
    - stores the historical baseline.

It does not:
    - compare snapshots;
    - analyze impact;
    - modify documents;
    - modify the source registry.
"""

from pathlib import Path
import shutil


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


SOURCE_REGISTRY = (
    PROJECT_ROOT
    /
    "tools"
    /
    "project_sync"
    /
    "reports"
    /
    "document_registry.json"
)


SNAPSHOT_PATH = (
    PROJECT_ROOT
    /
    "tools"
    /
    "project_sync"
    /
    "snapshots"
    /
    "previous_document_registry.json"
)


def create_snapshot():
    """
    Create baseline snapshot.

    The current document registry is copied
    without modifying the source artifact.
    """

    if not SOURCE_REGISTRY.exists():

        raise FileNotFoundError(
            "Document registry not found: "
            f"{SOURCE_REGISTRY}"
        )

    if not SOURCE_REGISTRY.is_file():

        raise ValueError(
            "Document registry path is not a file: "
            f"{SOURCE_REGISTRY}"
        )

    SNAPSHOT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.copyfile(
        SOURCE_REGISTRY,
        SNAPSHOT_PATH
    )

    return SNAPSHOT_PATH


if __name__ == "__main__":

    try:

        snapshot = create_snapshot()

        print(
            f"Snapshot created: {snapshot}"
        )

    except (
        OSError,
        ValueError
    ) as error:

        print(
            f"Snapshot creation failed: {error}"
        )

        raise SystemExit(1)