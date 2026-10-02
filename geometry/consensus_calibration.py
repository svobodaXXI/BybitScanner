"""GEO-U1 Slice H0: SHADOW-only Geometry threshold calibration methodology.

DIAGNOSTIC ONLY. Nothing in production imports this module; it never changes
``DEFAULT_SHADOW_REPORT_PARAMETERS``, the population policy, the readiness
constants or any production selection/classification. A candidate preset, if
any, lives only in the diagnostic result (``production_cutover_authorized`` is
always False).

Everything below up to ``# --- exact computation`` was fixed BEFORE any
sensitivity run or sweep and is never chosen from observed outcomes:

Objective (gate-first, lexicographic; no scalar score is used):
- evidence classes come from the baseline run on the exact crypto population
  (GEO-U1-POP-1): A selected PERSISTENT_COMPRESSION, B selected EXPANSION,
  C selected NO_PERSISTENT_WIDTH_TREND, D NO_ADMISSIBLE_PAIR negative controls;
- HARD_GATES reject a parameter set outright;
- surviving sets are ordered by PREFERENCE_ORDER; a set is preferred over the
  baseline only if it is strictly better on that order. The baseline (no lost
  selection, no change) can therefore only be beaten by fewer ambiguous
  (identity-tie-break) selections: agreement with production labels and
  moving terminal thresholds away from observed ratios are never rewarded;
- a preferred set must also stay preferred in every leave-one-out fold
  (otherwise FRAGILE), pass the exact determinism/future-row check and not be
  blocked by data concentration before it can be emitted as a SHADOW candidate.
"""

import json
import time
from collections import Counter, OrderedDict
from contextlib import contextmanager
from itertools import product
from math import isfinite

import geometry.consensus_selection as _selection
from .consensus_boundary import build_boundary_consensus
from .consensus_calibration_population import POLICY_V1, classify_cases
from .consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS

SCHEMA_VERSION = 1
MODE = "SHADOW_CALIBRATION_DIAGNOSTIC_ONLY"
PRODUCTION_CUTOVER_AUTHORIZED = False

PERSISTENT_COMPRESSION = "PERSISTENT_COMPRESSION"
EXPANSION = "EXPANSION"
NO_TREND = "NO_PERSISTENT_WIDTH_TREND"
NO_ADMISSIBLE = "NO_ADMISSIBLE_PAIR"
SELECTED_TRENDS = (PERSISTENT_COMPRESSION, EXPANSION, NO_TREND)

KEEP_BASELINE = "KEEP_BASELINE"
CANDIDATE_PRESET = "CANDIDATE_PRESET_FOR_SHADOW_VALIDATION"
MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
CALIBRATION_UNDERDETERMINED = "CALIBRATION_UNDERDETERMINED"
DATA_CONCENTRATION_BLOCKER = "DATA_CONCENTRATION_BLOCKER"

HARD_GATES = (
    "COMPRESSION_RETAINED: every class-A case stays SELECTED PERSISTENT_COMPRESSION",
    "EXPANSION_RETAINED: every class-B case stays SELECTED EXPANSION",
    "NEGATIVE_CONTROLS_NOT_SELECTED: no class-D case becomes SELECTED",
    "DETERMINISTIC_FUTURE_INVARIANT: exact rerun with appended future rows is "
    "identical (verified for every set eligible for proposal)",
    "POPULATION_GEO_U1_POP_1: case set equals the policy-eligible crypto set",
    "NO_SPECIAL_CASING: one flat 17-key parameter mapping for every case",
    "NO_TREND_CLASS_COLLAPSE: each selected trend class keeps >= 1 case",
)
PREFERENCE_ORDER = (
    "selected_lost (baseline SELECTED cases no longer SELECTED), lower first",
    "ambiguous_selections (SELECTED decided by IDENTITY_TIE_BREAK), lower first",
    "changed_cases (status, trend or selected identity differ), lower first",
    "parameters_changed vs baseline, lower first",
    "canonical parameter values, ascending (deterministic tie only)",
)
SENSITIVITY_RULE = (
    "LOW/HIGH = CURRENT -/+ 25% of the semantic magnitude (for ratio "
    "thresholds: of the distance from the neutral ratio 1.0); integers -/+ 1; "
    "snapped to the nearest value the SHADOW modules accept. Chosen from "
    "semantics only, never from case outcomes."
)
ACTIVE_RULE = (
    "a parameter is MATERIAL if LOW or HIGH changes the evidence class "
    "(selection status or terminal trend) of >= 1 case; IDENTITY_ONLY "
    "(selected pair changes, class unchanged) and INSENSITIVE parameters are "
    "frozen at CURRENT. Structural invariants are excluded before sensitivity "
    "and cannot become active. > 6 MATERIAL parameters -> "
    "CALIBRATION_UNDERDETERMINED (no sweep)."
)
MAX_ACTIVE_PARAMETERS = 6
CONCENTRATION_RULE = (
    "DATA_CONCENTRATION_BLOCKER if one symbol is > 50% of target cases, one "
    "timeframe is > 75% of target cases, or any hard-gate class (A, B, D) "
    "draws all of its cases from one symbol or from one timeframe."
)

# (name, LOW, HIGH, semantic justification); CURRENT is the unchanged default.
PARAMETER_DOMAIN = (
    ("inlier_band_atr", 0.15, 0.25,
     "pivot-to-line inlier tolerance (ATR); stays < separation_atr"),
    ("separation_atr", 0.5625, 0.9375,
     "inward body retreat (ATR) that splits touch clusters; stays > inlier band"),
    ("touch_band_atr", 0.15, 0.25, "boundary contact zone (ATR) for traversals"),
    ("minimum_swing_width_fraction", 0.225, 0.375,
     "departure needed as a fraction of envelope width"),
    ("minimum_swing_atr", 0.375, 0.625, "departure floor in ATR"),
    ("minimum_side_touch_clusters", 1, 3, "integer -/+ 1 (module minimum 1)"),
    ("min_cross_boundary_traversals", 0, 2, "integer -/+ 1 (module minimum 0)"),
    ("min_alternating_touches", 2, 4, "integer -/+ 1"),
    ("min_touch_balance", 0.1875, 0.3125, "minority/majority side touch ratio"),
    ("min_shared_support_coverage", 0.1875, 0.3125,
     "shared support span / episode span"),
    ("max_support_gap_fraction", 0.375, 0.625,
     "allowed stale tail after shared support / episode span"),
    ("terminal_window_bars", 24, 36,
     "nearest multiples of terminal_segments (3) inside -/+ 25% (22.5..37.5)"),
    ("terminal_segments", 2, 5,
     "integer; 4 does not divide 30 bars, so HIGH is the next valid divisor "
     "(5 segments of 6 bars >= 3)"),
    ("compression_max_ratio", 0.875, 0.925,
     "-/+ 25% of the 0.1 distance from neutral 1.0"),
    ("expansion_min_ratio", 1.075, 1.125,
     "-/+ 25% of the 0.1 distance from neutral 1.0"),
    ("segment_tolerance", 0.0375, 0.0625, "per-step monotonic tolerance"),
    ("single_bar_narrow_ratio", 0.375, 0.625,
     "last-bar range / median range flag (diagnostic only)"),
)

# H4-B policy: U-L-U or L-U-L is the first repeated two-boundary oscillation.
# Two touches establish only one transition; four demand extra recurrence and
# change recall. Historical H0/H2 LOW/HIGH results remain in their pinned files.
FROZEN_STRUCTURAL_PARAMETERS = {
    "min_alternating_touches": {
        "value": 3,
        "category": "STRUCTURAL_INVARIANT",
        "reason": "Three alternating touches prove repeated two-boundary oscillation; "
                  "two prove one transition, while four impose extra recurrence.",
    },
}
CALIBRATABLE_PARAMETER_DOMAIN = tuple(
    row for row in PARAMETER_DOMAIN if row[0] not in FROZEN_STRUCTURAL_PARAMETERS)


def _check_calibration_policy(active=()):
    for name, policy in FROZEN_STRUCTURAL_PARAMETERS.items():
        if DEFAULT_SHADOW_REPORT_PARAMETERS[name] != policy["value"]:
            raise ValueError(f"FROZEN_STRUCTURAL_DEFAULT_MISMATCH: {name}")
    invalid = set(active) - {row[0] for row in CALIBRATABLE_PARAMETER_DOMAIN}
    if invalid:
        raise ValueError(f"NON_CALIBRATABLE_ACTIVE_PARAMETERS: {sorted(invalid)}")

_BOUNDARY_KEYS = ("inlier_band_atr", "separation_atr")
_PAIR_KEYS = ("touch_band_atr", "minimum_swing_width_fraction",
              "minimum_swing_atr", "minimum_side_touch_clusters")
_OUTCOME_CLASS_KEYS = ("selection_status", "terminal_width_trend",
                       "selected_pair_identity")
SWEEP_COUNT_COLUMNS = (
    "compression_retained", "expansion_retained", "no_admissible_retained",
    "no_trend_retained", "changed_cases", "newly_selected", "newly_no_admissible",
    "pair_identity_changed", "selected_lost", "qualifying_gained",
    "ambiguous_selections",
)


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (bool, int, float, str)):
        value = value.item()
    if isinstance(value, float) and not isfinite(value):
        return None
    return value


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def parameter_key(parameters):
    return _dumps({k: parameters[k] for k in sorted(parameters)})


def validate_parameter_set(parameters):
    """One flat 17-key mapping of scalars (NO_SPECIAL_CASING) accepted by the
    SHADOW modules' documented constraints; returns problems (empty = valid)."""
    problems = []
    if set(parameters) != set(DEFAULT_SHADOW_REPORT_PARAMETERS):
        problems.append("PARAMETER_KEYS_DIFFER_FROM_DEFAULTS")
        return problems
    for name, policy in FROZEN_STRUCTURAL_PARAMETERS.items():
        if parameters[name] != policy["value"]:
            problems.append(f"FROZEN_STRUCTURAL_PARAMETER_VARIED: {name}")
    if any(isinstance(v, (dict, list, tuple)) or isinstance(v, bool)
           for v in parameters.values()):
        problems.append("NON_SCALAR_PARAMETER")
    if not 0 < parameters["inlier_band_atr"] < parameters["separation_atr"]:
        problems.append("INLIER_BAND_NOT_BELOW_SEPARATION")
    window, segments = parameters["terminal_window_bars"], parameters["terminal_segments"]
    if segments < 2 or window % segments or window // segments < 3:
        problems.append("TERMINAL_WINDOW_NOT_DIVISIBLE_INTO_3BAR_SEGMENTS")
    return problems


# --- population ------------------------------------------------------------

def load_target_population():
    """(cases, pinned_facts, classification, metadata) for GEO-U1-POP-1."""
    from tests.geometry_gold import ROOT, load_manifest

    gold = ROOT / "tests" / "fixtures" / "geometry_gold"
    manifests = [load_manifest(gold / name) for name in (
        "manifest_v1.json", "source_time_manifest_v1.json",
        "source_time_manifest_v2.json", "source_time_manifest_v3.json")]
    meta = [json.loads((gold / name).read_text(encoding="utf-8"))
            for name in ("instrument_metadata_v1.json", "instrument_metadata_v2.json")]
    classification = classify_cases(
        meta[0]["case_instruments"] + meta[1]["case_instruments"],
        {**meta[0]["instruments"], **meta[1]["instruments"]})
    pinned = {f["case_id"]: f for f in manifests[-1]["observed_slice_d_case_facts"]}
    cases = sorted((c for m in manifests for c in m["cases"]
                    if classification[c["case_id"]]["calibration_eligible"]),
                   key=lambda c: c["case_id"])
    return cases, pinned, classification


