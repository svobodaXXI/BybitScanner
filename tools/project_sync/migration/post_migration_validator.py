"""
BybitScanner Project Sync Framework

Post Migration Validator

Responsibility:
    Validate completed document migrations.

Flow:

    migration_execution_report.json
            ↓
    Post Migration Validation
            ↓
    Validation Report

This module:
    - validates migration execution status;
    - distinguishes EXECUTED from NO_UPDATES;
    - distinguishes NO_UPDATES from NOT_REQUIRED;
    - validates migrated documents;
    - validates updated document results;
    - validates created backups when migration was executed;
    - validates that every executed update belongs
      to the approved migration scope;
    - checks for execution errors;
    - creates a machine-readable validation result.

It does not:
    - modify documents;
    - execute migration;
    - create backups;
    - bypass Migration Control.
"""


from pathlib import Path
import json
import sys
from typing import Any


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


DOCUMENTS_ROOT = (
    PROJECT_ROOT
    /
    "DOCUMENTS"
)


REPORT_DIR = (
    PROJECT_ROOT
    /
    "tools"
    /
    "project_sync"
    /
    "reports"
)


EXECUTION_REPORT = (
    REPORT_DIR
    /
    "migration_execution_report.json"
)


VALIDATION_REPORT = (
    REPORT_DIR
    /
    "post_migration_validation_report.json"
)


