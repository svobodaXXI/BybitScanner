"""
BybitScanner Project Sync Framework

Document Registry

Responsibility:
    Scan project documentation
    and build structured document registry.

This module:
    - reads DOCUMENTS directory;
    - extracts document metadata;
    - classifies documents;
    - creates DocumentModel objects;
    - exports registry report.

It does not:
    - modify documents;
    - analyze dependencies;
    - perform impact analysis.
"""


from pathlib import Path
import json
import re

from tools.project_sync.models.document_model import DocumentModel


PROJECT_ROOT = Path("C:/BybitScanner")

DOCUMENTS_PATH = PROJECT_ROOT / "DOCUMENTS"

REPORT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "project_sync"
    / "reports"
    / "document_registry.json"
)


def read_document_text(path: Path) -> str:
    """
    Read document text with supported encodings.
    """

    encodings = [
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "cp1251",
    ]

    for encoding in encodings:

        try:
            return path.read_text(
                encoding=encoding
            )

        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "unknown",
        b"",
        0,
        1,
        f"Cannot decode document: {path}"
    )


def extract_field(content: str, field: str) -> str:
    """
    Extract simple metadata field.
    """

    pattern = rf"{field}:\s*\n?\s*(.+)"

    match = re.search(
        pattern,
        content,
        re.MULTILINE
    )

    if match:
        return match.group(1).strip()

    return ""


def classify_document(filename: str) -> tuple[str, str]:
    """
    Classify document type and validation level.
    """

    name = filename.upper()


    if name == "PROJECT_RULES.MD":
        return (
            "OFFICIAL_PROJECT_DOCUMENT",
            "STRICT"
        )


    if (
        "ARCHITECTURE" in name
        or name.endswith("_ARCH.MD")
    ):
        return (
            "ARCHITECTURE_DOCUMENT",
            "STRICT"
        )


    if (
        "CONTRACT" in name
    ):
        return (
            "CONTRACT_DOCUMENT",
            "STRICT"
        )


    if (
        "REGISTRY" in name
        or name in [
            "PROJECT_MAP.MD",
            "PROJECT_TREE.MD"
        ]
    ):
        return (
            "REGISTRY_DOCUMENT",
            "STRICT"
        )


    if name in [
        "README.MD",
        "DEVELOPMENT_GUIDE.MD",
        "TESTING_GUIDE.MD",
        "REQUIREMENTS.MD"
    ]:
        return (
            "REFERENCE_DOCUMENT",
            "LIGHT"
        )


    return (
        "OFFICIAL_PROJECT_DOCUMENT",
        "STRICT"
    )


def parse_document(path: Path) -> DocumentModel:
    """
    Convert markdown document into DocumentModel.
    """

    content = read_document_text(
        path
    )


    document_class, validation_level = classify_document(
        path.name
    )


    return DocumentModel(

        name=path.name,


        document_id=extract_field(
            content,
            "document_id"
        ),


        document_type=extract_field(
            content,
            "Document Type"
        ),


        document_class=document_class,


        validation_level=validation_level,


        version=extract_field(
            content,
            "Version"
        ),


        status=extract_field(
            content,
            "Status"
        ),


        purpose=extract_field(
            content,
            "purpose"
        ),


        location=str(path),


        last_update=extract_field(
            content,
            "Date"
        )
    )


def scan_documents() -> list[DocumentModel]:
    """
    Scan documents directory.
    """

    documents = []

    for file in DOCUMENTS_PATH.glob("*.md"):

        document = parse_document(
            file
        )

        documents.append(
            document
        )

    return documents



def save_registry(
    documents: list[DocumentModel]
):
    """
    Save document registry report.
    """

    REPORT_PATH.parent.mkdir(
        exist_ok=True
    )


    data = {
        "documents": [
            document.to_dict()
            for document in documents
        ]
    }


    REPORT_PATH.write_text(
        json.dumps(
            data,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )



def build_registry():
    """
    Main registry generation function.
    """

    documents = scan_documents()

    save_registry(
        documents
    )

    return documents



if __name__ == "__main__":

    registry = build_registry()

    print(
        f"Registered documents: {len(registry)}"
    )