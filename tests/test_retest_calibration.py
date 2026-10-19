import pytest

from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN, Boundary
from retest_calibration import (
    OUTCOME_ATR_UNAVAILABLE,
    OUTCOME_DATA_GAP,
    CalibrationCase,
    Candidate,
    RetestCalibrationError,
    causal_atr_series,
    evaluate_case,
    walk_forward_select,
)


MINUTE = 60_000


def bar(i, o, h, l, c):
    return {"open_time_ms": i * MINUTE, "close_time_ms": (i + 1) * MINUTE,
            "open": o, "high": h, "low": l, "close": c, "closed": True}


def case(boundary_id, start, near_miss_low=100.3, warmup=5):
    """Warm-up candles, a naked UP break of 100, then a near miss of the level."""
    rows = [bar(start + i, 99.0, 99.6, 98.6, 99.2) for i in range(warmup)]
    rows.append(bar(start + warmup, 99.4, 102.5, 99.3, 102.0))
    rows.append(bar(start + warmup + 1, 102.0, 102.4, near_miss_low, 101.0))
    boundary = Boundary.horizontal(boundary_id, 100.0, as_of_time_ms=(start + warmup) * MINUTE)
    return CalibrationCase(boundary, tuple(rows))


def test_atr_is_causal_future_candles_do_not_change_past_values():
    rows = list(case("a", 0).candles)
    base = causal_atr_series(rows, 3)
    extended = causal_atr_series(rows + [bar(len(rows), 101.0, 140.0, 60.0, 120.0)], 3)
    assert extended[: len(base)] == base
    assert base[:2] == [None, None]


def test_zone_from_atr_decides_the_near_miss():
    tight = evaluate_case(case("a", 0), Candidate(atr_period=3, multiplier=0.0))
    wide = evaluate_case(case("a", 0), Candidate(atr_period=3, multiplier=1.0))
    assert (tight["outcome"], wide["outcome"]) == (PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN)
    assert wide["retest_tolerance"] > 0


def test_missing_atr_after_breakout_fails_closed():
    result = evaluate_case(case("a", 0, warmup=0), Candidate(atr_period=50, multiplier=1.0))
    assert result["outcome"] == OUTCOME_ATR_UNAVAILABLE


def test_data_gap_is_reported_not_skipped():
    rows = list(case("a", 0).candles)
    gapped = CalibrationCase(case("a", 0).boundary, tuple(rows[:-1] + [bar(20, 102.0, 102.4, 99.0, 101.0)]))
    assert evaluate_case(gapped, Candidate(3, 1.0))["outcome"] == OUTCOME_DATA_GAP


def retests(outcomes):
    return float(sum(o["outcome"] == PHASE_RETEST_PROVEN for o in outcomes))


def test_selection_sees_only_pre_split_cases():
    train = [case("t1", 0), case("t2", 10)]
    straddle = case("s", 25)
    test = [case("x1", 100)]
    seen = []

    def objective(outcomes):
        seen.extend(o["boundary_id"] for o in outcomes)
        return retests(outcomes)

    candidates = [Candidate(3, 0.0), Candidate(3, 1.0)]
    result = walk_forward_select(train + [straddle] + test, candidates,
                                 split_time_ms=30 * MINUTE, objective=objective)
    assert set(seen) == {"t1", "t2"}
    assert result["selected"] == Candidate(3, 1.0)
    assert result["excluded_straddling"] == ["s"]
    assert [o["boundary_id"] for o in result["test_outcomes"]] == ["x1"]
    assert all(o["candidate"] == Candidate(3, 1.0) for o in result["test_outcomes"])

    # Rewriting post-split data cannot change the choice.
    altered = [case("x1", 100, near_miss_low=95.0)]
    again = walk_forward_select(train + altered, candidates, split_time_ms=30 * MINUTE, objective=retests)
    assert again["selected"] == result["selected"]
    assert again["train_scores"] == result["train_scores"]


def test_ties_keep_caller_order_and_non_finite_scores_are_disqualified():
    train = [case("t1", 0)]
    first, second = Candidate(3, 1.0), Candidate(4, 1.0)
    assert walk_forward_select(train, [first, second], split_time_ms=50 * MINUTE,
                               objective=lambda o: 1.0)["selected"] == first
    scores = iter([float("nan"), 0.0])
    result = walk_forward_select(train, [first, second], split_time_ms=50 * MINUTE,
                                 objective=lambda o: next(scores))
    assert result["selected"] == second and result["train_scores"][first] is None


