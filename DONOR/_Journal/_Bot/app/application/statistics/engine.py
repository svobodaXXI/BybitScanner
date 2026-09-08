"""Read-only, UI-neutral Statistics Engine V1."""

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from app.core.statistics.custom_field_resolver import CustomFieldResolver
from app.core.statistics.enums import CustomFieldPhase, CustomFieldStatus, CustomFieldValueType
from app.core.statistics.ids import CustomFieldDefinitionId, CustomFieldOptionId
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.statistics.trade_custom_value import TradeCustomValue
from app.core.trades.enums import TradeStatus
from app.core.trades.readiness import TradeReadinessStatus, evaluate_trade_readiness
from app.core.trades.trade_id import TradeId

from .models import (
    DynamicFieldCoverage,
    DynamicFieldCoverageRequest,
    DynamicFieldMetadata,
    CumulativePnLPoint,
    MetricCoverage,
    GroupedPerformanceRequest,
    GroupedPerformanceResult,
    PerformanceSummary,
    StatisticsFilter,
    StatisticsGroup,
    StatisticsGroupBy,
    StatisticsTradeRecord,
)
from .query import TradeStatisticsQuery


ZERO = Decimal("0")


class StatisticsEngine:
    """Calculate facts from immutable read models; it has no write boundary."""

    def __init__(self, query: TradeStatisticsQuery, resolver: CustomFieldResolver | None = None) -> None:
        if not isinstance(query, TradeStatisticsQuery):
            raise TypeError("query must implement TradeStatisticsQuery")
        self._query = query
        self._resolver = resolver or CustomFieldResolver()

    async def get_performance_summary(self, filters: StatisticsFilter | None = None) -> PerformanceSummary:
        actual_filter = filters or StatisticsFilter()
        records = await self._records(actual_filter)
        ready, counts = await self._eligible_records(records)
        counts["open_count"] = await self._current_open_count(actual_filter, records)
        return _summarize(ready, **counts)

    async def _current_open_count(self, filters: StatisticsFilter, records) -> int:
        """Count current visible OPEN positions independently of period metrics."""
        counter = getattr(self._query, "count_current_open", None)
        if counter is not None:
            return int(await counter(account_id=filters.account_id, instrument_id=filters.instrument_id))
        # Small in-memory query doubles may not expose the optimized counter.
        # Their records still provide a safe fallback for tests and adapters.
        return sum(1 for record in records if record.status is TradeStatus.OPEN)

    async def get_grouped_performance(self, request: GroupedPerformanceRequest) -> GroupedPerformanceResult:
        if not isinstance(request, GroupedPerformanceRequest):
            raise TypeError("request must be GroupedPerformanceRequest")
        all_records = await self._records(request.filters)
        records, counts = await self._eligible_records(all_records)
        if request.group_by is not StatisticsGroupBy.DYNAMIC_FIELD:
            groups = self._static_groups(records, request.group_by)
            return GroupedPerformanceResult(
                group_by=request.group_by,
                groups=_sort_groups(groups, request.min_sample_size),
                eligible_trade_count=len(records),
                known_value_count=len(records),
                missing_value_count=0,
                coverage_rate=Decimal("1") if records else None,
                **counts,
            )

        metadata = await self._resolve_dynamic_field(request.field_id, request.field_code)
        eligible = tuple(record for record in records if self._field_applies(metadata, record))
        values = await self._query.list_custom_values(
            tuple(record.trade_id for record in eligible), metadata.definition.id
        )
        for value in values:
            value.validate_against(metadata.definition)
        by_trade = _values_by_trade(values, metadata.definition.id)
        known = tuple(record for record in eligible if record.trade_id in by_trade)
        missing = tuple(record for record in eligible if record.trade_id not in by_trade)
        groups = self._dynamic_groups(
            known,
            by_trade,
            metadata,
            include_missing=request.include_missing,
            missing=missing,
        )
        return GroupedPerformanceResult(
            group_by=request.group_by,
            groups=_sort_groups(groups, request.min_sample_size),
            eligible_trade_count=len(eligible),
            known_value_count=len(known),
            missing_value_count=len(missing),
            coverage_rate=(Decimal(len(known)) / Decimal(len(eligible))) if eligible else None,
            **counts,
        )

    async def get_dynamic_field_coverage(
        self,
        request: DynamicFieldCoverageRequest,
    ) -> DynamicFieldCoverage:
        if not isinstance(request, DynamicFieldCoverageRequest):
            raise TypeError("request must be DynamicFieldCoverageRequest")
        all_records = await self._records(request.filters)
        records, _ = await self._eligible_records(all_records)
        metadata = await self._resolve_dynamic_field(request.field_id, request.field_code)
        eligible = tuple(record for record in records if self._field_applies(metadata, record))
        values = await self._query.list_custom_values(
            tuple(record.trade_id for record in eligible), metadata.definition.id
        )
        for value in values:
            value.validate_against(metadata.definition)
        known = {value.trade_id for value in values}
        filled = sum(1 for record in eligible if record.trade_id in known)
        return DynamicFieldCoverage(
            field_id=metadata.definition.id,
            field_code=str(metadata.definition.code),
            eligible_trade_count=len(eligible),
            filled_count=filled,
            missing_count=len(eligible) - filled,
            coverage_rate=(Decimal(filled) / Decimal(len(eligible))) if eligible else None,
        )

    async def get_metric_coverage(self, metric: str, filters: StatisticsFilter | None = None) -> MetricCoverage:
        """Expose metric-specific availability without treating missing facts as zero."""
        if not isinstance(metric, str) or not metric.strip():
            raise ValueError("metric must not be empty")
        normalized = metric.strip().upper()
        if normalized != "REALIZED_R":
            raise ValueError(f"unsupported metric: {metric}")
        records = await self._records(filters or StatisticsFilter())
        ready, _ = await self._eligible_records(records)
        calculated = sum(
            1 for record in ready
            if record.entry_price is not None
            and record.stop_price is not None
            and record.exit_price is not None
            and record.risk is not None
            and record.risk.amount.amount != ZERO
        )
        eligible = len(ready)
        return MetricCoverage(normalized, eligible, calculated, eligible - calculated, Decimal(calculated) / Decimal(eligible) if eligible else None)

    async def get_cumulative_pnl(self, filters: StatisticsFilter | None = None) -> tuple[CumulativePnLPoint, ...]:
        """Return an ordered realized equity curve for CLOSED+READY trades."""
        records = await self._records(filters or StatisticsFilter())
        ready, _ = await self._eligible_records(records)
        realized = tuple(record for record in ready if record.net_pnl is not None)
        currencies = {record.net_pnl.currency for record in realized}
        if len(currencies) > 1:
            raise ValueError("statistics cannot aggregate mixed currencies")
        currency = next(iter(currencies), None)
        if currency is None:
            return ()
        ordered = sorted(realized, key=lambda item: (item.filter_time, str(item.trade_id)))
        cumulative = ZERO
        points = []
        for record in ordered:
            pnl = record.net_pnl.amount
            cumulative += pnl
            points.append(CumulativePnLPoint(record.trade_id, record.filter_time, pnl, cumulative, currency))
        return tuple(points)

    async def _records(self, filters: StatisticsFilter) -> tuple[StatisticsTradeRecord, ...]:
        if not isinstance(filters, StatisticsFilter):
            raise TypeError("filters must be StatisticsFilter")
        records = tuple(await self._query.list_trades(filters))
        seen: set[TradeId] = set()
        result = []
        for record in records:
            if not isinstance(record, StatisticsTradeRecord):
                raise TypeError("statistics query must return StatisticsTradeRecord values")
            if record.trade_id in seen:
                raise ValueError("statistics query returned duplicate trade IDs")
            seen.add(record.trade_id)
            if _matches(record, filters):
                result.append(record)
        return tuple(result)

    async def _eligible_records(self, records):
        """Return READY CLOSED records plus explicit lifecycle/quality counts."""
        required_metadata = await self._required_statistics_fields()
        values_by_field: dict[object, dict[TradeId, TradeCustomValue]] = {}
        applicable_by_field: dict[object, set[TradeId]] = {}
        for metadata in required_metadata:
            applicable = {
                record.trade_id for record in records if self._field_applies(metadata, record)
            }
            applicable_by_field[metadata.definition.id] = applicable
            values = await self._query.list_custom_values(tuple(applicable), metadata.definition.id)
            for value in values:
                value.validate_against(metadata.definition)
            values_by_field[metadata.definition.id] = _values_by_trade(values, metadata.definition.id)

        ready = []
        incomplete_count = 0
        open_count = 0
        for record in records:
            applicable = tuple(
                metadata.definition for metadata in required_metadata
                if record.trade_id in applicable_by_field[metadata.definition.id]
            )
            filled = tuple(
                field_id for field_id, by_trade in values_by_field.items()
                if record.trade_id in by_trade
            )
            readiness = evaluate_trade_readiness(
                record,
                required_dynamic_fields=applicable,
                filled_dynamic_field_ids=filled,
            )
            if readiness.status is TradeReadinessStatus.READY and record.status is TradeStatus.CLOSED:
                ready.append(record)
            elif readiness.status is TradeReadinessStatus.OPEN:
                open_count += 1
            else:
                incomplete_count += 1
        return tuple(ready), {
            "ready_count": len(ready),
            "excluded_incomplete_count": incomplete_count,
            "open_count": open_count,
        }

    async def _required_statistics_fields(self) -> tuple[DynamicFieldMetadata, ...]:
        provider = getattr(self._query, "list_required_statistics_fields", None)
        if provider is None:
            return ()
        fields = tuple(await provider())
        if any(not isinstance(item, DynamicFieldMetadata) for item in fields):
            raise TypeError("statistics query must return DynamicFieldMetadata values")
        return fields

    async def _resolve_dynamic_field(self, field_id, field_code: str | None) -> DynamicFieldMetadata:
        normalized_id = None if field_id is None else (
            field_id if isinstance(field_id, CustomFieldDefinitionId) else CustomFieldDefinitionId(field_id)
        )
        metadata = await self._query.get_dynamic_field(field_id=normalized_id, field_code=field_code)
        if metadata is None:
            raise ValueError("dynamic statistics field was not found")
        if not isinstance(metadata, DynamicFieldMetadata):
            raise TypeError("statistics query must return DynamicFieldMetadata")
        return metadata

    def _field_applies(self, metadata: DynamicFieldMetadata, record: StatisticsTradeRecord) -> bool:
        # Statistics must keep analysing an inactive historical field. The
        # resolver still supplies phase/scope semantics; activating this local
        # copy does not mutate persisted metadata or collection policy.
        definition = metadata.definition
        if definition.status is CustomFieldStatus.INACTIVE:
            definition = definition.activate()
        context = record.resolution_context or CustomFieldResolutionContext(
            phase=CustomFieldPhase.POST_TRADE if record.status is TradeStatus.CLOSED else CustomFieldPhase.OPEN
        )
        return bool(self._resolver.resolve((definition,), metadata.scopes, context))

    @staticmethod
    def _static_groups(
        records: tuple[StatisticsTradeRecord, ...],
        group_by: StatisticsGroupBy,
    ) -> tuple[StatisticsGroup, ...]:
        buckets: dict[str, list[StatisticsTradeRecord]] = defaultdict(list)
        labels: dict[str, str] = {}
        for record in records:
            if group_by is StatisticsGroupBy.ACCOUNT:
                key, label = str(record.account_id), record.account_label or str(record.account_id)
            elif group_by is StatisticsGroupBy.INSTRUMENT:
                key, label = str(record.instrument_id), record.instrument_label or str(record.instrument_id)
            else:
                key = label = record.direction.value
            buckets[key].append(record)
            labels[key] = label
        return tuple(
            StatisticsGroup(key, labels[key], _summarize(tuple(values)))
            for key, values in buckets.items()
        )

    @staticmethod
    def _dynamic_groups(records, by_trade, metadata, *, include_missing, missing):
        buckets: dict[str, list[StatisticsTradeRecord]] = defaultdict(list)
        labels: dict[str, str] = {}
        options = {option.id: option for option in metadata.options}
        for record in records:
            value = by_trade[record.trade_id]
            key, label = _dynamic_value_identity(value, metadata.definition.value_type, options)
            buckets[key].append(record)
            labels[key] = label
        if include_missing and missing:
            buckets["__missing__"].extend(missing)
            labels["__missing__"] = "Missing"
        return tuple(
            StatisticsGroup(key, labels[key], _summarize(tuple(values)))
            for key, values in buckets.items()
        )


