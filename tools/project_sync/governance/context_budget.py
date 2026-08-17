"""Measure task-scoped AI recovery footprints without mutating project state."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Footprint:
    source: str
    bytes: int
    characters: int
    lines: int


@dataclass(frozen=True)
class DuplicateCandidate:
    normalized_text: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class BudgetReport:
    agents: Footprint
    change_request: Footprint
    context_dump: Footprint | None
    lightweight_sources: tuple[Footprint, ...]
    durable_sources: tuple[Footprint, ...]
    lightweight_bytes: int
    durable_bytes: int
    agents_plus_change_request_bytes: int
    duplicate_candidates: tuple[DuplicateCandidate, ...]


def _read_text(path: Path) -> str:
    payload = path.read_bytes()
    if payload.startswith(b"\xff\xfe"):
        return payload[2:].decode("utf-16-le")
    if payload.startswith(b"\xfe\xff"):
        return payload[2:].decode("utf-16-be")
    return payload.decode("utf-8-sig")


def _resolve_source(project_root: Path, reference: str) -> tuple[Path, str | None]:
    relative, separator, heading = reference.partition("#")
    candidate = (project_root / relative).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Source escapes project root: {reference}") from exc
    if not candidate.is_file():
        raise ValueError(f"Source cannot be resolved: {reference}")
    return candidate, heading if separator else None


def extract_markdown_section(text: str, heading: str) -> str:
    """Return one Markdown heading section, stopping at an equal/higher heading."""

    wanted = heading.strip().lstrip("#").strip().casefold()
    lines = text.splitlines(keepends=True)
    start = None
    level = None
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match and match.group(2).strip().casefold() == wanted:
            if start is not None:
                raise ValueError(f"Section heading is ambiguous: {heading}")
            start = index
            level = len(match.group(1))
    if start is None or level is None:
        raise ValueError(f"Section heading cannot be resolved: {heading}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return "".join(lines[start:end])


def measure_reference(project_root: str | Path, reference: str) -> Footprint:
    root = Path(project_root).resolve()
    path, heading = _resolve_source(root, reference)
    if heading is None:
        payload = path.read_bytes()
        text = _read_text(path)
        byte_count = len(payload)
    else:
        text = extract_markdown_section(_read_text(path), heading)
        byte_count = len(text.encode("utf-8"))
    return Footprint(reference, byte_count, len(text), len(text.splitlines()))


def _normalize_paragraph(paragraph: str) -> str:
    return " ".join(paragraph.split()).casefold()


def duplicate_candidates(
    project_root: str | Path,
    references: Sequence[str],
    *,
    minimum_characters: int = 80,
) -> tuple[DuplicateCandidate, ...]:
    """Return exact normalized cross-source paragraphs for human classification."""

    root = Path(project_root).resolve()
    occurrences: dict[str, set[str]] = {}
    for reference in dict.fromkeys(references):
        path, heading = _resolve_source(root, reference)
        text = _read_text(path)
        if heading is not None:
            text = extract_markdown_section(text, heading)
        for paragraph in re.split(r"(?:\r?\n){2,}", text):
            normalized = _normalize_paragraph(paragraph)
            if len(normalized) >= minimum_characters:
                occurrences.setdefault(normalized, set()).add(reference)
    return tuple(
        DuplicateCandidate(text, tuple(sorted(sources)))
        for text, sources in sorted(occurrences.items())
        if len(sources) > 1
    )


def _measure_unique(project_root: Path, references: Iterable[str]) -> tuple[Footprint, ...]:
    return tuple(measure_reference(project_root, item) for item in dict.fromkeys(references))


def build_budget_report(
    project_root: str | Path,
    change_request: str,
    *,
    context_dump: str | None = None,
    lightweight_references: Sequence[str] = (),
    durable_references: Sequence[str] = (),
    duplicate_references: Sequence[str] = (),
) -> BudgetReport:
    root = Path(project_root).resolve()
    agents = measure_reference(root, "AGENTS.md")
    request = measure_reference(root, change_request)
    dump = measure_reference(root, context_dump) if context_dump else None
    lightweight = _measure_unique(root, lightweight_references)
    durable = _measure_unique(root, durable_references)
    return BudgetReport(
        agents=agents,
        change_request=request,
        context_dump=dump,
        lightweight_sources=lightweight,
        durable_sources=durable,
        lightweight_bytes=agents.bytes + sum(item.bytes for item in lightweight),
        durable_bytes=agents.bytes + request.bytes + sum(item.bytes for item in durable),
        agents_plus_change_request_bytes=agents.bytes + request.bytes,
        duplicate_candidates=duplicate_candidates(root, duplicate_references),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_request")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--context-dump")
    parser.add_argument("--lightweight-reference", action="append", default=[])
    parser.add_argument("--durable-reference", action="append", default=[])
    parser.add_argument("--duplicate-reference", action="append", default=[])
    args = parser.parse_args()
    try:
        report = build_budget_report(
            args.project_root,
            args.change_request,
            context_dump=args.context_dump,
            lightweight_references=args.lightweight_reference,
            durable_references=args.durable_reference,
            duplicate_references=args.duplicate_reference,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
