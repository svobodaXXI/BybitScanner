"""
BybitScanner Project Sync Framework

Change Detection Engine

Responsibility:
    Detect changes in project files and generate
    a machine-readable change report.

The module:
    - scans project files;
    - calculates file metadata;
    - compares the current state with the previous
      change detection snapshot;
    - identifies added, modified and deleted files;
    - persists the current state;
    - generates change_report.json.

It does not:
    - modify project source files;
    - modify project documents;
    - execute migrations;
    - bypass migration approval.
"""

from pathlib import Path
import hashlib
import json
from datetime import datetime


# --------------------------------------------------
# PROJECT ROOT
# --------------------------------------------------

PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


# --------------------------------------------------
# PROJECT SYNC PATHS
# --------------------------------------------------

PROJECT_SYNC_ROOT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
)

REPORT_DIR = (
    PROJECT_SYNC_ROOT
    / "reports"
)

REPORT_PATH = (
    REPORT_DIR
    / "change_report.json"
)

STATE_DIR = (
    PROJECT_SYNC_ROOT
    / "state"
)

STATE_PATH = (
    STATE_DIR
    / "change_detection_state.json"
)


# --------------------------------------------------
# SCAN CONFIGURATION
# --------------------------------------------------

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}

EXCLUDED_FILES = {
    "change_report.json",
    "change_detection_state.json",
    "pipeline_report.json",
}


# --------------------------------------------------
# FILE HASH
# --------------------------------------------------

def calculate_file_hash(
    path: Path,
) -> str:
    """
    Calculate SHA-256 hash of a file.
    """

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as file:

        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


# --------------------------------------------------
# FILE SCAN
# --------------------------------------------------

def scan_project() -> dict:
    """
    Scan project files and return
    machine-readable file state.
    """

    files = {}

    for path in PROJECT_ROOT.rglob("*"):

        if not path.is_file():
            continue

        relative = path.relative_to(
            PROJECT_ROOT
        )

        if any(
            part in EXCLUDED_DIRECTORIES
            for part in relative.parts
        ):
            continue

        if path.name in EXCLUDED_FILES:
            continue

        try:

            stat = path.stat()

            files[str(relative)] = {
                "path": str(relative),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime
                ).isoformat(),
                "sha256": calculate_file_hash(
                    path
                ),
            }

        except (
            OSError,
            PermissionError,
        ):
            continue

    return files


# --------------------------------------------------
# LOAD PREVIOUS STATE
# --------------------------------------------------

def load_previous_state() -> dict:
    """
    Load the previous change detection state.
    """

    if not STATE_PATH.exists():
        return {}

    try:

        data = json.loads(
            STATE_PATH.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            data,
            dict,
        ):
            return data.get(
                "files",
                {}
            )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        pass

    return {}


# --------------------------------------------------
# CHANGE COMPARISON
# --------------------------------------------------

def detect_changes(
    previous: dict,
    current: dict,
) -> dict:
    """
    Compare previous and current project states.
    """

    previous_paths = set(
        previous.keys()
    )

    current_paths = set(
        current.keys()
    )

    added_paths = sorted(
        current_paths - previous_paths
    )

    deleted_paths = sorted(
        previous_paths - current_paths
    )

    common_paths = (
        previous_paths
        & current_paths
    )

    modified_paths = []

    for path in sorted(
        common_paths
    ):

        previous_hash = (
            previous[path]
            .get("sha256")
        )

        current_hash = (
            current[path]
            .get("sha256")
        )

        if previous_hash != current_hash:
            modified_paths.append(
                path
            )

    return {
        "added": added_paths,
        "modified": modified_paths,
        "deleted": deleted_paths,
    }


# --------------------------------------------------
# STATE PERSISTENCE
# --------------------------------------------------

def save_state(
    files: dict,
) -> None:
    """
    Persist the current project state.
    """

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    state = {
        "project": "BybitScanner",
        "created": datetime.now().isoformat(),
        "files": files,
    }

    STATE_PATH.write_text(
        json.dumps(
            state,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# --------------------------------------------------
# REPORT
# --------------------------------------------------

def build_report(
    previous: dict,
    current: dict,
    changes: dict,
) -> dict:
    """
    Build machine-readable change report.
    """

    added = changes["added"]
    modified = changes["modified"]
    deleted = changes["deleted"]

    total_changes = (
        len(added)
        + len(modified)
        + len(deleted)
    )

    return {
        "project": "BybitScanner",
        "engine": "change_detection",
        "version": "1.0",
        "created": datetime.now().isoformat(),
        "status": "SUCCESS",
        "previous_files": len(previous),
        "current_files": len(current),
        "changes_detected": total_changes > 0,
        "change_count": total_changes,
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "summary": {
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
        },
    }


def save_report(
    report: dict,
) -> None:
    """
    Persist the change detection report.
    """

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# --------------------------------------------------
# CHANGE DETECTION PIPELINE
# --------------------------------------------------

def run_change_detection() -> dict:
    """
    Execute the complete change detection workflow.
    """

    previous = load_previous_state()

    current = scan_project()

    changes = detect_changes(
        previous=previous,
        current=current,
    )

    report = build_report(
        previous=previous,
        current=current,
        changes=changes,
    )

    save_state(
        current
    )

    save_report(
        report
    )

    return report


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

def main() -> int:
    """
    Command-line entry point.
    """

    try:

        report = run_change_detection()

        print(
            "CHANGE DETECTION"
        )

        print(
            f"Status: {report['status']}"
        )

        print(
            f"Files: {report['current_files']}"
        )

        print(
            f"Changes: {report['change_count']}"
        )

        print(
            f"Added: {report['summary']['added']}"
        )

        print(
            f"Modified: {report['summary']['modified']}"
        )

        print(
            f"Deleted: {report['summary']['deleted']}"
        )

        print(
            f"Report: {REPORT_PATH}"
        )

        return 0

    except Exception as error:

        print(
            "CHANGE DETECTION"
        )

        print(
            "Status: FAILED"
        )

        print(
            f"Error: {error}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )