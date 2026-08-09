"""
BybitScanner Project Sync Framework

Document Validator

Responsibility:
    Validate official project documentation metadata.

This module:
    - reads document registry;
    - checks required metadata;
    - generates validation report.

It does not:
    - modify documents;
    - repair documents;
    - update versions.
"""


from pathlib import Path
import json


PROJECT_ROOT = Path("C:/BybitScanner")

REGISTRY_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_registry.json"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "validation_report.json"
)


REQUIRED_FIELDS = [
    "document_id",
    "document_type",
    "version",
    "status",
    "purpose",
    "last_update",
]


def load_registry():
    """
    Load document registry.
    """

    with open(
        REGISTRY_PATH,
        encoding="utf-8"
    ) as file:

        return json.load(file)


def validate_document(document):
    """
    Validate single document metadata.
    """

    errors = []
    warnings = []

    for field in REQUIRED_FIELDS:

        value = document.get(field, "")

        if not value:

            errors.append(field)

    if errors:

        return {
            "name": document["name"],
            "status": "WARNING",
            "missing_fields": errors
        }


    return {
        "name": document["name"],
        "status": "OK",
        "missing_fields": []
    }


def build_validation_report():

    registry = load_registry()

    results = []

    for document in registry["documents"]:

        results.append(
            validate_document(document)
        )


    report = {

        "validator":

        "document_validator",

        "documents_checked":

        len(results),

        "results":

        results

    }


    REPORT_PATH.parent.mkdir(
        exist_ok=True
    )


    with open(
        REPORT_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )


    return report



if __name__ == "__main__":

    report = build_validation_report()


    warnings = sum(
        1
        for item in report["results"]
        if item["status"] == "WARNING"
    )


    print(
        f"Documents checked: {report['documents_checked']}"
    )

    print(
        f"Warnings: {warnings}"
    )
