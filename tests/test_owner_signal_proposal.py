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


def _owner_chart_payload():
    period = 300_000
    return {
        "schema_version": 1, "source_kind": "OWNER_CHART_UNVERIFIED",
        "symbol": "BTCUSDT", "timeframe": "5", "pattern": "Falling Wedge",
        "bars": [
            {"open_time_ms": i * period, "open": 100, "high": 110,
             "low": 90, "close": 100}
            for i in range(120)
        ],
        "proposed_boundaries": [
            {"id": "upper", "type": "ray", "anchors": [
                {"bar_open_time_ms": 20 * period, "price": 108},
                {"bar_open_time_ms": 90 * period, "price": 102},
            ]},
            {"id": "lower", "type": "ray", "anchors": [
                {"bar_open_time_ms": 20 * period, "price": 95},
                {"bar_open_time_ms": 90 * period, "price": 93},
            ]},
        ],
        "idempotency_key": "owner-chart-token-0000000001", "note": "Scanner missed this wedge",
    }


def test_unscanned_owner_chart_is_archived_by_pattern_without_trading(tmp_path):
    from owner_signal_proposal import (
        record_owner_chart_proposal, list_owner_chart_training_examples,
    )
    payload = _owner_chart_payload()
    first = record_owner_chart_proposal(
        payload, directory=tmp_path, now_ms=121 * 300_000,
    )
    assert first["source_kind"] == "OWNER_CHART_UNVERIFIED"
    assert first["assessment"] == {
        "decision": "AWAITING_OFFLINE_REPLAY",
        "reason": "owner_supplied_source_not_scanner_evidence",
    }
    assert first["candidate_created"] is False and first["robot_candidate_id"] is None
    assert first["owner_source_snapshot"]["bars"] == payload["bars"]
    assert record_owner_chart_proposal(
        payload, directory=tmp_path, now_ms=121 * 300_000,
    ) == first
    assert list_owner_chart_training_examples("Falling Wedge", directory=tmp_path) == [first]
    assert list_owner_chart_training_examples("Rising Wedge", directory=tmp_path) == []
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_unscanned_owner_chart_rejects_partial_future_gaps_and_identity_collisions(tmp_path):
    from owner_signal_proposal import record_owner_chart_proposal
    payload = _owner_chart_payload()
    for corrupted in [
        {**payload, "bars": payload["bars"][:2]},
        {**payload, "bars": [*payload["bars"][:10], {
            **payload["bars"][10], "open_time_ms": 123,
        }, *payload["bars"][11:]]},
        {**payload, "bars": [{**row, "high": 1} for row in payload["bars"]]},
        {**payload, "source_kind": "SCANNER"},
    ]:
        with pytest.raises(OwnerSignalProposalError):
            record_owner_chart_proposal(
                corrupted, directory=tmp_path, now_ms=121 * 300_000,
            )
    with pytest.raises(OwnerSignalProposalError, match="invalid_owner_chart_chronology"):
        record_owner_chart_proposal(payload, directory=tmp_path, now_ms=3)
    first = record_owner_chart_proposal(payload, directory=tmp_path, now_ms=121 * 300_000)
    altered = {**payload, "proposed_boundaries": [
        {**payload["proposed_boundaries"][0], "anchors": [
            {**payload["proposed_boundaries"][0]["anchors"][0], "price": 109},
            payload["proposed_boundaries"][0]["anchors"][1],
        ]},
        payload["proposed_boundaries"][1],
    ]}
    with pytest.raises(OwnerSignalProposalConflict):
        record_owner_chart_proposal(altered, directory=tmp_path, now_ms=121 * 300_000)
    assert first["candidate_created"] is False


def test_unscanned_owner_chart_http_is_separate_from_scanner_archive(monkeypatch, tmp_path):
    import json
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from terminal.runtime.paper_http_server import PaperHttpHandler

    monkeypatch.setenv("BYBITSCANNER_OWNER_SIGNAL_PROPOSAL_DIR", str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    payload = _owner_chart_payload()
    try:
        request = Request(
            base + "/api/workspace/owner-unscanned-signal",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=3) as response:
            result = json.load(response)
        assert result["ok"] is True
        assert result["proposal"]["source_kind"] == "OWNER_CHART_UNVERIFIED"
        assert result["proposal"]["candidate_created"] is False
        with urlopen(
            base + "/api/workspace/owner-training-examples?pattern=Falling+Wedge",
            timeout=3,
        ) as response:
            archive = json.load(response)
        assert archive["training_authorized"] is False
        assert archive["category"] == "OWNER_CHART_UNVERIFIED"
        assert archive["examples"][0]["proposal_id"] == result["proposal"]["proposal_id"]
        with pytest.raises(HTTPError) as error:
            urlopen(
                base + "/api/workspace/owner-training-examples?pattern=Unknown",
                timeout=3,
            )
        assert error.value.code == 400
    finally:
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()


def test_unscanned_ikigai_box_archives_fibonacci_direction_without_robot_candidate(tmp_path):
    from owner_signal_proposal import (
        record_owner_chart_proposal, list_owner_chart_training_examples,
    )
    payload = _owner_chart_payload()
    payload.update(
        schema_version=2, pattern="Ikigai Box", direction="SHORT",
        proposed_boundaries=[{
            "id": "first_impulse_fibonacci", "type": "fibonacci",
            "anchors": [
                {"bar_open_time_ms": 10 * 300_000, "price": 95.0},
                {"bar_open_time_ms": 15 * 300_000, "price": 108.0},
            ],
        }],
    )
    first = record_owner_chart_proposal(
        payload, directory=tmp_path, now_ms=121 * 300_000,
    )
    assert first["submission"]["direction"] == "SHORT"
    assert first["submission"]["proposed_boundaries"] == payload["proposed_boundaries"]
    assert first["owner_source_snapshot"]["boundaries"][0]["kind"] == "fibonacci"
    assert first["candidate_created"] is False
    assert first["robot_candidate_id"] is None
    assert first["assessment"]["decision"] == "AWAITING_OFFLINE_REPLAY"
    assert list_owner_chart_training_examples("Ikigai Box", directory=tmp_path) == [first]
    assert record_owner_chart_proposal(
        payload, directory=tmp_path, now_ms=121 * 300_000,
    ) == first

    bad = {**payload, "direction": "LONG",
           "idempotency_key": "ikigai-invalid-dir-000001"}
    with pytest.raises(OwnerSignalProposalError, match="impulse_direction"):
        record_owner_chart_proposal(
            bad, directory=tmp_path, now_ms=121 * 300_000,
        )
    fake = {**payload, "proposed_boundaries": [{
        **payload["proposed_boundaries"][0], "type": "rectangle",
    }], "idempotency_key": "ikigai-invalid-rect-0001"}
    with pytest.raises(OwnerSignalProposalError, match="invalid_owner_chart_geometry"):
        record_owner_chart_proposal(
            fake, directory=tmp_path, now_ms=121 * 300_000,
        )
    assert len(list(tmp_path.rglob("*.json"))) == 1
