"""
BybitScanner Project Snapshot Generator v2.1

Responsibility:
    Create controlled project state snapshot.

Captures:
    - project files;
    - project state;
    - Project Sync state;
    - Pipeline state;
    - Architecture state;
    - Roadmap state;
    - Changelog state;
    - generated reports.

Does not:
    - modify project files;
    - execute migrations;
    - update documentation.
"""

from pathlib import Path
from datetime import datetime
import json
import os


PROJECT = "BybitScanner"


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


DOCUMENTS_ROOT = (
    PROJECT_ROOT
    / "DOCUMENTS"
)


REPORTS_ROOT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
)


SNAPSHOT_FILE = (
    PROJECT_ROOT
    / "SNAPSHOT.md"
)


PIPELINE_REPORT_FILE = (
    REPORTS_ROOT
    / "pipeline_report.json"
)


TRACKED_EXTENSIONS = (
    ".py",
    ".md",
    ".txt",
    ".json",
)


STATE_DOCUMENTS = [

    "PROJECT_STATE.md",

    "STATE_PROJECT_SYNC.md",

    "STATE_PIPELINE_ENGINE.md",

    "STATE_ARCHITECTURE.md",

    "ROADMAP.md",

    "CHANGELOG.md",

]


REPORT_FILES = [

    "pipeline_report.json",

    "migration_plan.json",

    "migration_decision.json",

    "migration_approval.json",

    "document_update_report.json",

    "migration_execution_report.json",

]


def collect_files():
    """
    Collect tracked project files.
    """

    files = []

    for root, dirs, filenames in os.walk(
        PROJECT_ROOT
    ):

        if "venv" in root:
            continue

        if "__pycache__" in root:
            continue

        for file in filenames:

            if file.endswith(
                TRACKED_EXTENSIONS
            ):

                path = (
                    Path(root)
                    / file
                )

                files.append(
                    {
                        "name":
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),

                        "size":
                            path.stat().st_size,
                    }
                )

    return files


def check_documents():
    """
    Check required state documents.
    """

    result = []

    for document in STATE_DOCUMENTS:

        path = (
            DOCUMENTS_ROOT
            / document
        )

        result.append(
            {
                "document":
                    document,

                "status":
                    "FOUND"
                    if path.exists()
                    else
                    "MISSING",
            }
        )

    return result


def check_reports():
    """
    Check expected Project Sync reports.
    """

    result = []

    for report in REPORT_FILES:

        path = (
            REPORTS_ROOT
            / report
        )

        result.append(
            {
                "report":
                    report,

                "status":
                    "FOUND"
                    if path.exists()
                    else
                    "MISSING",
            }
        )

    return result


