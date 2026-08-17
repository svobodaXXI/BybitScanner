"""Generate a compact, disposable ContextDump for one durable ChangeRequest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .change_request import load_change_request, validate_change_request
from .legacy_warning import load_registry, query_warnings, validate_registry


OUTPUT_DIRECTORY = Path("runtime/context")
REQUIRED_SCOPE_FIELDS = (
    "context_scope_paths",
    "context_test_paths",
    "context_excerpt_references",
)


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


def _legacy_warnings(project_root: Path, paths: Sequence[str]) -> list[dict[str, Any]]:
    registry_path = project_root / "DOCUMENTS/LEGACY_WARNINGS.json"
    if not registry_path.is_file():
        raise ContextDumpError("LegacyWarning registry cannot be resolved")
    registry = load_registry(registry_path)
    validation = validate_registry(registry)
    if not validation.valid:
        raise ContextDumpError("LegacyWarning registry is invalid: " + "; ".join(validation.errors))
    matches: dict[str, Mapping[str, Any]] = {}
    for path in paths:
        for warning in query_warnings(registry, path=path):
            matches[str(warning["warning_id"])] = warning
    return [dict(matches[key]) for key in sorted(matches)]


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
    warnings = _legacy_warnings(root, all_scoped_paths)
    status_payload = "\n".join(git_state.status_short).encode("utf-8")
    metadata = {
        "schema_version": "1.0",
        "artifact_type": "CONTEXT_DUMP",
        "authority": "NON_AUTHORITATIVE_DERIVED",
        "task_id": request["id"],
        "task_revision": request["revision"],
        "generated_at": generated_at,
        "source_revision": git_state.head,
        "branch": git_state.branch,
        "working_tree_dirty": git_state.dirty,
        "working_tree_status_sha256": _sha256_bytes(status_payload),
        "change_request_source": {
            "path": request_relative,
            "sha256": _sha256_bytes(request_path.read_bytes()),
        },
        "scoped_files": _scoped_file_records(root, all_scoped_paths),
        "source_files": _source_records(root, authority_references),
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
    args = parser.parse_args()
    try:
        output = generate_context_dump(args.project_root, args.change_request)
    except (ContextDumpError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