@pytest.mark.parametrize("kwargs", [
    {"cases": [], "candidates": [Candidate(3, 1.0)]},
    {"cases": [case("t1", 0)], "candidates": []},
])
def test_selection_requires_train_cases_and_candidates(kwargs):
    with pytest.raises(RetestCalibrationError):
        walk_forward_select(split_time_ms=50 * MINUTE, objective=retests, **kwargs)


@pytest.mark.parametrize("period,multiplier", [(0, 1.0), (True, 1.0), (3, -1.0), (3, float("nan"))])
def test_invalid_candidates_are_rejected(period, multiplier):
    with pytest.raises(Exception):
        Candidate(period, multiplier)


# --- MIRROR RETEST-4: fine physical-touch reference and labels -------------

from retest_calibration import (  # noqa: E402
    LABEL_EXCLUDED,
    LABEL_FN,
    LABEL_FP_LATE,
    LABEL_TN,
    LABEL_TP,
    LABEL_UNLABELED_NEAR_MISS,
    REF_AMBIGUOUS,
    REF_DATA_GAP,
    REF_NO_TOUCH,
    REF_TOUCH,
    label_detection,
    reference_touch,
    summarize_labels,
)

FIVE = 5 * MINUTE
LEVEL = Boundary.horizontal("lvl", 100.0, as_of_time_ms=0)


def fine(i, low):
    return bar(i, 101.0, 101.5, low, 101.2)


def test_reference_is_first_exact_fine_touch_after_breakout_close():
    rows = [fine(4, 99.0), fine(5, 100.4), fine(6, 100.0), fine(7, 99.0)]
    ref = reference_touch(LEVEL, "UP", 5 * MINUTE, rows)  # bar 4 is before the close
    assert (ref["status"], ref["touch_close_time_ms"]) == (REF_TOUCH, 7 * MINUTE)
    assert reference_touch(LEVEL, "UP", 0, [fine(0, 100.4), fine(1, 100.2)])["status"] == REF_NO_TOUCH
    assert reference_touch(LEVEL, "UP", 0, [fine(0, 100.4), fine(2, 99.0)])["status"] == REF_DATA_GAP
    rising = Boundary("rise", 0, 100.0, 1.0 / MINUTE, 0)
    assert reference_touch(rising, "UP", 0, [bar(0, 102.0, 102.5, 100.5, 102.2)])["status"] == REF_AMBIGUOUS


def outcome(phase, close=None):
    return {"outcome": phase, "retest_close_time_ms": close}


TOUCH = {"status": REF_TOUCH, "touch_open_time_ms": 6 * MINUTE, "touch_close_time_ms": 7 * MINUTE}


@pytest.mark.parametrize("result,reference,expected", [
    (outcome("RETEST_PROVEN", 2 * FIVE), TOUCH, (LABEL_TP, 3 * MINUTE)),        # same 5m candle
    (outcome("RETEST_PROVEN", FIVE), TOUCH, (LABEL_UNLABELED_NEAR_MISS, -2 * MINUTE)),
    (outcome("RETEST_PROVEN", 3 * FIVE), TOUCH, (LABEL_FP_LATE, 8 * MINUTE)),
    (outcome("RETEST_PROVEN", FIVE), {"status": REF_NO_TOUCH}, (LABEL_UNLABELED_NEAR_MISS, None)),
    (outcome("RETEST_CAMPAIGN_ACTIVE"), TOUCH, (LABEL_FN, None)),
    (outcome("RETEST_UNPROVEN"), TOUCH, (LABEL_FN, None)),
    (outcome("RETEST_CAMPAIGN_ACTIVE"), {"status": REF_NO_TOUCH}, (LABEL_TN, None)),
    (outcome("ATR_UNAVAILABLE"), TOUCH, (LABEL_EXCLUDED, None)),
    (outcome("RETEST_PROVEN", FIVE), {"status": REF_AMBIGUOUS}, (LABEL_EXCLUDED, None)),
])
def test_detection_labels(result, reference, expected):
    assert label_detection(result, reference, FIVE) == expected


def test_summary_bounds_keep_near_misses_unresolved():
    labels = [(LABEL_TP, 0), (LABEL_TP, 0), (LABEL_UNLABELED_NEAR_MISS, -60_000),
              (LABEL_UNLABELED_NEAR_MISS, None), (LABEL_FN, None), (LABEL_TN, None)]
    s = summarize_labels(labels)
    assert (s["detections"], s["precision_lower"], s["precision_upper"]) == (4, 0.5, 1.0)
    assert s["touch_recall"] == 3 / 4  # 2 TP + 1 early detection of a later touch, 1 FN
    assert summarize_labels([])["precision_lower"] is None
