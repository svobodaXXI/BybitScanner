"""Read-only validation and query interface for the LegacyWarning registry."""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ALLOWED_STATUSES = {"LEGACY", "DEPRECATED"}
ALLOWED_SEVERITIES = {"ADVISORY", "BLOCKING"}
REQUIRED_TEXT_FIELDS = {
    "warning_id",
    "status",
    "severity",
    "reason",
    "compatibility_boundary",
    "retention_policy",
    "introduced_revision",
    "owner",
    "retirement_conditions",
}


@dataclass(frozen=True)
class RegistryValidationResult:
    status: str
    errors: tuple[str, ...]
    advisory_count: int
    blocking_count: int

    @property
    def valid(self) -> bool:
        return not self.errors


def load_registry(path: str | Path) -> dict[str, Any]:
    """Load a LegacyWarning registry without mutating it or project state."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed LegacyWarning registry JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("LegacyWarning registry must be a JSON object")
    return data


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_warning(warning: Any, index: int) -> list[str]:
    prefix = f"warnings[{index}]"
    if not isinstance(warning, Mapping):
        return [f"{prefix} must be an object"]

    errors: list[str] = []
    for field in sorted(REQUIRED_TEXT_FIELDS):
        if not _non_empty_text(warning.get(field)):
            errors.append(f"{prefix} missing or empty field: {field}")

    status = warning.get("status")
    severity = warning.get("severity")
    if _non_empty_text(status) and status not in ALLOWED_STATUSES:
        errors.append(f"{prefix} invalid status: {status}")
    if _non_empty_text(severity) and severity not in ALLOWED_SEVERITIES:
        errors.append(f"{prefix} invalid severity: {severity}")

    paths = warning.get("affected_paths")
    symbols = warning.get("affected_symbols")
    usable_paths = isinstance(paths, list) and any(_non_empty_text(item) for item in paths)
    usable_symbols = isinstance(symbols, list) and any(_non_empty_text(item) for item in symbols)
    if not usable_paths and not usable_symbols:
        errors.append(f"{prefix} has no usable path or symbol scope")

    prohibited = warning.get("new_usage_prohibited")
    if not isinstance(prohibited, bool):
        errors.append(f"{prefix} new_usage_prohibited must be boolean")
    elif severity == "BLOCKING" and not prohibited:
        errors.append(f"{prefix} BLOCKING warning must prohibit new usage")

    replacement_available = warning.get("replacement_available")
    if not isinstance(replacement_available, bool):
        errors.append(f"{prefix} replacement_available must be boolean")
    elif replacement_available and not _non_empty_text(warning.get("canonical_replacement")):
        errors.append(f"{prefix} claims a replacement but canonical_replacement is missing")

    last_validated = warning.get("last_validated_revision")
    if last_validated is not None and not _non_empty_text(last_validated):
        errors.append(f"{prefix} last_validated_revision must be non-empty when supplied")

    return errors


def validate_registry(data: Mapping[str, Any]) -> RegistryValidationResult:
    """Validate registry records and expose the strongest valid warning level."""

    errors: list[str] = []
    if not _non_empty_text(data.get("schema_version")):
        errors.append("Missing or empty schema_version")
    if not _non_empty_text(data.get("registry_id")):
        errors.append("Missing or empty registry_id")

    warnings = data.get("warnings")
    if not isinstance(warnings, list):
        return RegistryValidationResult(
            "FAIL", tuple(errors + ["warnings must be a list"]), 0, 0
        )

    ids: list[str] = []
    for index, warning in enumerate(warnings):
        errors.extend(_validate_warning(warning, index))
        if isinstance(warning, Mapping) and _non_empty_text(warning.get("warning_id")):
            ids.append(warning["warning_id"])

    duplicate_ids = sorted({warning_id for warning_id in ids if ids.count(warning_id) > 1})
    for warning_id in duplicate_ids:
        errors.append(f"Duplicate warning_id: {warning_id}")

    advisory_count = sum(
        1 for warning in warnings if isinstance(warning, Mapping) and warning.get("severity") == "ADVISORY"
    )
    blocking_count = sum(
        1 for warning in warnings if isinstance(warning, Mapping) and warning.get("severity") == "BLOCKING"
    )

    if errors:
        status = "FAIL"
    elif blocking_count:
        status = "BLOCKING"
    elif advisory_count:
        status = "ADVISORY"
    else:
        status = "PASS"
    return RegistryValidationResult(status, tuple(errors), advisory_count, blocking_count)


def _path_matches(candidate: str, scope: str) -> bool:
    candidate = candidate.replace("\\", "/").lstrip("./")
    scope = scope.replace("\\", "/").lstrip("./")
    if any(token in scope for token in "*?["):
        return fnmatch.fnmatchcase(candidate, scope)
    if scope.endswith("/"):
        return candidate.startswith(scope)
    return candidate == scope


def query_warnings(
    data: Mapping[str, Any], *, path: str | None = None, symbol: str | None = None
) -> tuple[Mapping[str, Any], ...]:
    """Return warnings applying to an exact/prefix/glob path or exact symbol."""

    if path is None and symbol is None:
        raise ValueError("path or symbol is required")
    result: list[Mapping[str, Any]] = []
    for warning in data.get("warnings", []):
        if not isinstance(warning, Mapping):
            continue
        path_match = path is not None and any(
            _path_matches(path, item)
            for item in warning.get("affected_paths", [])
            if _non_empty_text(item)
        )
        symbol_match = symbol is not None and symbol in warning.get("affected_symbols", [])
        if path_match or symbol_match:
            result.append(warning)
    return tuple(result)


def warning_level(warnings: Sequence[Mapping[str, Any]]) -> str:
    """Return PASS, ADVISORY, or BLOCKING for a query result."""

    if any(warning.get("severity") == "BLOCKING" for warning in warnings):
        return "BLOCKING"
    if warnings:
        return "ADVISORY"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--path")
    parser.add_argument("--symbol")
    args = parser.parse_args()
    try:
        data = load_registry(args.registry)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    validation = validate_registry(data)
    if not validation.valid:
        print("FAIL")
        for error in validation.errors:
            print(f"- {error}")
        return 1

    if args.path is None and args.symbol is None:
        print(validation.status)
        return 0

    matches = query_warnings(data, path=args.path, symbol=args.symbol)
    level = warning_level(matches)
    print(level)
    for warning in matches:
        print(f"- {warning['warning_id']}: {warning['reason']}")
    return 2 if level == "BLOCKING" else 0


if __name__ == "__main__":
    raise SystemExit(main())
