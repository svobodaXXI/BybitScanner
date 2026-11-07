"""Owner new-signal intake: immutable review evidence, not trading candidates."""
from decimal import Decimal

import pytest

from geometry_feedback_store import bars_digest, source_revision
from owner_signal_proposal import (
    OwnerSignalProposalConflict, OwnerSignalProposalError,
    record_owner_signal_proposal,
)


def source():
    return {
        "schema_version": 1, "signal_id": "source:BTCUSDT:5:xyz",
        "symbol": "BTCUSDT", "timeframe": "5",
        "bars": [
            {"open_time_ms": i * 300000, "open": 101, "high": 110 + i * 0.1,
             "low": 90 + i * 0.1, "close": 100}
            for i in range(18)
        ],
        "boundaries": [
            {"boundary_id": "upper", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 0, "price": 110},
                {"bar_open_time_ms": 300000, "price": 110.1},
            ]},
            {"boundary_id": "lower", "kind": "ray", "anchors": [
                {"bar_open_time_ms": 0, "price": 90},
                {"bar_open_time_ms": 300000, "price": 90.1},
            ]},
        ],
    }


def proposal(snapshot):
    return {
        "schema_version": 1,
        "signal_id": snapshot["signal_id"],
        "snapshot_revision": source_revision(snapshot),
        "bars_sha256": bars_digest(snapshot),
        "pattern": "Falling Wedge",
        "note": "Owner new idea; not a trade",
        "idempotency_key": "owner-signal-test-000000001",
        "proposed_boundaries": [
            {"id": "upper", "type": "ray", "anchors": [
                {"bar_open_time_ms": 5 * 300000, "price": Decimal("111")},
                {"bar_open_time_ms": 15 * 300000, "price": Decimal("111.5")},
            ]},
            {"id": "lower", "type": "ray", "anchors": [
                {"bar_open_time_ms": 5 * 300000, "price": Decimal("90.5")},
                {"bar_open_time_ms": 15 * 300000, "price": Decimal("91.5")},
            ]},
        ],
    }


def test_owner_new_signal_record_is_append_only_and_not_robot_candidate(tmp_path):
    snapshot = source()
    request = proposal(snapshot)
    first = record_owner_signal_proposal(request, snapshot, directory=tmp_path)
    assert first["candidate_created"] is False
    assert first["robot_candidate_id"] is None
    assert first["assessment"]["decision"] == "REJECTED"
    assert first["assessment"]["reason"] == "ray_anchor_not_confirmed_pivot"
    assert first["submission"]["proposed_boundaries"][0]["anchors"][0]["price"] == 111.0
    assert record_owner_signal_proposal(request, snapshot, directory=tmp_path) == first
    assert len(list(tmp_path.rglob("*.json"))) == 1
    assert snapshot["boundaries"][0]["anchors"][0]["price"] == 110


def test_invalid_or_changed_proposal_fails_closed(tmp_path):
    snapshot = source()
    request = proposal(snapshot)
    with pytest.raises(OwnerSignalProposalConflict, match="source_snapshot_revision_conflict"):
        record_owner_signal_proposal({**request, "bars_sha256": "0" * 64}, snapshot, directory=tmp_path)
    with pytest.raises(OwnerSignalProposalError, match="two_complete_rays_required"):
        record_owner_signal_proposal({**request, "proposed_boundaries": request["proposed_boundaries"][:1]}, snapshot, directory=tmp_path)
    with pytest.raises(OwnerSignalProposalError, match="invalid_frozen_anchor"):
        wrong = proposal(snapshot)
        wrong["proposed_boundaries"][0]["anchors"][0]["bar_open_time_ms"] = 12345
        record_owner_signal_proposal(wrong, snapshot, directory=tmp_path)
    assert not list(tmp_path.rglob("*.json"))


def test_idempotency_cannot_reuse_identity_with_different_geometry(tmp_path):
    snapshot = source()
    request = proposal(snapshot)
    first = record_owner_signal_proposal(request, snapshot, directory=tmp_path)
    second = proposal(snapshot)
    second["proposed_boundaries"][0]["anchors"][0]["price"] = Decimal("115")
    with pytest.raises(OwnerSignalProposalConflict, match="existing_proposal_conflict"):
        record_owner_signal_proposal(second, snapshot, directory=tmp_path)
    assert record_owner_signal_proposal(request, snapshot, directory=tmp_path) == first
    assert len(list(tmp_path.rglob("*.json"))) == 1
