"""
BybitScanner Project Sync Framework

Impact Pipeline

Responsibility:
    Connect Change Detection
    with Impact Analysis.

This module:
    - reads change report;
    - extracts changed documents;
    - runs dependency impact calculation;
    - generates impact pipeline report.

It does not:
    - modify documents;
    - update documentation.
"""


from pathlib import Path
import json


PROJECT_ROOT = Path("C:/BybitScanner")


CHANGE_REPORT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "change_report.json"
)


DEPENDENCY_REPORT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_dependencies.json"
)


IMPACT_REPORT = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "impact_pipeline_report.json"
)



def load_json(path: Path) -> dict:
    """
    Load JSON artifact.
    """

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )



def find_dependents(
    document: str,
    dependencies: dict
) -> list[str]:
    """
    Find documents affected by change.
    """

    affected = []

    for item in dependencies.get(
        "documents",
        []
    ):

        if item.get("name") == document:

            affected.extend(
                item.get(
                    "dependents",
                    []
                )
            )


    return affected



def analyze_changes():
    """
    Run impact pipeline.
    """

    change_data = load_json(
        CHANGE_REPORT
    )

    dependency_data = load_json(
        DEPENDENCY_REPORT
    )


    changed_documents = [
        item["document"]
        for item in change_data.get(
            "changed_documents",
            []
        )
    ]


    affected_documents = []


    for document in changed_documents:

        affected_documents.extend(
            find_dependents(
                document,
                dependency_data
            )
        )


    affected_documents = sorted(
        set(affected_documents)
    )


    report = {

        "pipeline":
            "change_to_impact",

        "changed_documents":
            changed_documents,

        "affected_documents":
            affected_documents,

        "impact_count":
            len(affected_documents)

    }


    IMPACT_REPORT.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


    return report



if __name__ == "__main__":

    result = analyze_changes()

    print(
        f"Affected documents: {result['impact_count']}"
    )