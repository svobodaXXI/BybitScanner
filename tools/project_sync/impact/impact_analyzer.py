"""
BybitScanner Project Sync Framework

Document Impact Analyzer

Responsibility:
    Analyze the potential impact of project documents
    based on the document dependency graph.

This module:
    - reads document registry;
    - reads document dependency graph;
    - calculates impact level;
    - identifies affected documents;
    - exports impact report.

It does not:
    - modify documents;
    - update documentation;
    - perform automatic synchronization.
"""


from pathlib import Path
import json


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


REGISTRY_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_registry.json"
)


DEPENDENCY_REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_dependencies.json"
)


REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "impact_report.json"
)


def load_json(path: Path) -> dict:
    """
    Load JSON document.
    """

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def load_documents() -> list[dict]:
    """
    Load documents from document registry.
    """

    if not REGISTRY_PATH.exists():
        return []

    data = load_json(
        REGISTRY_PATH
    )

    return data.get(
        "documents",
        []
    )


def load_dependency_graph() -> list[dict]:
    """
    Load document dependency graph.
    """

    if not DEPENDENCY_REPORT_PATH.exists():
        return []

    data = load_json(
        DEPENDENCY_REPORT_PATH
    )

    return data.get(
        "documents",
        []
    )


def build_dependency_index(
    dependency_graph: list[dict]
) -> dict:
    """
    Build indexed dependency structure.
    """

    return {
        item["name"]: item
        for item in dependency_graph
        if "name" in item
    }


def calculate_impact_level(
    affected_count: int
) -> str:
    """
    Calculate impact level from affected document count.
    """

    if affected_count >= 3:
        return "HIGH"

    if affected_count >= 1:
        return "MEDIUM"

    return "LOW"


def analyze_impact(
    documents: list[dict] | None = None
) -> list[dict]:
    """
    Analyze document impact.

    The documents argument is optional.

    When omitted, the analyzer loads the current
    document registry automatically. This allows
    direct execution from the Project Sync Pipeline.
    """

    if documents is None:
        documents = load_documents()

    dependency_graph = load_dependency_graph()

    dependency_index = build_dependency_index(
        dependency_graph
    )

    impact = []

    document_names = {
        document.get("name")
        for document in documents
        if document.get("name")
    }

    for document_name in sorted(
        document_names
    ):

        node = dependency_index.get(
            document_name,
            {}
        )

        affected_documents = sorted(
            set(
                node.get(
                    "dependents",
                    []
                )
            )
        )

        affected_documents = [
            name
            for name in affected_documents
            if name in document_names
        ]

        affected_count = len(
            affected_documents
        )

        impact.append(
            {
                "document": document_name,

                "impact_level":
                    calculate_impact_level(
                        affected_count
                    ),

                "affected_documents":
                    affected_documents,

                "affected_count":
                    affected_count,
            }
        )

    return impact


def save_report(
    impact: list[dict]
) -> dict:
    """
    Save impact analysis report.
    """

    report = {
        "analyzer":
            "document_impact_analyzer",

        "documents_analyzed":
            len(impact),

        "impact":
            impact,
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    return report


def build_impact_report(
    documents: list[dict] | None = None
) -> dict:
    """
    Build and save complete impact report.
    """

    impact = analyze_impact(
        documents
    )

    return save_report(
        impact
    )


def main():
    """
    Standalone analyzer entry point.
    """

    report = build_impact_report()

    print(
        f"Impact analyzed: "
        f"{report['documents_analyzed']}"
    )

    return report


if __name__ == "__main__":
    main()