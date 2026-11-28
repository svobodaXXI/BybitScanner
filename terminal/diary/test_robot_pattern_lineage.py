"""Exact-ID host pattern enrichment; no VPS, runtime, or database writes."""
from dataclasses import replace
import pytest

from terminal.diary.test_campaign_lineage import fixture
from terminal.diary.ticker_finrez import project_paper_ticker_pnl
from terminal.diary.robot_pattern_lineage import attach_verified_robot_pattern_signals


def _case(pattern="IKIGAI_BOX", *, box=True):
    f = fixture()
    snapshot = f["snapshot"]
    selected = snapshot.episodes[1]
    candidate = {
        "trading_account_id": "paper", "candidate_id": "candidate-2",
        "symbol": "BTCUSDT",
        "robot_state_json": '{"execution":{"limit_order_id":"entry-2"}}',
    }
    trade = {
        **f["trades"][1], "pattern": pattern,
    }
    evidence = {
        "candidates": (candidate,),
        "trades": (trade,),
        "robot_entries": ({
            "trading_account_id": "paper", "order_id": "entry-2",
            "origin": "ROBOT",
        },),
        "obligations": (),
        "box_entries": ({
            "trading_account_id": "paper", "candidate_id": "candidate-2",
            "order_id": "entry-2", "role": "ENTRY",
        },) if box else (),
    }
    snapshot = replace(snapshot, wedge_evidence=evidence)
    report = project_paper_ticker_pnl(
        snapshot, account_id="paper", owner="ROBOT", period="ALL", now_ms=2000,
    )
    return snapshot, report, selected.trade_episode_id.value


@pytest.mark.parametrize("pattern", (
    "IKIGAI_BOX", "L-shape", "Triangle Compression", "Double Top",
    "Double Bottom", "MIRROR", "Other future verified pattern",
))
def test_labels_all_persisted_host_patterns_with_exact_entry_proof(pattern):
    snapshot, report, selected_id = _case(pattern, box=pattern == "IKIGAI_BOX")
    enriched = attach_verified_robot_pattern_signals(snapshot, report)
    proof = next(x for x in enriched["closed_episodes"]
                 if x["trade_episode_id"] == selected_id)["verified_signal"]
    assert proof["status"] == "PROVEN"
    assert proof["pattern"] == pattern
    assert proof["candidate_id"] == "candidate-2"
    assert proof["evidence_scope"] == "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE"
    assert enriched["tickers"] == report["tickers"]
    assert [x.get("verified_signal") for x in enriched["closed_episodes"] if x["trade_episode_id"] != selected_id] == [None]


def test_box_market_entry_ownership_does_not_require_limit_registry():
    snapshot, report, selected_id = _case()
    evidence = dict(snapshot.wedge_evidence, robot_entries=())
    snapshot = replace(snapshot, wedge_evidence=evidence)
    result = attach_verified_robot_pattern_signals(snapshot, report)
    assert next(x for x in result["closed_episodes"]
                if x["trade_episode_id"] == selected_id)["verified_signal"]["pattern"] == "IKIGAI_BOX"


@pytest.mark.parametrize("change", (
    {"robot_entries": ()},
    {"candidates": ()},
    {"trades": ()},
    {"box_entries": ()},
))
def test_missing_exact_identity_keeps_unknown(change):
    pattern = "IKIGAI_BOX" if "box_entries" in change else "L-shape"
    snapshot, report, eid = _case(pattern, box=pattern == "IKIGAI_BOX")
    if pattern != "IKIGAI_BOX":
        snapshot = replace(snapshot, wedge_evidence={
            **snapshot.wedge_evidence, "box_entries": (),
        })
    snapshot = replace(snapshot, wedge_evidence={**snapshot.wedge_evidence, **change})
    selected = next(x for x in attach_verified_robot_pattern_signals(snapshot, report)["closed_episodes"]
                    if x["trade_episode_id"] == eid)
    assert "verified_signal" not in selected


def test_conflicting_candidate_or_ambiguous_order_does_not_label():
    snapshot, report, eid = _case("L-shape", box=False)
    original = snapshot.wedge_evidence["candidates"][0]
    forged = dict(original, candidate_id="another-candidate")
    evidence = {
        **snapshot.wedge_evidence,
        "candidates": (original, forged),
        "box_entries": (),
    }
    snapshot = replace(snapshot, wedge_evidence=evidence)
    row = next(x for x in attach_verified_robot_pattern_signals(snapshot, report)["closed_episodes"]
               if x["trade_episode_id"] == eid)
    assert "verified_signal" not in row


def test_stale_revision_mismatched_financials_and_manual_scope_fail_closed():
    snapshot, report, eid = _case("Double Bottom", box=False)
    for altered in (
        {**report, "source_revision": 4},
        {**report, "owner": "MANUAL"},
        {**report, "closed_episodes": [
            {**row, "pnl_usdt": "300"} if row["trade_episode_id"] == eid else row
            for row in report["closed_episodes"]
        ]},
        {**report, "closed_episodes": [
            {**row, "cohort": "JOINT_MANAGEMENT"} if row["trade_episode_id"] == eid else row
            for row in report["closed_episodes"]
        ]},
    ):
        enriched = attach_verified_robot_pattern_signals(snapshot, altered)
        row = next(x for x in enriched["closed_episodes"] if x["trade_episode_id"] == eid)
        assert "verified_signal" not in row


def test_d2_conflicting_pattern_cannot_be_overwritten():
    snapshot, report, eid = _case("L-shape", box=False)
    report = {
        **report,
        "closed_episodes": [
            {**row, "setup_context": {
                "status": "EXACT_D2_LINK", "setup": {"pattern": "Double Top"},
            }} if row["trade_episode_id"] == eid else row
            for row in report["closed_episodes"]
        ],
    }
    enriched = attach_verified_robot_pattern_signals(snapshot, report)
    assert "verified_signal" not in next(
        x for x in enriched["closed_episodes"] if x["trade_episode_id"] == eid
    )


def test_wedge_uses_its_independent_stricter_lineage():
    snapshot, report, eid = _case("Falling Wedge", box=False)
    enriched = attach_verified_robot_pattern_signals(snapshot, report)
    assert "verified_signal" not in next(
        x for x in enriched["closed_episodes"] if x["trade_episode_id"] == eid
    )

def test_box_plan_owned_orders_resolve_only_verified_robot_handoff():
    snapshot, report, eid = _case()
    evidence = snapshot.wedge_evidence
    source_id, robot_id = "box-plan-example", "box-robot-example"
    source = dict(evidence["candidates"][0], candidate_id=source_id, robot_state_json=None)
    robot = dict(evidence["candidates"][0], candidate_id=robot_id)
    linked = dict(
        evidence, candidates=(source, robot),
        trades=(dict(evidence["trades"][0], candidate_id=robot_id),),
        box_entries=(dict(evidence["box_entries"][0], candidate_id=source_id),),
        box_handoffs=({"source_candidate_id": source_id, "robot_candidate_id": robot_id},),
    )
    def selected(evidence):
        result = attach_verified_robot_pattern_signals(replace(snapshot, wedge_evidence=evidence), report)
        return next(row for row in result["closed_episodes"] if row["trade_episode_id"] == eid)
    assert selected(linked)["verified_signal"]["candidate_id"] == robot_id
    assert selected(dict(linked, robot_entries=()))["verified_signal"]["pattern"] == "IKIGAI_BOX"
    assert "verified_signal" not in selected(dict(linked, box_handoffs=()))
    assert "verified_signal" not in selected(dict(linked, candidates=(source, robot, robot)))
    assert "verified_signal" not in selected(dict(linked, trades=(
        linked["trades"][0], dict(linked["trades"][0], candidate_id=source_id),
    )))
    assert "verified_signal" not in selected(dict(linked, candidates=(
        source, robot, dict(robot, candidate_id="unrelated"),
    )))


def test_handoff_reader_checks_actual_immutable_plan_and_clone(tmp_path):
    from tests.test_box_plan_persistence import snapshot as frozen_plan
    from terminal.persistence.sqlite_store import SQLiteStore
    from terminal.domain.models import Symbol
    from terminal.diary.scoped_statistics_reporter import _verified_box_handoffs
    import sqlite3
    from contextlib import closing
    path = tmp_path / "isolated.sqlite3"
    store = SQLiteStore.open(path)
    try:
        source, _ = store.save_box_plan_only(snapshot=frozen_plan(), created_at_ms=3001)
        robot, _ = store.handoff_box_plan_to_robot(
            source.candidate_id, symbol=Symbol("BTCUSDT"),
            expected_snapshot_sha256=source.snapshot_sha256, approved_at_ms=3002,
        )
    finally:
        store.close()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute("SELECT * FROM robot_candidates")]
    assert _verified_box_handoffs(rows) == ({
        "source_candidate_id": source.candidate_id,
        "robot_candidate_id": robot.candidate_id,
    },)
    assert _verified_box_handoffs([dict(row, snapshot_sha256="0" * 64)
                                  if row["candidate_id"] == robot.candidate_id else row
                                  for row in rows]) == ()
    assert _verified_box_handoffs([row for row in rows if row["candidate_id"] != source.candidate_id]) == ()
