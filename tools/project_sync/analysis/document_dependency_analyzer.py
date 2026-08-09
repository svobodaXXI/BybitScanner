"""
BybitScanner Project Sync Framework

Document Dependency Analyzer

Version:
1.1

Responsibility:
    Analyze relationships between
    official project documents.

This module:
    - reads document registry;
    - applies dependency rules;
    - builds document dependency graph;
    - exports dependency report;
    - provides Pipeline Engine compatible interface.

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


REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_dependencies.json"
)



DEPENDENCY_RULES = {

    "PROJECT_RULES.md": [
        "ASSISTANT_PROTOCOL.md",
        "DOCUMENTATION_RULES.md",
        "CODE_RULES.md",
        "WORKFLOW_RULES.md",
    ],


    "PROJECT_CONTRACTS.md": [
        "ARCHITECTURE_RULES.md",
        "PROJECT_SYNC.md",
    ],


    "PROJECT_SYNC.md": [
        "PROJECT_SYNC_ARCHITECTURE.md",
        "PROJECT_STATE.md",
    ],


    "ARCHITECTURE_RULES.md": [
        "PROJECT_MAP.md",
        "MODULE_REGISTRY.md",
        "LAYER_REGISTRY.md",
    ],


    "ROADMAP.md": [
        "PROJECT_STATE.md",
        "SNAPSHOT.md",
    ],


    "CHANGELOG.md": [
        "SNAPSHOT.md",
        "PROJECT_STATE.md",
    ],

}



def load_registry() -> list[dict]:
    """
    Load document registry.
    """

    if not REGISTRY_PATH.exists():

        return []


    data = json.loads(
        REGISTRY_PATH.read_text(
            encoding="utf-8"
        )
    )


    return data.get(
        "documents",
        []
    )



def build_dependency_graph(
    documents: list[dict]
) -> list[dict]:
    """
    Build document dependency graph.
    """

    result = []


    document_names = {
        document["name"]
        for document in documents
    }


    for document in documents:

        name = document["name"]


        dependencies = [

            item

            for item in DEPENDENCY_RULES.get(
                name,
                []
            )

            if item in document_names

        ]


        result.append(
            {
                "name": name,

                "dependencies": dependencies,

                "dependents": [],
            }
        )


    for item in result:

        for dependency in item["dependencies"]:

            for target in result:

                if target["name"] == dependency:

                    target["dependents"].append(
                        item["name"]
                    )


    return result



def save_report(
    graph: list[dict]
):
    """
    Save dependency report.
    """

    REPORT_PATH.parent.mkdir(
        exist_ok=True
    )


    REPORT_PATH.write_text(

        json.dumps(

            {
                "analyzer":
                    "document_dependency_analyzer",

                "documents_analyzed":
                    len(graph),

                "documents":
                    graph,

            },

            indent=4,

            ensure_ascii=False,

        ),

        encoding="utf-8",
    )



def analyze_dependencies():
    """
    Main analyzer entry point.

    Used by:
        - standalone execution;
        - Pipeline Engine Stage.
    """

    documents = load_registry()


    graph = build_dependency_graph(
        documents
    )


    save_report(
        graph
    )


    return graph



def run_dependency_analysis():
    """
    Pipeline Engine compatible wrapper.
    """

    return analyze_dependencies()



if __name__ == "__main__":

    result = analyze_dependencies()


    print(
        f"Analyzed documents: {len(result)}"
    )