class PostMigrationValidator:
    """
    Validate completed migration execution.
    """

    def __init__(
        self,
        execution_report: dict[str, Any]
    ):

        self.report = (
            execution_report
            if isinstance(
                execution_report,
                dict
            )
            else {}
        )

        self.result = {

            "component":
                "post_migration_validator",

            "version":
                "2.4",

            "status":
                "INITIALIZED",

            "migration_required":
                self.report.get(
                    "migration_required"
                ),

            "documents":
                [],

            "checks":
                {},

            "errors":
                []
        }

    def validate_execution_status(
        self
    ) -> bool:
        """
        Validate migration execution status.
        """

        status = self.report.get(
            "status",
            ""
        )

        migration_required = self.report.get(
            "migration_required"
        )

        if status == "NOT_REQUIRED":

            if migration_required is not False:

                self.result["errors"].append(
                    "invalid_not_required_state"
                )

                self.result["checks"][
                    "execution_status"
                ] = "FAILED"

                return False

            self.result["checks"][
                "execution_status"
            ] = "NOT_REQUIRED"

            return True

        if status == "NO_UPDATES":

            if migration_required is not True:

                self.result["errors"].append(
                    "invalid_no_updates_state"
                )

                self.result["checks"][
                    "execution_status"
                ] = "FAILED"

                return False

            self.result["checks"][
                "execution_status"
            ] = "NO_UPDATES"

            return True

        if status == "EXECUTED":

            if migration_required is not True:

                self.result["errors"].append(
                    "invalid_executed_state"
                )

                self.result["checks"][
                    "execution_status"
                ] = "FAILED"

                return False

            self.result["checks"][
                "execution_status"
            ] = "SUCCESS"

            return True

        self.result["errors"].append(
            "migration_execution_invalid"
        )

        self.result["checks"][
            "execution_status"
        ] = "FAILED"

        return False

    def resolve_document(
        self,
        document: str
    ):
        """
        Resolve project document path safely.

        Supports:

            PROJECT_ROOT / document
            DOCUMENTS_ROOT / document

        Absolute paths and paths escaping
        project roots are rejected.
        """

        if not isinstance(
            document,
            str
        ):

            return None

        try:

            requested = Path(
                document
            )

            if requested.is_absolute():

                return None

            project_root = (
                PROJECT_ROOT.resolve()
            )

            documents_root = (
                DOCUMENTS_ROOT.resolve()
            )

            candidates = [

                (
                    project_root
                    /
                    requested
                ).resolve(),

                (
                    documents_root
                    /
                    requested
                ).resolve()

            ]

        except (
            OSError,
            RuntimeError
        ):

            return None

        for path in candidates:

            try:

                if not path.is_relative_to(
                    project_root
                ):

                    continue

                if not (
                    path.exists()
                    and
                    path.is_file()
                ):

                    continue

                return path

            except (
                OSError,
                RuntimeError
            ):

                continue

        return None

    def validate_documents(
        self
    ) -> bool:
        """
        Validate project documents.
        """

        documents = self.report.get(
            "documents",
            []
        )

        status = self.report.get(
            "status",
            ""
        )

        if not isinstance(
            documents,
            list
        ):

            self.result["errors"].append(
                "invalid_documents_format"
            )

            self.result["checks"][
                "documents"
            ] = "FAILED"

            return False

        self.result["documents"] = (
            documents
        )

        if status == "NOT_REQUIRED":

            if documents:

                self.result["errors"].append(
                    "unexpected_documents_for_not_required"
                )

                self.result["checks"][
                    "documents"
                ] = "FAILED"

                return False

            self.result["checks"][
                "documents"
            ] = "NOT_REQUIRED"

            return True

        if not documents:

            self.result["errors"].append(
                "migration_documents_empty"
            )

            self.result["checks"][
                "documents"
            ] = "FAILED"

            return False

        valid = True

        for document in documents:

            if not isinstance(
                document,
                str
            ):

                self.result["errors"].append(
                    "invalid_document_entry"
                )

                valid = False

                continue

            if self.resolve_document(
                document
            ) is None:

                self.result["errors"].append(
                    f"document_not_found:{document}"
                )

                valid = False

        self.result["checks"][
            "documents"
        ] = (
            "SUCCESS"
            if valid
            else
            "FAILED"
        )

        return valid

    def validate_updates(
        self
    ) -> bool:
        """
        Validate prepared update instructions
        against the reported migration document scope.
        """

        status = self.report.get(
            "status",
            ""
        )

        updates = self.report.get(
            "updates",
            {}
        )

        documents = self.report.get(
            "documents",
            []
        )

        if not isinstance(
            updates,
            dict
        ):

            self.result["errors"].append(
                "invalid_updates_format"
            )

            self.result["checks"][
                "updates"
            ] = "FAILED"

            return False

        if not isinstance(
            documents,
            list
        ):

            self.result["errors"].append(
                "invalid_documents_format"
            )

            self.result["checks"][
                "updates"
            ] = "FAILED"

            return False

        approved_documents = set(
            document
            for document in documents
            if isinstance(
                document,
                str
            )
        )

        if status == "NOT_REQUIRED":

            if updates:

                self.result["errors"].append(
                    "unexpected_updates_for_not_required"
                )

                self.result["checks"][
                    "updates"
                ] = "FAILED"

                return False

            self.result["checks"][
                "updates"
            ] = "NOT_REQUIRED"

            return True

        if status == "NO_UPDATES":

            if updates:

                self.result["errors"].append(
                    "unexpected_updates_for_no_updates"
                )

                self.result["checks"][
                    "updates"
                ] = "FAILED"

                return False

            self.result["checks"][
                "updates"
            ] = "NO_UPDATES"

            return True

        if status != "EXECUTED":

            self.result["errors"].append(
                "invalid_update_validation_state"
            )

            self.result["checks"][
                "updates"
            ] = "FAILED"

            return False

        if not updates:

            self.result["errors"].append(
                "executed_without_updates"
            )

            self.result["checks"][
                "updates"
            ] = "FAILED"

            return False

        valid = True

        for document, update in updates.items():

            if not isinstance(
                document,
                str
            ):

                self.result["errors"].append(
                    "invalid_update_document_entry"
                )

                valid = False

                continue

            if document not in approved_documents:

                self.result["errors"].append(
                    f"update_target_not_approved:{document}"
                )

                valid = False

            if isinstance(
                update,
                str
            ):

                continue

            if (
                isinstance(
                    update,
                    dict
                )
                and
                isinstance(
                    update.get(
                        "content"
                    ),
                    str
                )
            ):

                continue

            self.result["errors"].append(
                f"invalid_update:{document}"
            )

            valid = False

        self.result["checks"][
            "updates"
        ] = (
            "SUCCESS"
            if valid
            else
            "FAILED"
        )

        return valid

    def validate_updated_documents(
        self
    ) -> bool:
        """
        Validate the actual updated document list.
        """

        status = self.report.get(
            "status",
            ""
        )

        updated = self.report.get(
            "updated",
            []
        )

        documents = self.report.get(
            "documents",
            []
        )

        if not isinstance(
            updated,
            list
        ):

            self.result["errors"].append(
                "invalid_updated_format"
            )

            self.result["checks"][
                "updated_documents"
            ] = "FAILED"

            return False

        if not isinstance(
            documents,
            list
        ):

            self.result["errors"].append(
                "invalid_documents_format"
            )

            self.result["checks"][
                "updated_documents"
            ] = "FAILED"

            return False

        approved_paths = set()

        for document in documents:

            if not isinstance(
                document,
                str
            ):

                continue

            resolved = self.resolve_document(
                document
            )

            if resolved is not None:

                approved_paths.add(
                    str(
                        resolved.resolve()
                    )
                )

        if status in {
            "NOT_REQUIRED",
            "NO_UPDATES"
        }:

            if updated:

                self.result["errors"].append(
                    "unexpected_updated_documents"
                )

                self.result["checks"][
                    "updated_documents"
                ] = "FAILED"

                return False

            self.result["checks"][
                "updated_documents"
            ] = (
                "NOT_REQUIRED"
                if status == "NOT_REQUIRED"
                else
                "NO_UPDATES"
            )

            return True

        if status != "EXECUTED":

            self.result["errors"].append(
                "invalid_updated_validation_state"
            )

            self.result["checks"][
                "updated_documents"
            ] = "FAILED"

            return False

        if not updated:

            self.result["errors"].append(
                "executed_without_updated_documents"
            )

            self.result["checks"][
                "updated_documents"
            ] = "FAILED"

            return False

        valid = True

        for updated_document in updated:

            if not isinstance(
                updated_document,
                str
            ):

                self.result["errors"].append(
                    "invalid_updated_document_entry"
                )

                valid = False

                continue

            try:

                updated_path = Path(
                    updated_document
                ).resolve()

            except (
                OSError,
                RuntimeError
            ):

                self.result["errors"].append(
                    f"updated_document_resolution_failed:{updated_document}"
                )

                valid = False

                continue

            if not (
                updated_path.exists()
                and
                updated_path.is_file()
            ):

                self.result["errors"].append(
                    f"updated_document_not_found:{updated_document}"
                )

                valid = False

                continue

            try:

                if not updated_path.is_relative_to(
                    PROJECT_ROOT.resolve()
                ):

                    self.result["errors"].append(
                        f"updated_document_outside_project:{updated_document}"
                    )

                    valid = False

                    continue

            except (
                OSError,
                RuntimeError
            ):

                self.result["errors"].append(
                    f"updated_document_resolution_failed:{updated_document}"
                )

                valid = False

                continue

            if str(
                updated_path
            ) not in approved_paths:

                self.result["errors"].append(
                    f"updated_document_not_approved:{updated_document}"
                )

                valid = False

        self.result["checks"][
            "updated_documents"
        ] = (
            "SUCCESS"
            if valid
            else
            "FAILED"
        )

        return valid

    def validate_backups(
        self
    ) -> bool:
        """
        Validate migration backups.
        """

        status = self.report.get(
            "status",
            ""
        )

        backups = self.report.get(
            "backups",
            []
        )

        if not isinstance(
            backups,
            list
        ):

            self.result["errors"].append(
                "invalid_backups_format"
            )

            self.result["checks"][
                "backups"
            ] = "FAILED"

            return False

        if status in {
            "NOT_REQUIRED",
            "NO_UPDATES"
        }:

            if backups:

                self.result["errors"].append(
                    "unexpected_backups_without_document_updates"
                )

                self.result["checks"][
                    "backups"
                ] = "FAILED"

                return False

            self.result["checks"][
                "backups"
            ] = (
                "NOT_REQUIRED"
                if status == "NOT_REQUIRED"
                else
                "NO_UPDATES"
            )

            return True

        if status != "EXECUTED":

            self.result["errors"].append(
                "invalid_backup_validation_state"
            )

            self.result["checks"][
                "backups"
            ] = "FAILED"

            return False

        if not backups:

            self.result["errors"].append(
                "migration_backups_empty"
            )

            self.result["checks"][
                "backups"
            ] = "FAILED"

            return False

        valid = True

        for backup in backups:

            if not isinstance(
                backup,
                str
            ):

                self.result["errors"].append(
                    "invalid_backup_entry"
                )

                valid = False

                continue

            backup_path = Path(
                backup
            )

            if not (
                backup_path.exists()
                and
                backup_path.is_file()
            ):

                self.result["errors"].append(
                    f"backup_not_found:{backup}"
                )

                valid = False

        self.result["checks"][
            "backups"
        ] = (
            "SUCCESS"
            if valid
            else
            "FAILED"
        )

        return valid

    def validate_execution_errors(
        self
    ) -> bool:
        """
        Validate migration execution errors.
        """

        errors = self.report.get(
            "errors",
            []
        )

        if not isinstance(
            errors,
            list
        ):

            self.result["errors"].append(
                "invalid_errors_format"
            )

            self.result["checks"][
                "execution_errors"
            ] = "FAILED"

            return False

        if errors:

            for error in errors:

                self.result["errors"].append(
                    f"execution_error:{error}"
                )

            self.result["checks"][
                "execution_errors"
            ] = "FAILED"

            return False

        self.result["checks"][
            "execution_errors"
        ] = "SUCCESS"

        return True

    def validate(
        self
    ):
        """
        Execute complete post-migration validation.
        """

        execution_ok = (
            self.validate_execution_status()
        )

        documents_ok = (
            self.validate_documents()
        )

        updates_ok = (
            self.validate_updates()
        )

        updated_documents_ok = (
            self.validate_updated_documents()
        )

        backups_ok = (
            self.validate_backups()
        )

        errors_ok = (
            self.validate_execution_errors()
        )

        if not (
            execution_ok
            and
            documents_ok
            and
            updates_ok
            and
            updated_documents_ok
            and
            backups_ok
            and
            errors_ok
            and
            not self.result["errors"]
        ):

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        execution_status = (
            self.report.get(
                "status"
            )
        )

        if execution_status == "NOT_REQUIRED":

            self.result["status"] = (
                "NOT_REQUIRED"
            )

            return self.result

        if execution_status == "NO_UPDATES":

            self.result["status"] = (
                "NO_UPDATES"
            )

            return self.result

        self.result["status"] = (
            "VALIDATED"
        )

        return self.result


def load_execution_report(
    path: Path
) -> dict[str, Any]:
    """
    Load migration execution report safely.
    """

    if not path.exists():

        return {}

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError
    ):

        return {}

    return (
        data
        if isinstance(
            data,
            dict
        )
        else {}
    )


def validate_migration(
    execution_report: dict[str, Any]
):
    """
    Validate migration execution report.
    """

    return PostMigrationValidator(
        execution_report
    ).validate()


def save_report(
    result: dict
):
    """
    Save post-migration validation report.
    """

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    VALIDATION_REPORT.write_text(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


if __name__ == "__main__":

    report_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else EXECUTION_REPORT
    )

    execution_report = load_execution_report(
        report_path
    )

    if not execution_report:

        result = {

            "component":
                "post_migration_validator",

            "version":
                "2.4",

            "status":
                "FAILED",

            "migration_required":
                None,

            "documents":
                [],

            "checks":
                {},

            "errors":
                [
                    "migration_execution_report_not_found"
                ]
        }

    else:

        result = validate_migration(
            execution_report
        )

    save_report(
        result
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )