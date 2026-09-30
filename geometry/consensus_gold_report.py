"""GEO-U1 Slice D: SHADOW-vs-production delta report on exact Geometry Gold.

DIAGNOSTIC ONLY. Nothing here is imported by the production engine, winner,
classifiers, Telegram or Robot. The report places the unchanged production
Geometry winner beside the Slice C SHADOW selection and lists structural
differences as FACTS. It never declares either side better, assigns a family
to the SHADOW pair, or proposes thresholds.

Field vocabulary: UNAVAILABLE = the fixture/production result has no exact
evidence for the field; NOT_COMPARABLE = both sides may carry a number but the
definitions differ, so no delta is computed and no mapping is invented.
"""

from collections import Counter
from dataclasses import asdict, is_dataclass
from math import isfinite

from .consensus_boundary import build_boundary_consensus
from .consensus_selection import select_envelope_pair_shadow

UNAVAILABLE = "UNAVAILABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"
SCHEMA_VERSION = 1

# Diagnostic presets reused unchanged from the merged Slice C Gold invariance
# test. They are explicit report parameters, NOT calibrated thresholds, and
# were not tuned on this report's output.
DEFAULT_SHADOW_REPORT_PARAMETERS = {
    "inlier_band_atr": 0.2,
    "separation_atr": 0.75,
    "touch_band_atr": 0.2,
    "minimum_swing_width_fraction": 0.30,
    "minimum_swing_atr": 0.5,
    "minimum_side_touch_clusters": 2,
    "min_cross_boundary_traversals": 1,
    "min_alternating_touches": 3,
    "min_touch_balance": 0.25,
    "min_shared_support_coverage": 0.25,
    "max_support_gap_fraction": 0.5,
    "terminal_window_bars": 30,
    "terminal_segments": 3,
    "compression_max_ratio": 0.9,
    "expansion_min_ratio": 1.1,
    "segment_tolerance": 0.05,
    "single_bar_narrow_ratio": 0.5,
}
_BOUNDARY_KEYS = ("inlier_band_atr", "separation_atr")
_TRACE_ROWS = 5


def _plain(value, counter):
    """JSON-safe copy: tuples -> lists, non-finite floats -> None (counted)."""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): _plain(v, counter) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v, counter) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if hasattr(value, "item"):          # numpy scalar
        value = value.item()
    if isinstance(value, float):
        if isfinite(value):
            return value
        counter[0] += 1
        return None
    if isinstance(value, int):
        return value
    return str(value)


def _line_value(slope, intercept, index):
    return slope * index + intercept


def _production_side(frame, as_of):
    # Imported here so the diagnostic module keeps production imports out of
    # module load; these calls mirror tests.geometry_gold._analyze exactly.
    import geometry.engine as engine
    from pivots import find_pivots
    from wedge.analyzer import _freshness_predicate
    from wedge.detector import detect_structure

    highs, lows = find_pivots(frame.copy())
    geometry = engine.analyze_geometry(
        highs, lows, current_index=len(frame) - 1, candles=frame,
        freshness_predicate=_freshness_predicate)
    if geometry is None:
        return None, {"geometry_present": False, "identity": None,
                      "classification": UNAVAILABLE, "upper": UNAVAILABLE,
                      "lower": UNAVAILABLE, "start_index": None,
                      "end_index": None, "current_index": len(frame) - 1,
                      "compression": UNAVAILABLE, "touches": UNAVAILABLE,
                      "pair_metrics": UNAVAILABLE}
    detected = detect_structure(geometry, candles=frame)
    features = detected.get("features") or {}

    def line(item):
        return {key: item.get(key) for key in (
            "anchor_index", "second_index", "slope", "intercept", "points",
            "confirmations", "support_ratio", "structure_span", "anchor_span")}

    touches = geometry.touches or {}
    pair = geometry.pair_metrics or {}
    compression = geometry.compression or {}
    record = {
        "geometry_present": True,
        "identity": [int(geometry.upper_line["anchor_index"]),
                     int(geometry.upper_line["second_index"]),
                     int(geometry.lower_line["anchor_index"]),
                     int(geometry.lower_line["second_index"]),
                     int(geometry.start_index), int(geometry.end_index)],
        "classification": {
            "detected": detected.get("detected"),
            "candidate": detected.get("candidate"),
            "pattern": detected.get("pattern"),
            "reason": detected.get("reason"),
            "feature_flags": {k: features.get(k) for k in (
                "compression", "touches", "apex", "validation", "freshness",
                "freshness_window")},
        },
        "upper": line(geometry.upper_line),
        "lower": line(geometry.lower_line),
        "start_index": int(geometry.start_index),
        "end_index": int(geometry.end_index),
        "current_index": int(geometry.current_index),
        "compression": {k: compression.get(k) for k in (
            "start_width", "end_width", "compression_percent", "is_compressing")},
        "touches": {k: touches.get(k) for k in (
            "upper_touches", "lower_touches", "total_touches", "valid")},
        "pair_metrics": {k: pair.get(k) for k in (
            "common_span", "shared_structure_span", "anchor_balance",
            "true_converging", "boundary_crossed", "boundary_order_valid")},
    }
    return geometry, record


