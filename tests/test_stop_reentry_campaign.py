"""STOP retry: cross-pattern logical setup + STOP proof + risk + no exposure."""
from dataclasses import replace
from decimal import Decimal

from terminal.application.stop_reentry_campaign import Attempt, Campaign, propose_stop_retry
from terminal.application.stop_reentry_setup import LogicalSetup


def campaign(*, attempts=None, budget="10"):
    if attempts is None:
        attempts = (Attempt("box-first", "stop-exec-1", Decimal("3")),)
    return Campaign("box-idea-1", "LABUSDT", "LONG", Decimal(budget), attempts)


def retry(c=None, *, setup_overrides=None, **overrides):
    source = c if c is not None else campaign()
    candidate_id = overrides.get("candidate_id", "mirror-confirmation-2")
    direction = overrides.get("direction", "LONG")
    setup = LogicalSetup(
        signal_id=candidate_id, previous_signal_id=source.attempts[-1].candidate_id,
        family="MIRROR", direction=direction, campaign_direction="LONG",
        last_stop_closed_at_ms=1000, formation_closed_at_ms=1100,
        confirmation_closed_at_ms=1200, closed_candle_proven=True,
        owning_strategy_entry_ready=True, same_frozen_thesis=True,
    )
    if setup_overrides:
        setup = replace(setup, **setup_overrides)
    args = dict(
        candidate_id=candidate_id, symbol="LABUSDT", direction=direction,
        setup=setup, prior_stop_execution_id="stop-exec-1",
        stop_proven_in_ledger=True, no_open_or_pending=True, robot_ready=True,
        new_worst_case_loss_usdt=Decimal("4"),
    )
    args.update(overrides)
    return propose_stop_retry(source, **args)


def test_different_pattern_can_confirm_same_idea_without_second_engine():
    result = retry()
    assert result.outcome == "ALLOW"
    assert len(result.campaign.attempts) == 2
    assert result.campaign.attempts[-1].candidate_id == "mirror-confirmation-2"
    assert result.campaign.attempts[0].candidate_id == "box-first"


def test_second_retry_allowed_fourth_entry_blocked():
    two = campaign(attempts=(
        Attempt("box-first", "stop-exec-1", Decimal("3")),
        Attempt("mirror-second", "stop-exec-2", Decimal("2")),
    ))
    second_retry = retry(two, candidate_id="wedge-third",
                         prior_stop_execution_id="stop-exec-2",
                         setup_overrides={"family": "Falling Wedge"})
    assert second_retry.outcome == "ALLOW"
    assert retry(second_retry.campaign, candidate_id="fourth",
                 prior_stop_execution_id="stop-exec-3").reason == "retry_limit"


def test_duplicate_candidate_never_reserves_again():
    result = retry(candidate_id="box-first")
    assert result.outcome == "DUPLICATE"
    assert result.campaign == campaign()


def test_risk_never_resets_between_stop_attempts():
    assert retry(new_worst_case_loss_usdt=Decimal("8")).reason == "cumulative_risk_exceeded"
    assert retry(new_worst_case_loss_usdt=Decimal("7")).outcome == "ALLOW"


def test_stop_must_be_reconciled_durable_execution():
    for stop in (None, "", "another-stop"):
        assert retry(prior_stop_execution_id=stop).outcome == "WAIT"
    for proof in (False, None, "true"):
        assert retry(stop_proven_in_ledger=proof).outcome == "WAIT"


def test_requires_no_exposure_and_ready_robot():
    for proof in (False, None, "true"):
        assert retry(no_open_or_pending=proof).outcome == "WAIT"
        assert retry(robot_ready=proof).outcome == "WAIT"


def test_changed_direction_or_symbol_is_not_retry():
    assert retry(direction="SHORT").outcome == "DENY"
    assert retry(symbol="OTHERUSDT").outcome == "DENY"


def test_requires_new_proven_post_stop_setup():
    assert retry(setup_overrides={"owning_strategy_entry_ready": False}).outcome == "WAIT"
    assert retry(setup_overrides={"same_frozen_thesis": False}).outcome == "DENY"
    assert retry(setup_overrides={"confirmation_closed_at_ms": 999}).outcome == "WAIT"
    assert retry(setup_overrides={"signal_id": "unrelated-signal"}).outcome == "WAIT"
    assert retry(setup=None).outcome == "WAIT"


def test_double_bottom_lineage_works_only_above_confirmed_neckline():
    qualified = retry(setup_overrides={
        "family": "DOUBLE_BOTTOM",
        "neckline": Decimal("100"), "confirmation_close": Decimal("100.1"),
    })
    assert qualified.outcome == "ALLOW"
    blocked = retry(setup_overrides={
        "family": "DOUBLE_BOTTOM",
        "neckline": Decimal("100"), "confirmation_close": Decimal("99.9"),
    })
    assert blocked.outcome == "WAIT"


def test_missing_or_invalid_budget_and_costs_fail_closed():
    for amount in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), None):
        assert retry(new_worst_case_loss_usdt=amount).outcome == "WAIT"
    assert retry(campaign(budget="0")).outcome == "WAIT"
    bad = campaign(attempts=(replace(campaign().attempts[0],
        realized_loss_cost_usdt=Decimal("NaN")),))
    assert retry(bad).outcome == "WAIT"
