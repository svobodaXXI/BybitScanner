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
