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


def test_proven_wedge_finrez_enrichment_and_unproven_is_absent():
    from terminal.diary.wedge_lineage import attach_verified_wedge_signals
    snapshot, kwargs = case()
    row = {
        "trade_episode_id": kwargs["trade_episode_id"], "symbol": "BTCUSDT",
        "side": "LONG", "opened_at_ms": 1200, "closed_at_ms": 1300,
        "pnl_usdt": "1.8", "execution_count": 2, "cohort": "ROBOT",
        "setup_context": {"status": "NO_EXACT_EPISODE_LINK"},
    }
    report = {"account_id": "paper", "owner": "ROBOT",
              "source_revision": 5, "closed_episodes": [row],
              "tickers": [{"symbol": "BTCUSDT", "pnl_usdt": "1.8"}]}
    result = attach_verified_wedge_signals(snapshot, report)
    signal = result["closed_episodes"][0]["verified_signal"]
    assert signal["trade_episode_id"] == kwargs["trade_episode_id"]
    assert signal["source_revision"] == 5
    assert signal["candidate_id"] == "candidate-2"
    assert signal["pattern"] == "Falling Wedge"
    assert signal["source_timeframe"] == "5m"
    assert signal["status"] == "PROVEN"
    assert {k: v for k, v in result["closed_episodes"][0].items()
            if k != "verified_signal"} == row
    assert result["tickers"] == report["tickers"]
    for source, item in (
        (replace(snapshot, wedge_evidence=None), report),
        (snapshot, {**report, "owner": "MANUAL"}),
        (snapshot, {**report, "closed_episodes": [{**row, "cohort": "JOINT_MANAGEMENT"}]}),
        (snapshot, {**report, "closed_episodes": [{**row, "pnl_usdt": "999"}]}),
    ):
        assert "verified_signal" not in attach_verified_wedge_signals(
            source, item)["closed_episodes"][0]


def test_unrelated_candidates_without_order_proof_do_not_hide_exact_wedge():
    from terminal.diary.wedge_lineage import attach_verified_wedge_signals
    snapshot, kwargs = case()
    valid = snapshot.wedge_evidence["candidates"][0]
    incomplete = (
        dict(valid, candidate_id="rejected", symbol="ETHUSDT",
             robot_state_json='{"decision":"REJECTED"}'),
        dict(valid, candidate_id="legacy", symbol="ETHUSDT",
             robot_state_json='{"execution":{}}'),
        dict(valid, candidate_id="corrupt", symbol="ETHUSDT",
             robot_state_json="{invalid"),
    )
    evidence = dict(snapshot.wedge_evidence, candidates=incomplete + (valid,))
    updated = replace(snapshot, wedge_evidence=evidence)
    assert project_selected_paper_wedge(updated, **kwargs)["candidate_id"] == "candidate-2"
    row = {
        "trade_episode_id": kwargs["trade_episode_id"], "symbol": "BTCUSDT",
        "side": "LONG", "opened_at_ms": 1200, "closed_at_ms": 1300,
        "pnl_usdt": "1.8", "execution_count": 2, "cohort": "ROBOT",
        "setup_context": {"status": "NO_EXACT_EPISODE_LINK"},
    }
    report = {
        "account_id": "paper", "owner": "ROBOT", "source_revision": 5,
        "closed_episodes": [row], "tickers": [{"symbol": "BTCUSDT", "pnl_usdt": "1.8"}],
    }
    enriched = attach_verified_wedge_signals(updated, report)
    assert enriched["closed_episodes"][0]["verified_signal"]["candidate_id"] == "candidate-2"
    assert enriched["closed_episodes"][0]["pnl_usdt"] == row["pnl_usdt"]
    assert enriched["closed_episodes"][0]["setup_context"] == row["setup_context"]


def test_missing_target_entry_identity_remains_unproven_despite_other_candidates():
    import pytest
    snapshot, kwargs = case()
    valid = snapshot.wedge_evidence["candidates"][0]
    invalid_target = dict(valid, robot_state_json='{"execution":{}}')
    unrelated = dict(valid, candidate_id="other", robot_state_json='{"execution":{"limit_order_id":"unrelated"}}')
    evidence = dict(snapshot.wedge_evidence, candidates=(invalid_target, unrelated))
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)


def test_competing_exact_entry_candidate_remains_unproven():
    import pytest
    snapshot, kwargs = case()
    valid = snapshot.wedge_evidence["candidates"][0]
    other = dict(valid, candidate_id="competing-candidate")
    evidence = dict(snapshot.wedge_evidence, candidates=(valid, other))
    with pytest.raises(WedgeLineageUnproven):
        project_selected_paper_wedge(replace(snapshot, wedge_evidence=evidence), **kwargs)