def load_pipeline_state():
    """
    Read the canonical Pipeline report.

    The snapshot does not invent Pipeline state.
    All Pipeline status information is derived from
    pipeline_report.json.
    """

    default_state = {
        "status": "UNKNOWN",
        "version": "UNKNOWN",
        "stages": 0,
        "errors": [],
        "created": None,
        "available": False,
    }

    if not PIPELINE_REPORT_FILE.exists():
        return default_state

    try:

        report = json.loads(
            PIPELINE_REPORT_FILE.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return default_state

    if not isinstance(
        report,
        dict,
    ):

        return default_state

    errors = report.get(
        "errors",
        [],
    )

    if not isinstance(
        errors,
        list,
    ):

        errors = [
            str(errors)
        ]

    return {
        "status":
            str(
                report.get(
                    "status",
                    "UNKNOWN",
                )
            ),

        "version":
            str(
                report.get(
                    "version",
                    "UNKNOWN",
                )
            ),

        "stages":
            report.get(
                "stages",
                0,
            ),

        "errors":
            errors,

        "created":
            report.get(
                "created"
            ),

        "available":
            True,
    }


def derive_migration_state(
    pipeline_state,
):
    """
    Derive migration state from the canonical
    Pipeline migration result.

    No migration state is hardcoded.
    """

    if not pipeline_state.get(
        "available",
        False,
    ):

        return "UNKNOWN"

    report = None

    try:

        report = json.loads(
            PIPELINE_REPORT_FILE.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return "UNKNOWN"

    if not isinstance(
        report,
        dict,
    ):

        return "UNKNOWN"

    for result in report.get(
        "results",
        [],
    ):

        if not isinstance(
            result,
            dict,
        ):

            continue

        if result.get(
            "stage"
        ) != "migration":

            continue

        data = result.get(
            "data",
            {},
        )

        if not isinstance(
            data,
            dict,
        ):

            return "UNKNOWN"

        status = str(
            data.get(
                "status",
                "UNKNOWN",
            )
        )

        if status == "PENDING_APPROVAL":
            return "PENDING_APPROVAL"

        if status in {
            "EXECUTED",
            "COMPLETED",
            "SUCCESS",
        }:
            return "EXECUTED"

        if status in {
            "FAILED",
            "ERROR",
        }:
            return "FAILED"

        if status == "NO_UPDATES":
            return "NO_UPDATES"

        return status

    return "UNKNOWN"


def derive_documentation_state(
    documents,
):
    """
    Derive documentation state from the
    actual checked document set.
    """

    missing = [
        item
        for item in documents
        if item.get("status") != "FOUND"
    ]

    if missing:
        return "INCOMPLETE"

    return "SYNCHRONIZED"


def create_snapshot():
    """
    Create the controlled project snapshot.

    The snapshot reflects the actual current
    Pipeline and migration state.
    """

    files = collect_files()

    documents = check_documents()

    reports = check_reports()

    pipeline = load_pipeline_state()

    migration = derive_migration_state(
        pipeline
    )

    documentation = (
        derive_documentation_state(
            documents
        )
    )

    with open(
        SNAPSHOT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "# BybitScanner Project Snapshot\n\n"
        )

        f.write(
            "Version:\n\n"
            "2.1\n\n"
        )

        f.write(
            "Date:\n\n"
            +
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            +
            "\n\n"
        )

        f.write(
            "---\n\n"
        )

        f.write(
            "# PROJECT_STATUS\n\n"
        )

        f.write(
            "Project:\n\n"
            f"{PROJECT}\n\n"
        )

        f.write(
            "Pipeline:\n\n"
            f"{pipeline['status']}\n\n"
        )

        f.write(
            "Pipeline Version:\n\n"
            f"{pipeline['version']}\n\n"
        )

        f.write(
            "Pipeline Stages:\n\n"
            f"{pipeline['stages']}\n\n"
        )

        f.write(
            "Pipeline Report:\n\n"
            f"{PIPELINE_REPORT_FILE}\n\n"
        )

        f.write(
            "Migration:\n\n"
            f"{migration}\n\n"
        )

        f.write(
            "Documentation:\n\n"
            f"{documentation}\n\n"
        )

        f.write(
            "---\n\n"
        )

        f.write(
            "# STATE_DOCUMENTS\n\n"
        )

        for item in documents:

            f.write(
                f"- {item['document']} "
                f"({item['status']})\n"
            )

        f.write(
            "\n---\n\n"
        )

        f.write(
            "# PROJECT_SYNC_REPORTS\n\n"
        )

        for item in reports:

            f.write(
                f"- {item['report']} "
                f"({item['status']})\n"
            )

        f.write(
            "\n---\n\n"
        )

        f.write(
            "# PROJECT_FILES\n\n"
        )

        f.write(
            f"Total files: {len(files)}\n\n"
        )

        for item in files:

            f.write(
                f"- {item['name']} "
                f"({item['size']} bytes)\n"
            )

        f.write(
            "\n---\n\n"
        )

        f.write(
            "# FINAL_STATE\n\n"
        )

        f.write(
            "Architecture:\n\n"
            "STABLE\n\n"
        )

        f.write(
            "Project Sync:\n\n"
            f"{pipeline['status']}\n\n"
        )

        f.write(
            "Automation:\n\n"
            "ACTIVE DEVELOPMENT\n\n"
        )

        f.write(
            "Snapshot:\n\n"
            "CREATED\n"
        )

    return SNAPSHOT_FILE


if __name__ == "__main__":

    result = create_snapshot()

    print(
        "PROJECT SNAPSHOT"
    )

    print(
        "Status: CREATED"
    )

    print(
        f"File: {result}"
    )
