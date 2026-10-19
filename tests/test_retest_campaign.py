import pytest

from geometry.naked_retest import (
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_LEVEL_INVALIDATED,
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
    STOP_FEE_INCLUSIVE_BREAK_EVEN,
    STOP_KEEP_CURRENT,
    RetestCampaignError,
    campaign_exit_intent,
    entry_gate,
    open_campaign_budget,
    remainder_stop_policy,
)


# Arbitrary test amounts; they are not risk policy.
def gate(budget, phase=PHASE_CAMPAIGN_ACTIVE, realized=0.0, live=0.0, new=1.0, reward=10.0):
    return entry_gate(budget, campaign_phase=phase, realized_loss_costs_usdt=realized,
                      live_pending_worst_case_usdt=live, new_attempt_worst_case_usdt=new,
                      remaining_net_reward_usdt=reward)


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


def test_negative_loss_amounts_cannot_net_profits_into_budget():
    with pytest.raises(RetestCampaignError):
        gate(open_campaign_budget(5.0), realized=-1.0)


@pytest.mark.parametrize("phase", [PHASE_WAITING_BREAKOUT, PHASE_RETEST_PROVEN,
                                   PHASE_RETEST_UNPROVEN, PHASE_LEVEL_INVALIDATED])
def test_no_attempts_outside_an_active_campaign(phase):
    # Covers overshoot after the retest and any automatic reversal (rules 7, 8).
    assert gate(open_campaign_budget(5.0), phase=phase).decision == DECISION_DENY


@pytest.mark.parametrize("r0", [0, -1, None, float("inf"), True])
def test_r0_must_be_positive_and_finite(r0):
    with pytest.raises(RetestCampaignError):
        open_campaign_budget(r0)


def test_partial_take_split_and_break_even_requires_protection():
    assert PARTIAL_TAKE_FRACTION + RETEST_REMAINDER_FRACTION == 1.0
    assert remainder_stop_policy(partial_take_confirmed=True, protection_preserved=True) == \
        STOP_FEE_INCLUSIVE_BREAK_EVEN
    for confirmed, preserved in [(True, False), (False, True), (True, None), ("yes", True)]:
        assert remainder_stop_policy(partial_take_confirmed=confirmed,
                                     protection_preserved=preserved) == STOP_KEEP_CURRENT


def test_only_a_proven_retest_closes_the_remainder():
    assert campaign_exit_intent(PHASE_RETEST_PROVEN) == EXIT_CLOSE_REMAINDER
    for phase in (PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_UNPROVEN, PHASE_LEVEL_INVALIDATED):
        assert campaign_exit_intent(phase) is None
