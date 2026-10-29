"""Reentry diary uses existing robot trade statistical facts, not a second ledger."""
from dataclasses import replace
from decimal import Decimal

import pytest

from terminal.diary.reentry_attempts import (
    ReentryAttemptLink, ReentryDiaryEvidenceError, project_reentry_campaigns,
)
from terminal.statistics.models import RobotStatisticsTrade


def trade(index=1, *, pattern="IKIGAI_BOX", exit_reason="STOP", fees="0.2"):
    entry = 2000 + (index - 1) * 2000
    return RobotStatisticsTrade(
        trade_id=f"trade-{index}", trading_account_id="PAPER",
        candidate_id=f"candidate-{index}", symbol="LABUSDT", direction="LONG",
        pattern=pattern, source_timeframe="1",
        signal_time_ms=entry - 200, entry_time_ms=entry, entry_path="LIMIT",
        actual_wv=Decimal("1"), average_entry=Decimal("100"),
        entry_quantity=Decimal("1"), entry_position_version=index,
        stop_price=Decimal("99"), take_price=Decimal("102"),
        exit_time_ms=entry + 700, exit_price=Decimal("99"),
        exit_reason=exit_reason, realized_pnl_usdt=Decimal("-1"),
        realized_pnl_pct=Decimal("-1"),
        fees_costs_usdt=Decimal(fees) if fees is not None else None,
    )


def link(index, campaign_id="thesis-1"):
    return ReentryAttemptLink(campaign_id, index, f"trade-{index}", f"candidate-{index}")


def test_diary_aggregates_new_patterns_under_same_campaign_with_costs():
    trades = (trade(1), trade(2, pattern="MIRROR"),
              trade(3, pattern="L-shape", exit_reason="TAKE"))
    entries = project_reentry_campaigns(trades, (link(3), link(1), link(2)))
    assert len(entries) == 1
    result = entries[0]
    assert [a.pattern for a in result.attempts] == ["IKIGAI_BOX", "MIRROR", "L-shape"]
    assert [a.attempt_index for a in result.attempts] == [1, 2, 3]
    assert result.stop_exits == 2
    assert result.gross_pnl_usdt == Decimal("-3")
    assert result.known_cost_net_pnl_usdt == Decimal("-3.6")
    assert result.cost_complete


def test_missing_cost_not_silently_zero_in_diary():
    result = project_reentry_campaigns(
        (trade(1), trade(2, pattern="DOUBLE_BOTTOM", fees=None)),
        (link(1), link(2)),
    )[0]
    assert result.gross_pnl_usdt == Decimal("-2")
    assert not result.cost_complete
    assert result.known_cost_net_pnl_usdt is None
    assert result.attempts[1].known_cost_net_pnl_usdt is None


def test_no_trade_link_guessing_by_symbol_or_pattern():
    with pytest.raises(ReentryDiaryEvidenceError, match="not a completed"):
        project_reentry_campaigns((trade(1),), (link(1), link(2)))


def test_duplicate_trade_or_candidate_is_rejected():
    with pytest.raises(ReentryDiaryEvidenceError, match="multiple attempts"):
        project_reentry_campaigns((trade(1),), (link(1), link(1, "different")))
    duplicate_candidate = replace(trade(2), candidate_id="candidate-1")
    with pytest.raises(ReentryDiaryEvidenceError, match="candidate attributed"):
        project_reentry_campaigns((trade(1), duplicate_candidate),
                                  (link(1), link(2)))


def test_fourth_attempt_cannot_be_hidden_in_statistics():
    with pytest.raises(ReentryDiaryEvidenceError, match="invalid attempt linkage"):
        project_reentry_campaigns((trade(1),), (ReentryAttemptLink(
            "thesis-1", 4, "trade-1", "candidate-1",
        ),))


def test_missing_first_attempt_or_gap_fails_closed():
    with pytest.raises(ReentryDiaryEvidenceError, match="not contiguous"):
        project_reentry_campaigns((trade(2),), (link(2),))
    with pytest.raises(ReentryDiaryEvidenceError, match="not contiguous"):
        project_reentry_campaigns((trade(1), trade(3)), (link(1), link(3)))


def test_new_attempt_only_after_observed_stop_not_take():
    with pytest.raises(ReentryDiaryEvidenceError, match="non-STOP"):
        project_reentry_campaigns((trade(1, exit_reason="TAKE"), trade(2)),
                                  (link(1), link(2)))


def test_new_attempt_cannot_reuse_pre_stop_signal():
    t2 = replace(trade(2), signal_time_ms=trade(1).exit_time_ms)
    with pytest.raises(ReentryDiaryEvidenceError, match="not new"):
        project_reentry_campaigns((trade(1), t2), (link(1), link(2)))


def test_new_attempt_cannot_overlap_old_position():
    t2 = replace(trade(2), entry_time_ms=trade(1).exit_time_ms)
    with pytest.raises(ReentryDiaryEvidenceError, match="overlapping"):
        project_reentry_campaigns((trade(1), t2), (link(1), link(2)))


@pytest.mark.parametrize("mutate", [
    {"symbol": "NEWUSDT"}, {"direction": "SHORT"},
    {"trading_account_id": "OTHER"},
])
def test_no_cross_account_symbol_or_direction_retries(mutate):
    with pytest.raises(ReentryDiaryEvidenceError, match="cross-account"):
        project_reentry_campaigns((trade(1), replace(trade(2), **mutate)),
                                  (link(1), link(2)))


def test_trade_and_candidate_link_must_match_existing_statistical_provenance():
    with pytest.raises(ReentryDiaryEvidenceError, match="candidate link differs"):
        project_reentry_campaigns((trade(1),), (ReentryAttemptLink(
            "thesis-1", 1, "trade-1", "another-candidate",
        ),))


def test_invalid_fees_and_gross_are_rejected():
    with pytest.raises(ReentryDiaryEvidenceError, match="invalid cost"):
        project_reentry_campaigns((replace(trade(1), fees_costs_usdt=Decimal("NaN")),),
                                  (link(1),))
    with pytest.raises(ReentryDiaryEvidenceError, match="invalid completed"):
        project_reentry_campaigns((replace(trade(1),
                                           realized_pnl_usdt=Decimal("Infinity")),),
                                  (link(1),))


def test_multiple_campaigns_are_distinct_and_deterministically_ordered():
    a = trade(1)
    b = replace(trade(2), symbol="BTCUSDT")
    result = project_reentry_campaigns(
        (b, a), (link(1, "b"), link(2, "a")),
    )
    assert [item.campaign_id for item in result] == ["a", "b"]
    assert [item.symbol for item in result] == ["BTCUSDT", "LABUSDT"]