# --- exact computation -------------------------------------------------------

class ExactMemo:
    """Per-case exact memo of pure SHADOW stages.

    Boundaries are keyed by their two parameters, pair sets by (boundary key,
    pair parameters) and terminal evidence by (boundary key, pair identity,
    terminal parameters). The unchanged ``select_envelope_pair_shadow`` runs
    every time; only identical pure calls return their identical immutable
    result. Nothing is approximated.
    """

    def __init__(self, frame, as_of_index, pair_slots=3):
        self.frame = frame
        self.as_of = as_of_index
        self.boundaries = {}
        self.pairs = OrderedDict()
        self.pair_slots = pair_slots
        self.terminals = {}
        self.boundary_key = None

    def boundaries_for(self, parameters):
        key = tuple(parameters[k] for k in _BOUNDARY_KEYS)
        if key not in self.boundaries:
            common = dict(as_of_index=self.as_of, episode_start_index=0,
                          **{k: parameters[k] for k in _BOUNDARY_KEYS})
            self.boundaries[key] = (
                build_boundary_consensus(self.frame, side="upper", **common),
                build_boundary_consensus(self.frame, side="lower", **common))
        self.boundary_key = key
        return self.boundaries[key]

    def _pairs(self, candles, uppers, lowers, **kwargs):
        expected = self.boundaries[self.boundary_key]
        if uppers is not expected[0] or lowers is not expected[1]:
            raise RuntimeError("memo boundary mismatch")
        key = (self.boundary_key, tuple(sorted(kwargs.items())))
        if key in self.pairs:
            self.pairs.move_to_end(key)
        else:
            self.pairs[key] = self._original_pairs(candles, uppers, lowers, **kwargs)
            while len(self.pairs) > self.pair_slots:
                self.pairs.popitem(last=False)
        return self.pairs[key]

    def _terminal(self, frame, pair, **kwargs):
        key = (self.boundary_key, pair.upper_boundary_identity,
               pair.lower_boundary_identity, tuple(sorted(kwargs.items())))
        if key not in self.terminals:
            self.terminals[key] = self._original_terminal(frame, pair, **kwargs)
        return self.terminals[key]

    @contextmanager
    def active(self):
        self._original_pairs = _selection.build_envelope_pair_consensus
        self._original_terminal = _selection.terminal_compression_evidence
        _selection.build_envelope_pair_consensus = self._pairs
        _selection.terminal_compression_evidence = self._terminal
        try:
            yield self
        finally:
            _selection.build_envelope_pair_consensus = self._original_pairs
            _selection.terminal_compression_evidence = self._original_terminal


def selection_outcome(selection):
    """Compact JSON-plain facts of one SHADOW selection (no judgement)."""
    terminal = selection.terminal
    pair = selection.selected_pair
    outcome = {
        "selection_status": selection.selection_status,
        "terminal_width_trend": (terminal.terminal_width_trend
                                 if terminal is not None else "UNAVAILABLE"),
        "candidate_count": selection.candidate_count,
        "admissible_count": selection.admissible_count,
        "selected_pair_identity": selection.selected_pair_identity,
        "deciding_component": selection.deciding_component,
        "rejection_reasons_of_top_ranked": selection.rejection_reasons,
        "terminal_compression_ratio": getattr(terminal, "terminal_compression_ratio", None),
        "realized_contraction_ratio": getattr(terminal, "realized_contraction_ratio", None),
        "terminal_relative_width_slope": getattr(
            terminal, "terminal_relative_width_slope", None),
        "selected_pair_evidence": None if pair is None else {k: getattr(pair, k) for k in (
            "upper_touch_count", "lower_touch_count", "alternating_touch_count",
            "cross_boundary_traversal_count", "touch_balance",
            "shared_support_span", "shared_support_coverage_ratio")},
    }
    return json.loads(_dumps(_plain(outcome)))


def case_outcome(case, frame, parameters, memo=None):
    """Exact SHADOW outcome of one case under one parameter set."""
    as_of = int(case["as_of_index"])
    prefix = frame.iloc[:as_of + 1].copy(deep=True).reset_index(drop=True)
    memo = memo or ExactMemo(prefix, as_of)
    uppers, lowers = memo.boundaries_for(parameters)
    selection_parameters = {k: v for k, v in parameters.items()
                            if k not in _BOUNDARY_KEYS}
    with memo.active():
        selection = _selection.select_envelope_pair_shadow(
            memo.frame, uppers, lowers, as_of_index=as_of, episode_start_index=0,
            episode_end_index=as_of, **selection_parameters)
    return selection_outcome(selection)


def _group_order(parameter_sets):
    """Order sets so memo slots are reused: boundary, then pair parameters."""
    def key(item):
        params = item[1]
        return (tuple(params[k] for k in _BOUNDARY_KEYS),
                tuple(params[k] for k in _PAIR_KEYS), item[0])
    return sorted(parameter_sets, key=key)


