"""Generate a compact, disposable ContextDump for one durable ChangeRequest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .change_request import load_change_request, validate_change_request
from .legacy_warning import enforce_scoped_warnings, load_registry, validate_registry


OUTPUT_DIRECTORY = Path("runtime/context")
REQUIRED_SCOPE_FIELDS = (
    "context_scope_paths",
    "context_test_paths",
    "context_excerpt_references",
)
METADATA_PATTERN = re.compile(
    r"<!-- CONTEXT_DUMP_METADATA_BEGIN -->\s*"
    r"```json\s*(?P<payload>.*?)\s*```\s*"
    r"<!-- CONTEXT_DUMP_METADATA_END -->",
    re.DOTALL,
)
VALIDATION_EXIT_CODES = {"PASS": 0, "ADVISORY": 0, "STALE": 1, "FAIL": 1, "BLOCKING": 2}


class ContextDumpError(ValueError):
    """Raised when required task authority or scope cannot be resolved."""


@dataclass(frozen=True)
class GitState:
    branch: str
    head: str
    status_short: tuple[str, ...]

    @property
    def dirty(self) -> bool:
        return bool(self.status_short)


@dataclass(frozen=True)
class ContextValidationResult:
    status: str
    reasons: tuple[str, ...]
    warning_ids: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.status in {"PASS", "ADVISORY"}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_project_path(project_root: Path, relative_path: str) -> Path:
    candidate = (project_root / relative_path).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ContextDumpError(f"Path escapes project root: {relative_path}") from exc
    return candidate


def _required_string_list(data: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = data.get(field)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ContextDumpError(f"Missing or invalid task scope field: {field}")
    return tuple(value)


def _optional_string_list(data: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = data.get(field, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ContextDumpError(f"Invalid task scope field: {field}")
    return tuple(value)


def _split_reference(reference: str) -> tuple[str, str | None]:
    path, separator, anchor = reference.partition("#")
    return path, anchor if separator else None


def _extract_markdown_section(content: str, anchor: str, reference: str) -> str:
    lines = content.splitlines()
    target = anchor.strip().lower()
    start = None
    level = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue
        hashes, _, title = stripped.partition(" ")
        if title.strip().lower() == target:
            start = index
            level = len(hashes)
            break
    if start is None or level is None:
        raise ContextDumpError(f"Authority section cannot be resolved: {reference}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].lstrip()
        if not stripped.startswith("#"):
            continue
        hashes, separator, _ = stripped.partition(" ")
        if separator and len(hashes) <= level:
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def _read_git_state(project_root: Path) -> GitState:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout.strip()

    try:
        branch = run("branch", "--show-current") or "DETACHED"
        head = run("rev-parse", "HEAD")
        status = tuple(line for line in run("status", "--short").splitlines() if line)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContextDumpError(f"Local Git state cannot be resolved: {exc}") from exc
    return GitState(branch=branch, head=head, status_short=status)


def _source_records(project_root: Path, references: Sequence[str]) -> list[dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for reference in references:
        relative_path, _ = _split_reference(reference)
        source = _safe_project_path(project_root, relative_path)
        if not source.is_file():
            raise ContextDumpError(f"Authoritative source is missing: {relative_path}")
        records[relative_path] = {
            "path": relative_path.replace("\\", "/"),
            "sha256": _sha256_bytes(source.read_bytes()),
        }
    return [records[path] for path in sorted(records)]


def _scoped_file_records(project_root: Path, paths: Sequence[str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for relative_path in sorted(set(paths)):
        source = _safe_project_path(project_root, relative_path)
        if not source.is_file():
            raise ContextDumpError(f"Declared task path is missing: {relative_path}")
        records.append(
            {
                "path": relative_path.replace("\\", "/"),
                "sha256": _sha256_bytes(source.read_bytes()),
            }
        )
    return records


def _status_path(status_line: str) -> str:
    value = status_line[3:] if len(status_line) > 3 else ""
    if " -> " in value:
        value = value.rsplit(" -> ", 1)[1]
    return value.strip('"').replace("\\", "/")


def _scoped_status(status: Sequence[str], paths: Sequence[str]) -> tuple[str, ...]:
    declared = {path.replace("\\", "/") for path in paths}
    return tuple(sorted(line for line in status if _status_path(line) in declared))


def _warning_record_hash(warning: Mapping[str, Any]) -> str:
    payload = json.dumps(warning, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return _sha256_bytes(payload)


def _legacy_warning_state(
    project_root: Path, paths: Sequence[str], symbols: Sequence[str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    registry_path = project_root / "DOCUMENTS/LEGACY_WARNINGS.json"
    if not registry_path.is_file():
        raise ContextDumpError("LegacyWarning registry cannot be resolved")
    registry = load_registry(registry_path)
    validation = validate_registry(registry)
    if not validation.valid:
        raise ContextDumpError("LegacyWarning registry is invalid: " + "; ".join(validation.errors))
    enforcement = enforce_scoped_warnings(registry, paths=paths, symbols=symbols)
    warnings = [dict(warning) for warning in enforcement.warnings]
    state = {
        "registry_path": "DOCUMENTS/LEGACY_WARNINGS.json",
        "registry_id": registry.get("registry_id"),
        "schema_version": registry.get("schema_version"),
        "applicable": [
            {
                "warning_id": warning["warning_id"],
                "severity": warning["severity"],
                "record_sha256": _warning_record_hash(warning),
            }
            for warning in warnings
        ],
    }
    return state, warnings


def load_context_dump_metadata(path: str | Path) -> dict[str, Any]:
    """Load the structured provenance block from a generated ContextDump."""

    content = Path(path).read_text(encoding="utf-8")
    match = METADATA_PATTERN.search(content)
    if match is None:
        raise ContextDumpError("ContextDump metadata block is missing")
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError as exc:
        raise ContextDumpError(f"Malformed ContextDump metadata JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContextDumpError("ContextDump metadata must be a JSON object")
    return payload


def build_context_dump(
    project_root: str | Path,
    change_request_path: str | Path,
    *,
    git_state: GitState,
    generated_at: str,
) -> str:
    """Build ContextDump Markdown without writing any file."""

    root = Path(project_root).resolve()
    request_path = Path(change_request_path)
    if not request_path.is_absolute():
        request_path = root / request_path
    try:
        request_relative = request_path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ContextDumpError("ChangeRequest path escapes project root") from exc
    request = load_change_request(request_path)
    validation = validate_change_request(request)
    if not validation.valid:
        raise ContextDumpError("ChangeRequest is invalid: " + "; ".join(validation.errors))

    scope_paths = _required_string_list(request, "context_scope_paths")
    test_paths = _required_string_list(request, "context_test_paths")
    scope_symbols = _optional_string_list(request, "context_scope_symbols")
    excerpt_references = _required_string_list(request, "context_excerpt_references")
    authority_references = _required_string_list(request, "authoritative_references")
    unknown_excerpts = sorted(set(excerpt_references) - set(authority_references))
    if unknown_excerpts:
        raise ContextDumpError(
            "Excerpt reference is not authoritative for this task: " + ", ".join(unknown_excerpts)
        )

    excerpts: list[tuple[str, str]] = []
    for reference in excerpt_references:
        relative_path, anchor = _split_reference(reference)
        if not anchor:
            raise ContextDumpError(f"Excerpt reference requires a section anchor: {reference}")
        source = _safe_project_path(root, relative_path)
        if not source.is_file():
            raise ContextDumpError(f"Authority excerpt source is missing: {relative_path}")
        content = source.read_text(encoding="utf-8")
        excerpts.append((reference, _extract_markdown_section(content, anchor, reference)))

    all_scoped_paths = tuple(sorted(set(scope_paths + test_paths)))
    warning_state, warnings = _legacy_warning_state(root, all_scoped_paths, scope_symbols)
    scoped_status = _scoped_status(git_state.status_short, all_scoped_paths)
    status_payload = "\n".join(scoped_status).encode("utf-8")
    metadata = {
        "schema_version": "1.1",
        "artifact_type": "CONTEXT_DUMP",
        "authority": "NON_AUTHORITATIVE_DERIVED",
        "task_id": request["id"],
        "task_revision": request["revision"],
        "generated_at": generated_at,
        "source_revision": git_state.head,
        "branch": git_state.branch,
        "working_tree_dirty": git_state.dirty,
        "scoped_git_status": list(scoped_status),
        "scoped_git_status_sha256": _sha256_bytes(status_payload),
        "change_request_source": {
            "path": request_relative,
            "sha256": _sha256_bytes(request_path.read_bytes()),
        },
        "scoped_files": _scoped_file_records(root, all_scoped_paths),
        "source_files": _source_records(root, authority_references),
        "legacy_warning_state": warning_state,
    }

    def bullets(values: Sequence[str]) -> str:
        return "\n".join(f"- {value}" for value in values) if values else "- None"

    sections = [
        f"# ContextDump — {request['id']}",
        "",
        "> NON-AUTHORITATIVE DERIVED ARTIFACT. Rebuild from the current local checkout before use when provenance changes.",
        "",
        "<!-- CONTEXT_DUMP_METADATA_BEGIN -->",
        "```json",
        json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False),
        "```",
        "<!-- CONTEXT_DUMP_METADATA_END -->",
        "",
        "## Objective",
        "",
        str(request["objective"]),
        "",
        "## Approved scope",
        "",
        bullets(request["approved_scope"]),
        "",
        "## Prohibited scope",
        "",
        bullets(request["prohibited_scope"]),
        "",
        "## Acceptance and verification",
        "",
        bullets(request["acceptance_criteria"] + request["verification_requirements"]),
        "",
        "## Authoritative references",
        "",
        bullets(authority_references),
        "",
        "## Affected paths",
        "",
        bullets(sorted(scope_paths)),
        "",
        "## Focused tests",
        "",
        bullets(sorted(test_paths)),
        "",
        "## Unresolved decisions",
        "",
        bullets(request["unresolved_decisions"]),
        "",
        "## Relevant LegacyWarnings",
        "",
    ]
    if warnings:
        for warning in warnings:
            sections.append(
                f"- {warning['severity']} `{warning['warning_id']}`: {warning['reason']} "
                f"Replacement: `{warning.get('canonical_replacement') or 'none'}`."
            )
    else:
        sections.append("- None for the declared task paths.")
    sections.extend(["", "## Selected authoritative excerpts", ""])
    for reference, excerpt in excerpts:
        sections.extend([f"### {reference}", "", excerpt, ""])
    return "\n".join(sections).rstrip() + "\n"


def _records_by_path(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, list):
        raise ContextDumpError(f"ContextDump {field} must be a list")
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ContextDumpError(f"ContextDump {field} contains a malformed record")
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ContextDumpError(f"ContextDump {field} contains a malformed record")
        result[path] = digest
    return result


def validate_context_dump(
    project_root: str | Path,
    context_dump_path: str | Path,
    change_request_path: str | Path,
    *,
    git_state: GitState | None = None,
) -> ContextValidationResult:
    """Validate ContextDump provenance and enforce warnings for its declared scope."""

    root = Path(project_root).resolve()
    try:
        metadata = load_context_dump_metadata(context_dump_path)
        request_path = Path(change_request_path)
        if not request_path.is_absolute():
            request_path = root / request_path
        try:
            request_relative = request_path.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise ContextDumpError("ChangeRequest path escapes project root") from exc
        request = load_change_request(request_path)
        request_validation = validate_change_request(request)
        if not request_validation.valid:
            raise ContextDumpError(
                "ChangeRequest is invalid: " + "; ".join(request_validation.errors)
            )
        scope_paths = _required_string_list(request, "context_scope_paths")
        test_paths = _required_string_list(request, "context_test_paths")
        scope_symbols = _optional_string_list(request, "context_scope_symbols")
        authority_references = _required_string_list(request, "authoritative_references")
        all_scoped_paths = tuple(sorted(set(scope_paths + test_paths)))
        current_git = git_state or _read_git_state(root)
        expected_sources = {
            record["path"]: record["sha256"]
            for record in _source_records(root, authority_references)
        }
        expected_scoped = {
            record["path"]: record["sha256"]
            for record in _scoped_file_records(root, all_scoped_paths)
        }
        warning_state, warnings = _legacy_warning_state(
            root, all_scoped_paths, scope_symbols
        )
        stored_sources = _records_by_path(metadata.get("source_files"), "source_files")
        stored_scoped = _records_by_path(metadata.get("scoped_files"), "scoped_files")
    except (ContextDumpError, OSError, ValueError) as exc:
        return ContextValidationResult("FAIL", (str(exc),), ())

    stale: list[str] = []
    if (
        metadata.get("schema_version") != "1.1"
        or metadata.get("artifact_type") != "CONTEXT_DUMP"
        or metadata.get("authority") != "NON_AUTHORITATIVE_DERIVED"
    ):
        return ContextValidationResult("FAIL", ("Invalid ContextDump identity/authority",), ())
    if metadata.get("task_id") != request.get("id"):
        stale.append("task identity changed")
    if metadata.get("task_revision") != request.get("revision"):
        stale.append("task revision changed")
    if metadata.get("branch") != current_git.branch:
        stale.append("branch changed")
    if metadata.get("source_revision") != current_git.head:
        stale.append("HEAD changed")
    request_source = metadata.get("change_request_source")
    if (
        not isinstance(request_source, Mapping)
        or request_source.get("path") != request_relative
        or request_source.get("sha256") != _sha256_bytes(request_path.read_bytes())
    ):
        stale.append("ChangeRequest content changed")
    if stored_sources != expected_sources:
        stale.append("authoritative source content changed")
    if stored_scoped != expected_scoped:
        stale.append("scoped file content changed")
    scoped_status = _scoped_status(current_git.status_short, all_scoped_paths)
    scoped_status_hash = _sha256_bytes("\n".join(scoped_status).encode("utf-8"))
    if metadata.get("scoped_git_status_sha256") != scoped_status_hash:
        stale.append("scoped Git state changed")
    if metadata.get("legacy_warning_state") != warning_state:
        stale.append("relevant LegacyWarning state changed")

    warning_ids = tuple(str(warning["warning_id"]) for warning in warnings)
    if stale:
        return ContextValidationResult("STALE", tuple(stale), warning_ids)
    enforcement = enforce_scoped_warnings(
        load_registry(root / "DOCUMENTS/LEGACY_WARNINGS.json"),
        paths=all_scoped_paths,
        symbols=scope_symbols,
    )
    if enforcement.status == "BLOCKING":
        return ContextValidationResult(
            "BLOCKING", ("Applicable BLOCKING LegacyWarning",), warning_ids
        )
    if enforcement.status == "ADVISORY":
        return ContextValidationResult("ADVISORY", (), warning_ids)
    return ContextValidationResult("PASS", (), ())


def generate_context_dump(
    project_root: str | Path,
    change_request_path: str | Path,
    *,
    git_state: GitState | None = None,
    generated_at: str | None = None,
) -> Path:
    """Generate one ContextDump at the canonical ignored runtime location."""

    root = Path(project_root).resolve()
    request = load_change_request(
        Path(change_request_path)
        if Path(change_request_path).is_absolute()
        else root / change_request_path
    )
    task_id = request.get("id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ContextDumpError("ChangeRequest identity cannot be resolved")
    content = build_context_dump(
        root,
        change_request_path,
        git_state=git_state or _read_git_state(root),
        generated_at=generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    output = root / OUTPUT_DIRECTORY / f"{task_id}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_request", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--validate-context", type=Path)
    args = parser.parse_args()
    if args.validate_context is not None:
        result = validate_context_dump(
            args.project_root, args.validate_context, args.change_request
        )
        print(result.status)
        for reason in result.reasons:
            print(f"- {reason}")
        for warning_id in result.warning_ids:
            print(f"- LegacyWarning: {warning_id}")
        return VALIDATION_EXIT_CODES[result.status]
    try:
        output = generate_context_dump(args.project_root, args.change_request)
    except (ContextDumpError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
