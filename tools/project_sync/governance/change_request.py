"""Read-only parser and validator for durable ChangeRequest Markdown files."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


METADATA_PATTERN = re.compile(
    r"<!-- CHANGE_REQUEST_METADATA_BEGIN -->\s*"
    r"```json\s*(?P<payload>.*?)\s*```\s*"
    r"<!-- CHANGE_REQUEST_METADATA_END -->",
    re.DOTALL,
)

ALLOWED_STATUSES = {
    "DRAFT",
    "AWAITING_APPROVAL",
    "APPROVED_NOT_IMPLEMENTED",
    "IN_PROGRESS",
    "IMPLEMENTED_AWAITING_VERIFICATION",
    "VERIFIED",
    "RECORDED",
    "CLOSED",
    "REJECTED",
    "CANCELLED",
    "SUPERSEDED",
    "BLOCKED",
}

ALLOWED_LIFECYCLE_STAGES = {
    "TASK",
    "SPEC",
    "CONTEXT",
    "IMPLEMENT",
    "VERIFY",
    "RECORD",
}

REQUIRED_TEXT_FIELDS = {
    "schema_version",
    "id",
    "title",
    "status",
    "revision",
    "lifecycle_stage",
    "objective",
    "current_phase",
    "current_checkpoint",
    "implementation_status",
    "next_phase",
    "next_phase_authorization",
}

REQUIRED_LIST_FIELDS = {
    "non_goals",
    "approved_scope",
    "prohibited_scope",
    "authoritative_references",
    "approved_decisions",
    "unresolved_decisions",
    "acceptance_criteria",
    "verification_requirements",
    "risks",
    "rollback_boundaries",
    "implementation_phases",
    "related_commits",
    "amendment_history",
}

REVISION_PATTERN = re.compile(r"^[1-9]\d*\.\d+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
COMPLETED_CHECKPOINT_PATTERN = re.compile(r"^(PHASE_\d+)_COMPLETED$")


@dataclass(frozen=True)
class ValidationResult:
    status: str
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.status == "PASS"


def load_change_request(path: str | Path) -> dict[str, Any]:
    """Load the JSON metadata block from a durable ChangeRequest Markdown file."""

    content = Path(path).read_text(encoding="utf-8")
    match = METADATA_PATTERN.search(content)
    if match is None:
        raise ValueError("ChangeRequest metadata block is missing")
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed ChangeRequest metadata JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("ChangeRequest metadata must be a JSON object")
    return payload


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _phase_ids(phases: Any) -> list[str]:
    if not isinstance(phases, list):
        return []
    return [
        phase.get("id", "")
        for phase in phases
        if isinstance(phase, dict) and _is_non_empty_text(phase.get("id"))
    ]


def validate_change_request(data: Mapping[str, Any]) -> ValidationResult:
    """Validate stable ChangeRequest v1 invariants without semantic inference."""

    errors: list[str] = []

    for field in sorted(REQUIRED_TEXT_FIELDS):
        if not _is_non_empty_text(data.get(field)):
            errors.append(f"Missing or empty text field: {field}")

    for field in sorted(REQUIRED_LIST_FIELDS):
        value = data.get(field)
        if not isinstance(value, list):
            errors.append(f"Missing or invalid list field: {field}")
        elif field != "unresolved_decisions" and field != "amendment_history" and not value:
            errors.append(f"Required list must not be empty: {field}")

    status = data.get("status")
    if _is_non_empty_text(status) and status not in ALLOWED_STATUSES:
        errors.append(f"Invalid status: {status}")

    lifecycle_stage = data.get("lifecycle_stage")
    if _is_non_empty_text(lifecycle_stage) and lifecycle_stage not in ALLOWED_LIFECYCLE_STAGES:
        errors.append(f"Invalid lifecycle_stage: {lifecycle_stage}")

    revision = data.get("revision")
    if _is_non_empty_text(revision) and REVISION_PATTERN.fullmatch(revision) is None:
        errors.append(f"Invalid revision: {revision}")

    phase_ids = _phase_ids(data.get("implementation_phases"))
    if len(phase_ids) != len(set(phase_ids)):
        errors.append("Duplicate implementation phase IDs")

    current_phase = data.get("current_phase")
    next_phase = data.get("next_phase")
    if phase_ids:
        if current_phase not in phase_ids:
            errors.append("current_phase is not declared in implementation_phases")
        if next_phase not in phase_ids:
            errors.append("next_phase is not declared in implementation_phases")
        if current_phase in phase_ids and next_phase in phase_ids:
            if phase_ids.index(next_phase) <= phase_ids.index(current_phase):
                errors.append("next_phase must follow current_phase")

    checkpoint = data.get("current_checkpoint")
    implementation_status = data.get("implementation_status")
    if _is_non_empty_text(checkpoint):
        completed = COMPLETED_CHECKPOINT_PATTERN.fullmatch(checkpoint)
        if completed and implementation_status != f"{completed.group(1)}_IMPLEMENTED_VERIFIED":
            errors.append("Completed checkpoint is inconsistent with implementation_status")

    for index, item in enumerate(data.get("related_commits", [])):
        commit_id = item.get("commit") if isinstance(item, dict) else item
        if not _is_non_empty_text(commit_id) or COMMIT_PATTERN.fullmatch(commit_id) is None:
            errors.append(f"Malformed related commit at index {index}")

    return ValidationResult("FAIL" if errors else "PASS", tuple(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        data = load_change_request(args.path)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    result = validate_change_request(data)
    print(result.status)
    for error in result.errors:
        print(f"- {error}")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