def _case_worker(args):
    case, parameter_sets, cache_dir = args
    from pathlib import Path
    from tests.geometry_gold import _load_frame

    # Optional exact on-disk cache keyed by fixture + parameter set.
    cache_path = None if cache_dir is None else Path(cache_dir) / (
        case["case_id"] + ".json")
    cache = {}
    if cache_path is not None and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("fixture_ref") != case["fixture_ref"]:
            cache = {}
    entries = cache.setdefault("entries", {})
    cache["fixture_ref"] = case["fixture_ref"]
    frame = _load_frame(case)
    as_of = int(case["as_of_index"])
    memo = ExactMemo(frame.iloc[:as_of + 1].copy(deep=True).reset_index(drop=True), as_of)
    outcomes, timings = {}, {}
    for label, params in _group_order(parameter_sets):
        key = parameter_key(params)
        if key in entries:
            outcomes[label], timings[label] = entries[key]
            continue
        started = time.perf_counter()
        outcomes[label] = case_outcome(case, frame, params, memo)
        timings[label] = time.perf_counter() - started
        if cache_path is not None:
            entries[key] = [outcomes[label], timings[label]]
            cache_path.write_text(_dumps(cache), encoding="utf-8")
    return case["case_id"], outcomes, timings


def _pool_map(function, jobs, processes):
    # close()+join() instead of the context manager: Pool.terminate() reads
    # signal.SIGTERM, and this repository's own top-level ``signal`` package
    # shadows the stdlib module when the repo root is on sys.path.
    from multiprocessing import Pool
    pool = Pool(processes or min(len(jobs), 16))
    try:
        return pool.map(function, jobs, chunksize=1)
    finally:
        pool.close()
        pool.join()


def compute_outcomes(cases, parameter_sets, processes=None, cache_dir=None):
    """{case_id: {label: outcome}} plus timings; one exact worker per case."""
    jobs = [(case, list(parameter_sets), cache_dir) for case in cases]
    if processes == 1:
        results = [_case_worker(job) for job in jobs]
    else:
        results = _pool_map(_case_worker, jobs, processes)
    outcomes = {cid: rows for cid, rows, _ in results}
    timings = {cid: t for cid, _, t in results}
    return outcomes, timings


def _future_worker(args):
    case, parameters = args
    import pandas as pd
    from tests.geometry_gold import _load_frame
    from .consensus_evidence_readiness import case_facts
    from .consensus_gold_report import build_gold_case_report

    frame = _load_frame(case)
    future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
    facts = [case_facts(build_gold_case_report(case, f, parameters))
             for f in (frame, pd.concat([frame, future], ignore_index=True))]
    return case["case_id"], [json.loads(_dumps(_plain(f))) for f in facts]


def verify_exact_future_invariance(cases, parameters, outcomes, processes=None):
    """Unmemoized full report path, plain and with future NaN rows, must equal
    the memo outcome on every class field. Returns mismatching case ids."""
    results = _pool_map(_future_worker, [(c, parameters) for c in cases], processes)
    mismatches = []
    fields = ("selection_status", "terminal_width_trend", "candidate_count",
              "admissible_count", "selected_pair_identity",
              "terminal_compression_ratio", "realized_contraction_ratio")
    for case_id, (plain, future) in results:
        memo = outcomes[case_id]
        if plain != future or any(plain[f] != memo[f] for f in fields):
            mismatches.append(case_id)
    return sorted(mismatches)


# --- pure evaluation (stored outcomes in, facts out) --------------------------

def evidence_class(outcome):
    if outcome["selection_status"] == "SELECTED":
        return outcome["terminal_width_trend"]
    return outcome["selection_status"]


def _signature(outcome):
    return tuple(_dumps(outcome[k]) for k in _OUTCOME_CLASS_KEYS)


def evaluate_parameter_set(baseline, candidate, case_ids, parameters):
    """Gate results and raw counts of one set against the baseline (facts)."""
    ids = sorted(case_ids)
    roles = {c: evidence_class(baseline[c]) for c in ids}
    classes = {c: evidence_class(candidate[c]) for c in ids}

    def of_role(role):
        return [c for c in ids if roles[c] == role]

    lost_comp = [c for c in of_role(PERSISTENT_COMPRESSION)
                 if classes[c] != PERSISTENT_COMPRESSION]
    lost_exp = [c for c in of_role(EXPANSION) if classes[c] != EXPANSION]
    admitted = [c for c in of_role(NO_ADMISSIBLE)
                if candidate[c]["selection_status"] == "SELECTED"]
    selected_counts = Counter(classes[c] for c in ids
                              if candidate[c]["selection_status"] == "SELECTED")
    failures = []
    if lost_comp:
        failures.append(f"COMPRESSION_CASE_LOST: {', '.join(lost_comp)}")
    if lost_exp:
        failures.append(f"EXPANSION_CASE_LOST: {', '.join(lost_exp)}")
    if admitted:
        failures.append(f"NEGATIVE_CONTROL_ADMITTED: {', '.join(admitted)}")
    if validate_parameter_set(parameters):
        failures.append("NO_SPECIAL_CASING: " + ", ".join(
            validate_parameter_set(parameters)))
    collapsed = [t for t in SELECTED_TRENDS if selected_counts[t] == 0]
    if collapsed:
        failures.append(f"TREND_CLASS_COLLAPSE: {', '.join(collapsed)}")

    baseline_selected = {c for c in ids if baseline[c]["selection_status"] == "SELECTED"}
    candidate_selected = {c for c in ids if candidate[c]["selection_status"] == "SELECTED"}
    changed = [c for c in ids if _signature(baseline[c]) != _signature(candidate[c])]
    ambiguous = [c for c in sorted(candidate_selected)
                 if candidate[c]["deciding_component"] == "IDENTITY_TIE_BREAK"]
    differing = sorted(k for k in parameters
                       if parameters[k] != DEFAULT_SHADOW_REPORT_PARAMETERS[k])
    return {
        "gates_passed": not failures,
        "gate_failures": failures,
        "compression_retained": len(of_role(PERSISTENT_COMPRESSION)) - len(lost_comp),
        "expansion_retained": len(of_role(EXPANSION)) - len(lost_exp),
        "no_admissible_retained": sum(
            candidate[c]["selection_status"] == NO_ADMISSIBLE for c in of_role(NO_ADMISSIBLE)),
        "no_trend_retained": sum(classes[c] == NO_TREND for c in of_role(NO_TREND)),
        "selected_trend_counts": {t: selected_counts[t] for t in SELECTED_TRENDS},
        "changed_cases": changed,
        "class_changes": [[c, roles[c], classes[c]] for c in ids if roles[c] != classes[c]],
        "newly_selected": sorted(candidate_selected - baseline_selected),
        "newly_no_admissible": sorted(
            c for c in baseline_selected
            if candidate[c]["selection_status"] == NO_ADMISSIBLE),
        "selected_lost": sorted(baseline_selected - candidate_selected),
        "pair_identity_changed": [
            c for c in sorted(baseline_selected & candidate_selected)
            if baseline[c]["selected_pair_identity"]
            != candidate[c]["selected_pair_identity"]],
        "qualifying_gained": [c for c in ids
                              if roles[c] not in (PERSISTENT_COMPRESSION, EXPANSION)
                              and classes[c] in (PERSISTENT_COMPRESSION, EXPANSION)],
        "ambiguous_selections": ambiguous,
        "parameters_changed": differing,
    }


