"""Owner geometry-feedback evidence: immutable source, revision and idempotency."""
from copy import deepcopy
import json

import pytest

from geometry_feedback_store import (
    GeometryFeedbackConflict,
    GeometryFeedbackError,
    bars_digest,
    latest_review,
    record_review,
    source_revision,
)


def _source():
    return {
        "schema_version": 1,
        "signal_id": "source:TESTUSDT:5:abc",
        "symbol": "TESTUSDT",
        "timeframe": "5",
        "bars": [
            {"open_time_ms": 1000, "open": 10, "high": 14, "low": 9, "close": 12},
            {"open_time_ms": 301000, "open": 12, "high": 15, "low": 10, "close": 11},
            {"open_time_ms": 601000, "open": 11, "high": 16, "low": 10, "close": 14},
        ],
        "boundaries": [
            {"boundary_id": "upper", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 1000, "price": 13},
                {"bar_open_time_ms": 601000, "price": 14},
            ]},
            {"boundary_id": "lower", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 1000, "price": 9},
                {"bar_open_time_ms": 601000, "price": 11},
            ]},
        ],
    }


def _payload(source=None, *, label="GEOMETRY_CORRECTED", token="test-unique-idempotency-00001"):
    source = source or _source()
    edited = [
        {"id": row["boundary_id"], "type": row["kind"], "anchors": deepcopy(row["anchors"])}
        for row in source["boundaries"]
    ]
    edited[0]["anchors"][0]["price"] = 13.5
    return {
        "schema_version": 1,
        "signal_id": source["signal_id"],
        "snapshot_revision": source_revision(source),
        "bars_sha256": bars_digest(source),
        "label": label,
        "note": "Исправил верхнюю границу",
        "idempotency_key": token,
        "corrected_boundaries": edited if label == "GEOMETRY_CORRECTED" else [],
    }


def test_review_roundtrip_keeps_source_immutable_and_returns_timestamp_coordinates(tmp_path):
    source = _source()
    original = deepcopy(source)
    review = record_review(_payload(source), source, directory=tmp_path)
    assert source == original
    assert len(list(tmp_path.rglob("*.json"))) == 1
    assert review["source_boundaries"] == original["boundaries"]
    assert review["submission"]["corrected_boundaries"][0]["anchors"][0] == {
        "bar_open_time_ms": 1000, "price": 13.5,
    }
    assert latest_review(source["signal_id"], snapshot=source, directory=tmp_path) == review
    assert record_review(_payload(source), source, directory=tmp_path) == review
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_append_only_reviews_preserve_prior_correction(tmp_path):
    source = _source()
    first = record_review(_payload(source), source, directory=tmp_path)
    second = record_review(_payload(source, label="CONFIRMED", token="test-unique-idempotency-00002"), source, directory=tmp_path)
    assert second["review_id"] != first["review_id"]
    assert len(list(tmp_path.rglob("*.json"))) == 2
    assert sorted(json.loads(path.read_text())["review_id"] for path in tmp_path.rglob("*.json")) == sorted([
        first["review_id"], second["review_id"],
    ])


def test_rejects_stale_snapshot_or_reused_token_with_new_data(tmp_path):
    source = _source()
    payload = _payload(source)
    with pytest.raises(GeometryFeedbackConflict, match="source_snapshot_revision_conflict"):
        record_review({**payload, "snapshot_revision": "0" * 64}, source, directory=tmp_path)
    record_review(payload, source, directory=tmp_path)
    with pytest.raises(GeometryFeedbackConflict, match="idempotency_key_reused"):
        record_review({**payload, "note": "другой отзыв"}, source, directory=tmp_path)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=2),
    lambda p: p["corrected_boundaries"].pop(),
    lambda p: p["corrected_boundaries"][0]["anchors"][0].update(bar_open_time_ms=1001),
    lambda p: p["corrected_boundaries"][0]["anchors"][0].update(price=float("nan")),
    lambda p: p["corrected_boundaries"][0].update(id="unknown"),
    lambda p: p["corrected_boundaries"][0].update(type="segment"),
    lambda p: p["corrected_boundaries"][0]["anchors"][0].update(price=13),
    lambda p: p.update(signal_id="source:OTHERUSDT:5:abc"),
])
def test_rejects_malformed_or_unrelated_geometry_without_writing(tmp_path, mutation):
    source = _source()
    payload = _payload(source)
    mutation(payload)
    with pytest.raises(GeometryFeedbackError):
        record_review(payload, source, directory=tmp_path)
    assert not list(tmp_path.rglob("*.json"))


def test_no_corrected_boundaries_on_non_edit_reviews(tmp_path):
    source = _source()
    payload = _payload(source, label="UNCERTAIN")
    record = record_review(payload, source, directory=tmp_path)
    assert record["submission"]["corrected_boundaries"] == []
