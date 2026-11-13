"""Wedge exact-ID lineage regressions; no runtime or PAPER database writes."""
from dataclasses import replace
from terminal.diary.test_campaign_lineage import fixture
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.diary.wedge_lineage import WedgeLineageUnproven, project_selected_paper_wedge


def case():
    old = fixture()
    base = old["snapshot"]
    source = base.episodes[1].trade_episode_id.value
    evidence = {
        "candidates": ({
            "trading_account_id": "paper", "candidate_id": "candidate-2",
            "symbol": "BTCUSDT",
            "robot_state_json": '{"execution":{"limit_order_id":"entry-2"}}',
        },),
        "trades": ({
            "trading_account_id": "paper", "candidate_id": "candidate-2",
            "trade_id": "trade-2", "symbol": "BTCUSDT", "direction": "LONG",
            "pattern": "Falling Wedge", "source_timeframe": "5m",
            "signal_time_ms": 1150, "entry_time_ms": 1200,
            "exit_time_ms": 1300, "exit_reason": "TAKE",
        },),
        "robot_entries": ({
            "trading_account_id": "paper", "order_id": "entry-2",
            "origin": "ROBOT",
        },),
        "obligations": ({
            "trading_account_id": "paper", "trade_id": "trade-2",
            "status": "RESOLVED", "winning_leg": "TAKE",
            "order_id": "exit-2", "exec_id": "close-2",
        },),
    }
    snapshot = replace(base, wedge_evidence=evidence)
    return snapshot, dict(account_id="paper", owner="ROBOT",
                          trade_episode_id=source, source_revision=5)


def test_exact_wedge_candidate_order_execution_episode():
    snapshot, kwargs = case()
    result = project_selected_paper_wedge(snapshot, **kwargs)
    assert result["signal_pattern"] == "Falling Wedge"
    assert result["candidate_id"] == "candidate-2"
    assert result["known_execution_fees_usdt"] == "0.2"
    assert [x["order_id"] for x in result["execution_allocations"]] == ["entry-2", "exit-2"]
    assert len(result["source_sha256"]) == 64
    assert result["market_candles_coverage"] == "NOT_PROVIDED"


def test_rejects_candidate_without_exact_order():
    import pytest
    snapshot, kwargs = case()
    evidence = dict(snapshot.wedge_evidence)
    evidence["candidates"] = (dict(evidence["candidates"][0],
                                  robot_state_json='{"execution":{"limit_order_id":"other"}}'),)
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)


def test_rejects_missing_robot_entry_proof_and_duplicate_candidate():
    import pytest
    snapshot, kwargs = case()
    evidence = dict(snapshot.wedge_evidence, robot_entries=())
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)
    evidence = dict(snapshot.wedge_evidence)
    evidence["candidates"] = evidence["candidates"] * 2
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)


def test_rejects_wrong_exit_revision_and_pattern():
    import pytest
    snapshot, kwargs = case()
    for modified in (dict(kwargs, source_revision=4),):
        with pytest.raises(WedgeLineageUnproven):
            project_selected_paper_wedge(snapshot, **modified)
    evidence = dict(snapshot.wedge_evidence)
    evidence["trades"] = (dict(evidence["trades"][0], pattern="Box"),)
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)
    evidence = dict(snapshot.wedge_evidence)
    evidence["obligations"] = (dict(evidence["obligations"][0], exec_id="other"),)
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)
