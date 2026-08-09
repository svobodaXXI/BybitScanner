"""
BybitScanner Project Sync Framework

State Intelligence Analyzer

Responsibility:
    Analyze project STATE documents
    and build unified project state model.

This module:
    - reads STATE documents;
    - extracts metadata;
    - detects state relations;
    - creates unified state intelligence report.

It does not:
    - modify documents;
    - change project state;
    - execute migrations.
"""

from pathlib import Path
import json
import re


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


DOCUMENTS_PATH = (
    PROJECT_ROOT
    / "DOCUMENTS"
)


REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "state_intelligence_report.json"
)


STATE_DOCUMENTS = [
    "PROJECT_STATE.md",
    "STATE_ARCHITECTURE.md",
    "STATE_PROJECT_SYNC.md",
    "STATE_DOCUMENTATION.md",
    "STATE_DEVELOPMENT.md",
    "STATE_PIPELINE_ENGINE.md",
]


def read_document(
    path: Path
) -> str:
    """
    Read markdown document safely.
    """

    if not path.exists():
        return ""

    try:
        return path.read_text(
            encoding="utf-8"
        )

    except OSError:
        return ""


def extract_field(
    content: str,
    field: str
):
    """
    Extract a simple document field.
    """

    pattern = (
        rf"^{re.escape(field)}:\s*$"
        rf"\n+\s*(.+?)\s*$"
    )

    match = re.search(
        pattern,
        content,
        re.MULTILINE
    )

    if match:
        return match.group(1).strip()

    return None


def extract_document_version(
    content: str
):
    """
    Extract document version.
    """

    return extract_field(
        content,
        "Version"
    )


def extract_document_type(
    content: str
):
    """
    Extract document type.
    """

    return extract_field(
        content,
        "Document Type"
    )


def extract_document_status(
    content: str
):
    """
    Extract document status.
    """

    return extract_field(
        content,
        "Status"
    )


def analyze_document(
    document: str
):
    """
    Analyze a single state document.
    """

    path = (
        DOCUMENTS_PATH
        / document
    )

    content = read_document(
        path
    )

    exists = path.exists()

    return {
        "document":
            document,

        "exists":
            exists,

        "version":
            extract_document_version(
                content
            ),

        "status":
            extract_document_status(
                content
            ),

        "document_type":
            extract_document_type(
                content
            ),

        "size":
            len(content),
    }


def detect_state_health(
    states: list[dict]
):
    """
    Detect state package health.
    """

    missing = [
        item["document"]
        for item in states
        if not item["exists"]
    ]

    invalid = [
        item["document"]
        for item in states
        if item["exists"]
        and (
            item["version"] is None
            or item["status"] is None
        )
    ]

    if missing:
        status = "WARNING"

    elif invalid:
        status = "WARNING"

    else:
        status = "HEALTHY"

    return {
        "status":
            status,

        "missing_documents":
            missing,

        "invalid_documents":
            invalid,

        "documents_checked":
            len(states),
    }


def detect_state_relations(
    states: list[dict]
):
    """
    Detect basic relations between state documents.
    """

    versions = {}

    statuses = {}

    for state in states:
        document = state["document"]

        versions[document] = state["version"]
        statuses[document] = state["status"]

    return {
        "versions":
            versions,

        "statuses":
            statuses,
    }


def analyze_states():
    """
    Build unified state intelligence model.
    """

    states = []

    for document in STATE_DOCUMENTS:
        states.append(
            analyze_document(
                document
            )
        )

    health = detect_state_health(
        states
    )

    relations = detect_state_relations(
        states
    )

    return {
        "component":
            "state_intelligence",

        "version":
            "2.1",

        "status":
            "READY",

        "documents_analyzed":
            len(states),

        "state_health":
            health,

        "state_relations":
            relations,

        "states":
            states,
    }


def save_report(
    report: dict
):
    """
    Save machine-readable state intelligence report.
    """

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def run():
    """
    Execute State Intelligence analysis.
    """

    report = analyze_states()

    save_report(
        report
    )

    return report


if __name__ == "__main__":

    result = run()

    print(
        "STATE INTELLIGENCE ENGINE"
    )

    print(
        f"Status: {result['state_health']['status']}"
    )

    print(
        f"Documents: {result['documents_analyzed']}"
    )