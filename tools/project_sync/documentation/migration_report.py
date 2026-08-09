"""
BybitScanner Project Sync Framework

Migration Report Generator
"""

from pathlib import Path
import json


def generate_report(plan_file: str):

    source = Path(plan_file)

    if not source.exists():
        return {
            "status": "ERROR",
            "message": "Migration plan not found"
        }

    plan = json.loads(
        source.read_text(
            encoding="utf-8"
        )
    )

    report = {
        "document": plan.get("document"),
        "migration_required": plan.get(
            "migration_required",
            False
        ),
        "planned_actions": plan.get(
            "actions",
            []
        ),
        "approval_required": True,
        "status": "READY_FOR_SYNCHRONIZATION"
    }

    return report


if __name__ == "__main__":

    import sys

    result = generate_report(
        sys.argv[1]
    )

    output = Path(
        "tools/project_sync/reports/migration_report.json"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_text(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )