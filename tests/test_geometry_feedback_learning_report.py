"""Offline-learning report tests: no Scanner, Robot, trading or PAPER DB access."""
import json

import pytest

from geometry_feedback_learning_report import (
    GeometryLearningReportError, _analyze_case, _overlapping_windows,
    build_geometry_learning_report, discover_reviewed_signal_ids,
    write_geometry_learning_report,
)
from tests.test_geometry_feedback_export import _archive_and_review


def test_auto_discovery_reports_verified_owner_corrections_and_overlap(tmp_path):
    first = "source-original:" + "1" * 24
    second = "source-original:" + "2" * 24
    signals, reviews = _archive_and_review(tmp_path, first)
    _archive_and_review(tmp_path, second, label="CONFIRMED")
    report = build_geometry_learning_report(
        archive_directory=signals, feedback_dir=reviews,
    )
    assert discover_reviewed_signal_ids(feedback_dir=reviews) == [first, second]
    assert report["detector_training"] == "NOT_RUN"
    assert report["partition"] == "UNASSIGNED_REQUIRES_TEMPORAL_GROUPED_HOLDOUT"
    assert report["summary"] == {
        "eligible_signals": 2, "confirmed": 1, "corrected": 1,
        "false_positive": 0, "changed_anchors": 1,
        "shifted_bar_anchors": 0, "changed_price_anchors": 1,
    }
    corrected = next(case for case in report["cases"] if case["signal_id"] == first)
    assert corrected["anchor_changes"] == [{
        "boundary_id": "upper", "anchor_number": 1,
        "bar_shift": 0, "price_shift_percent": -4.166667,
        "price_changed": True,
    }]
    assert report["overlapping_window_groups"][0]["signal_ids"] == [first, second]
    assert len(report["overlapping_window_groups"]) == 1
    path = tmp_path / "report.json"
    write_geometry_learning_report(report, path)
    assert json.loads(path.read_text()) == report
    with pytest.raises(FileExistsError):
        write_geometry_learning_report(report, path)


def test_uncertain_excluded_but_false_positive_remains_actionable(tmp_path):
    false = "source-original:" + "3" * 24
    uncertain = "source-original:" + "4" * 24
    signals, reviews = _archive_and_review(tmp_path, false, label="FALSE_POSITIVE")
    _archive_and_review(tmp_path, uncertain, label="UNCERTAIN")
    report = build_geometry_learning_report(archive_directory=signals, feedback_dir=reviews)
    assert report["discovered_reviews"] == 2
    assert report["skipped_uncertain"] == 1
    assert report["summary"]["false_positive"] == 1
    assert [case["signal_id"] for case in report["cases"]] == [false]


def test_stale_source_or_malformed_discovered_review_fails_closed(tmp_path):
    signal_id = "source-original:" + "5" * 24
    signals, reviews = _archive_and_review(tmp_path, signal_id)
    with pytest.raises(GeometryLearningReportError, match="unverified_source_or_review"):
        build_geometry_learning_report([signal_id], archive_directory=tmp_path / "missing", feedback_dir=reviews)
    (record,) = reviews.rglob("*.json")
    record.write_text('{"submission":{}}', encoding="utf-8")
    with pytest.raises(GeometryLearningReportError, match="unverifiable_review_path"):
        build_geometry_learning_report(archive_directory=signals, feedback_dir=reviews)


def test_duplicate_ids_rejected_and_empty_review_dir_is_not_claimed_as_training(tmp_path):
    signal_id = "source-original:" + "6" * 24
    with pytest.raises(GeometryLearningReportError, match="duplicate_or_invalid_signal_ids"):
        build_geometry_learning_report([signal_id, signal_id], archive_directory=tmp_path, feedback_dir=tmp_path)
    result = build_geometry_learning_report(archive_directory=tmp_path, feedback_dir=tmp_path / "empty")
    assert result["summary"]["eligible_signals"] == 0
    assert result["detector_acceptance"] == "NOT_EVALUATED"


def test_candle_reanchor_and_non_overlapping_time_windows_are_reported():
    example = {
        "signal_id": "test-1", "review_id": "test-review", "symbol": "AAAUSDT",
        "timeframe": "5", "pattern": "Falling Wedge", "label": "GEOMETRY_CORRECTED",
        "source_revision_sha256": "revision", "bars_sha256": "bars",
        "frozen_bars": [{"open_time_ms": t} for t in [300000, 600000, 900000]],
        "original_boundaries": [{"boundary_id": "upper", "kind": "ray", "anchors": [
            {"bar_open_time_ms": 300000, "price": 10},
            {"bar_open_time_ms": 600000, "price": 11},
        ]}],
        "corrected_boundaries": [{"boundary_id": "upper", "kind": "ray", "anchors": [
            {"bar_open_time_ms": 600000, "price": 10},
            {"bar_open_time_ms": 900000, "price": 12},
        ]}],
    }
    case = _analyze_case(example)
    assert [m["bar_shift"] for m in case["anchor_changes"]] == [1, 1]
    assert [m["price_changed"] for m in case["anchor_changes"]] == [False, True]
    later = {**case, "signal_id": "test-2", "window_start_ms": 1200000, "window_end_ms": 1500000}
    groups = _overlapping_windows([later, case])
    assert len(groups) == 2
    assert groups[0]["signal_ids"] == ["test-1"]
    assert groups[1]["signal_ids"] == ["test-2"]
