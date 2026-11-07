"""Audit owner-corrected geometry offline; never train or mutate the Scanner.

Every sample is revalidated against its immutable signal and append-only owner
review by reviewed_example. This module deliberately does not partition
training/validation/test cases or promote detector settings.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets

from geometry_feedback_export import GeometryExportError, reviewed_example
from geometry_feedback_store import feedback_directory
from signal_geometry_snapshot import canonical_bytes


class GeometryLearningReportError(ValueError):
    """Evidence cannot be trusted or transformed into a diagnostic report."""


def discover_reviewed_signal_ids(*, feedback_dir=None) -> list[str]:
    """Discover review identities without changing archive contents."""
    root = Path(feedback_dir) if feedback_dir is not None else feedback_directory()
    if not root.exists():
        return []
    if not root.is_dir() or root.is_symlink():
        raise GeometryLearningReportError("invalid_feedback_directory")
    found: set[str] = set()
    for path in sorted(root.glob("*/*.json")):
        try:
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError("symlinked_review")
            value = json.loads(path.read_text(encoding="utf-8"))
            signal_id = value["submission"]["signal_id"]
            if not isinstance(signal_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", signal_id):
                raise ValueError("invalid_signal_id")
            key = hashlib.sha256(signal_id.encode("utf-8")).hexdigest()[:40]
            if path.parent.name != key or path.stem != value["review_id"]:
                raise ValueError("review_path_identity_mismatch")
            found.add(signal_id)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise GeometryLearningReportError("unverifiable_review_path") from exc
    return sorted(found)


def _analyze_case(example: dict) -> dict:
    bars = example.get("review_bars", example["frozen_bars"])
    times = [bar["open_time_ms"] for bar in bars]
    index = {time: i for i, time in enumerate(times)}
    if not times or len(index) != len(times):
        raise GeometryLearningReportError("invalid_frozen_candle_window")
    label = example["label"]
    moves: list[dict] = []
    if label == "GEOMETRY_CORRECTED":
        originals = {line["boundary_id"]: line for line in example["original_boundaries"]}
        corrected = {line["boundary_id"]: line for line in example["corrected_boundaries"]}
        if len(originals) != len(example["original_boundaries"]) or set(originals) != set(corrected):
            raise GeometryLearningReportError("boundary_identity_mismatch")
        for boundary_id in sorted(originals):
            left, right = originals[boundary_id], corrected[boundary_id]
            if left["kind"] != right["kind"] or len(left["anchors"]) != len(right["anchors"]):
                raise GeometryLearningReportError("boundary_topology_mismatch")
            for number, (old, new) in enumerate(zip(left["anchors"], right["anchors"]), start=1):
                if old == new:
                    continue
                try:
                    delta_bars = index[new["bar_open_time_ms"]] - index[old["bar_open_time_ms"]]
                    price_shift_percent = (new["price"] / old["price"] - 1) * 100
                except (KeyError, TypeError, ZeroDivisionError) as exc:
                    raise GeometryLearningReportError("invalid_anchor_delta") from exc
                if not math.isfinite(price_shift_percent):
                    raise GeometryLearningReportError("unbounded_price_delta")
                moves.append({
                    "boundary_id": boundary_id,
                    "anchor_number": number,
                    "bar_shift": delta_bars,
                    "price_shift_percent": round(price_shift_percent, 6),
                    "price_changed": new["price"] != old["price"],
                })
        if not moves:
            raise GeometryLearningReportError("unchanged_corrected_geometry")
    elif label not in ("CONFIRMED", "FALSE_POSITIVE") or example["corrected_boundaries"]:
        raise GeometryLearningReportError("unusable_review_label")
    return {
        "signal_id": example["signal_id"],
        "review_id": example["review_id"],
        "symbol": example["symbol"],
        "timeframe": example["timeframe"],
        "pattern": example["pattern"],
        "label": label,
        "bars_sha256": example["bars_sha256"],
        "source_revision_sha256": example["source_revision_sha256"],
        "review_context": example.get("review_context", "SOURCE_TIME_ONLY"),
        "review_as_of_ms": example.get("review_as_of_ms", times[-1]),
        "window_start_ms": times[0],
        "window_end_ms": times[-1],
        "anchor_changes": moves,
    }



def _pivot_provenance(example: dict) -> list[dict]:
    """Trace owner-corrected rays through the *existing* 3x3 pivot pipeline.

    Frozen candles are the only market input. Never supplement with later candles,
    promote a hand-edited wick to a pivot, or change detector thresholds.
    """
    import pandas as pd
    from geometry.candidate import build_candidate_lines
    from geometry.filter import filter_candidates
    from pivots import find_pivots

    bars = example.get("review_bars", example["frozen_bars"])
    indexes = {bar["open_time_ms"]: i for i, bar in enumerate(bars)}
    frame = pd.DataFrame(
        [{"high": bar["high"], "low": bar["low"]} for bar in bars]
    )
    highs, lows = find_pivots(frame)
    originals = {line["boundary_id"]: line for line in example["original_boundaries"]}
    reports = []

    for line in example["corrected_boundaries"]:
        boundary_id = line["boundary_id"]
        original = originals[boundary_id]
        if original["anchors"] == line["anchors"]:
            continue
        # A generic sidecar may contain segments or pattern-specific levels.
        # Their pivot semantics must not be guessed from their visual position.
        if boundary_id not in ("upper", "lower") or len(line["anchors"]) != 2:
            reports.append({
                "boundary_id": boundary_id,
                "diagnosis": "BOUNDARY_NOT_A_STANDARD_TWO_ANCHOR_RAY",
            })
            continue

        upper = boundary_id == "upper"
        side = "high" if upper else "low"
        pivots = highs if upper else lows
        report_anchors = []
        for n, anchor in enumerate(line["anchors"], start=1):
            index = indexes[anchor["bar_open_time_ms"]]
            wick = bars[index][side]
            on_wick = math.isclose(float(anchor["price"]), float(wick),
                                   rel_tol=1e-8, abs_tol=1e-12)
            confirmable = 3 <= index < len(bars) - 3
            blockers = []
            if confirmable:
                for neighbor in range(index - 3, index + 4):
                    if neighbor == index:
                        continue
                    competing = bars[neighbor][side]
                    if (competing >= wick if upper else competing <= wick):
                        blockers.append(neighbor - index)
            strict_local = confirmable and not blockers
            in_pivots = on_wick and any(
                p["index"] == index
                and math.isclose(float(p["price"]), float(anchor["price"]),
                                 rel_tol=1e-8, abs_tol=1e-12)
                for p in pivots
            )
            if not on_wick:
                status = "NOT_ON_CANDLE_WICK"
            elif not confirmable:
                status = "NOT_YET_CONFIRMABLE_3X3_AT_SNAPSHOT"
            elif not strict_local:
                status = "NOT_STRICT_3X3_EXTREMUM"
            elif not in_pivots:
                status = "REMOVED_BY_MIN_CHANGE"
            else:
                status = "IN_SCANNER_PIVOT_SET"
            report_anchors.append({
                "anchor_number": n,
                "candle_index": index,
                "price_on_wick": on_wick,
                "local_3x3": strict_local,
                "in_scanner_pivots": in_pivots,
                "blocking_neighbor_bar_offsets": blockers,
                "status": status,
            })

        if not all(anchor["in_scanner_pivots"] for anchor in report_anchors):
            stage = "PIVOT_IDENTIFICATION"
            raw_pair = None
            filtered_pair = None
        elif len(pivots) > 125:
            # Offline report should never produce unbounded quadratic work.
            stage = "CANDIDATE_CHECK_BUDGET_EXCEEDED"
            raw_pair = None
            filtered_pair = None
        else:
            indices = tuple(a["candle_index"] for a in report_anchors)
            candidates = build_candidate_lines(pivots)
            raw_pair = any(
                (c["anchor_index"], c["second_index"]) == indices
                for c in candidates
            )
            if not raw_pair:
                stage = "CANDIDATE_GENERATION"
                filtered_pair = False
            else:
                filtered = filter_candidates(candidates)
                filtered_pair = any(
                    (c["anchor_index"], c["second_index"]) == indices
                    for c in filtered
                )
                stage = ("CANDIDATE_FILTER" if not filtered_pair
                         else "LATER_GEOMETRY_SELECTION_OR_VALIDATION")
        reports.append({
            "boundary_id": boundary_id,
            "first_unmatched_stage": stage,
            "generated_as_candidate": raw_pair,
            "survived_candidate_filter": filtered_pair,
            "anchors": report_anchors,
        })
    return reports

def _overlapping_windows(cases: list[dict]) -> list[dict]:
    """Group overlapping same-market windows, not train/validation/test splits.

    Cross-market correlation still requires a global temporal embargo before
    any future holdout. Groups are diagnostics, not leakage clearance.
    """
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for case in cases:
        grouped[(case["symbol"], str(case["timeframe"]))].append(case)
    clusters = []
    for (symbol, timeframe), group in sorted(grouped.items()):
        current: dict | None = None
        for case in sorted(group, key=lambda x: (x["window_start_ms"], x["window_end_ms"], x["signal_id"])):
            if current is None or case["window_start_ms"] > current["window_end_ms"]:
                if current is not None:
                    clusters.append(current)
                current = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "window_start_ms": case["window_start_ms"],
                    "window_end_ms": case["window_end_ms"],
                    "signal_ids": [case["signal_id"]],
                }
            else:
                current["window_end_ms"] = max(current["window_end_ms"], case["window_end_ms"])
                current["signal_ids"].append(case["signal_id"])
        if current is not None:
            clusters.append(current)
    for cluster in clusters:
        cluster["signal_ids"].sort()
    return clusters


def build_geometry_learning_report(
    signal_ids: list[str] | None = None, *, archive_directory=None, feedback_dir=None,
) -> dict:
    """Create diagnostics from verified on-disk owner reviews, no training."""
    ids = (discover_reviewed_signal_ids(feedback_dir=feedback_dir)
           if signal_ids is None else list(signal_ids))
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) for i in ids):
        raise GeometryLearningReportError("duplicate_or_invalid_signal_ids")
    cases = []
    skipped_uncertain = 0
    for signal_id in sorted(ids):
        try:
            example = reviewed_example(signal_id, archive_directory=archive_directory, feedback_directory=feedback_dir)
        except GeometryExportError as exc:
            if str(exc) == "review_not_training_eligible":
                skipped_uncertain += 1
                continue
            raise GeometryLearningReportError("unverified_source_or_review") from exc
        if example.get("split") != "UNASSIGNED_REQUIRES_GROUPED_HOLDOUT":
            raise GeometryLearningReportError("prepartitioned_evidence_not_allowed")
        case = _analyze_case(example)
        case["pivot_provenance"] = _pivot_provenance(example) if case["label"] == "GEOMETRY_CORRECTED" else []
        cases.append(case)
    by_pattern = defaultdict(Counter)
    labels = Counter()
    moved = 0
    bar_shifted = 0
    price_shifted = 0
    for case in cases:
        labels[case["label"]] += 1
        by_pattern[(case["pattern"] or "UNKNOWN", str(case["timeframe"]))][case["label"]] += 1
        for move in case["anchor_changes"]:
            moved += 1
            bar_shifted += move["bar_shift"] != 0
            price_shifted += move["price_changed"]
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_OWNER_GEOMETRY_DIAGNOSTICS",
        "detector_training": "NOT_RUN",
        "detector_acceptance": "NOT_EVALUATED",
        "partition": "UNASSIGNED_REQUIRES_TEMPORAL_GROUPED_HOLDOUT",
        "discovered_reviews": len(ids),
        "skipped_uncertain": skipped_uncertain,
        "summary": {
            "eligible_signals": len(cases),
            "confirmed": labels["CONFIRMED"],
            "corrected": labels["GEOMETRY_CORRECTED"],
            "false_positive": labels["FALSE_POSITIVE"],
            "changed_anchors": moved,
            "shifted_bar_anchors": bar_shifted,
            "changed_price_anchors": price_shifted,
        },
        "pattern_timeframes": [
            {"pattern": pattern, "timeframe": timeframe,
             "confirmed": counts["CONFIRMED"],
             "corrected": counts["GEOMETRY_CORRECTED"],
             "false_positive": counts["FALSE_POSITIVE"]}
            for (pattern, timeframe), counts in sorted(by_pattern.items())
        ],
        "overlapping_window_groups": _overlapping_windows(cases),
        "cases": cases,
    }


def write_geometry_learning_report(report: dict, output: str | Path) -> None:
    """Exclusively publish the complete diagnostic report; never overwrite."""
    path = Path(output)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_bytes(report) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
