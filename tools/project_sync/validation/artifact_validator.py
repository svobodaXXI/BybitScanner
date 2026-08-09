"""
BybitScanner Project Sync Framework

Artifact Validator

Validates project documentation artifacts.
Supports:
- MACHINE_READABLE documents
- LEGACY documents
"""

from pathlib import Path


REQUIRED_FIELDS = [
    "document_id",
    "purpose",
    "machine_readable",
    "parser_version",
    "version",
    "status",
]


class ArtifactValidator:
    """
    Validates documentation artifacts.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

        self.errors = []
        self.warnings = []

        self.document_type = None
        self.migration_required = False

    def load(self):
        if not self.file_path.exists():
            self.errors.append(
                f"File not found: {self.file_path}"
            )
            return None

        return self.file_path.read_text(
            encoding="utf-8"
        )

    def detect_document_type(self, content: str):
        if "# DOCUMENT_METADATA" in content:
            self.document_type = "MACHINE_READABLE"
        else:
            self.document_type = "LEGACY"
            self.migration_required = True

    def validate_metadata(self, content: str):

        if self.document_type != "MACHINE_READABLE":
            self.warnings.append(
                "Metadata validation skipped: legacy document format"
            )
            return

        for field in REQUIRED_FIELDS:
            if f"{field}:" not in content:
                self.errors.append(
                    f"Missing metadata field: {field}"
                )

    def validate_structure(self, content: str):

        if self.document_type == "MACHINE_READABLE":

            if "# END_OF_DOCUMENT" not in content:
                self.warnings.append(
                    "Missing END_OF_DOCUMENT marker"
                )

        else:
            self.warnings.append(
                "Legacy document structure detected"
            )

    def validate(self):

        content = self.load()

        if content is None:
            return self.result()

        self.detect_document_type(content)

        self.validate_metadata(content)

        self.validate_structure(content)

        return self.result()

    def result(self):

        if self.errors:
            status = "INVALID"

        elif self.migration_required:
            status = "WARNING"

        else:
            status = "VALID"

        return {
            "file": str(self.file_path),
            "document_type": self.document_type,
            "status": status,
            "migration_required": self.migration_required,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_artifact(file_path: str):
    validator = ArtifactValidator(file_path)
    return validator.validate()


if __name__ == "__main__":

    import sys
    import json

    target = sys.argv[1]

    result = validate_artifact(target)

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )