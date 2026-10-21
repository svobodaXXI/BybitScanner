from decimal import Decimal as D

import pytest

from retest_account_risk import (
    DECISION_OK,
    account_risk_limit,
    daily_loss_headroom_usdt,
    freeze_r0,
    position_worst_case_loss_usdt,
)
from retest_campaign import DECISION_DENY, DECISION_WAIT, open_campaign_budget


def gate(**overrides):
    # Shape of the live ``daily_loss_gate`` decision fact (PAPER_AUTO, 2026-10-19).
    value = {
        "enabled": True, "data_available": True, "latched": False,
        "baseline_equity_usdt": "5212.934694639739999999999995",
        "current_adjusted_equity_usdt": "5212.934694639739999999999995",
        "block_pct": "-10", "resume_pct": "-7",
    }
    value.update(overrides)
    return value


def test_headroom_is_the_distance_to_the_existing_block_without_a_new_percentage():
    decision, reason, headroom = daily_loss_headroom_usdt(gate())

    assert (decision, reason) == (DECISION_OK, "headroom")
    assert headroom == pytest.approx(D("521.2934694639739999999999995"))


def test_headroom_shrinks_with_losses_and_grows_with_gains_of_the_day():
    base = daily_loss_headroom_usdt(gate())[2]
    lost = daily_loss_headroom_usdt(gate(current_adjusted_equity_usdt="5100"))[2]
    won = daily_loss_headroom_usdt(gate(current_adjusted_equity_usdt="5300"))[2]

    assert lost < base < won
    assert base - lost == pytest.approx(D("112.934694639739999999999995"))


@pytest.mark.parametrize(
    ("overrides", "decision", "reason"),
    [
        ({"enabled": False}, DECISION_WAIT, "daily_gate_disabled"),
        ({"enabled": None}, DECISION_WAIT, "daily_gate_disabled"),
        ({"data_available": False}, DECISION_WAIT, "daily_gate_data_unavailable"),
        ({"latched": True}, DECISION_DENY, "daily_loss_latched"),
        ({"latched": None}, DECISION_WAIT, "daily_loss_latch_unknown"),
        ({"baseline_equity_usdt": None}, DECISION_WAIT, "daily_gate_values_unknown"),
        ({"current_adjusted_equity_usdt": "NaN"}, DECISION_WAIT, "daily_gate_values_unknown"),
        ({"block_pct": 10.0}, DECISION_WAIT, "daily_gate_values_unknown"),
        ({"block_pct": "10"}, DECISION_WAIT, "daily_gate_values_invalid"),
        ({"block_pct": "-100"}, DECISION_WAIT, "daily_gate_values_invalid"),
        ({"baseline_equity_usdt": "0"}, DECISION_WAIT, "daily_gate_values_invalid"),
        ({"current_adjusted_equity_usdt": "4600"}, DECISION_DENY, "daily_loss_headroom_exhausted"),
    ],
)
def test_unknown_or_blocking_gate_state_never_yields_a_limit(overrides, decision, reason):
    assert daily_loss_headroom_usdt(gate(**overrides))[:2] == (decision, reason)


@pytest.mark.parametrize("missing", [None, "gate", [], 7])
def test_proven_daily_loss_latch_denies_even_if_equity_is_unavailable():
    verdict = daily_loss_headroom_usdt(gate(data_available=False, latched=True))
    assert verdict[:2] == (DECISION_DENY, "daily_loss_latched")


def test_missing_gate_waits(missing):
    assert daily_loss_headroom_usdt(missing)[:2] == (DECISION_WAIT, "daily_gate_unavailable")


def test_committed_obligations_reduce_the_available_limit():
    limit = account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=["10.5", D("20"), 4])

    assert limit.decision == DECISION_OK
    assert limit.committed_usdt == D("34.5")
    assert limit.limit_usdt == limit.headroom_usdt - D("34.5")


def test_no_obligations_is_a_proven_empty_list_but_none_is_unknown():
    assert account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=[]).committed_usdt == 0
    unknown = account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=None)
    assert (unknown.decision, unknown.reason) == (DECISION_WAIT, "obligations_unknown")
    assert unknown.limit_usdt is None


