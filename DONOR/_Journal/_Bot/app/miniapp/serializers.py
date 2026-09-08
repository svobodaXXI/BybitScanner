"""Exact JSON-safe serializers for Mini App read models."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from app.application.dtos import CustomValueView, MiniAppTradePage, MiniAppTradeRow, TradeView
from app.application.attention import AttentionResult
from app.application.statistics import (
    DynamicFieldCoverage,
    GroupedPerformanceResult,
    PerformanceSummary,
    MetricCoverage,
    CumulativePnLPoint,
    StatisticMetricDefinition,
    StatisticsLayout,
    metric_value,
)
from app.core.statistics.ids import CustomFieldOptionId
from app.core.trades.readiness import evaluate_trade_readiness


def _decimal(value: Decimal | None):
    return None if value is None else str(value)


def serialize_summary(summary: PerformanceSummary) -> dict:
    return {
        "sample_size": summary.sample_size,
        "trade_count": summary.trade_count,
        "win_count": summary.win_count,
        "loss_count": summary.loss_count,
        "breakeven_count": summary.breakeven_count,
        "win_rate": _decimal(summary.win_rate),
        "gross_pnl": _decimal(summary.gross_pnl),
        "net_pnl": _decimal(summary.net_pnl),
        "total_fees": _decimal(summary.total_fees),
        "total_expenses": _decimal(summary.total_expenses),
        "average_net_pnl": _decimal(summary.average_net_pnl),
        "average_win": _decimal(summary.average_win),
        "average_loss": _decimal(summary.average_loss),
        "profit_factor": _decimal(summary.profit_factor),
        "expectancy": _decimal(summary.expectancy),
        "largest_win": _decimal(summary.largest_win),
        "largest_loss": _decimal(summary.largest_loss),
        "median_net_pnl": _decimal(summary.median_net_pnl),
        "currency": summary.currency,
        "ready_count": summary.ready_count,
        "excluded_incomplete_count": summary.excluded_incomplete_count,
        "open_count": summary.open_count,
    }


def serialize_grouped(result: GroupedPerformanceResult) -> dict:
    return {
        "group_by": result.group_by.value,
        "eligible_trade_count": result.eligible_trade_count,
        "known_value_count": result.known_value_count,
        "missing_value_count": result.missing_value_count,
        "coverage_rate": _decimal(result.coverage_rate),
        "ready_count": result.ready_count,
        "excluded_incomplete_count": result.excluded_incomplete_count,
        "open_count": result.open_count,
        "groups": [
            {"key": group.key, "label": group.label, **serialize_summary(group.summary)}
            for group in result.groups
        ],
    }


def serialize_coverage(result: DynamicFieldCoverage) -> dict:
    return {
        "field_id": str(result.field_id),
        "field_code": result.field_code,
        "eligible_trade_count": result.eligible_trade_count,
        "filled_count": result.filled_count,
        "missing_count": result.missing_count,
        "coverage_rate": _decimal(result.coverage_rate),
    }


def serialize_metric_coverage(result: MetricCoverage) -> dict:
    return {
        "metric": result.metric,
        "eligible_trade_count": result.eligible_trade_count,
        "calculated_count": result.calculated_count,
        "missing_count": result.missing_count,
        "coverage_rate": _decimal(result.coverage_rate),
    }


def serialize_metric_definition(item: StatisticMetricDefinition) -> dict:
    return {
        "metric_id": item.metric_id,
        "display_name": item.display_name,
        "category": item.category,
        "description": item.description,
        "format": item.format.value,
        "supports_overview": item.supports_overview,
        "supports_home": item.supports_home,
        "default_visualization": item.default_visualization,
        "coverage_metric": item.coverage_metric,
    }


def serialize_statistics_layout(layout: StatisticsLayout) -> dict:
    return {
        "overview_metric_ids": list(layout.overview_metric_ids),
        "home_metric_ids": list(layout.home_metric_ids),
        "home_metric_period": layout.home_metric_period.value,
    }


def serialize_cumulative_series(points: tuple[CumulativePnLPoint, ...]) -> list[dict]:
    return [{"trade_id": str(point.trade_id), "at": _datetime(point.at), "pnl": _decimal(point.pnl), "cumulative_pnl": _decimal(point.cumulative_pnl), "currency": point.currency} for point in points]


def serialize_statistics_overview(result, definitions) -> dict:
    series = result["series"]
    summary = result["summary"]
    layout = result["layout"]
    coverage = result.get("coverage", {})
    by_id = {item.metric_id: item for item in definitions}
    cards = []
    for metric_id in layout.overview_metric_ids:
        definition = by_id.get(metric_id)
        if definition is None:
            continue
        card = {"metric_id": metric_id, "display_name": definition.display_name, "format": definition.format.value, "value": _decimal(metric_value(definition, summary, cumulative=series)), "n": summary.trade_count}
        if metric_id in coverage:
            item = coverage[metric_id]
            card["coverage"] = {"eligible": item.eligible_trade_count, "calculated": item.calculated_count, "missing": item.missing_count, "rate": _decimal(item.coverage_rate)}
        cards.append(card)
    return {"layout": serialize_statistics_layout(layout), "cards": cards, "summary": serialize_summary(summary), "cumulative_pnl": serialize_cumulative_series(series)}


def serialize_automatic_factor(item, enabled: bool) -> dict:
    """Keep technical routing metadata out of the normal card fields."""
    return {
        "factor_id": item.factor_id,
        "name": item.display_name,
        "description": item.description,
        "applicability": item.applicability,
        "enabled": enabled,
        "status": "AVAILABLE" if item.active else "INACTIVE",
        "technical": {
            "category_id": item.category_id.value,
            "value_type": item.value_type.value,
            "unit": item.unit,
            "source_kind": item.source_kind.value,
            "capture_semantics": item.capture_semantics.value,
            "timeframe_window": item.timeframe_window,
            "timeframe": item.timeframe,
            "window": item.window,
            "calculation_version": item.calculation_version,
        },
    }


def serialize_trade_page(page: MiniAppTradePage) -> dict:
    return {
        "items": [serialize_trade_row(item) for item in page.items],
        "limit": page.limit,
        "offset": page.offset,
        "has_more": page.has_more,
    }


def serialize_trade_row(row: MiniAppTradeRow) -> dict:
    trade = serialize_trade(row.trade)
    trade["instrument"] = None if row.instrument is None else {
        "id": str(row.instrument.instrument_id),
        "symbol": row.instrument.symbol,
        "name": row.instrument.name,
        "exchange": row.instrument.exchange,
        "market": row.instrument.market,
    }
    return trade


def serialize_trade(trade: TradeView) -> dict:
    readiness = evaluate_trade_readiness(trade)
    return {
        "trade_id": str(trade.trade_id),
        "account_id": str(trade.account_id),
        "instrument_id": str(trade.instrument_id),
        "direction": trade.direction.value,
        "status": trade.status.value,
        "opened_at": _datetime(trade.opened_at),
        "closed_at": _datetime(trade.closed_at),
        "entry_price": _decimal(trade.entry_price.value),
        "exit_price": None if trade.exit_price is None else _decimal(trade.exit_price.value),
        "quantity": _decimal(trade.quantity.value),
        "fees": _decimal(trade.fees.amount),
        "currency": trade.fees.currency,
        "expenses": [
            {"amount": _decimal(expense.amount.amount), "currency": expense.amount.currency}
            for expense in trade.expenses
        ],
        "gross_pnl": None if trade.gross_pnl is None else _decimal(trade.gross_pnl.amount),
        "net_pnl": None if trade.net_pnl is None else _decimal(trade.net_pnl.amount),
        "data_status": readiness.status.value,
        "missing_reasons": list(readiness.missing),
    }


def serialize_custom_value(item: CustomValueView) -> dict:
    raw = item.value.value
    if isinstance(raw, CustomFieldOptionId):
        raw = str(raw)
    elif isinstance(raw, Decimal):
        raw = str(raw)
    return {
        "field_id": str(item.value.field_id),
        "definition_version": item.value.definition_version,
        "code": None if item.definition is None else str(item.definition.code),
        "label": None if item.definition is None else item.definition.name,
        "type": None if item.definition is None else item.definition.value_type.value,
        "source": item.value.source.value,
        "recorded_at": _datetime(item.value.recorded_at),
        "value": raw,
        "option_label": None if item.option is None else item.option.label,
    }


def serialize_trade_details(result) -> dict:
    readiness = result.readiness or evaluate_trade_readiness(result.trade)
    payload = {
        "trade": serialize_trade(result.trade),
        "custom_values": [serialize_custom_value(item) for item in result.custom_values],
    }
    payload["trade"]["data_status"] = readiness.status.value
    payload["trade"]["missing_reasons"] = list(readiness.missing)
    instrument = getattr(result, "instrument", None)
    payload["instrument"] = None if instrument is None else {
        "id": str(instrument.instrument_id),
        "symbol": instrument.symbol,
        "name": instrument.name,
        "exchange": instrument.exchange,
        "market": instrument.market,
    }
    return payload


def serialize_dynamic_field(definition) -> dict:
    return {
        "field_id": str(definition.id),
        "label": definition.name,
        "type": definition.value_type.value,
        "source": definition.source.value,
        "phase": definition.phase.value,
        "status": definition.status.value,
        "required": definition.required,
        "required_for_statistics": definition.required_for_statistics,
    }


def serialize_attention(result: AttentionResult) -> dict:
    return {
        "summary": {
            "total_attention": result.summary.total_attention,
            "open_count": result.summary.open_count,
            "incomplete_count": result.summary.incomplete_count,
        },
        "items": [
            {
                "trade_id": str(item.trade_id),
                "instrument": item.instrument_label or "Инструмент недоступен",
                "direction": item.trade.direction.value,
                "lifecycle_status": item.trade.status.value,
                "data_status": item.readiness.status.value,
                "opened_at": _datetime(item.trade.opened_at),
                "missing_reasons": list(item.readiness.missing),
            }
            for item in result.items
        ],
    }


def _datetime(value: datetime | None):
    return None if value is None else value.astimezone(timezone.utc).isoformat()
