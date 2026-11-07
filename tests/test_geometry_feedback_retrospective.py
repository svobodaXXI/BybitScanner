"""Retrospective owner annotation provenance: no trading or PAPER DB access."""
from __future__ import annotations

import json

import pytest

from geometry_feedback_export import reviewed_example, GeometryExportError
from geometry_feedback_store import bars_digest, latest_review, record_review, source_revision
from retrospective_signal_bars import (
    RetrospectiveBarsError, extension_digest, fetch_closed_extension, validate_extension,
)
from signal_archive import record_original_signal
from tests.test_geometry_feedback_export import _snapshot


def _next_bars():
    return [
        {"open_time_ms": 900_000, "open": 12, "high": 14, "low": 11, "close": 13},
        {"open_time_ms": 1_200_000, "open": 13, "high": 15, "low": 12, "close": 14},
    ]


def _correction(snapshot, extension):
    rays = [{"id": item["boundary_id"], "type": item["kind"],
             "anchors": [dict(a) for a in item["anchors"]]}
            for item in snapshot["boundaries"]]
    rays[0]["anchors"][1] = {"bar_open_time_ms": extension[-1]["open_time_ms"], "price": 15.0}
    return {
        "schema_version": 1,
        "signal_id": snapshot["signal_id"],
        "snapshot_revision": source_revision(snapshot),
        "bars_sha256": bars_digest(snapshot),
        "context_as_of_ms": 1_200_000,
        "context_bars_sha256": extension_digest(extension),
        "label": "GEOMETRY_CORRECTED",
        "corrected_boundaries": rays,
        "idempotency_key": "review-retrospective-1234567",
        "note": "Позже увидел подтверждение клина",
    }


def test_server_extension_rejects_gap_open_bar_and_unbounded_request():
    snap = _snapshot("source-original:" + "a" * 24)
    extension = _next_bars()
    assert validate_extension(snap, extension, 1_200_000) == [
        {field: float(value) if field != "open_time_ms" else value
         for field, value in bar.items()} for bar in extension
    ]
    with pytest.raises(RetrospectiveBarsError, match="noncontiguous"):
        validate_extension(snap, extension[1:], 1_200_000)
    with pytest.raises(RetrospectiveBarsError, match="noncontiguous"):
        validate_extension(snap, extension, 900_000)
    with pytest.raises(RetrospectiveBarsError, match="invalid_retrospective_ohlc"):
        validate_extension(snap, [{**extension[0], "high": 1}, extension[1]], 1_200_000)

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"retCode": 0, "result": {"list": [
                [str(bar["open_time_ms"]), str(bar["open"]), str(bar["high"]),
                 str(bar["low"]), str(bar["close"])] for bar in reversed(extension)
            ]}}

    class FakeHttp:
        def get(self, url, *, params, timeout):
            assert "bybit.com/v5/market/kline" in url
            assert params["start"] == 900_000 and params["end"] == 1_200_000
            assert params["limit"] == 2 and timeout <= 10
            return FakeResponse()

    asof, verified = fetch_closed_extension(
        snap, as_of_ms=1_200_000, session=FakeHttp(), now_ms=1_800_000,
    )
    assert asof == 1_200_000 and verified == validate_extension(snap, extension, asof)
    with pytest.raises(RetrospectiveBarsError, match="invalid_retrospective_cutoff"):
        fetch_closed_extension(snap, as_of_ms=1_500_000, session=FakeHttp(), now_ms=1_500_000)


def test_corrected_anchor_may_use_later_candle_without_changing_original_archive(tmp_path):
    signal_id = "source-original:" + "b" * 24
    snapshot = _snapshot(signal_id)
    extras = _next_bars()
    signals = tmp_path / "signals"
    reviews = tmp_path / "reviews"
    assert record_original_signal(
        signal_id, symbol="BTCUSDT", timeframe="5", pattern="Falling Wedge",
        text="Original signal", image_bytes=b"png", geometry_snapshot=snapshot,
        directory=signals,
    )
    payload = _correction(snapshot, extras)
    recorded = record_review(payload, snapshot, directory=reviews, review_bars=extras)
    assert recorded["submission"]["context_as_of_ms"] == 1_200_000
    assert recorded["retrospective_bars"][-1]["open_time_ms"] == 1_200_000
    assert record_review(payload, snapshot, directory=reviews, review_bars=extras) == recorded
    assert latest_review(signal_id, snapshot=snapshot, directory=reviews) == recorded
    offline = reviewed_example(signal_id, archive_directory=signals, feedback_directory=reviews)
    assert offline["frozen_bars"] == snapshot["bars"]
    assert offline["review_bars"] == [*snapshot["bars"], *recorded["retrospective_bars"]]
    assert offline["review_context"] == "RETROSPECTIVE_CLOSED_BARS"
    assert offline["review_as_of_ms"] == 1_200_000
    assert offline["corrected_boundaries"][0]["anchors"][-1]["bar_open_time_ms"] == 1_200_000
    assert snapshot["bars"][-1]["open_time_ms"] == 600_000
    assert len(list(reviews.rglob("*.json"))) == 1

    with pytest.raises(ValueError, match="retrospective_context_hash_conflict"):
        record_review({**payload, "context_bars_sha256": "0" * 64},
                      snapshot, directory=reviews, review_bars=extras)
    with pytest.raises(ValueError):
        record_review(payload, snapshot, directory=reviews)
    path, = reviews.rglob("*.json")
    stored = json.loads(path.read_text())
    stored["retrospective_bars"][0]["high"] = 999
    path.write_text(json.dumps(stored))
    with pytest.raises(GeometryExportError):
        reviewed_example(signal_id, archive_directory=signals, feedback_directory=reviews)


def test_legacy_correction_stays_source_time_only(tmp_path):
    snap = _snapshot("source-original:" + "c" * 24)
    lines = [{"id": line["boundary_id"], "type": line["kind"], "anchors": [
        dict(anchor) for anchor in line["anchors"]]}
        for line in snap["boundaries"]]
    lines[0]["anchors"][1]["price"] = 12.5
    payload = {
        "schema_version": 1, "signal_id": snap["signal_id"],
        "snapshot_revision": source_revision(snap),
        "bars_sha256": bars_digest(snap), "label": "GEOMETRY_CORRECTED",
        "corrected_boundaries": lines, "idempotency_key": "legacy-test-feedback-1234",
    }
    saved = record_review(payload, snap, directory=tmp_path)
    assert "retrospective_bars" not in saved and "context_as_of_ms" not in saved["submission"]
    assert latest_review(snap["signal_id"], snapshot=snap, directory=tmp_path) == saved