def preference_key(evaluation, parameters):
    return (len(evaluation["selected_lost"]), len(evaluation["ambiguous_selections"]),
            len(evaluation["changed_cases"]), len(evaluation["parameters_changed"]),
            parameter_key(parameters))


def preferred_over_baseline(evaluation, baseline_evaluation, parameters):
    if not evaluation["gates_passed"]:
        return False
    return (preference_key(evaluation, parameters)[:4]
            < preference_key(baseline_evaluation, DEFAULT_SHADOW_REPORT_PARAMETERS)[:4])


def leave_one_out(baseline, candidate, case_ids, parameters):
    """Is 'preferred over baseline' stable when any single case is removed?"""
    ids = sorted(case_ids)
    full = preferred_over_baseline(
        evaluate_parameter_set(baseline, candidate, ids, parameters),
        evaluate_parameter_set(baseline, baseline, ids, DEFAULT_SHADOW_REPORT_PARAMETERS),
        parameters)
    flips = []
    for removed in ids:
        rest = [c for c in ids if c != removed]
        fold = preferred_over_baseline(
            evaluate_parameter_set(baseline, candidate, rest, parameters),
            evaluate_parameter_set(baseline, baseline, rest,
                                   DEFAULT_SHADOW_REPORT_PARAMETERS),
            parameters)
        if fold != full:
            flips.append(removed)
    return {"preferred_full": full, "conclusion_flips_when_removed": flips,
            "robustness": "FRAGILE" if flips else "ROBUST"}


def sensitivity_parameter_sets():
    """[(label, parameters)]: BASELINE plus calibratable LOW/HIGH only."""
    _check_calibration_policy()
    sets = [("BASELINE", dict(DEFAULT_SHADOW_REPORT_PARAMETERS))]
    for name, low, high, _ in CALIBRATABLE_PARAMETER_DOMAIN:
        for tag, value in (("LOW", low), ("HIGH", high)):
            sets.append((f"{name}={tag}", {**DEFAULT_SHADOW_REPORT_PARAMETERS, name: value}))
    return sets


def summarize_sensitivity(outcomes, case_ids):
    """Descriptive one-at-a-time table and the MATERIAL/IDENTITY_ONLY split."""
    _check_calibration_policy()
    base = {c: outcomes[c]["BASELINE"] for c in case_ids}
    rows = []
    status = {}
    for name, low, high, rationale in CALIBRATABLE_PARAMETER_DOMAIN:
        row = {"parameter": name, "low": low,
               "current": DEFAULT_SHADOW_REPORT_PARAMETERS[name], "high": high,
               "rationale": rationale}
        material = identity = False
        for tag, value in (("LOW", low), ("HIGH", high)):
            params = {**DEFAULT_SHADOW_REPORT_PARAMETERS, name: value}
            cand = {c: outcomes[c][f"{name}={tag}"] for c in case_ids}
            ev = evaluate_parameter_set(base, cand, case_ids, params)
            row[tag.lower() + "_effect"] = {k: ev[k] for k in (
                "changed_cases", "class_changes", "newly_selected",
                "newly_no_admissible", "pair_identity_changed",
                "qualifying_gained", "gate_failures")}
            row[tag.lower() + "_effect"]["changed_case_count"] = len(ev["changed_cases"])
            row[tag.lower() + "_effect"]["qualifying_lost"] = [
                c for c, role, _ in ev["class_changes"]
                if role in (PERSISTENT_COMPRESSION, EXPANSION)]
            row[tag.lower() + "_effect"]["negative_controls_admitted"] = [
                c for c, role, _ in ev["class_changes"]
                if role == NO_ADMISSIBLE and c in ev["newly_selected"]]
            material |= bool(ev["class_changes"])
            identity |= bool(ev["pair_identity_changed"])
        row["sensitivity"] = ("MATERIAL" if material else
                              "IDENTITY_ONLY" if identity else "INSENSITIVE")
        status[name] = row["sensitivity"]
        rows.append(row)
    active = [n for n, _, _, _ in CALIBRATABLE_PARAMETER_DOMAIN
              if status[n] == "MATERIAL"]
    return rows, active


