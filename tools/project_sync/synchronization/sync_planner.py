from pathlib import Path
import json

PROJECT_ROOT = Path("C:/BybitScanner")
REPORTS_DIR = PROJECT_ROOT / "tools" / "project_sync" / "reports"

IMPACT_REPORT = REPORTS_DIR / "impact_report.json"
CHANGE_REPORT = REPORTS_DIR / "change_report.json"
STATE_REPORT = REPORTS_DIR / "state_intelligence_report.json"
REPORT_PATH = REPORTS_DIR / "synchronization_plan.json"


def load_json(path):
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


def load_impact_report():
    return load_json(IMPACT_REPORT)


def load_change_report():
    return load_json(CHANGE_REPORT)


def load_state_report():
    return load_json(STATE_REPORT)


def collect_affected_documents(impact):
    affected = impact.get("affected_documents", [])

    if not isinstance(affected, list):
        return []

    return list(dict.fromkeys(
        document
        for document in affected
        if isinstance(document, str)
    ))


def collect_changed_documents(changes_report):
    changed = changes_report.get("changed_documents", [])

    if not isinstance(changed, list):
        return []

    result = []

    for entry in changed:
        if isinstance(entry, dict):
            document = entry.get("document")
            if isinstance(document, str):
                result.append(document)
        elif isinstance(entry, str):
            result.append(entry)

    return list(dict.fromkeys(result))


def extract_change_summary(changes_report):
    changed = changes_report.get("changed_documents", [])

    if not isinstance(changed, list):
        changed = []

    added = []
    removed = []
    modified = []

    for entry in changed:
        if isinstance(entry, str):
            modified.append(entry)
            continue

        if not isinstance(entry, dict):
            continue

        document = entry.get("document")
        change_type = str(
            entry.get("change_type", "")
        ).upper()

        if not isinstance(document, str):
            continue

        if change_type == "ADDED":
            added.append(document)
        elif change_type in ("DELETED", "REMOVED"):
            removed.append(document)
        elif change_type == "MODIFIED":
            modified.append(document)

    added = list(dict.fromkeys(added))
    removed = list(dict.fromkeys(removed))
    modified = list(dict.fromkeys(modified))

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "total_changes": (
            len(added)
            + len(removed)
            + len(modified)
        )
    }


def determine_actions(document, change_summary):
    actions = []

    changed_paths = []

    for field in ("added", "removed", "modified"):
        values = change_summary.get(field, [])

        if isinstance(values, list):
            changed_paths.extend(
                str(value).lower()
                for value in values
            )

    combined = " ".join(changed_paths)
    document_lower = document.lower()

    if (
        "project_state" in combined
        or "state" in combined
        or "project_state" in document_lower
    ):
        actions.append("synchronize_state_reference")

    if "metadata" in combined:
        actions.append("validate_document_metadata")

    if "machine" in combined:
        actions.append("validate_machine_readable_fields")

    if "version" in combined:
        actions.append("update_document_version")

    if not actions:
        actions = [
            "validate_structure",
            "preserve_document_content"
        ]

    return list(dict.fromkeys(actions))


def build_migration_entry(document, change_summary):
    return {
        "document": document,
        "changes": change_summary,
        "actions": determine_actions(
            document,
            change_summary
        ),
        "risk": "LOW",
        "approval_required": True
    }


def build_plan():
    impact = load_impact_report()
    changes_report = load_change_report()
    state_report = load_state_report()

    affected_documents = collect_affected_documents(impact)
    changed_documents = collect_changed_documents(changes_report)
    change_summary = extract_change_summary(changes_report)

    migration_plan = []

    for document in affected_documents:
        migration_plan.append(
            build_migration_entry(
                document,
                change_summary
            )
        )

    return {
        "component": "synchronization_planner",
        "version": "2.2",
        "sources": [
            "impact_report",
            "change_report",
            "state_intelligence_report"
        ],
        "state_health": state_report.get(
            "state_health",
            {}
        ),
        "documents_to_review": affected_documents,
        "changed_documents": changed_documents,
        "change_summary": change_summary,
        "migration_plan": migration_plan,
        "count": len(migration_plan),
        "migration_required": bool(migration_plan),
        "approval_required": bool(migration_plan),
        "status": "READY"
    }


def save_plan(plan):
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    REPORT_PATH.write_text(
        json.dumps(
            plan,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def create_sync_plan():
    plan = build_plan()
    save_plan(plan)
    return plan


if __name__ == "__main__":
    result = create_sync_plan()

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )
