"""RVL-G3 Geometry Gold baseline report.

Produces per-case machine-readable or text output from the existing RVL-G2
runner. The report deliberately has no aggregate quality score: one structural
regression must remain visible even if every other case passes.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from tests.geometry_gold import load_manifest, run_geometry_gold


ANCHOR_FIELDS = (
    "upper_anchor",
    "upper_second",
    "lower_anchor",
    "lower_second",
    "start",
    "end",
)


def _anchor_delta(expected: list[int] | None, observed: list[int] | None):
    if expected is None or observed is None:
        return None
    if len(expected) != len(ANCHOR_FIELDS) or len(observed) != len(ANCHOR_FIELDS):
        raise ValueError("Geometry identity must contain six indices")
    return {
        field: int(actual) - int(want)
        for field, want, actual in zip(ANCHOR_FIELDS, expected, observed)
    }


def _classify(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expectation = case["expectation"]
    kind = expectation["kind"]
    observed = result["observed"]
    passed = bool(result["passed"])

    false_positive = False
    false_negative = False

    if kind == "POSITIVE_ANCHOR":
        if not passed and (
            observed.get("geometry_identity") is None
            or observed.get("detected") is False
        ):
            false_negative = True
    elif kind == "NO_GEOMETRY":
        false_positive = not passed and observed.get("geometry_identity") is not None
    elif kind == "FORBIDDEN_ANCHOR_PAIR":
        false_positive = not passed
    elif kind == "LOCALITY_INVARIANT":
        if not passed:
            if observed.get("geometry_identity") is None:
                false_negative = True
            else:
                false_positive = True

    expected_identity = expectation.get("geometry_identity")
    observed_identity = observed.get("geometry_identity")

    return {
        "case_id": case["case_id"],
        "symbol": case["symbol"],
        "expectation_kind": kind,
        "status": "PASS" if passed else "FAIL",
        "changed_vs_baseline": not passed,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "anchor_delta": _anchor_delta(expected_identity, observed_identity),
        "expected": expectation,
        "observed": observed,
        "errors": list(result["errors"]),
    }


def build_baseline_report(
    *,
    manifest: dict[str, Any] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = load_manifest() if manifest is None else manifest
    results = run_geometry_gold() if results is None else results

    cases = manifest["cases"]
    if len(cases) != len(results):
        raise ValueError("Geometry Gold manifest/result count mismatch")

    by_id = {result["case_id"]: result for result in results}
    if len(by_id) != len(results):
        raise ValueError("duplicate Geometry Gold result case_id")

    report_cases = []
    for case in cases:
        result = by_id.get(case["case_id"])
        if result is None:
            raise ValueError(f"missing Geometry Gold result for {case['case_id']}")
        report_cases.append(_classify(case, result))

    return {
        "schema_version": 1,
        "baseline": "geometry_gold_manifest_v1",
        "case_count": len(report_cases),
        "passed_cases": [case["case_id"] for case in report_cases if case["status"] == "PASS"],
        "failed_cases": [case["case_id"] for case in report_cases if case["status"] == "FAIL"],
        "changed_cases": [
            case["case_id"] for case in report_cases if case["changed_vs_baseline"]
        ],
        "false_positive_cases": [
            case["case_id"] for case in report_cases if case["false_positive"]
        ],
        "false_negative_cases": [
            case["case_id"] for case in report_cases if case["false_negative"]
        ],
        "cases": report_cases,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "Geometry Gold baseline report",
        f"Cases: {report['case_count']}",
        f"Passed: {len(report['passed_cases'])}",
        f"Failed: {len(report['failed_cases'])}",
        f"Changed vs baseline: {', '.join(report['changed_cases']) or 'none'}",
        f"False positives: {', '.join(report['false_positive_cases']) or 'none'}",
        f"False negatives: {', '.join(report['false_negative_cases']) or 'none'}",
        "",
    ]

    for case in report["cases"]:
        lines.append(
            f"[{case['status']}] {case['case_id']} ({case['expectation_kind']})"
        )
        if case["anchor_delta"] is not None:
            delta = ", ".join(
                f"{field}={value:+d}" for field, value in case["anchor_delta"].items()
            )
            lines.append(f"  anchor_delta: {delta}")
        if case["false_positive"]:
            lines.append("  classification: FALSE_POSITIVE")
        if case["false_negative"]:
            lines.append("  classification: FALSE_NEGATIVE")
        for error in case["errors"]:
            lines.append(f"  error: {error}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Geometry Gold baseline report")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = build_baseline_report()
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))

    return 0 if not report["failed_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
