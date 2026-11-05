from decimal import Decimal as D

import pytest

from geometry.naked_retest import (
    CAMPAIGN_LONG,
    CAMPAIGN_SHORT,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_RETEST_PROVEN,
    PHASE_RETEST_UNPROVEN,
    PHASE_WAITING_BREAKOUT,
)
from retest_campaign import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_WAIT,
    EXIT_CLOSE_REMAINDER,
    PARTIAL_TAKE_FRACTION,
    RETEST_REMAINDER_FRACTION,
    STOP_KEEP_CURRENT,
    STOP_NET_BREAK_EVEN,
    RetestCampaignError,
    campaign_exit_intent,
    entry_gate,
    freeze_campaign_r0,
    net_break_even_remainder_stop,
    open_campaign_budget,
)


# Arbitrary test amounts; they are not risk policy.
def gate(budget, phase=PHASE_CAMPAIGN_ACTIVE, reliable=True, realized=0.0, live=0.0, new=1.0, reward=10.0):
    return entry_gate(budget, campaign_phase=phase, data_reliable=reliable,
                      realized_loss_costs_usdt=realized, live_pending_worst_case_usdt=live,
                      new_attempt_worst_case_usdt=new, remaining_net_reward_usdt=reward)


def test_cap_is_min_of_r0_and_half_remaining_reward():
    budget = open_campaign_budget(4.0)
    assert gate(budget, new=4.0, reward=10.0).decision == DECISION_ALLOW   # cap 4
    assert gate(budget, new=4.0, reward=6.0).decision == DECISION_DENY     # cap 3
    assert gate(budget, new=3.0, reward=6.0).budget.cap_usdt == 3.0


def test_attempt_count_is_unlimited_while_cumulative_loss_fits():
    budget = open_campaign_budget(5.0)
    realized = 0.0
    for _ in range(10):  # well past three attempts
        result = gate(budget, realized=realized, new=0.4, reward=100.0)
        assert result.decision == DECISION_ALLOW
        budget, realized = result.budget, realized + 0.4
    assert gate(budget, realized=realized, new=1.1, reward=100.0).decision == DECISION_DENY


def test_cap_never_grows_back_when_reward_recovers():
    budget = gate(open_campaign_budget(5.0), new=0.5, reward=2.0).budget
    assert budget.cap_usdt == 1.0
    assert gate(budget, new=2.0, reward=100.0).decision == DECISION_DENY
    exhausted = gate(budget, reward=0.0)
    assert (exhausted.decision, exhausted.budget.cap_usdt) == (DECISION_DENY, 0.0)
    assert gate(exhausted.budget, new=0.01, reward=100.0).decision == DECISION_DENY


def test_live_and_pending_worst_case_counts_against_the_cap():
    budget = open_campaign_budget(5.0)
    assert gate(budget, realized=1.0, live=2.0, new=2.0).decision == DECISION_ALLOW
    assert gate(budget, realized=1.0, live=2.5, new=2.0).decision == DECISION_DENY


@pytest.mark.parametrize("field", ["realized", "live", "new", "reward"])
def test_unknown_inputs_wait_without_touching_budget(field):
    budget = open_campaign_budget(5.0)
    for unknown in (None, float("nan")):
        result = gate(budget, **{field: unknown})
        assert (result.decision, result.budget) == (DECISION_WAIT, budget)


@pytest.mark.parametrize("reliable", [False, None, "true", 1])
def test_unreliable_data_blocks_admission(reliable):
    budget = open_campaign_budget(5.0)
    result = gate(budget, reliable=reliable)
    assert (result.decision, result.reason, result.budget) == (DECISION_WAIT, "data_unreliable", budget)


def test_negative_loss_amounts_cannot_net_profits_into_budget():
    with pytest.raises(RetestCampaignError):
        gate(open_campaign_budget(5.0), realized=-1.0)


@pytest.mark.parametrize("phase", [PHASE_WAITING_BREAKOUT, PHASE_RETEST_PROVEN, PHASE_RETEST_UNPROVEN])
def test_no_attempts_outside_an_active_campaign(phase):
    # Covers overshoot after the retest and any automatic reversal (rules 7, 8).
    assert gate(open_campaign_budget(5.0), phase=phase).decision == DECISION_DENY


@pytest.mark.parametrize("r0", [0, -1, None, float("inf"), True])
def test_r0_must_be_positive_and_finite(r0):
    with pytest.raises(RetestCampaignError):
        open_campaign_budget(r0)


def test_r0_follows_idea_potential_and_account_limit():
    assert freeze_campaign_r0(idea_potential_net_usdt=10.0, account_risk_limit_usdt=3.0) == 3.0
    assert freeze_campaign_r0(idea_potential_net_usdt=4.0, account_risk_limit_usdt=3.0) == 2.0
    for potential, limit in [(None, 3.0), (10.0, None), (0.0, 3.0), (10.0, 0.0), (float("nan"), 3.0)]:
        assert freeze_campaign_r0(idea_potential_net_usdt=potential, account_risk_limit_usdt=limit) is None


def test_r0_is_frozen_and_profit_does_not_restore_it():
    budget = open_campaign_budget(freeze_campaign_r0(idea_potential_net_usdt=10.0, account_risk_limit_usdt=3.0))
    after = gate(budget, realized=2.5, new=0.4, reward=100.0)
    assert after.decision == DECISION_ALLOW and after.budget.r0_usdt == 3.0
    # A later profitable attempt is not an input: realized losses stay 2.5.
    assert gate(after.budget, realized=2.5, new=0.6, reward=100.0).decision == DECISION_DENY
    with pytest.raises(Exception):
        after.budget.r0_usdt = 10.0  # frozen dataclass


def test_partial_take_split():
    assert PARTIAL_TAKE_FRACTION + RETEST_REMAINDER_FRACTION == 1.0


def test_only_a_proven_retest_closes_the_remainder():
    assert campaign_exit_intent(PHASE_RETEST_PROVEN) == EXIT_CLOSE_REMAINDER
    for phase in (PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_UNPROVEN, PHASE_WAITING_BREAKOUT):
        assert campaign_exit_intent(phase) is None


# --- remainder STOP keeping whole-trade net PnL >= 0 (test values only) -----

def trade(direction, **overrides):
    long = direction == CAMPAIGN_LONG
    values = dict(
        campaign_direction=direction, partial_take_confirmed=True, protection_preserved=True,
        current_stop_price=D("95") if long else D("105"), mark_price=D("108") if long else D("92"),
        entry_qty=D("4"), entry_avg_price=D("100"), entry_fees_usdt=D("0.2"),
        partial_qty=D("1"), partial_avg_price=D("110") if long else D("90"), partial_fees_usdt=D("0.05"),
        funding_usdt=D("0.1"), remainder_exit_fee_rate=D("0.001"), slippage_price=D("0.05"),
        tick_size=D("0.01"),
    )
    values.update(overrides)
    return values


def net_at(v, stop):
    q2 = v["entry_qty"] - v["partial_qty"]
    long = v["campaign_direction"] == CAMPAIGN_LONG
    fill = stop - v["slippage_price"] if long else stop + v["slippage_price"]
    sign = 1 if long else -1
    gross = sign * (v["partial_qty"] * (v["partial_avg_price"] - v["entry_avg_price"])
                    + q2 * (fill - v["entry_avg_price"]))
    costs = v["entry_fees_usdt"] + v["partial_fees_usdt"] + v["funding_usdt"]
    return gross - costs - v["remainder_exit_fee_rate"] * q2 * fill


@pytest.mark.parametrize("direction,tick_step", [(CAMPAIGN_LONG, D("-0.01")), (CAMPAIGN_SHORT, D("0.01"))])
def test_break_even_stop_is_the_tightest_safe_tick(direction, tick_step):
    v = trade(direction)
    plan = net_break_even_remainder_stop(**v)
    assert plan.decision == STOP_NET_BREAK_EVEN
    assert net_at(v, plan.stop_price) >= 0 and plan.worst_case_net_pnl_usdt == net_at(v, plan.stop_price)
    assert net_at(v, plan.stop_price + tick_step) < 0  # one tick looser loses money
    assert plan.stop_price % v["tick_size"] == 0
    if direction == CAMPAIGN_LONG:
        assert plan.stop_price == D("96.94")


@pytest.mark.parametrize("direction", [CAMPAIGN_LONG, CAMPAIGN_SHORT])
def test_costs_move_the_stop_toward_profit(direction):
    cheap = net_break_even_remainder_stop(**trade(direction, funding_usdt=D("0")))
    costly = net_break_even_remainder_stop(**trade(direction, funding_usdt=D("1")))
    if direction == CAMPAIGN_LONG:
        assert costly.stop_price > cheap.stop_price
    else:
        assert costly.stop_price < cheap.stop_price


@pytest.mark.parametrize("overrides,reason", [
    ({"partial_take_confirmed": False}, "partial_take_not_confirmed"),
    ({"partial_take_confirmed": None}, "partial_take_not_confirmed"),
    ({"protection_preserved": False}, "protection_not_preserved"),
    ({"current_stop_price": None}, "protection_not_preserved"),
    ({"mark_price": D("96.90")}, "break_even_not_placeable_vs_mark"),
    ({"current_stop_price": D("97")}, "current_stop_already_tighter"),
])
def test_current_protection_is_kept_whenever_the_move_is_not_safe(overrides, reason):
    plan = net_break_even_remainder_stop(**trade(CAMPAIGN_LONG, **overrides))
    assert (plan.decision, plan.reason) == (STOP_KEEP_CURRENT, reason)


def test_short_not_placeable_above_mark_mirrors():
    plan = net_break_even_remainder_stop(**trade(CAMPAIGN_SHORT, mark_price=D("104")))
    assert (plan.decision, plan.reason) == (STOP_KEEP_CURRENT, "break_even_not_placeable_vs_mark")


@pytest.mark.parametrize("overrides", [
    {"entry_qty": 4.0},                      # float, not Decimal evidence
    {"partial_qty": D("4")},                 # no remainder
    {"remainder_exit_fee_rate": D("1")},
    {"slippage_price": D("-0.01")},
    {"tick_size": D("0")},
    {"funding_usdt": D("NaN")},
    {"campaign_direction": "FLAT"},
])
def test_untrusted_trade_evidence_fails_closed(overrides):
    with pytest.raises(RetestCampaignError):
        net_break_even_remainder_stop(**trade(CAMPAIGN_LONG, **overrides))
