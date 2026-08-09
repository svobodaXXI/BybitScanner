"""
BybitScanner Project Sync Framework

Sync State Builder

Responsibility:
    Build unified Project Sync system state.

This module:
    - collects existing reports;
    - combines subsystem results;
    - creates unified state artifact.

It does not:
    - scan project files;
    - modify documents;
    - perform validation.
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


STATE_PATH = (
    REPORTS_PATH
    / "project_sync_state.json"
)


def load_report(filename: str) -> dict:
    """
    Load report JSON file.
    """

    path = REPORTS_PATH / filename

    if not path.exists():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def build_state() -> dict:
    """
    Build unified Project Sync state.
    """

    document_registry = load_report(
        "document_registry.json"
    )

    validation = load_report(
        "validation_report.json"
    )

    dependencies = load_report(
        "document_dependencies.json"
    )

    impact = load_report(
        "impact_report.json"
    )

    changes = load_report(
        "change_report.json"
    )

    health = load_report(
        "project_health_report.json"
    )


    state = {

        "system":
            "Project Sync Framework",

        "status":
            health.get(
                "status",
                "UNKNOWN"
            ),


        "documents":
            len(
                document_registry.get(
                    "documents",
                    []
                )
            ),


        "validation":
            {
                "status":
                    "AVAILABLE"
                    if validation
                    else "MISSING"
            },


        "dependencies":
            {
                "status":
                    "AVAILABLE"
                    if dependencies
                    else "MISSING"
            },


        "impact":
            {
                "affected_documents":
                    impact.get(
                        "impact_count",
                        0
                    )
            },


        "changes":
            {
                "detected":
                    changes.get(
                        "change_count",
                        0
                    )
            },


        "health":
            {
                "status":
                    health.get(
                        "status",
                        "UNKNOWN"
                    )
            },


        "reports":
            {
                "document_registry":
                    True,

                "validation":
                    bool(validation),

                "dependencies":
                    bool(dependencies),

                "impact":
                    bool(impact),

                "changes":
                    bool(changes),

                "health":
                    bool(health)
            }
    }


    return state



def save_state(state: dict):
    """
    Save unified state artifact.
    """

    STATE_PATH.write_text(
        json.dumps(
            state,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )



def main():

    state = build_state()

    save_state(
        state
    )

    print(
        "Project Sync state created:"
    )

    print(
        STATE_PATH
    )



if __name__ == "__main__":

    main()