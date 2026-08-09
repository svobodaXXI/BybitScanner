"""
BybitScanner Project Sync Framework

Impact Analyzer

Responsibility:
    Analyze possible impact of document changes
    using dependency graph.

This module:
    - reads document dependency registry;
    - finds affected documents;
    - generates impact report.

It does not:
    - modify documents;
    - update documentation;
    - detect changes itself.
"""


from pathlib import Path
import json


PROJECT_ROOT = Path("C:/BybitScanner")


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
    / "impact_report.json"
)



def load_dependencies() -> dict:
    """
    Load dependency registry.
    """

    return json.loads(
        DEPENDENCY_REPORT.read_text(
            encoding="utf-8"
        )
    )



def build_graph(data: dict) -> dict:
    """
    Build dependency graph.
    """

    graph = {}

    for document in data.get(
        "documents",
        []
    ):

        name = document["name"]

        graph[name] = (
            document.get(
                "dependents",
                []
            )
        )

    return graph



def collect_impact(
    graph: dict,
    changed_document: str
) -> list[str]:
    """
    Find all affected documents.
    """

    affected = set()

    queue = [
        changed_document
    ]


    while queue:

        current = queue.pop(0)


        for dependent in graph.get(
            current,
            []
        ):

            if dependent not in affected:

                affected.add(
                    dependent
                )

                queue.append(
                    dependent
                )


    return sorted(
        affected
    )



def analyze_impact(
    changed_document: str
):
    """
    Main impact analysis.
    """

    data = load_dependencies()

    graph = build_graph(
        data
    )


    affected = collect_impact(
        graph,
        changed_document
    )


    report = {

        "analyzer":
            "impact_analyzer",

        "changed_document":
            changed_document,

        "affected_documents":
            affected,

        "impact_count":
            len(affected)
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

    result = analyze_impact(
        "PROJECT_STATE.md"
    )

    print(
        f"Affected documents: {result['impact_count']}"
    )