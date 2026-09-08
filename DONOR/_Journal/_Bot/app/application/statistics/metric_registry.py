"""Stable statistics metric catalog and user layout validation."""

from dataclasses import dataclass
from enum import StrEnum


class MetricFormat(StrEnum):
    MONEY = "MONEY"
    NUMBER = "NUMBER"
    PERCENT = "PERCENT"
    RATIO = "RATIO"
    COUNT = "COUNT"


@dataclass(frozen=True, slots=True)
class StatisticMetricDefinition:
    metric_id: str
    display_name: str
    category: str
    description: str
    format: MetricFormat | str
    supports_overview: bool
    supports_home: bool
    default_visualization: str | None = None
    coverage_metric: str | None = None

    def __post_init__(self):
        if not self.metric_id or not self.metric_id.strip():
            raise ValueError("metric_id must be a non-empty string")
        object.__setattr__(self, "format", MetricFormat(self.format))
        if type(self.supports_overview) is not bool or type(self.supports_home) is not bool:
            raise TypeError("metric capabilities must be bool")


class StatisticsMetricRegistry:
    def __init__(self, definitions=()):
        items = tuple(definitions)
        if any(not isinstance(item, StatisticMetricDefinition) for item in items):
            raise TypeError("definitions must contain StatisticMetricDefinition values")
        if len({item.metric_id for item in items}) != len(items):
            raise ValueError("metric_id must be unique")
        self._definitions = items
        self._by_id = {item.metric_id: item for item in items}

    def get(self, metric_id: str):
        return self._by_id.get(metric_id)

    def __iter__(self):
        return iter(self._definitions)

    def __len__(self):
        return len(self._definitions)

    def list(self, *, overview_only=False, home_only=False):
        return tuple(item for item in self._definitions if (not overview_only or item.supports_overview) and (not home_only or item.supports_home))

    def normalize_ids(self, ids, *, home=False):
        """Drop unknown/inactive capabilities and duplicate IDs safely."""
        result = []
        for metric_id in ids or ():
            definition = self.get(metric_id)
            if definition is None or (home and not definition.supports_home) or (not home and not definition.supports_overview):
                continue
            if metric_id not in result:
                result.append(metric_id)
        return tuple(result)


INITIAL_METRIC_DEFINITIONS = (
    StatisticMetricDefinition("net_pnl", "Net PnL", "RESULT", "Итоговый результат после комиссий и расходов", MetricFormat.MONEY, True, True),
    StatisticMetricDefinition("cumulative_pnl", "Cumulative PnL", "RESULT", "Накопленный результат по закрытым готовым сделкам", MetricFormat.MONEY, True, True, "SERIES"),
    StatisticMetricDefinition("profit_factor", "Profit Factor", "RESULT", "Отношение суммы прибыльных сделок к убыточным", MetricFormat.RATIO, True, True),
    StatisticMetricDefinition("expectancy", "Expectancy", "RESULT", "Средний результат на сделку", MetricFormat.MONEY, True, True),
    StatisticMetricDefinition("winrate", "Winrate", "RESULT", "Доля прибыльных сделок без учета безубыточных", MetricFormat.PERCENT, True, True),
    StatisticMetricDefinition("avg_win", "Average Win", "RESULT", "Средняя прибыльная сделка", MetricFormat.MONEY, True, False),
    StatisticMetricDefinition("avg_loss", "Average Loss", "RESULT", "Средняя убыточная сделка", MetricFormat.MONEY, True, False),
    StatisticMetricDefinition("payoff_ratio", "Payoff Ratio", "RESULT", "Средняя прибыль к средней потере", MetricFormat.RATIO, True, False),
    StatisticMetricDefinition("trade_count", "Trade Count", "ACTIVITY", "Количество готовых сделок", MetricFormat.COUNT, True, True),
    StatisticMetricDefinition("max_drawdown", "Max Drawdown", "RISK", "Максимальная просадка кривой результата", MetricFormat.MONEY, True, True),
    StatisticMetricDefinition("avg_realized_r", "Average Realized R", "RISK", "Средний реализованный R", MetricFormat.NUMBER, True, False, coverage_metric="REALIZED_R"),
    StatisticMetricDefinition("avg_planned_rr", "Average Planned R:R", "RISK", "Среднее плановое соотношение риска и прибыли", MetricFormat.RATIO, True, False),
    StatisticMetricDefinition("best_trade", "Best Trade", "RESULT", "Лучшая готовая сделка", MetricFormat.MONEY, True, False),
    StatisticMetricDefinition("worst_trade", "Worst Trade", "RESULT", "Худшая готовая сделка", MetricFormat.MONEY, True, False),
    StatisticMetricDefinition("max_loss_streak", "Max Loss Streak", "RISK", "Максимальная серия убыточных сделок", MetricFormat.COUNT, True, False),
)

DEFAULT_STATISTICS_METRIC_REGISTRY = StatisticsMetricRegistry(INITIAL_METRIC_DEFINITIONS)


class HomeMetricPeriod(StrEnum):
    DAYS_7 = "7d"
    DAYS_30 = "30d"
    DAYS_90 = "90d"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class StatisticsLayout:
    overview_metric_ids: tuple[str, ...] = ("net_pnl", "trade_count", "winrate", "profit_factor")
    home_metric_ids: tuple[str, ...] = ("cumulative_pnl", "profit_factor", "expectancy", "max_drawdown")
    home_metric_period: HomeMetricPeriod | str = HomeMetricPeriod.ALL

    def __post_init__(self):
        object.__setattr__(self, "overview_metric_ids", tuple(self.overview_metric_ids))
        object.__setattr__(self, "home_metric_ids", tuple(self.home_metric_ids))
        object.__setattr__(self, "home_metric_period", HomeMetricPeriod(self.home_metric_period))
        if len(self.home_metric_ids) > 6:
            raise ValueError("home_metric_ids cannot contain more than 6 metrics")

    def normalized(self, registry=DEFAULT_STATISTICS_METRIC_REGISTRY):
        unsupported_home = [metric_id for metric_id in self.home_metric_ids if registry.get(metric_id) is not None and not registry.get(metric_id).supports_home]
        if unsupported_home:
            raise ValueError(f"metrics do not support Home pins: {', '.join(unsupported_home)}")
        return StatisticsLayout(
            registry.normalize_ids(self.overview_metric_ids),
            registry.normalize_ids(self.home_metric_ids, home=True),
            self.home_metric_period,
        )


def metric_value(definition: StatisticMetricDefinition, summary, *, cumulative=None):
    """Map a stable ID to an engine result without putting formulas in the UI."""
    values = {
        "net_pnl": summary.net_pnl, "profit_factor": summary.profit_factor,
        "expectancy": summary.expectancy, "winrate": summary.win_rate,
        "avg_win": summary.average_win, "avg_loss": summary.average_loss,
        "trade_count": summary.trade_count, "best_trade": summary.largest_win,
        "worst_trade": summary.largest_loss,
    }
    if definition.metric_id == "cumulative_pnl":
        return None if not cumulative else cumulative[-1].cumulative_pnl
    if definition.metric_id == "payoff_ratio":
        if summary.average_win is None or summary.average_loss in (None, 0): return None
        return summary.average_win / abs(summary.average_loss)
    if definition.metric_id == "max_drawdown":
        if not cumulative: return None
        peak = cumulative[0].cumulative_pnl
        drawdown = 0
        for point in cumulative:
            peak = max(peak, point.cumulative_pnl)
            drawdown = min(drawdown, point.cumulative_pnl - peak)
        return drawdown
    return values.get(definition.metric_id)