def _boundary_record(boundary):
    return {
        "seed_anchor_indices": boundary.seed_anchor_indices,
        "slope": boundary.slope, "intercept": boundary.intercept,
        "inlier_pivot_indices": boundary.inlier_pivot_indices,
        "touch_count_distinct": boundary.touch_count_distinct,
        "support_span": boundary.support_span,
        "support_coverage_ratio": boundary.support_coverage_ratio,
        "first_supported_pivot": boundary.first_supported_pivot,
        "last_supported_pivot": boundary.last_supported_pivot,
        "mean_residual_atr": boundary.mean_residual_atr,
        "max_residual_atr": boundary.max_residual_atr,
        "excursion_pivot_indices": boundary.excursion_pivot_indices,
        "body_integrity": boundary.body_integrity,
    }


def _shadow_side(frame, uppers, lowers, as_of, parameters):
    selection_parameters = {k: v for k, v in parameters.items()
                            if k not in _BOUNDARY_KEYS}
    selection = select_envelope_pair_shadow(
        frame, uppers, lowers, as_of_index=as_of, episode_start_index=0,
        episode_end_index=as_of, **selection_parameters)
    reason_counts = Counter(reason for row in selection.selection_trace
                            for reason in row.rejection_reasons)
    record = {
        "selection_status": selection.selection_status,
        "candidate_count": selection.candidate_count,
        "admissible_count": selection.admissible_count,
        "rejected_count": selection.rejected_count,
        "selected_pair_identity": selection.selected_pair_identity,
        "rejection_reasons_of_top_ranked": selection.rejection_reasons,
        "rejection_reason_counts": dict(sorted(
            reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "deciding_component": selection.deciding_component,
        "runner_up": None if selection.runner_up_identity is None else {
            "identity": selection.runner_up_identity,
            "quality_tuple": selection.runner_up_quality_tuple,
        },
        "quality_fields": selection.quality_fields,
        "final_quality_tuple": selection.final_quality_tuple,
        "terminal_of_top_ranked": selection.terminal,
        "trace_top": selection.selection_trace[:_TRACE_ROWS],
        "upper": UNAVAILABLE, "lower": UNAVAILABLE, "pair": UNAVAILABLE,
    }
    pair = selection.selected_pair
    if pair is not None:
        record["upper"] = _boundary_record(pair.upper_boundary)
        record["lower"] = _boundary_record(pair.lower_boundary)
        record["pair"] = {k: getattr(pair, k) for k in (
            "pair_valid", "pair_invalid_reasons", "width_at_start",
            "width_at_end", "width_change_ratio", "compression_ratio",
            "boundaries_cross_inside_episode", "boundary_intersection_index",
            "upper_touch_count", "lower_touch_count", "touch_balance",
            "alternating_touch_count", "alternating_touch_sequence",
            "cross_boundary_traversal_count", "meaningful_swing_count",
            "opposite_boundary_reach_fraction", "shared_support_start",
            "shared_support_end", "shared_support_span",
            "shared_support_coverage_ratio")}
    return pair, selection, record


def _delta(production, pair, selection):
    production_present = production["geometry_present"]
    shadow_present = pair is not None
    presence = {
        (True, True): "BOTH_PRESENT", (True, False): "PRODUCTION_ONLY",
        (False, True): "SHADOW_ONLY", (False, False): "NEITHER",
    }[(production_present, shadow_present)]
    terminal = selection.terminal
    delta = {
        "presence_agreement": presence,
        "classification": {
            "status": NOT_COMPARABLE,
            "production_pattern": (production["classification"]["pattern"]
                                   if production_present else UNAVAILABLE),
            "shadow": "NO_FAMILY_ASSIGNED_IN_SLICE_D",
        },
        "support_coverage": NOT_COMPARABLE,
        "touch_evidence": NOT_COMPARABLE,
        "terminal_compression": {
            "status": NOT_COMPARABLE,
            "production_is_compressing": (production["compression"]
                                          ["is_compressing"]
                                          if production_present else UNAVAILABLE),
            "shadow_terminal_width_trend": (
                terminal.terminal_width_trend if terminal is not None
                else UNAVAILABLE),
        },
    }
    if not (production_present and shadow_present):
        delta["sides"] = UNAVAILABLE
        delta["widths_at_production_interval"] = UNAVAILABLE
        delta["identity"] = UNAVAILABLE
        return delta

    sides = {}
    for side in ("upper", "lower"):
        prod = production[side]
        shadow = getattr(pair, f"{side}_boundary")
        anchors = (prod["anchor_index"], prod["second_index"])
        support = set(shadow.inlier_pivot_indices)
        sides[side] = {
            "production_anchors": anchors,
            "shadow_support": shadow.inlier_pivot_indices,
            "production_anchors_in_shadow_support": sum(
                a in support for a in anchors),
            "shadow_support_not_production_anchors": len(support - set(anchors)),
            "seed_anchor_match": tuple(anchors) == shadow.seed_anchor_indices,
            "slope_delta_shadow_minus_production": shadow.slope - prod["slope"],
            "production_anchor_span": prod["anchor_span"],
            "shadow_support_span": shadow.support_span,
            "span_delta_shadow_minus_production": (
                shadow.support_span - prod["anchor_span"]
                if prod["anchor_span"] is not None else UNAVAILABLE),
        }
    delta["sides"] = sides
    start, end = production["start_index"], production["end_index"]
    widths = {}
    for label, index in (("start", start), ("end", end)):
        shadow_width = (_line_value(pair.upper_boundary.slope,
                                    pair.upper_boundary.intercept, index)
                        - _line_value(pair.lower_boundary.slope,
                                      pair.lower_boundary.intercept, index))
        prod_width = production["compression"][f"{label}_width"]
        widths[label] = {
            "index": index, "production_width": prod_width,
            "shadow_signed_width": shadow_width,
            "delta_shadow_minus_production": (
                shadow_width - prod_width if prod_width is not None
                else UNAVAILABLE),
        }
    delta["widths_at_production_interval"] = widths
    delta["identity"] = {
        "production_identity": production["identity"],
        "both_sides_seed_anchor_match": all(
            s["seed_anchor_match"] for s in sides.values()),
        "both_sides_anchors_inside_shadow_support": all(
            s["production_anchors_in_shadow_support"] == 2
            for s in sides.values()),
    }
    return delta


def compose_case_report(case, frame, upper_candidates, lower_candidates,
                        parameters=None):
    """One case report. ``frame`` may contain rows after the cutoff; they are
    sliced away before production or SHADOW code sees anything."""
    parameters = dict(DEFAULT_SHADOW_REPORT_PARAMETERS
                      if parameters is None else parameters)
    as_of = int(case["as_of_index"])
    if as_of < 0 or as_of >= len(frame):
        raise ValueError(f"{case['case_id']}: as_of_index outside frame")
    prefix = frame.iloc[:as_of + 1].copy(deep=True).reset_index(drop=True)
    _, production = _production_side(prefix, as_of)
    pair, selection, shadow = _shadow_side(
        prefix, upper_candidates, lower_candidates, as_of, parameters)
    report = {
        "case_id": case["case_id"], "symbol": case.get("symbol", UNAVAILABLE),
        "timeframe": case.get("timeframe", UNAVAILABLE),
        "evidence_class": case.get("evidence_class", UNAVAILABLE),
        "expectation_kind": case.get("expectation", {}).get("kind", UNAVAILABLE),
        "as_of_index": as_of, "frame_rows": as_of + 1,
        "production": production, "shadow": shadow,
        "delta": _delta(production, pair, selection),
    }
    counter = [0]
    plain = _plain(report, counter)
    plain["non_finite_values_replaced"] = counter[0]
    return plain


def build_gold_case_report(case, frame, parameters=None):
    """Build Slice A boundaries on the cutoff prefix, then compose the report."""
    parameters = dict(DEFAULT_SHADOW_REPORT_PARAMETERS
                      if parameters is None else parameters)
    boundary = dict(as_of_index=int(case["as_of_index"]),
                    episode_start_index=0,
                    **{k: parameters[k] for k in _BOUNDARY_KEYS})
    return compose_case_report(
        case, frame,
        build_boundary_consensus(frame, side="upper", **boundary),
        build_boundary_consensus(frame, side="lower", **boundary),
        parameters)


def aggregate_reports(cases):
    """Counts only. No ranking, scoring or overall performance figure."""
    def counts(items):
        return dict(sorted(Counter(items).items(), key=lambda kv: (-kv[1], kv[0])))

    comparable = [c for c in cases if c["delta"]["identity"] != UNAVAILABLE]
    rejected = [c for c in cases
                if c["shadow"]["selection_status"] == "NO_ADMISSIBLE_PAIR"]
    selected = [c for c in cases
                if c["shadow"]["selection_status"] == "SELECTED"]
    top_reasons = Counter(r for c in rejected
                          for r in c["shadow"]["rejection_reasons_of_top_ranked"])
    trend = lambda c: (c["shadow"]["terminal_of_top_ranked"]
                       or {}).get("terminal_width_trend", UNAVAILABLE)
    return {
        "total_cases": len(cases),
        "cases_with_shadow_candidates": sum(
            c["shadow"]["candidate_count"] > 0 for c in cases),
        "cases_with_admissible_shadow_selection": len(selected),
        "cases_with_rejected_shadow_selection": len(rejected),
        "top_rejection_reasons_of_top_ranked": dict(sorted(
            top_reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "identity_comparable_cases": len(comparable),
        "both_sides_seed_anchor_match": sum(
            c["delta"]["identity"]["both_sides_seed_anchor_match"]
            for c in comparable),
        "both_sides_production_anchors_inside_shadow_support": sum(
            c["delta"]["identity"]["both_sides_anchors_inside_shadow_support"]
            for c in comparable),
        "presence_agreement": counts(
            c["delta"]["presence_agreement"] for c in cases),
        "production_pattern_counts": counts(
            c["production"]["classification"]["pattern"] for c in cases
            if c["production"]["geometry_present"]),
        "classification_agreement": NOT_COMPARABLE,
        "terminal_trend_counts_top_ranked": counts(trend(c) for c in cases),
        "terminal_trend_counts_selected_only": counts(trend(c) for c in selected),
    }


def build_gold_delta_report(manifest_path=None, parameters=None, case_ids=None):
    """Full deterministic report over the exact-fixture Geometry Gold cases."""
    # Gold loaders live with the test fixtures; imported lazily so nothing in
    # the runtime import graph depends on them.
    from tests.geometry_gold import MANIFEST, _load_frame, load_manifest

    parameters = dict(DEFAULT_SHADOW_REPORT_PARAMETERS
                      if parameters is None else parameters)
    manifest = load_manifest(MANIFEST if manifest_path is None else manifest_path)
    cases = [build_gold_case_report(case, _load_frame(case), parameters)
             for case in manifest["cases"]
             if case_ids is None or case["case_id"] in case_ids]
    return {
        "mode": "SHADOW_DELTA_REPORT_ONLY", "schema_version": SCHEMA_VERSION,
        "verdict": "NONE_FACTS_ONLY", "parameters": parameters,
        "cases": cases, "aggregate": aggregate_reports(cases),
    }


def format_delta_table(report):
    """Compact human-readable review table; never wired to runtime output."""
    rows = [("case", "prod", "prod_pattern", "cands", "adm", "shadow",
             "trend", "seed_match", "up_dslope", "lo_dslope")]
    for c in report["cases"]:
        sides = c["delta"]["sides"]
        ident = c["delta"]["identity"]
        rows.append((
            c["case_id"][:34],
            "Y" if c["production"]["geometry_present"] else "N",
            str((c["production"]["classification"] or {}).get("pattern", "-"))
            if c["production"]["geometry_present"] else "-",
            str(c["shadow"]["candidate_count"]),
            str(c["shadow"]["admissible_count"]),
            c["shadow"]["selection_status"],
            (c["shadow"]["terminal_of_top_ranked"] or {}).get(
                "terminal_width_trend", "-"),
            "-" if ident == UNAVAILABLE else str(ident["both_sides_seed_anchor_match"]),
            "-" if sides == UNAVAILABLE else
            f"{sides['upper']['slope_delta_shadow_minus_production']:+.3g}",
            "-" if sides == UNAVAILABLE else
            f"{sides['lower']['slope_delta_shadow_minus_production']:+.3g}",
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(v.ljust(w) for v, w in zip(r, widths)) for r in rows]
    agg = report["aggregate"]
    lines.append("")
    lines.append(f"cases={agg['total_cases']} "
                 f"with_candidates={agg['cases_with_shadow_candidates']} "
                 f"admissible={agg['cases_with_admissible_shadow_selection']} "
                 f"presence={agg['presence_agreement']} "
                 f"(facts only; no verdict)")
    return "\n".join(lines)
