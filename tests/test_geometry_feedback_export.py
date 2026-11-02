"""Proof that Scanner training fixtures come from actual archived source + owner review."""
import json

import pytest

from geometry_feedback_export import GeometryExportError, export_reviewed_examples, reviewed_example
from geometry_feedback_store import bars_digest, record_review, source_revision
from signal_archive import record_original_signal


def _snapshot(signal_id):
    return {
        "schema_version": 1, "signal_id": signal_id,
        "symbol": "BTCUSDT", "timeframe": "5",
        "bars": [
            {"open_time_ms": 300000, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0},
            {"open_time_ms": 600000, "open": 11.0, "high": 13.0, "low": 10.0, "close": 12.0},
        ],
        "boundaries": [
            {"boundary_id": "upper", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 300000, "price": 12.0},
                {"bar_open_time_ms": 600000, "price": 13.0},
            ]},
            {"boundary_id": "lower", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 300000, "price": 9.0},
                {"bar_open_time_ms": 600000, "price": 10.0},
            ]},
        ],
    }


def _archive_and_review(root, signal_id, *, label="GEOMETRY_CORRECTED"):
    snapshot = _snapshot(signal_id)
    signals = root / "signals"
    reviews = root / "reviews"
    assert record_original_signal(
        signal_id, symbol="BTCUSDT", timeframe="5", pattern="Falling Wedge",
        text="Scanner original", image_bytes=b"png-test-bytes",
        geometry_snapshot=snapshot, directory=signals,
    )
    corrections = [
        {"id": item["boundary_id"], "type": item["kind"],
         "anchors": [dict(anchor) for anchor in item["anchors"]]}
        for item in snapshot["boundaries"]
    ]
    corrections[0]["anchors"][0]["price"] = 11.5
    payload = {
        "schema_version": 1, "signal_id": signal_id,
        "snapshot_revision": source_revision(snapshot), "bars_sha256": bars_digest(snapshot),
        "label": label, "note": "Owner verified wedge",
        "idempotency_key": "review-fixture-test-token-00001",
        "corrected_boundaries": corrections if label == "GEOMETRY_CORRECTED" else [],
    }
    record_review(payload, snapshot, directory=reviews)
    return signals, reviews


def test_export_uses_verified_archived_candles_and_correction_without_scanner_mutation(tmp_path):
    signal_id = "source-original:" + "a" * 24
    signals, reviews = _archive_and_review(tmp_path, signal_id)
    record = reviewed_example(signal_id, archive_directory=signals, feedback_directory=reviews)
    assert record["schema"] == "owner_geometry_feedback_example_v1"
    assert record["split"] == "UNASSIGNED_REQUIRES_GROUPED_HOLDOUT"
    assert record["symbol"] == "BTCUSDT"
    assert record["pattern"] == "Falling Wedge"
    assert record["frozen_bars"][0]["open_time_ms"] == 300000
    assert record["original_boundaries"][0]["anchors"][0]["price"] == 12.0
    assert record["corrected_boundaries"][0]["anchors"][0]["price"] == 11.5
    output = tmp_path / "owner-reviewed.jsonl"
    assert export_reviewed_examples(
        [signal_id], output, archive_directory=signals, feedback_directory=reviews,
    ) == 1
    assert json.loads(output.read_text().strip()) == record
    with pytest.raises(FileExistsError):
        export_reviewed_examples(
            [signal_id], output, archive_directory=signals, feedback_directory=reviews,
        )


def test_export_rejects_unreviewed_uncertain_duplicate_and_missing_source(tmp_path):
    signal_id = "source-original:" + "b" * 24
    signals, reviews = _archive_and_review(tmp_path, signal_id, label="UNCERTAIN")
    with pytest.raises(GeometryExportError, match="review_not_training_eligible"):
        reviewed_example(signal_id, archive_directory=signals, feedback_directory=reviews)
    with pytest.raises(GeometryExportError, match="frozen_signal_unavailable"):
        reviewed_example("source-original:" + "c" * 24, archive_directory=signals, feedback_directory=reviews)
    path = tmp_path / "forbidden.jsonl"
    with pytest.raises(GeometryExportError, match="empty_or_duplicate_signal_ids"):
        export_reviewed_examples([signal_id, signal_id], path,
                                 archive_directory=signals, feedback_directory=reviews)
    with pytest.raises(GeometryExportError, match="review_not_training_eligible"):
        export_reviewed_examples([signal_id], path,
                                 archive_directory=signals, feedback_directory=reviews)
    assert not path.exists()


def test_export_does_not_trust_modified_original_rays_in_review(tmp_path):
    signal_id = "source-original:" + "d" * 24
    signals, reviews = _archive_and_review(tmp_path, signal_id)
    review_path, = list(reviews.rglob("*.json"))
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record["source_boundaries"][0]["anchors"][0]["price"] = 999
    review_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(GeometryExportError, match="unverified_feedback_evidence"):
        reviewed_example(signal_id, archive_directory=signals, feedback_directory=reviews)
