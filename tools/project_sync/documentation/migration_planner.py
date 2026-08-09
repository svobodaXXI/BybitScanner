"""
BybitScanner Project Sync Framework

Document Migration Planner

Creates migration plans for legacy documents.
"""

from pathlib import Path
import json


class MigrationPlanner:

    def __init__(self, document_path: str):
        self.document_path = Path(document_path)

    def analyze(self):

        if not self.document_path.exists():
            return {
                "status": "ERROR",
                "message": "Document not found"
            }

        content = self.document_path.read_text(
            encoding="utf-8"
        )

        legacy = "# DOCUMENT_METADATA" not in content

        return {
            "document": str(self.document_path),
            "legacy": legacy,
            "migration_required": legacy,
            "actions": self.build_actions(legacy)
        }

    def build_actions(self, legacy):

        if not legacy:
            return []

        return [
            "add_document_metadata",
            "add_machine_readable_fields",
            "validate_structure",
            "preserve_document_content",
            "update_version"
        ]


def create_migration_plan(document_path: str):

    planner = MigrationPlanner(document_path)

    return planner.analyze()


if __name__ == "__main__":

    import sys

    document = sys.argv[1]

    result = create_migration_plan(document)

    output = Path(
        "tools/project_sync/reports/migration_plan.json"
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