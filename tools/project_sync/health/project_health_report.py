"""
BybitScanner Project Sync Framework

Project Health Report

Responsibility:
    Analyze current Project Sync subsystem state.

This module:
    - checks generated reports;
    - checks required subsystems;
    - builds health report.

It does not:
    - modify project files;
    - repair problems automatically.
"""


from pathlib import Path
import json


PROJECT_ROOT = Path("C:/BybitScanner")


REPORTS_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
)


OUTPUT_PATH = (
    REPORTS_PATH
    / "project_health_report.json"
)


REQUIRED_REPORTS = [
    "scan_report.json",
    "module_registry.json",
    "architecture_registry.json",
    "validation_report.json",
    "document_registry.json",
    "document_dependencies.json",
    "impact_report.json",
    "impact_pipeline_report.json",
    "change_report.json",
]


def check_reports() -> dict:
    """
    Check required Project Sync artifacts.
    """

    missing = []
    existing = []

    for report in REQUIRED_REPORTS:

        path = REPORTS_PATH / report

        if path.exists():
            existing.append(report)

        else:
            missing.append(report)

    return {
        "required": len(REQUIRED_REPORTS),
        "existing": len(existing),
        "missing": missing,
    }


def build_health_report() -> dict:
    """
    Build project health status.
    """

    report_check = check_reports()


    if report_check["missing"]:
        status = "WARNING"

    else:
        status = "OK"


    return {
        "analyzer": "project_health_report",

        "status": status,

        "reports": report_check,
    }


def save_report(data: dict):
    """
    Save health report artifact.
    """

    OUTPUT_PATH.parent.mkdir(
        exist_ok=True
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            data,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def main():

    report = build_health_report()

    save_report(
        report
    )

    print(
        f"Health status: {report['status']}"
    )


if __name__ == "__main__":

    main()