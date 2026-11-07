"""Focused PAPER_TEST MIRROR budget policy tests: no runtime or DB mutations."""

from decimal import Decimal

from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE
from mirror_retest_robot import (
    ATTACHED,
    BLOCKED,
    DEFERRED,
    MirrorRobotPolicy,
    _campaign_budget,
)
from retest_account_risk import AccountRiskLimit, DECISION_OK


def _policy(*, paper_test):
    return MirrorRobotPolicy(
        candles=None,
        account_risk_limit_usdt=lambda _: AccountRiskLimit(DECISION_OK, "test", Decimal("100")),
        quantity_step=lambda _: Decimal("1"),
        paper_test=paper_test,
    )


def test_paper_test_does_not_block_entry_on_campaign_loss_cap():
    campaign = {"state": {"phase": PHASE_CAMPAIGN_ACTIVE, "data_blocked": False}}
    # Existing financial gate rejects this: 25 exceeds 0.5 * 20 potential.
    normal = _campaign_budget(
        _policy(paper_test=False), campaign, (),
        worst_case=Decimal("25"), potential=Decimal("20"), now_ms=1,
    )
    assert normal["decision"] == BLOCKED
    assert normal["reason"] == "campaign_gate_deny:campaign_budget_exceeded"
    testing = _campaign_budget(
        _policy(paper_test=True), campaign, (),
        worst_case=Decimal("25"), potential=Decimal("20"), now_ms=1,
    )
    assert testing["decision"] == ATTACHED
    assert testing["reason"] == "paper_test_financial_policy"
    assert testing["gate"].budget.r0_usdt > 0


def test_paper_test_still_requires_active_reliable_campaign():
    policy = _policy(paper_test=True)
    inactive = _campaign_budget(
        policy, {"state": {"phase": "RETEST_PROVEN"}}, (),
        worst_case=Decimal("1"), potential=Decimal("20"), now_ms=1,
    )
    assert inactive["decision"] == BLOCKED
    assert inactive["reason"] == "campaign_not_active"
    unreliable = _campaign_budget(
        policy, {"state": {"phase": PHASE_CAMPAIGN_ACTIVE, "data_blocked": True}}, (),
        worst_case=Decimal("1"), potential=Decimal("20"), now_ms=1,
    )
    assert unreliable["decision"] == DEFERRED
    assert unreliable["reason"] == "campaign_data_unreliable"