def _matches(record: StatisticsTradeRecord, filters: StatisticsFilter) -> bool:
    if filters.account_id is not None and record.account_id != filters.account_id:
        return False
    if filters.instrument_id is not None and record.instrument_id != filters.instrument_id:
        return False
    if filters.direction is not None and record.direction is not filters.direction:
        return False
    if filters.status is not None and record.status is not filters.status:
        return False
    if filters.from_at is not None and record.filter_time < filters.from_at:
        return False
    if filters.to_at is not None and record.filter_time >= filters.to_at:
        return False
    return True


def _values_by_trade(values: Iterable[TradeCustomValue], field_id) -> dict[TradeId, TradeCustomValue]:
    result = {}
    for value in values:
        if not isinstance(value, TradeCustomValue):
            raise TypeError("statistics query must return TradeCustomValue values")
        if value.field_id != field_id:
            raise ValueError("statistics query returned a value for another field")
        if value.trade_id in result:
            raise ValueError("statistics query returned duplicate dynamic values")
        result[value.trade_id] = value
    return result


def _dynamic_value_identity(value: TradeCustomValue, value_type, options):
    raw = value.value
    if value_type is CustomFieldValueType.CHOICE:
        if not isinstance(raw, CustomFieldOptionId):
            raise ValueError("CHOICE historical value must contain option identity")
        option = options.get(raw)
        return f"choice:{raw}", option.label if option is not None else str(raw)
    if value_type is CustomFieldValueType.NUMBER:
        return f"number:{raw}", str(raw)
    if value_type is CustomFieldValueType.YES_NO:
        return f"yes_no:{str(raw).lower()}", str(raw).lower()
    return f"text:{raw}", str(raw)


