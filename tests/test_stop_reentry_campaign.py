"""STOP retry campaign transition: no network or PAPER runtime mutation."""
from dataclasses import replace
from decimal import Decimal

from terminal.application.stop_reentry_campaign import (
    Attempt, Campaign, propose_stop_retry,
)


def campaign(*, attempts=None, budget="10"):
    if attempts is None:
        attempts = (
            Attempt("box-first", "stop-exec-1", Decimal("3")),
        )
    return Campaign("box-idea-1", "LABUSDT", "LONG", Decimal(budget), attempts)


def retry(c=None, **overrides):
    args = dict(
        candidate_id="mirror-confirmation-2",
        symbol="LABUSDT",
        direction="LONG",
        confirmed_signal=True,
        same_frozen_thesis=True,
        prior_stop_execution_id="stop-exec-1",
        new_worst_case_loss_usdt=Decimal("4"),
    )
    args.update(overrides)
    return propose_stop_retry(c or campaign(), **args)


def test_different_pattern_can_confirm_same_idea_without_new_execution_path():
    result = retry()
    assert result.outcome == "ALLOW"
    assert len(result.campaign.attempts) == 2
    assert result.campaign.attempts[-1].candidate_id == "mirror-confirmation-2"
    assert result.campaign.attempts[0].candidate_id == "box-first"


def test_second_retry_allowed_third_retry_blocked():
    two = campaign(attempts=(
        Attempt("box-first", "stop-exec-1", Decimal("3")),
        Attempt("mirror-second", "stop-exec-2", Decimal("2")),
    ))
    second_retry = retry(
        two, candidate_id="wedge-third",
        prior_stop_execution_id="stop-exec-2",
    )
    assert second_retry.outcome == "ALLOW"
    assert retry(
        second_retry.campaign, candidate_id="fourth",
        prior_stop_execution_id="stop-exec-3",
    ).reason == "retry_limit"


def test_duplicate_candidate_never_reserves_again():
    result = retry(candidate_id="box-first")
    assert result.outcome == "DUPLICATE"
    assert result.campaign == campaign()


def test_risk_never_resets_between_stop_attempts():
    assert retry(new_worst_case_loss_usdt=Decimal("8")).reason == "cumulative_risk_exceeded"
    assert retry(new_worst_case_loss_usdt=Decimal("7")).outcome == "ALLOW"


def test_unproven_or_wrong_stop_blocks():
    for stop in (None, "", "another-stop"):
        assert retry(prior_stop_execution_id=stop).outcome == "WAIT"


def test_changed_direction_or_symbol_is_not_retry():
    assert retry(direction="SHORT").outcome == "DENY"
    assert retry(symbol="OTHERUSDT").outcome == "DENY"


def test_requires_valid_fresh_confirmed_signal():
    assert retry(confirmed_signal=False).outcome == "WAIT"
    assert retry(same_frozen_thesis=False).outcome == "WAIT"


def test_missing_or_invalid_budget_and_costs_fail_closed():
    for amount in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), None):
        assert retry(new_worst_case_loss_usdt=amount).outcome == "WAIT"
    assert retry(campaign(budget="0")).outcome == "WAIT"
    bad = campaign(attempts=(replace(campaign().attempts[0], realized_loss_cost_usdt=Decimal("NaN")),))
    assert retry(bad).outcome == "WAIT"
