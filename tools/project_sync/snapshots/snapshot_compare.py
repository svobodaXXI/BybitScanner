"""
BybitScanner Project Sync Framework

Snapshot Compare Engine

Responsibility:
    Compare project snapshots and detect
    structural state changes.

This module:
    - loads previous snapshot;
    - loads current snapshot;
    - compares project state;
    - generates change report.

It does not:
    - modify project files;
    - update documentation;
    - perform synchronization.
"""


from pathlib import Path
import json


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


SNAPSHOT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "snapshots"
)


REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "change_report.json"
)



def load_snapshot(path: Path) -> dict:
    """
    Load snapshot file.
    """

    if not path.exists():
        return {}


    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )



def find_snapshots() -> list[Path]:
    """
    Find available snapshots.
    """

    if not SNAPSHOT_PATH.exists():
        return []


    return sorted(
        SNAPSHOT_PATH.glob(
            "*.json"
        )
    )



def compare_snapshots(
    previous: dict,
    current: dict
) -> dict:
    """
    Compare two snapshots.
    """

    previous_keys = set(
        previous.keys()
    )

    current_keys = set(
        current.keys()
    )


    return {

        "added":

            list(
                current_keys - previous_keys
            ),


        "removed":

            list(
                previous_keys - current_keys
            ),


        "changed":

            [
                key
                for key in previous_keys & current_keys
                if previous[key] != current[key]
            ]

    }



def save_report(
    result: dict
):
    """
    Save change report.
    """

    REPORT_PATH.parent.mkdir(
        exist_ok=True
    )


    REPORT_PATH.write_text(

        json.dumps(

            {
                "analyzer":
                    "snapshot_compare",

                "status":
                    "READY",

                "changes":
                    result

            },

            indent=4,

            ensure_ascii=False

        ),

        encoding="utf-8"

    )



def run_snapshot_compare():
    """
    Main execution.
    """

    snapshots = find_snapshots()


    if len(snapshots) < 2:

        result = {

            "added": [],

            "removed": [],

            "changed": [],

            "message":
                "Not enough snapshots for comparison."

        }

        save_report(result)

        return result



    previous = load_snapshot(
        snapshots[-2]
    )


    current = load_snapshot(
        snapshots[-1]
    )


    result = compare_snapshots(
        previous,
        current
    )


    save_report(
        result
    )


    return result



if __name__ == "__main__":

    result = run_snapshot_compare()


    print(
        "SNAPSHOT COMPARE ENGINE"
    )


    print(
        "Status: READY"
    )


    print(
        f"Changes: {len(result.get('changed', []))}"
    )