def sweep_parameter_sets(active):
    """Full finite grid over active parameters' LOW/CURRENT/HIGH; frozen rest."""
    _check_calibration_policy(active)
    domain = {name: (low, DEFAULT_SHADOW_REPORT_PARAMETERS[name], high)
              for name, low, high, _ in CALIBRATABLE_PARAMETER_DOMAIN}
    sets, invalid = [], []
    for values in product(*(domain[name] for name in active)):
        params = {**DEFAULT_SHADOW_REPORT_PARAMETERS, **dict(zip(active, values))}
        label = "GRID:" + ",".join(f"{n}={v}" for n, v in zip(active, values))
        (invalid if validate_parameter_set(params) else sets).append((label, params))
    return sets, invalid


def derived_parameter_sets(active):
    """(label -> parameters, sweep labels, invalid labels) from the locked
    domain alone; the pinned record therefore stores labels, not values."""
    _check_calibration_policy(active)
    sets = dict(sensitivity_parameter_sets())
    if len(active) > MAX_ACTIVE_PARAMETERS:
        return sets, [], []
    grid, invalid = sweep_parameter_sets(active)
    sets.update(grid)
    return sets, [label for label, _ in grid], [label for label, _ in invalid]


def concentration_summary(cases, classification, baseline):
    """Counts and the fixed CONCENTRATION_RULE (facts only)."""
    ids = [c["case_id"] for c in cases]
    by_id = {c["case_id"]: c for c in cases}
    symbol = {i: classification[i]["instrument_symbol"] for i in ids}
    timeframe = {i: str(by_id[i]["timeframe"]) for i in ids}
    roles = {i: evidence_class(baseline[i]) for i in ids}
    counts = lambda items: dict(sorted(Counter(items).items()))
    triggers = []
    total = len(ids)
    for value, n in Counter(symbol.values()).items():
        if n * 2 > total:
            triggers.append(f"SYMBOL_SHARE: {value} {n}/{total}")
    for value, n in Counter(timeframe.values()).items():
        if n * 4 > total * 3:
            triggers.append(f"TIMEFRAME_SHARE: {value} {n}/{total}")
    per_class = {}
    for role, label in ((PERSISTENT_COMPRESSION, "A"), (EXPANSION, "B"),
                        (NO_ADMISSIBLE, "D")):
        members = [i for i in ids if roles[i] == role]
        per_class[role] = {"symbols": counts(symbol[i] for i in members),
                           "timeframes": counts(timeframe[i] for i in members)}
        if len(set(symbol[i] for i in members)) == 1:
            triggers.append(f"CLASS_{label}_SINGLE_SYMBOL: {symbol[members[0]]}")
        if len(set(timeframe[i] for i in members)) == 1:
            triggers.append(f"CLASS_{label}_SINGLE_TIMEFRAME: {timeframe[members[0]]}m "
                            f"({len(members)}/{len(members)})")
    return {
        "rule": CONCENTRATION_RULE,
        "timeframe_counts": counts(timeframe.values()),
        "symbol_counts": counts(symbol.values()),
        "repeated_symbols": {s: n for s, n in counts(symbol.values()).items() if n > 1},
        "cashcat_share": f"{sum(s == 'CASHCATUSDT' for s in symbol.values())}/{total}",
        "symbol_type_counts": counts(
            classification[i]["symbol_type"] or "ordinary" for i in ids),
        "qualifying_by_symbol": counts(symbol[i] for i in ids
                                       if roles[i] in (PERSISTENT_COMPRESSION, EXPANSION)),
        "per_hard_gate_class": per_class,
        "triggers": triggers,
        "data_concentration_blocker": bool(triggers),
    }


def build_calibration_result(cases, classification, outcomes, *, sensitivity_rows,
                             active, sweep_labels, invalid_labels, parameter_sets,
                             determinism, performance):
    """Assemble the facts-only GeometryCalibrationResult record (pure)."""
    _check_calibration_policy(active)
    for label, params in parameter_sets.items():
        if any(params[name] != policy["value"]
               for name, policy in FROZEN_STRUCTURAL_PARAMETERS.items()):
            raise ValueError(f"FROZEN_STRUCTURAL_PARAMETER_VARIED: {label}")
    ids = sorted(c["case_id"] for c in cases)
    base = {c: outcomes[c]["BASELINE"] for c in ids}
    base_eval = evaluate_parameter_set(base, base, ids, DEFAULT_SHADOW_REPORT_PARAMETERS)
    concentration = concentration_summary(cases, classification, base)
    population_ok = ids == sorted(i for i, row in classification.items()
                                  if row["calibration_eligible"])
    reasons = []
    if not population_ok:
        reasons.append("POPULATION_DIFFERS_FROM_GEO_U1_POP_1")

    evaluated, candidates, rejected, loo = [], [], [], {}
    for label in sweep_labels:
        params = parameter_sets[label]
        cand = {c: outcomes[c][label] for c in ids}
        ev = evaluate_parameter_set(base, cand, ids, params)
        preferred = preferred_over_baseline(ev, base_eval, params)
        record = {"label": label, "parameters": params,
                  "preferred_over_baseline": preferred, **ev}
        if label in determinism and determinism[label]:
            record["gates_passed"] = False
            record["gate_failures"] = record["gate_failures"] + [
                "DETERMINISM_FUTURE_ROWS_MISMATCH: " + ", ".join(determinism[label])]
            record["preferred_over_baseline"] = preferred = False
        evaluated.append(record)
        if not record["gates_passed"]:
            rejected.append({"label": label, "reasons": record["gate_failures"]})
            continue
        loo[label] = leave_one_out(base, cand, ids, params)
        if preferred:
            candidates.append(record)
    candidates.sort(key=lambda r: preference_key(r, r["parameters"]))
    robust = [r for r in candidates if loo[r["label"]]["robustness"] == "ROBUST"
              and r["label"] in determinism and not determinism[r["label"]]]

    if len(active) > MAX_ACTIVE_PARAMETERS:
        action = MORE_EVIDENCE_REQUIRED
        reasons.append(f"{CALIBRATION_UNDERDETERMINED}: {len(active)} material "
                       f"parameters > {MAX_ACTIVE_PARAMETERS}")
    elif not population_ok:
        action = MORE_EVIDENCE_REQUIRED
    elif robust and not concentration["data_concentration_blocker"]:
        action = CANDIDATE_PRESET
        reasons.append(f"robust gate-passing preset preferred over baseline: "
                       f"{robust[0]['label']}")
    elif robust:
        action = MORE_EVIDENCE_REQUIRED
        reasons.append(f"{DATA_CONCENTRATION_BLOCKER}: "
                       + "; ".join(concentration["triggers"]))
    elif candidates:
        action = MORE_EVIDENCE_REQUIRED
        reasons.append("only FRAGILE or unverified presets are preferred over baseline")
    else:
        action = KEEP_BASELINE
        reasons.append("no gate-passing parameter set is strictly preferred over "
                       "the baseline under the locked preference order")
    if concentration["data_concentration_blocker"] and action != MORE_EVIDENCE_REQUIRED:
        reasons.append(f"{DATA_CONCENTRATION_BLOCKER} (informational for "
                       f"{action}): " + "; ".join(concentration["triggers"]))

    gate_passing = [r["label"] for r in evaluated if r["gates_passed"]]
    sweep_table = [
        [r["label"], r["gates_passed"], r["preferred_over_baseline"],
         *(r[k] if isinstance(r[k], int) else len(r[k]) for k in SWEEP_COUNT_COLUMNS),
         sorted({f.split(":")[0] for f in r["gate_failures"]})]
        for r in evaluated]
    failure_codes = Counter(code for row in sweep_table for code in row[-1])
    return {
        "mode": MODE, "schema_version": SCHEMA_VERSION,
        "population_policy": POLICY_V1.policy_version,
        "population_matches_policy": population_ok,
        "case_ids": ids,
        "objective": {"hard_gates": HARD_GATES, "preference_order": PREFERENCE_ORDER,
                      "scalar_score": None},
        "baseline_parameters": dict(DEFAULT_SHADOW_REPORT_PARAMETERS),
        "baseline_evaluation": base_eval,
        "sensitivity_rule": SENSITIVITY_RULE,
        "active_rule": ACTIVE_RULE,
        "sensitivity_summary": sensitivity_rows,
        "active_parameters": active,
        "frozen_parameters": [n for n in DEFAULT_SHADOW_REPORT_PARAMETERS if n not in active],
        "frozen_structural_parameters": {
            name: dict(policy) for name, policy in FROZEN_STRUCTURAL_PARAMETERS.items()},
        "tested_parameter_set_count": len(sweep_labels),
        "invalid_grid_combinations": {
            "count": len(invalid_labels),
            "reason": "TERMINAL_WINDOW_NOT_DIVISIBLE_INTO_3BAR_SEGMENTS (not run)"},
        "sweep_table": {"columns": ["label", "gates_passed", "preferred_over_baseline",
                                    *SWEEP_COUNT_COLUMNS, "gate_failure_codes"],
                        "rows": sweep_table},
        "gate_passing_sets": gate_passing,
        "gate_passing_evaluations": {r["label"]: r for r in evaluated if r["gates_passed"]},
        "candidate_presets": [{"label": r["label"], "parameters": r["parameters"],
                               "robustness": loo[r["label"]]["robustness"],
                               "determinism_checked": r["label"] in determinism}
                              for r in candidates],
        "rejected_presets": {"count": len(rejected),
                             "by_failure_code": dict(sorted(failure_codes.items())),
                             "labels": [r["label"] for r in rejected]},
        "leave_one_out_summary": {
            "sets_evaluated": len(loo),
            "robust": sorted(k for k, v in loo.items() if v["robustness"] == "ROBUST"),
            "fragile": {k: v["conclusion_flips_when_removed"]
                        for k, v in sorted(loo.items()) if v["robustness"] == "FRAGILE"},
            "preferred_full": sorted(k for k, v in loo.items() if v["preferred_full"]),
        },
        "determinism_future_rows": {k: {"mismatches": v} for k, v in sorted(determinism.items())},
        "concentration_summary": concentration,
        "recommended_action": action,
        "proposed_shadow_preset": (robust[0]["parameters"]
                                   if action == CANDIDATE_PRESET else None),
        "reasons": reasons,
        "production_cutover_authorized": PRODUCTION_CUTOVER_AUTHORIZED,
        "performance": performance,
    }


def compact_outcome_matrix(outcomes, labels):
    """Per case: distinct outcomes + one index per label (lossless)."""
    matrix = {}
    for case_id in sorted(outcomes):
        table, index = [], {}
        rows = []
        for label in labels:
            text = _dumps(outcomes[case_id][label])
            if text not in index:
                index[text] = len(table)
                table.append(outcomes[case_id][label])
            rows.append(index[text])
        matrix[case_id] = {"distinct_outcomes": table, "outcome_index": rows}
    return {"labels": list(labels), "cases": matrix}


def expand_outcome_matrix(matrix):
    labels = matrix["labels"]
    return {cid: {label: row["distinct_outcomes"][i]
                  for label, i in zip(labels, row["outcome_index"])}
            for cid, row in matrix["cases"].items()}


