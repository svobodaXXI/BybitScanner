from datetime import datetime, timezone

from app.application.statistics.metric_registry import HomeMetricPeriod, StatisticsLayout
from app.infrastructure.persistence.models.statistics_layout import StatisticsLayoutORM


def statistics_layout_from_orm(model):
    return StatisticsLayout(tuple(model.overview_metric_ids or ()), tuple(model.home_metric_ids or ()), model.home_metric_period)


def statistics_layout_to_orm(account_id, layout):
    return StatisticsLayoutORM(account_id=account_id.value, overview_metric_ids=list(layout.overview_metric_ids), home_metric_ids=list(layout.home_metric_ids), home_metric_period=layout.home_metric_period.value, updated_at=datetime.now(timezone.utc))
