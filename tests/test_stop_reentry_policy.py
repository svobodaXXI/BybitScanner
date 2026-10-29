"""Issue #592: STOP reentry policy must fail closed before Robot Admission."""

from dataclasses import replace

from terminal.application.stop_reentry_policy import (
    ALLOW, DENY, WAIT, ReentryEvidence, evaluate_stop_reentry,
)


def eligible(**overrides):
    evidence = ReentryEvidence(
        attempts_started=1,
        previous_exit="STOP",
        stop_closed=True,
        fresh_confirmed_signal=True,
        same_campaign_and_direction=True,
        campaign_valid=True,
        no_open_or_pending=True,
        robot_ready=True,
        risk_budget_ok=True,
    )
    return replace(evidence, **overrides)


def test_first_and_second_stop_retry_only():
    assert evaluate_stop_reentry(eligible(attempts_started=1)).outcome == ALLOW
    assert evaluate_stop_reentry(eligible(attempts_started=2)).outcome == ALLOW
    assert evaluate_stop_reentry(eligible(attempts_started=3)).outcome == DENY
    assert evaluate_stop_reentry(eligible(attempts_started=4)).outcome == DENY


def test_unknown_attempt_history_fails_closed():
    for count in (0, -1, True):
        assert evaluate_stop_reentry(eligible(attempts_started=count)).outcome == WAIT


def test_only_verified_stop_qualifies():
    for exit_reason in (None, "OPEN", "CANCELLED", "UNKNOWN"):
        assert evaluate_stop_reentry(eligible(previous_exit=exit_reason)).outcome == WAIT
    assert evaluate_stop_reentry(eligible(stop_closed=False)).outcome == WAIT
    assert evaluate_stop_reentry(eligible(previous_exit="TAKE")).outcome == DENY
    assert evaluate_stop_reentry(eligible(previous_exit="INVALIDATED")).outcome == DENY


def test_no_unconfirmed_or_conflicting_reentry():
    for field in (
        "fresh_confirmed_signal",
        "same_campaign_and_direction",
        "no_open_or_pending",
        "robot_ready",
        "risk_budget_ok",
    ):
        assert evaluate_stop_reentry(eligible(**{field: False})).outcome == WAIT
    assert evaluate_stop_reentry(eligible(campaign_valid=False)).outcome == DENY


def test_pure_gate_does_not_grant_order_authority():
    decision = evaluate_stop_reentry(eligible())
    assert (decision.outcome, decision.reason) == (
        ALLOW, "eligible_for_canonical_admission"
    )