def baseline_table(cases, pinned, outcomes):
    rows = []
    for case in cases:
        cid = case["case_id"]
        o = outcomes[cid]["BASELINE"]
        f = pinned[cid]
        rows.append({
            "case_id": cid, "symbol": case["symbol"], "timeframe": str(case["timeframe"]),
            **{k: o[k] for k in ("selection_status", "terminal_width_trend",
                                 "candidate_count", "admissible_count",
                                 "selected_pair_identity", "selected_pair_evidence",
                                 "terminal_compression_ratio",
                                 "realized_contraction_ratio",
                                 "terminal_relative_width_slope")},
            "production_detected": f["production_detected"],
            "production_pattern": f["production_pattern"],
            "matches_pinned_facts": all(o[k] == f[k] for k in (
                "selection_status", "terminal_width_trend", "candidate_count",
                "admissible_count", "selected_pair_identity",
                "terminal_compression_ratio", "realized_contraction_ratio")),
        })
    return rows


def run_calibration(processes=None, log=print, cache_dir=None):
    """Full deterministic H0 run (expensive). Returns the JSON-plain record."""
    started = time.perf_counter()
    cases, pinned, classification = load_target_population()
    ids = [c["case_id"] for c in cases]

    sens_sets = sensitivity_parameter_sets()
    outcomes, timings = compute_outcomes(cases, sens_sets, processes, cache_dir)
    table = baseline_table(cases, pinned, outcomes)
    if not all(r["matches_pinned_facts"] for r in table):
        raise RuntimeError("BASELINE_MISMATCH: calibration stopped")
    log(f"baseline exact; sensitivity done in {time.perf_counter() - started:.0f}s")
    rows, active = summarize_sensitivity(outcomes, ids)
    log(f"active={active}")

    parameter_sets = dict(sens_sets)
    sweep_labels, invalid = [], []
    if len(active) <= MAX_ACTIVE_PARAMETERS:
        grid, invalid_sets = sweep_parameter_sets(active)
        invalid = [label for label, _ in invalid_sets]
        new = [(l, p) for l, p in grid
               if parameter_key(p) not in {parameter_key(q) for q in parameter_sets.values()}]
        alias = {l: next(k for k, q in parameter_sets.items()
                         if parameter_key(q) == parameter_key(p))
                 for l, p in grid if (l, p) not in new}
        if new:
            more, more_t = compute_outcomes(cases, new, processes, cache_dir)
            for cid in ids:
                outcomes[cid].update(more[cid])
                timings[cid].update(more_t[cid])
        parameter_sets.update(dict(new))
        for label, target in alias.items():
            parameter_sets[label] = parameter_sets[target]
            for cid in ids:
                outcomes[cid][label] = outcomes[cid][target]
                timings[cid][label] = 0.0
        sweep_labels = [l for l, _ in grid]
        log(f"sweep {len(sweep_labels)} sets done at {time.perf_counter() - started:.0f}s")

    # Exact determinism / future-row check for every set eligible for proposal.
    ids_sorted = sorted(ids)
    base = {c: outcomes[c]["BASELINE"] for c in ids_sorted}
    base_eval = evaluate_parameter_set(base, base, ids_sorted, DEFAULT_SHADOW_REPORT_PARAMETERS)
    determinism = {}
    for label in sweep_labels:
        cand = {c: outcomes[c][label] for c in ids_sorted}
        ev = evaluate_parameter_set(base, cand, ids_sorted, parameter_sets[label])
        if (preferred_over_baseline(ev, base_eval, parameter_sets[label])
                and leave_one_out(base, cand, ids_sorted,
                                  parameter_sets[label])["robustness"] == "ROBUST"):
            determinism[label] = verify_exact_future_invariance(
                cases, parameter_sets[label], cand, processes)
    log(f"determinism checks: {len(determinism)}")

    labels = [l for l, _ in sens_sets] + [l for l in sweep_labels
                                          if l not in dict(sens_sets)]
    per_set = {l: sum(timings[c].get(l, 0.0) for c in ids) for l in labels}
    slowest = max(((c, l, t) for c in ids for l, t in timings[c].items()),
                  key=lambda x: x[2])
    performance = {
        "parameter_sets_tested": len(labels),
        "exact_case_runs": sum(len(timings[c]) for c in ids),
        "memo_alias_case_runs": sum(1 for c in ids for t in timings[c].values() if t == 0.0),
        "this_invocation_elapsed_seconds": round(time.perf_counter() - started, 1),
        "exact_case_run_seconds_sum": round(sum(sum(timings[c].values()) for c in ids), 1),
        "case_run_timings_source": ("exact disk cache of the cold run" if cache_dir
                                    else "this invocation"),
        "per_set_case_seconds_by_matrix_label": [round(per_set[l], 1) for l in labels],
        "per_case_seconds": {c: round(sum(timings[c].values()), 1) for c in ids},
        "slowest_case_run": {"case_id": slowest[0], "set": slowest[1],
                             "seconds": round(slowest[2], 2)},
        "processes": processes or min(len(cases), 16),
    }
    result = build_calibration_result(
        cases, classification, outcomes, sensitivity_rows=rows, active=active,
        sweep_labels=sweep_labels, invalid_labels=invalid,
        parameter_sets=parameter_sets, determinism=determinism,
        performance=performance)
    result["baseline_table"] = table
    result["outcome_matrix"] = compact_outcome_matrix(outcomes, labels)
    return json.loads(_dumps(_plain(result)))


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="GEO-U1 H0 SHADOW calibration (diagnostic)")
    parser.add_argument("--write", type=Path, required=True)
    parser.add_argument("--processes", type=int, default=None)
    parser.add_argument("--cache-dir", default=None)
    args = parser.parse_args()
    record = run_calibration(args.processes, cache_dir=args.cache_dir)
    args.write.write_text(json.dumps(record, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
    print(record["recommended_action"], record["reasons"])
