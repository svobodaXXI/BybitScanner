import pytest

from app.application.statistics.metric_registry import (
    DEFAULT_STATISTICS_METRIC_REGISTRY,
    StatisticsLayout,
    StatisticsMetricRegistry,
    StatisticMetricDefinition,
)


def test_initial_metric_ids_are_stable_and_unique():
    ids = [item.metric_id for item in DEFAULT_STATISTICS_METRIC_REGISTRY]
    assert ids == ["net_pnl", "cumulative_pnl", "profit_factor", "expectancy", "winrate", "avg_win", "avg_loss", "payoff_ratio", "trade_count", "max_drawdown", "avg_realized_r", "avg_planned_rr", "best_trade", "worst_trade", "max_loss_streak"]
    assert len(ids) == len(set(ids))


def test_layout_ignores_unknown_ids_but_rejects_invalid_home_pins():
    layout = StatisticsLayout(overview_metric_ids=("future_metric", "net_pnl"), home_metric_ids=("future_metric", "cumulative_pnl"))
    normalized = layout.normalized()
    assert normalized.overview_metric_ids == ("net_pnl",)
    assert normalized.home_metric_ids == ("cumulative_pnl",)
    with pytest.raises(ValueError, match="Home pins"):
        StatisticsLayout(home_metric_ids=("avg_win",)).normalized()


def test_registry_rejects_duplicate_ids():
    item = StatisticMetricDefinition("x", "X", "test", "x", "NUMBER", True, False)
    with pytest.raises(ValueError, match="unique"):
        StatisticsMetricRegistry((item, item))
