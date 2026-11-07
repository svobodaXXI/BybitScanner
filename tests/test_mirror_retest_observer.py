import json
from pathlib import Path

import pytest

from geometry.naked_retest import (
    EVENT_DATA_GAP,
    EVENT_NAKED_BREAKOUT,
    EVENT_RETEST_PROVEN,
    EVENT_RETEST_UNPROVEN,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_RETEST_PROVEN,
    PHASE_RETEST_UNPROVEN,
    Boundary,
)
from mirror_retest_observer import (
    DECISION_BLOCK,
    DECISION_WAIT,
    AccountFacts,
    Observation,
    ObservationJournal,
    decide,
    observe_closed_candle,
    observe_history,
)
from tools.research_mirror_integration_2 import boundary_from_manifest

FIXTURES = Path(__file__).parent / "fixtures" / "mirror_integration_2"
FIVE = 300_000


def load(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return boundary_from_manifest(data["manifest"]), data


def gate(**overrides):
    value = {"enabled": True, "data_available": True, "latched": False,
             "baseline_equity_usdt": "5000", "current_adjusted_equity_usdt": "5000", "block_pct": "-10"}
    value.update(overrides)
    return value


def bar(i, o, h, l, c):
    return {"open_time_ms": i * FIVE, "close_time_ms": (i + 1) * FIVE,
            "open": o, "high": h, "low": l, "close": c, "closed": True}


def flat_boundary():
    return Boundary.horizontal("flat:100", 100.0, as_of_time_ms=0)


def active_state():
    state = None
    boundary = flat_boundary()
    state, record = observe_closed_candle(boundary, state, bar(0, 99.0, 102.0, 98.5, 101.5), symbol="X")
    assert record.event == EVENT_NAKED_BREAKOUT and state["phase"] == PHASE_CAMPAIGN_ACTIVE
    return boundary, state


# Real saved historical cases (Bybit public klines, RETEST-4 manifest).

def test_real_proven_case_observes_breakout_then_retest_and_never_executes():
    boundary, data = load("proven_1000luncusdt_upper")
    state, records = observe_history(boundary, data["coarse_5m"], symbol=data["manifest"]["symbol"],
                                     fine_candles=data["fine_1m"])

    assert state["phase"] == PHASE_RETEST_PROVEN
    assert [(r.event, r.decision) for r in records] == [
        (EVENT_NAKED_BREAKOUT, DECISION_WAIT), (EVENT_RETEST_PROVEN, DECISION_BLOCK)]
    breakout, retest = records
    assert breakout.candle_close_time_ms == data["manifest"]["breakout_close_time_ms"]
    assert breakout.campaign_direction == "SHORT"            # UP breakout -> SHORT campaign
    assert "r0_wait:daily_gate_unavailable" in breakout.reasons
    assert "policy_wait:robot_execution_not_authorized" in breakout.reasons
    assert retest.exit_intent == "CLOSE_REMAINDER"
    for record in records:
        assert (record.executable, record.admission_allowed, record.mode) == (False, False, "OBSERVE_ONLY")


def test_real_unproven_case_ends_fail_closed_without_exit_intent():
    boundary, data = load("unproven_brusdt_upper")
    state, records = observe_history(boundary, data["coarse_5m"], symbol=data["manifest"]["symbol"],
                                     fine_candles=data["fine_1m"])

    assert state["phase"] == PHASE_RETEST_UNPROVEN
    assert [r.event for r in records] == [EVENT_NAKED_BREAKOUT, EVENT_RETEST_UNPROVEN]
    assert records[-1].decision == DECISION_BLOCK
    assert records[-1].exit_intent is None


def test_real_case_with_account_facts_still_waits_for_an_attempt_plan():
    boundary, data = load("proven_1000luncusdt_upper")
    _, records = observe_history(
        boundary, data["coarse_5m"], symbol="1000LUNCUSDT", fine_candles=data["fine_1m"],
        idea_potential_net_usdt="40", account=AccountFacts(gate(), []))
    breakout = records[0]

    assert breakout.decision == DECISION_WAIT
    assert breakout.r0_decision == "OK" and breakout.r0_usdt == pytest.approx(20.0)
    assert breakout.research_policy == "WAIT"
    assert any(reason.startswith("policy_wait:unknown:") for reason in breakout.reasons)


# Decision rules.

def test_latched_account_blocks_an_active_campaign():
    boundary, state = active_state()
    decision, reasons, facts = decide(state=state, boundary_id=boundary.boundary_id,
                                      idea_potential_net_usdt="40", account=AccountFacts(gate(latched=True), []))

    assert decision == DECISION_BLOCK
    assert "r0_deny:daily_loss_latched" in reasons


def test_unknown_obligations_wait():
    boundary, state = active_state()
    decision, reasons, _ = decide(state=state, boundary_id=boundary.boundary_id,
                                  idea_potential_net_usdt="40", account=AccountFacts(gate(), None))

    assert decision == DECISION_WAIT
    assert "r0_wait:obligations_unknown" in reasons


def test_research_policy_allow_is_never_reported_as_allow(monkeypatch):
    import mirror_retest_observer as observer
    from mirror_retest_robot_bridge import MirrorRobotObservation

    def allow(**kwargs):
        return MirrorRobotObservation("MIRROR_RETEST", kwargs["boundary_id"], PHASE_CAMPAIGN_ACTIVE, "SHORT",
                                      "ALLOW", "within_campaign_budget", None)

    monkeypatch.setattr(observer, "observe_for_robot", allow)
    boundary, state = active_state()
    decision, reasons, _ = decide(state=state, boundary_id=boundary.boundary_id,
                                  idea_potential_net_usdt="40", account=AccountFacts(gate(), []))

    assert decision == DECISION_WAIT
    assert "robot_execution_not_authorized" in reasons


def test_data_gap_during_campaign_waits_and_before_breakout_has_no_campaign():
    boundary, state = active_state()
    state, record = observe_closed_candle(boundary, state, bar(3, 101.0, 101.5, 100.5, 101.2), symbol="X")
    assert record.event == EVENT_DATA_GAP
    assert record.decision == DECISION_WAIT and "data_unreliable" in record.reasons

    fresh, record = observe_closed_candle(boundary, None, bar(0, 99.0, 99.5, 98.0, 99.2), symbol="X")
    assert record is None                                      # no transition -> nothing recorded
    gap, record = observe_closed_candle(boundary, fresh, bar(2, 99.0, 99.5, 98.0, 99.2), symbol="X")
    assert record.event == EVENT_DATA_GAP
    assert record.reasons == ("data_unreliable", "no_campaign", "observe_only")


# Journal.

def test_journal_is_idempotent_and_refuses_executable_records(tmp_path):
    boundary, data = load("proven_1000luncusdt_upper")
    _, records = observe_history(boundary, data["coarse_5m"], symbol="1000LUNCUSDT",
                                 fine_candles=data["fine_1m"])
    path = tmp_path / "observations.jsonl"

    assert ObservationJournal(path).append(records) == 2
    assert ObservationJournal(path).append(records) == 0      # re-run: same ids, nothing appended
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and all(json.loads(line)["executable"] is False for line in lines)

    forged = Observation(**{**records[0].__dict__, "observation_id": "x", "executable": True})
    with pytest.raises(ValueError):
        ObservationJournal(path).append([forged])


# Candidate snapshot -> frozen boundaries (same transform as RETEST-4).

def snapshot(**overrides):
    value = {
        "pattern": "Rising Wedge",
        "robot_geometry": {"robot_coordinate_timeframe": "1",
                           "upper_line": {"slope": "0.0002", "intercept": "1.25"},
                           "lower_line": {"slope": "0.0005", "intercept": "1.10"}},
        "scanner_geometry_cursor": {"timeframe": "1", "geometry_index": 240,
                                    "source_candle_time_ms": 1_789_000_000_000},
    }
    value.update(overrides)
    return value


def test_snapshot_boundaries_match_the_retest4_transform():
    from mirror_retest_observer import boundaries_from_candidate_snapshot
    from tools.research_mirror_retest_4 import boundaries as retest4_boundaries

    mine = boundaries_from_candidate_snapshot(candidate_id="c1", created_at_ms=1_789_000_060_000,
                                              signal_snapshot=snapshot())
    row = {"candidate_id": "c1", "as_of_ms": 1_789_000_060_000, "cursor_index": 240,
           "cursor_time_ms": 1_789_000_000_000,
           "upper": {"slope": 0.0002, "intercept": 1.25}, "lower": {"slope": 0.0005, "intercept": 1.10}}

    assert list(mine) == retest4_boundaries(row)
    assert mine[0].boundary_id == "c1:upper" and mine[0].as_of_time_ms == 1_789_000_060_000


@pytest.mark.parametrize("broken", [
    {"robot_geometry": None},
    {"scanner_geometry_cursor": {"timeframe": "5", "geometry_index": 1, "source_candle_time_ms": 1}},
    {"robot_geometry": {"robot_coordinate_timeframe": "1", "upper_line": {"slope": "x", "intercept": "1"},
                        "lower_line": {"slope": "1", "intercept": "1"}}},
    {"robot_geometry": {"robot_coordinate_timeframe": "1", "upper_line": {"slope": "1", "intercept": "1"}}},
])
def test_incomplete_snapshot_yields_no_boundary(broken):
    from mirror_retest_observer import boundaries_from_candidate_snapshot

    assert boundaries_from_candidate_snapshot(candidate_id="c1", created_at_ms=1,
                                              signal_snapshot=snapshot(**broken)) is None
