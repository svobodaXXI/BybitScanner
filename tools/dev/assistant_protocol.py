"""Assemble the legacy Assistant Protocol from its ordered source packages.

The package text is authoritative. The projection exists for old links and
machine readers; it is never an independently edited source.
"""
from __future__ import annotations

import argparse
from pathlib import Path

PACKAGE_DIR = Path("DOCUMENTS/ASSISTANT_RULES")
PROJECTION = Path("DOCUMENTS/ASSISTANT_PROTOCOL.md")
PACKAGES = (
    "00-core.md",
    "10-harness-and-publication.md",
    "11-result-first.md",
    "20-runtime-ownership.md",
    "30-user-actions.md",
    "40-operational-checks.md",
    "50-communication.md",
    "60-context.md",
    "70-workspace-continuation.md",
    "80-development.md",
    "90-maintenance.md",
    "99-revision.md",
)


def assemble(root: Path) -> str:
    directory = root / PACKAGE_DIR
    actual = {path.name for path in directory.glob("*.md")}
    if actual != set(PACKAGES):
        raise ValueError(f"protocol package mismatch: missing={sorted(set(PACKAGES) - actual)}, extra={sorted(actual - set(PACKAGES))}")
    return "".join((directory / name).read_text(encoding="utf-8") for name in PACKAGES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the compatibility projection")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    expected = assemble(root)
    projection = root / PROJECTION
    if args.write:
        projection.write_text(expected, encoding="utf-8", newline="\n")
        return 0
    if projection.read_text(encoding="utf-8") != expected:
        parser.exit(1, "Assistant Protocol projection differs; regenerate from packages.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
