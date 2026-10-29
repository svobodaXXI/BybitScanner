"""Closed-candle reentry setups: STOP -> new pattern, no second open trade."""
from dataclasses import replace
from decimal import Decimal

from terminal.application.stop_reentry_setup import (
    LogicalSetup, qualify_logical_reentry,
)


def base(**overrides):
    result = LogicalSetup(
        signal_id="l-shape-after-stop",
        previous_signal_id="engulfing-first",
        family="L-shape",
        direction="LONG",
        campaign_direction="LONG",
        last_stop_closed_at_ms=1_000,
        formation_closed_at_ms=1_100,
        confirmation_closed_at_ms=1_200,
        closed_candle_proven=True,
        owning_strategy_entry_ready=True,
        same_frozen_thesis=True,
    )
    return replace(result, **overrides)


def result(**overrides):
    return qualify_logical_reentry(base(**overrides))


def test_engulfing_stop_then_l_shape_continuation_qualifies():
    assert result().outcome == "ALLOW"


def test_engulfing_stop_then_double_bottom_neckline_confirmed_long():
    assert result(
        family="DOUBLE_BOTTOM",
        neckline=Decimal("100"),
        confirmation_close=Decimal("100.01"),
    ).outcome == "ALLOW"


def test_shadow_or_unclosed_double_bottom_never_enters():
    for close in ("99.9", "100", "99"):
        assert result(
            family="DOUBLE_BOTTOM", neckline=Decimal("100"),
            confirmation_close=Decimal(close),
        ).outcome == "WAIT"
    assert result(
        family="DOUBLE_BOTTOM", neckline=Decimal("100"),
        confirmation_close=Decimal("101"), closed_candle_proven=False,
    ).outcome == "WAIT"


def test_engulfing_stop_then_double_top_neckline_confirmed_short():
    assert result(
        family="DOUBLE_TOP",
        direction="SHORT", campaign_direction="SHORT",
        neckline=Decimal("100"), confirmation_close=Decimal("99.99"),
    ).outcome == "ALLOW"
    assert result(
        family="DOUBLE_TOP",
        direction="SHORT", campaign_direction="SHORT",
        neckline=Decimal("100"), confirmation_close=Decimal("100"),
    ).outcome == "WAIT"


def test_wrong_double_pattern_direction_denied():
    assert result(
        family="DOUBLE_BOTTOM",
        direction="SHORT", campaign_direction="SHORT",
        neckline=Decimal("100"), confirmation_close=Decimal("101"),
    ).outcome == "DENY"
    assert result(
        family="DOUBLE_TOP",
        direction="LONG", campaign_direction="LONG",
        neckline=Decimal("100"), confirmation_close=Decimal("99"),
    ).outcome == "DENY"


def test_mirror_box_wedge_use_own_strategy_confirmation():
    for family in ("MIRROR", "IKIGAI_BOX", "Rising Wedge", "Falling Wedge"):
        assert result(family=family).outcome == "ALLOW"
        assert result(family=family, owning_strategy_entry_ready=False).outcome == "WAIT"


def test_stop_is_not_a_signal_and_old_signal_is_not_reused():
    assert result(signal_id="engulfing-first").outcome == "WAIT"
    assert result(signal_id="").outcome == "WAIT"
    assert result(confirmation_closed_at_ms=1_000).outcome == "WAIT"
    assert result(formation_closed_at_ms=1_300).outcome == "WAIT"
    assert result(confirmation_closed_at_ms=999).outcome == "WAIT"


def test_forming_candle_and_nonboolean_evidence_fail_closed():
    assert result(closed_candle_proven="true").outcome == "WAIT"
    assert result(owning_strategy_entry_ready=1).outcome == "WAIT"
    assert result(same_frozen_thesis="true").outcome == "DENY"
    assert result(confirmation_closed_at_ms=True).outcome == "WAIT"


def test_invalidated_idea_or_direction_cannot_be_called_retry():
    assert result(same_frozen_thesis=False).outcome == "DENY"
    assert result(direction="SHORT").outcome == "DENY"


def test_unknown_pattern_or_neckline_does_not_create_new_detector():
    assert result(family="DOUBLE_TRIPLE_THING").outcome == "WAIT"
    for neck in (None, Decimal("NaN"), Decimal("-1")):
        assert result(
            family="DOUBLE_BOTTOM",
            neckline=neck, confirmation_close=Decimal("101"),
        ).outcome == "WAIT"