def _sort_groups(groups: Iterable[StatisticsGroup], min_sample_size: int) -> tuple[StatisticsGroup, ...]:
    return tuple(sorted(
        (group for group in groups if group.summary.sample_size >= min_sample_size),
        key=lambda group: (-group.summary.sample_size, group.key),
    ))


def _summarize(records: tuple[StatisticsTradeRecord, ...], *, ready_count=0, excluded_incomplete_count=0, open_count=0) -> PerformanceSummary:
    # The engine passes only CLOSED+READY records. Missing values never become
    # zero; zero is a real breakeven result and remains eligible.
    realized = tuple(record for record in records if record.status is TradeStatus.CLOSED and record.net_pnl is not None)
    currency = _single_currency(realized)
    gross = sum((record.gross_pnl.amount if record.gross_pnl is not None else ZERO for record in realized), ZERO)
    net_values = tuple(record.net_pnl.amount for record in realized if record.net_pnl is not None)
    net = sum(net_values, ZERO)
    fees = sum((record.fees.amount for record in realized), ZERO)
    expenses = sum((expense.amount.amount for record in realized for expense in record.expenses), ZERO)
    wins = tuple(value for value in net_values if value > ZERO)
    losses = tuple(value for value in net_values if value < ZERO)
    breakevens = tuple(value for value in net_values if value == ZERO)
    denominator = len(wins) + len(losses)
    gross_profit = sum(wins, ZERO)
    gross_loss = abs(sum(losses, ZERO))
    profit_factor = None if gross_loss == ZERO else gross_profit / gross_loss
    average_net = net / Decimal(len(net_values)) if net_values else None
    return PerformanceSummary(
        sample_size=len(net_values),
        trade_count=len(net_values),
        win_count=len(wins),
        loss_count=len(losses),
        breakeven_count=len(breakevens),
        win_rate=(Decimal(len(wins)) / Decimal(denominator)) if denominator else None,
        gross_pnl=gross,
        net_pnl=net,
        total_fees=fees,
        total_expenses=expenses,
        average_net_pnl=average_net,
        average_win=(sum(wins, ZERO) / Decimal(len(wins))) if wins else None,
        average_loss=(sum(losses, ZERO) / Decimal(len(losses))) if losses else None,
        profit_factor=profit_factor,
        expectancy=average_net,
        largest_win=max(wins) if wins else None,
        largest_loss=min(losses) if losses else None,
        median_net_pnl=_median(net_values),
        currency=currency,
        ready_count=ready_count,
        excluded_incomplete_count=excluded_incomplete_count,
        open_count=open_count,
    )


def _single_currency(records) -> str | None:
    currencies = {
        value.currency
        for record in records
        for value in (record.fees, record.gross_pnl, record.net_pnl)
        if value is not None
    }
    currencies.update(
        expense.amount.currency
        for record in records
        for expense in record.expenses
    )
    if len(currencies) > 1:
        raise ValueError("statistics cannot aggregate mixed currencies")
    return next(iter(currencies), None)


def _median(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")
