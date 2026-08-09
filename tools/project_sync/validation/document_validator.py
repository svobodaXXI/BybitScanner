"""
BybitScanner Project Sync Framework

Document Validator

Responsibility:
    Validate official project documentation
    against document registry rules.

This module:
    - reads document registry;
    - checks required metadata;
    - generates validation report.

It does not:
    - modify documents;
    - repair documents;
    - update registry.
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


STRICT_REQUIRED_FIELDS = [
    "document_id",
    "document_type",
    "version",
    "status",
    "purpose",
    "last_update",
]


LIGHT_REQUIRED_FIELDS = [
    "name",
]


def load_registry() -> list[dict]:
    """
    Load document registry.
    """

    data = json.loads(
        REGISTRY_PATH.read_text(
            encoding="utf-8"
        )
    )

    return data.get(
        "documents",
        []
    )


def validate_document(
    document: dict
) -> dict:
    """
    Validate single document.
    """

    validation_level = document.get(
        "validation_level",
        "STRICT"
    )


    if validation_level == "LIGHT":
        required_fields = LIGHT_REQUIRED_FIELDS

    else:
        required_fields = STRICT_REQUIRED_FIELDS


    missing = []


    for field in required_fields:

        if not document.get(field):

            missing.append(
                field
            )


    if missing:

        status = "WARNING"

    else:

        status = "OK"


    return {
        "name": document.get(
            "name"
        ),

        "status": status,

        "missing_fields": missing
    }


def build_validation_report():
    """
    Build validation report.
    """

    documents = load_registry()


    results = []


    for document in documents:

        results.append(
            validate_document(
                document
            )
        )


    report = {

        "validator":
            "document_validator",

        "documents_checked":
            len(results),

        "results":
            results
    }


    REPORT_PATH.write_text(

        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        ),

        encoding="utf-8"
    )


    return report



if __name__ == "__main__":

    report = build_validation_report()


    print(
        f"Validated documents: {report['documents_checked']}"
    )