"""GEO-U1 Slice E: facts-only calibration-readiness gate for Geometry evidence.

DIAGNOSTIC ONLY. It counts what the exact-fixture Slice D reports show and
applies one fixed, documented minimum-evidence rule. It never calibrates,
chooses or changes a threshold, and nothing in production imports it.

Readiness rule (conservative; every line must hold, otherwise NOT ready):
- at least MIN_EXACT_CASES exact source-time/READY cases;
- every case has complete provenance;
- among cases with an admissible SHADOW selection, at least
  MIN_PERSISTENT_COMPRESSION PERSISTENT_COMPRESSION, MIN_EXPANSION EXPANSION
  and MIN_NO_TREND NO_PERSISTENT_WIDTH_TREND terminal trends, so a later
  threshold can be tested against both width directions and a neutral class;
- at least MIN_NO_ADMISSIBLE cases with no admissible SHADOW pair
  (negative controls);
- at least MIN_PRODUCTION_DETECTED cases the unchanged production path detects.
The numbers are fixed before looking at the expanded set and must only be
changed by a separately authorized slice.
"""

from collections import Counter
from dataclasses import dataclass

MIN_EXACT_CASES = 12
MIN_PERSISTENT_COMPRESSION = 3
MIN_EXPANSION = 2
MIN_NO_TREND = 3
MIN_NO_ADMISSIBLE = 2
MIN_PRODUCTION_DETECTED = 3

READINESS_RULE = (
    f"exact_cases>={MIN_EXACT_CASES}; provenance complete for all; "
    f"selected PERSISTENT_COMPRESSION>={MIN_PERSISTENT_COMPRESSION}; "
    f"selected EXPANSION>={MIN_EXPANSION}; "
    f"selected NO_PERSISTENT_WIDTH_TREND>={MIN_NO_TREND}; "
    f"no-admissible-pair cases>={MIN_NO_ADMISSIBLE}; "
    f"production detected cases>={MIN_PRODUCTION_DETECTED}"
)

REPRODUCIBILITY_RULE = (
    "selected PERSISTENT_COMPRESSION/EXPANSION count only when independently "
    "reproduced (two separate runs, one with future rows, identical report)"
)


@dataclass(frozen=True)
class GeometryEvidenceReadiness:
    exact_case_count: int
    newly_recovered_case_count: int
    persistent_compression_count: int
    expansion_count: int
    no_persistent_trend_count: int
    non_positive_width_count: int
    insufficient_window_count: int
    rejected_selection_count: int
    production_positive_family_counts: tuple[tuple[str, int], ...]
    production_detected_count: int
    source_provenance_complete_count: int
    unrecoverable_targets: tuple[str, ...]
    diversity_gaps: tuple[str, ...]
    calibration_ready: bool
    calibration_blockers: tuple[str, ...]
    readiness_rule: str


_REQUIRED_PROVENANCE = (
    "source", "request", "retrieved_at_utc", "timezone", "interval_ms",
    "scanner_record", "cutoff_rule", "cutoff_candle_open_ms",
    "first_candle_open_ms", "last_candle_open_ms", "bars", "normalization",
    "validation",
)


def exact_source_time_case_problems(case, payload):
    """Why a manifest case may NOT enter exact Gold; empty tuple = eligible.

    A screenshot-only or visually timed case has no fixture candles, cutoff or
    retrieval provenance, so it always fails here.
    """
    problems = []
    if case.get("evidence_class") != "EXACT_SOURCE_TIME":
        problems.append("EVIDENCE_CLASS_NOT_EXACT_SOURCE_TIME")
    for key in ("symbol", "timeframe", "fixture_ref", "as_of_index",
                "cutoff_candle_open_ms"):
        if case.get(key) in (None, ""):
            problems.append(f"MISSING_{key.upper()}")
    payload = payload or {}
    provenance = payload.get("provenance") or {}
    problems += [f"MISSING_PROVENANCE_{key.upper()}"
                 for key in _REQUIRED_PROVENANCE if key not in provenance]
    candles = payload.get("candles") or []
    if not candles:
        problems.append("NO_FIXTURE_CANDLES")
        return tuple(problems)
    interval = provenance.get("interval_ms")
    times = [row[0] for row in candles]
    if interval and times != [times[0] + i * interval for i in range(len(times))]:
        problems.append("CANDLE_SPACING_NOT_EXACT")
    if case.get("as_of_index") != len(candles) - 1:
        problems.append("AS_OF_INDEX_NOT_LAST_FIXTURE_ROW")
    if times[-1] != case.get("cutoff_candle_open_ms") or times[-1] != provenance.get(
            "cutoff_candle_open_ms"):
        problems.append("CUTOFF_CANDLE_NOT_PINNED")
    validation = provenance.get("validation") or {}
    if validation.get("recorded_anchor_prices_match_fixture") is not True:
        problems.append("RECORDED_ANCHOR_PRICES_NOT_VERIFIED")
    return tuple(problems)


