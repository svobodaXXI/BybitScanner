"""
BybitScanner Project Sync Framework

Document Update Engine

Responsibility:
    Execute controlled document update workflow
    using an explicitly approved migration artifact.

Input:
    migration_approval.json
    migration update instructions

Output:
    document_update_report.json

This module:
    - validates explicit approval state;
    - resolves project documents;
    - validates requested updates;
    - creates document backups before modification;
    - applies only explicitly prepared updates;
    - preserves document encoding;
    - reports every update operation;
    - refuses to treat an empty update set as execution;
    - preserves migration_required=True for NO_UPDATES;
    - never modifies a document before all requested
      updates have passed validation.

It does not:
    - modify documents without explicit approval;
    - invent document content;
    - update unspecified documents;
    - bypass migration control.
"""


from pathlib import Path
from datetime import datetime
import json
import shutil
import sys


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


BACKUP_DIR = (
    PROJECT_ROOT
    /
    "Backups"
    /
    "document_updates"
)


UPDATE_REPORT = (
    REPORT_DIR
    /
    "document_update_report.json"
)


class DocumentUpdater:
    """
    Controlled document update engine.
    """

    def __init__(
        self,
        migration: dict
    ):

        self.migration = (
            migration
            if isinstance(
                migration,
                dict
            )
            else {}
        )

        self.result = {

            "component":
                "document_updater",

            "version":
                "2.4",

            "status":
                "INITIALIZED",

            "migration_required":
                True,

            "documents":
                [],

            "actions":
                [],

            "updates":
                {},

            "backups":
                [],

            "updated":
                [],

            "errors":
                []
        }

    def validate_approval(
        self
    ) -> bool:
        """
        Validate explicit migration approval.

        Approval is valid only when the approval
        controller has explicitly produced an
        APPROVED artifact.

        No single field is accepted as a substitute
        for explicit approval.
        """

        return (

            self.migration.get(
                "status"
            )
            ==
            "APPROVED"

            and

            self.migration.get(
                "decision"
            )
            ==
            "APPROVED"

            and

            self.migration.get(
                "approval"
            )
            is True

            and

            self.migration.get(
                "explicit_approval"
            )
            is True

            and

            self.migration.get(
                "automatic_approval",
                False
            )
            is False

            and

            self.migration.get(
                "migration_required"
            )
            is True

        )

    def resolve_document_path(
        self,
        document: str
    ):
        """
        Resolve document location.

        Supports:

            PROJECT_ROOT / document
            DOCUMENTS_ROOT / document

        Absolute paths and paths escaping the
        project/document roots are rejected.
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

            candidates = [

                (
                    PROJECT_ROOT
                    /
                    requested
                ).resolve(),

                (
                    DOCUMENTS_ROOT
                    /
                    requested
                ).resolve()

            ]

            project_root = (
                PROJECT_ROOT
                .resolve()
            )

            documents_root = (
                DOCUMENTS_ROOT
                .resolve()
            )

        except (
            OSError,
            RuntimeError
        ):

            return None

        for path in candidates:

            try:

                if path.is_relative_to(
                    project_root
                ) and (
                    path.exists()
                    and
                    path.is_file()
                ):

                    return path

                if path.is_relative_to(
                    documents_root
                ) and (
                    path.exists()
                    and
                    path.is_file()
                ):

                    return path

            except (
                OSError,
                RuntimeError
            ):

                continue

        return None

    def backup_document(
        self,
        document: str
    ):
        """
        Create a timestamped document backup.
        """

        source = self.resolve_document_path(
            document
        )

        if source is None:

            self.result["errors"].append(
                f"document_not_found:{document}"
            )

            return None

        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        backup = (
            BACKUP_DIR
            /
            f"{source.name}.{timestamp}.bak"
        )

        try:

            shutil.copy2(
                source,
                backup
            )

        except Exception as error:

            self.result["errors"].append(
                f"backup_failed:{document}:{error}"
            )

            return None

        self.result["backups"].append(
            str(backup)
        )

        return backup

    def get_updates(
        self
    ) -> dict:
        """
        Read explicitly supplied document updates.

        Supported migration fields:

            updates
            document_updates

        Expected structure:

            {
                "DOCUMENTS/PROJECT_STATE.md": {
                    "content": "..."
                }
            }

        or:

            {
                "DOCUMENTS/PROJECT_STATE.md": "..."
            }
        """

        updates = self.migration.get(
            "updates"
        )

        if updates is None:

            updates = self.migration.get(
                "document_updates"
            )

        if updates is None:

            return {}

        if not isinstance(
            updates,
            dict
        ):

            self.result["errors"].append(
                "invalid_updates_format"
            )

            return {}

        return updates

    def normalize_update(
        self,
        update
    ):
        """
        Normalize one update instruction.

        Accepted forms:

            "new document content"

        or:

            {
                "content": "new document content"
            }
        """

        if isinstance(
            update,
            str
        ):

            return update

        if isinstance(
            update,
            dict
        ):

            content = update.get(
                "content"
            )

            if isinstance(
                content,
                str
            ):

                return content

        return None

    def validate_update_targets(
        self,
        updates: dict
    ) -> bool:
        """
        Validate that every requested update
        points to an existing project document.
        """

        valid = True

        for document in updates:

            if not isinstance(
                document,
                str
            ):

                self.result["errors"].append(
                    "invalid_document_target"
                )

                valid = False

                continue

            source = self.resolve_document_path(
                document
            )

            if source is None:

                self.result["errors"].append(
                    f"document_not_found:{document}"
                )

                valid = False

        return valid

    def validate_update_content(
        self,
        updates: dict
    ) -> bool:
        """
        Validate all update instructions
        before any document is modified.
        """

        valid = True

        for document, update in updates.items():

            content = self.normalize_update(
                update
            )

            if content is None:

                self.result["errors"].append(
                    f"invalid_update:{document}"
                )

                valid = False

        return valid

    def validate_document_targets_match(
        self,
        updates: dict
    ) -> bool:
        """
        Validate that every update target is
        explicitly included in the approved
        document list.

        The updater never expands the approved
        migration scope.
        """

        documents = self.migration.get(
            "documents",
            []
        )

        if not isinstance(
            documents,
            list
        ):

            self.result["errors"].append(
                "invalid_documents_format"
            )

            return False

        approved_documents = set(
            document
            for document in documents
            if isinstance(
                document,
                str
            )
            and document
        )

        valid = True

        for document in updates:

            if document not in approved_documents:

                self.result["errors"].append(
                    f"update_target_not_approved:{document}"
                )

                valid = False

        return valid

    def write_document(
        self,
        document: str,
        content: str
    ) -> bool:
        """
        Apply one explicitly approved document update.
        """

        source = self.resolve_document_path(
            document
        )

        if source is None:

            self.result["errors"].append(
                f"document_not_found:{document}"
            )

            return False

        if not isinstance(
            content,
            str
        ):

            self.result["errors"].append(
                f"invalid_content:{document}"
            )

            return False

        try:

            source.write_text(
                content,
                encoding="utf-8"
            )

        except Exception as error:

            self.result["errors"].append(
                f"write_failed:{document}:{error}"
            )

            return False

        self.result["updated"].append(
            str(source)
        )

        return True

    def execute(
        self
    ):
        """
        Execute controlled document update workflow.

        An approved migration with no explicitly
        prepared updates is a no-op and is reported
        as NO_UPDATES.

        NO_UPDATES does not mean that migration
        became unnecessary. The migration remains
        required, but no document update was executed.
        """

        if not self.validate_approval():

            self.result["status"] = (
                "WAITING_APPROVAL"
            )

            self.result["migration_required"] = (
                True
            )

            return self.result

        documents = self.migration.get(
            "documents",
            []
        )

        actions = self.migration.get(
            "actions",
            []
        )

        if not isinstance(
            documents,
            list
        ):

            self.result["errors"].append(
                "invalid_documents_format"
            )

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        if not isinstance(
            actions,
            list
        ):

            self.result["errors"].append(
                "invalid_actions_format"
            )

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        self.result["documents"] = (
            documents
        )

        self.result["actions"] = (
            actions
        )

        updates = self.get_updates()

        self.result["updates"] = (
            updates
        )

        if self.result["errors"]:

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        if not updates:

            self.result["status"] = (
                "NO_UPDATES"
            )

            self.result["migration_required"] = (
                True
            )

            return self.result

        if not self.validate_update_targets(
            updates
        ):

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        if not self.validate_document_targets_match(
            updates
        ):

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        if not self.validate_update_content(
            updates
        ):

            self.result["status"] = (
                "FAILED"
            )

            return self.result

        for document in updates:

            backup = self.backup_document(
                document
            )

            if backup is None:

                self.result["status"] = (
                    "FAILED"
                )

                return self.result

        for document, update in updates.items():

            content = self.normalize_update(
                update
            )

            if not self.write_document(
                document,
                content
            ):

                self.result["status"] = (
                    "FAILED"
                )

                return self.result

        self.result["status"] = (
            "UPDATED"
        )

        self.result["migration_required"] = (
            True
        )

        return self.result


def save_report(
    result: dict
):
    """
    Save document update report.
    """

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    UPDATE_REPORT.write_text(

        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        ),

        encoding="utf-8"
    )


def update_document(
    migration: dict
):
    """
    Execute document update workflow
    and persist the resulting report.
    """

    result = DocumentUpdater(
        migration
    ).execute()

    save_report(
        result
    )

    return result


if __name__ == "__main__":

    if len(sys.argv) < 2:

        print(
            "Usage: document_updater.py migration.json"
        )

        raise SystemExit(1)

    migration_file = Path(
        sys.argv[1]
    )

    if not migration_file.exists():

        print(
            f"Migration file not found: {migration_file}"
        )

        raise SystemExit(1)

    try:

        migration = json.loads(
            migration_file.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:

        print(
            f"Invalid migration JSON: {error}"
        )

        raise SystemExit(1)

    if not isinstance(
        migration,
        dict
    ):

        print(
            "Invalid migration JSON: root must be an object"
        )

        raise SystemExit(1)

    result = update_document(
        migration
    )

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
    )