@pytest.mark.parametrize("bad", [None, "x", True, 1.5, "NaN"])
def test_any_unknown_obligation_waits(bad):
    limit = account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=["5", bad])

    assert (limit.decision, limit.reason) == (DECISION_WAIT, "obligation_unknown")


def test_negative_obligation_is_invalid_not_a_credit():
    limit = account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=["-50"])

    assert (limit.decision, limit.reason) == (DECISION_WAIT, "obligation_invalid")


def test_obligations_at_or_above_headroom_exhaust_the_limit():
    exact = account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=["521.2934694639739999999999995"])
    over = account_risk_limit(daily_gate=gate(), committed_worst_case_usdt=["600"])

    assert (exact.decision, exact.reason) == (DECISION_DENY, "account_risk_exhausted")
    assert (over.decision, over.reason) == (DECISION_DENY, "account_risk_exhausted")


def test_r0_is_half_the_net_potential_when_the_account_limit_is_larger():
    result = freeze_r0(idea_potential_net_usdt="40", daily_gate=gate(), committed_worst_case_usdt=[])

    assert result.decision == DECISION_OK
    assert result.r0_usdt == pytest.approx(20.0)
    assert open_campaign_budget(result.r0_usdt).cap_usdt == pytest.approx(20.0)


def test_r0_is_capped_by_the_account_limit_when_that_is_smaller():
    result = freeze_r0(
        idea_potential_net_usdt="5000", daily_gate=gate(), committed_worst_case_usdt=["500"],
    )

    assert result.decision == DECISION_OK
    assert result.r0_usdt == pytest.approx(float(result.account_limit.limit_usdt))
    assert result.r0_usdt == pytest.approx(21.2934694639739999999999995)


@pytest.mark.parametrize(
    ("potential", "decision", "reason"),
    [(None, DECISION_WAIT, "idea_potential_unknown"), ("x", DECISION_WAIT, "idea_potential_unknown"),
     (12.5, DECISION_WAIT, "idea_potential_unknown"), ("0", DECISION_DENY, "no_net_potential"),
     ("-3", DECISION_DENY, "no_net_potential")],
)
def test_unknown_or_non_positive_potential_never_freezes_r0(potential, decision, reason):
    result = freeze_r0(idea_potential_net_usdt=potential, daily_gate=gate(), committed_worst_case_usdt=[])

    assert (result.decision, result.reason, result.r0_usdt) == (decision, reason, None)


def test_account_state_blocks_r0_before_the_potential_is_considered():
    result = freeze_r0(
        idea_potential_net_usdt="40", daily_gate=gate(latched=True), committed_worst_case_usdt=[],
    )

    assert (result.decision, result.reason, result.r0_usdt) == (DECISION_DENY, "daily_loss_latched", None)
    unknown = freeze_r0(idea_potential_net_usdt="40", daily_gate=gate(), committed_worst_case_usdt=None)
    assert (unknown.decision, unknown.r0_usdt) == (DECISION_WAIT, None)


def test_position_worst_case_loss_includes_both_side_fees():
    long = position_worst_case_loss_usdt(
        direction="LONG", quantity="100", entry_price="10", stop_price="9.5", fee_rate="0.0006",
    )
    short = position_worst_case_loss_usdt(
        direction="SHORT", quantity=D("100"), entry_price="10", stop_price="10.5", fee_rate="0.0006",
    )

    assert long == D("100") * (D("0.5") + D("0.0006") * D("19.5"))
    assert short == D("100") * (D("0.5") + D("0.0006") * D("20.5"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stop_price": None},                       # unprotected -> unknown
        {"stop_price": "10"},                       # no distance
        {"stop_price": "11"},                       # wrong side for LONG
        {"quantity": "0"},
        {"quantity": 5.5},
        {"direction": "FLAT"},
        {"fee_rate": "-0.1"},
        {"entry_price": "NaN"},
    ],
)
def test_position_worst_case_loss_is_unknown_for_unusable_inputs(kwargs):
    base = dict(direction="LONG", quantity="100", entry_price="10", stop_price="9.5", fee_rate="0.0006")
    base.update(kwargs)

    assert position_worst_case_loss_usdt(**base) is None