def case_facts(case_report):
    """Compact, JSON-plain facts of one Slice D case record (no judgement)."""
    production = case_report["production"]
    shadow = case_report["shadow"]
    terminal = shadow["terminal_of_top_ranked"] or {}
    present = production["geometry_present"]
    return {
        "case_id": case_report["case_id"],
        "symbol": case_report["symbol"],
        "timeframe": case_report["timeframe"],
        "production_geometry_present": present,
        "production_identity": production["identity"],
        "production_detected": bool(present
                                    and production["classification"]["detected"]),
        "production_pattern": (production["classification"]["pattern"]
                               if present else None),
        "selection_status": shadow["selection_status"],
        "candidate_count": shadow["candidate_count"],
        "admissible_count": shadow["admissible_count"],
        "selected_pair_identity": shadow["selected_pair_identity"],
        "terminal_width_trend": terminal.get("terminal_width_trend", "UNAVAILABLE"),
        "terminal_compression_ratio": terminal.get("terminal_compression_ratio"),
        "realized_contraction_ratio": terminal.get("realized_contraction_ratio"),
        "rejection_reasons_of_top_ranked": list(
            shadow["rejection_reasons_of_top_ranked"]),
        "presence_agreement": case_report["delta"]["presence_agreement"],
    }


def _counts(items):
    return dict(sorted(Counter(items).items(), key=lambda kv: (-kv[1], kv[0])))


def aggregate_case_facts(facts):
    """Count-only expanded aggregate; no ranking or score."""
    selected = [f for f in facts if f["selection_status"] == "SELECTED"]
    return {
        "total_cases": len(facts),
        "terminal_trend_counts_selected": _counts(
            f["terminal_width_trend"] for f in selected),
        "terminal_trend_counts_all_top_ranked": _counts(
            f["terminal_width_trend"] for f in facts),
        "selection_status_counts": _counts(f["selection_status"] for f in facts),
        "production_pattern_counts": _counts(
            f["production_pattern"] for f in facts
            if f["production_geometry_present"]),
        "production_detected_count": sum(f["production_detected"] for f in facts),
        "presence_agreement": _counts(f["presence_agreement"] for f in facts),
    }


def assess_geometry_evidence_readiness(
    facts, *, newly_recovered_case_ids, provenance_complete_case_ids,
    unrecoverable_targets, reproduced_case_ids=None,
):
    """Apply the fixed readiness rule to compact case facts (see case_facts).

    ``reproduced_case_ids`` (optional) adds REPRODUCIBILITY_RULE; when omitted
    the result is exactly the Slice E behaviour.
    """
    ids = [f["case_id"] for f in facts]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case_id in readiness input")
    selected = [f for f in facts if f["selection_status"] == "SELECTED"]
    trends = Counter(f["terminal_width_trend"] for f in selected)
    all_trends = Counter(f["terminal_width_trend"] for f in facts)
    detected = [f for f in facts if f["production_detected"]]
    families = Counter(f["production_pattern"] for f in detected)
    no_admissible = len(facts) - len(selected)
    provenance = sum(case_id in provenance_complete_case_ids for case_id in ids)

    checks = (
        ("EXACT_CASES", len(facts), MIN_EXACT_CASES),
        ("PERSISTENT_COMPRESSION", trends["PERSISTENT_COMPRESSION"],
         MIN_PERSISTENT_COMPRESSION),
        ("EXPANSION", trends["EXPANSION"], MIN_EXPANSION),
        ("NO_PERSISTENT_WIDTH_TREND", trends["NO_PERSISTENT_WIDTH_TREND"],
         MIN_NO_TREND),
        ("NO_ADMISSIBLE_PAIR", no_admissible, MIN_NO_ADMISSIBLE),
        ("PRODUCTION_DETECTED", len(detected), MIN_PRODUCTION_DETECTED),
    )
    gaps = [f"{name}: have {have}, need >= {need}"
            for name, have, need in checks if have < need]
    blockers = list(gaps)
    if provenance != len(facts):
        blockers.append(
            f"PROVENANCE_INCOMPLETE: {len(facts) - provenance} case(s)")
    rule = READINESS_RULE
    if reproduced_case_ids is not None:
        # Opt-in (Slice F): a selected compression/expansion case counts toward
        # its minimum only with independent-rerun evidence. Thresholds unchanged.
        rule = f"{READINESS_RULE}; {REPRODUCIBILITY_RULE}"
        for trend, minimum in (("PERSISTENT_COMPRESSION", MIN_PERSISTENT_COMPRESSION),
                               ("EXPANSION", MIN_EXPANSION)):
            cases = [f["case_id"] for f in selected
                     if f["terminal_width_trend"] == trend]
            missing = sorted(c for c in cases if c not in reproduced_case_ids)
            reproduced = len(cases) - len(missing)
            if missing and reproduced < minimum:
                blockers.append(
                    f"UNREPRODUCED_{trend}: reproduced {reproduced}, need >= "
                    f"{minimum}; missing {', '.join(missing)}")
    return GeometryEvidenceReadiness(
        exact_case_count=len(facts),
        newly_recovered_case_count=sum(i in newly_recovered_case_ids for i in ids),
        persistent_compression_count=trends["PERSISTENT_COMPRESSION"],
        expansion_count=trends["EXPANSION"],
        no_persistent_trend_count=trends["NO_PERSISTENT_WIDTH_TREND"],
        non_positive_width_count=all_trends["NON_POSITIVE_WIDTH"],
        insufficient_window_count=all_trends["INSUFFICIENT_WINDOW"],
        rejected_selection_count=no_admissible,
        production_positive_family_counts=tuple(sorted(families.items())),
        production_detected_count=len(detected),
        source_provenance_complete_count=provenance,
        unrecoverable_targets=tuple(sorted(unrecoverable_targets)),
        diversity_gaps=tuple(gaps),
        calibration_ready=not blockers,
        calibration_blockers=tuple(blockers),
        readiness_rule=rule,
    )
