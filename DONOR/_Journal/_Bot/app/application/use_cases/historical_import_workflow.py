"""Preview/plan/import orchestration for the user-controlled Bybit first import."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import re

from app.application.errors import HistoricalPreviewError
from app.core.imports import HistoricalImportMode, HistoricalImportPlan, HistoricalImportPreview, JournalTradeState, LogicalTradePreview, HistoryProgress, check_normalized_bybit_execution
from app.core.instruments import Instrument
from app.core.imports.history import JournalTradeStateRecord
from .historical_reconstruction import HistoricalTradeAggregationAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HistoricalImportSelection:
    mode: HistoricalImportMode
    supported_history_from: datetime
    selected_start: datetime | None = None
    selected_end: datetime | None = None

    def __post_init__(self) -> None:
        mode = self.mode if isinstance(self.mode, HistoricalImportMode) else HistoricalImportMode(self.mode)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "supported_history_from", _utc(self.supported_history_from, "supported_history_from"))
        end = _utc(self.selected_end, "selected_end") if self.selected_end is not None else datetime.now(timezone.utc)
        if mode is HistoricalImportMode.NEW_ONLY:
            start = end
        elif mode is HistoricalImportMode.LAST_30_DAYS:
            start = max(self.supported_history_from, end - timedelta(days=30))
        elif mode is HistoricalImportMode.ALL_AVAILABLE:
            start = self.supported_history_from
        else:
            if self.selected_start is None:
                raise ValueError("CUSTOM selection requires selected_start")
            start = _utc(self.selected_start, "selected_start")
        if start < self.supported_history_from:
            raise ValueError("selected_start cannot precede supported history")
        if end > datetime.now(timezone.utc) + timedelta(seconds=5):
            raise ValueError("selected_end cannot be in the future")
        if start > end:
            raise ValueError("selected_start must be <= selected_end")
        object.__setattr__(self, "selected_start", start)
        object.__setattr__(self, "selected_end", end)


@dataclass(frozen=True, slots=True)
class HistoricalImportResult:
    added_trade_count: int
    already_imported_trade_count: int
    processed_execution_count: int
    errors: tuple[str, ...] = ()
    planned_journal_trades: int = 0
    created: int = 0
    updated: int = 0
    already_existing: int = 0
    baseline: int = 0
    skipped: int = 0


class PreviewHistoricalImport:
    """Build an immutable plan; this class has no persistence write path."""

    def __init__(self, source, execution_repository, instrument_repository=None):
        self._source = source
        self._executions = execution_repository
        self._instruments = instrument_repository

    async def execute(self, selection: HistoricalImportSelection, *, facts=None, progress_callback=None) -> tuple[HistoricalImportPreview, HistoricalImportPlan]:
        context = {
            "stage": "FETCH_RAW",
            "account_id": None,
            "raw_execution_count": None,
            "normalized_execution_count": None,
            "symbol_count": None,
            "snapshot_used": facts is not None,
        }
        try:
            return await self._execute(selection, facts=facts, progress_callback=progress_callback, context=context)
        except HistoricalPreviewError:
            raise
        except Exception as error:
            fact = context.get("fact")
            logger.exception(
                "Historical preview failed stage=%s account_id=%s selected_start=%s selected_end=%s "
                "history_available_from=%s raw_execution_count=%s normalized_execution_count=%s "
                "symbol_count=%s symbol=%s execTime=%s execId=%s side=%s qty=%s current_position_qty=%s snapshot_used=%s "
                "exception_type=%s exception_message=%s",
                context["stage"], context.get("account_id"), selection.selected_start, selection.selected_end,
                selection.supported_history_from, context.get("raw_execution_count"),
                context.get("normalized_execution_count"),
                context.get("symbol_count"),
                context.get("symbol"), getattr(fact, "executed_at", None),
                getattr(fact, "external_execution_id", None), getattr(getattr(fact, "side", None), "value", None),
                getattr(getattr(fact, "quantity", None), "value", None), context.get("current_position_qty"),
                context.get("snapshot_used"), type(error).__name__, _safe_detail(error),
            )
            stage = context["stage"]
            code = {
                "BUILD_POSITION_CONTEXT": "HISTORICAL_POSITION_CONTEXT",
                "AGGREGATE_LOGICAL_TRADES": "HISTORICAL_AGGREGATION",
                "NORMALIZE": "HISTORICAL_NORMALIZATION",
                "FETCH_RAW": "HISTORICAL_FETCH",
            }.get(stage, "HISTORICAL_AGGREGATION")
            raise HistoricalPreviewError(stage, code, _safe_detail(error)) from error

    async def _execute(self, selection: HistoricalImportSelection, *, facts=None, progress_callback=None, context=None) -> tuple[HistoricalImportPreview, HistoricalImportPlan]:
        if not isinstance(selection, HistoricalImportSelection):
            raise TypeError("selection must be HistoricalImportSelection")
        if facts is None:
            context["account_id"] = getattr(self._source, "account_id", None)
            context["stage"] = "FETCH_RAW"
            facts = tuple(await self._source.fetch_historical_executions(
                start_at=selection.supported_history_from,
                end_at=selection.selected_end,
            ))
        else:
            facts = tuple(facts)
        if facts:
            context["account_id"] = facts[0].account_id
        context["raw_execution_count"] = len(facts)
        facts = _dedupe_normalized_facts(facts)
        context["stage"] = "NORMALIZE"
        for fact in facts:
            compatibility = check_normalized_bybit_execution(fact)
            if not compatibility.supported:
                raise ValueError(f"Bybit execution is incompatible: {compatibility.reason}")
        context["normalized_execution_count"] = len(facts)
        context["symbol_count"] = len({fact.instrument_id for fact in facts})
        if progress_callback is not None:
            value = progress_callback(HistoryProgress("aggregate", 0, 0, len(facts)))
            if hasattr(value, "__await__"):
                await value
        facts = tuple(sorted(facts, key=lambda item: (item.executed_at, str(item.external_execution_id))))
        context["stage"] = "BUILD_POSITION_CONTEXT"
        service = HistoricalTradeAggregationAdapter()
        aggregates = []
        aggregate_source_ids: dict[int, set[str]] = {}
        context["stage"] = "AGGREGATE_LOGICAL_TRADES"
        for fact in facts:
            context["fact"] = fact
            context["symbol"] = await self._symbol(fact.instrument_id)
            current = service.get(fact.account_id, fact.instrument_id)
            context["current_position_qty"] = None if current is None else current.open_quantity.value
            application = service.apply_fact(fact)
            fact_id = str(fact.external_execution_id)
            for aggregate in application.aggregates:
                aggregate_source_ids.setdefault(id(aggregate), set()).add(fact_id)
                if not any(item is aggregate for item in aggregates):
                    aggregates.append(aggregate)
            if application.reversal:
                logger.info(
                    "Historical position reversal reconstructed account_id=%s symbol=%s "
                    "execTime=%s execId=%s side=%s qty=%s prior_position_qty=%s residual_qty=%s",
                    fact.account_id, context["symbol"], fact.executed_at, fact.external_execution_id,
                    fact.side.value, fact.quantity.value,
                    application.prior_position_qty, application.residual_qty,
                )

        selected_facts = tuple(item for item in facts if selection.selected_start <= item.executed_at <= selection.selected_end)
        selected_ids = {str(item.external_execution_id) for item in selected_facts}
        selected_aggregates = [aggregate for aggregate in aggregates if aggregate_source_ids.get(id(aggregate), set()) & selected_ids]
        boundary = [aggregate for aggregate in selected_aggregates if aggregate.opened_at < selection.selected_start]
        baseline = [aggregate for aggregate in aggregates if aggregate.status.value == "OPEN" and aggregate.opened_at < selection.selected_start]

        context["stage"] = "CHECK_ALREADY_IMPORTED"
        imported_ids = set()
        imported_trade_ids = set()
        for fact in selected_facts:
            if not hasattr(self._executions, "get_by_external_id"):
                continue
            existing = await self._executions.get_by_external_id(
                exchange=fact.exchange,
                account_id=fact.account_id,
                external_execution_id=str(fact.external_execution_id),
            )
            if existing is not None:
                imported_ids.add(str(fact.external_execution_id))
                if existing.trade_id is not None:
                    imported_trade_ids.add(str(existing.trade_id))
        if progress_callback is not None:
            value = progress_callback(HistoryProgress("existing", 0, 0, len(selected_facts)))
            if hasattr(value, "__await__"):
                await value

        context["stage"] = "BUILD_PREVIEW_COUNTS"
        logical_views_list = []
        for aggregate in selected_aggregates:
            logical_views_list.append(await self._view(
                aggregate, aggregate in boundary, False,
                aggregate_source_ids.get(id(aggregate), ()),
            ))
        logical_views = tuple(logical_views_list)
        baseline_views_list = []
        for aggregate in baseline:
            baseline_views_list.append(await self._view(
                aggregate, False, True, aggregate_source_ids.get(id(aggregate), ()),
            ))
        baseline_views = tuple(baseline_views_list)
        counts_by_symbol: dict[str, int] = {}
        for aggregate in selected_aggregates:
            symbol = await self._symbol(aggregate.instrument_id)
            counts_by_symbol[symbol] = counts_by_symbol.get(symbol, 0) + 1
        context["symbol_count"] = len(counts_by_symbol)
        preview = HistoricalImportPreview(
            selected_start=selection.selected_start,
            selected_end=selection.selected_end,
            supported_history_from=selection.supported_history_from,
            execution_count=len(selected_facts),
            logical_trade_count=len(selected_aggregates),
            symbol_count=len(counts_by_symbol),
            already_imported_execution_count=len(imported_ids),
            already_imported_trade_count=len(imported_trade_ids),
            would_import_trade_count=sum(
                1 for aggregate in selected_aggregates
                if aggregate not in boundary and not any(
                    str(item.external_execution_id) in imported_ids for item in aggregate.executions
                )
            ),
            boundary_crossing_trade_count=len(boundary),
            first_executed_at=None if not selected_facts else selected_facts[0].executed_at,
            last_executed_at=None if not selected_facts else selected_facts[-1].executed_at,
            counts_by_symbol=tuple(sorted(counts_by_symbol.items())),
            logical_trades=logical_views,
            baseline_open_trades=baseline_views,
            raw_exchange_execution_count=len(selected_ids),
            reconstruction_leg_count=sum(item.execution_count for item in selected_aggregates),
        )
        plan_facts = []
        for aggregate in selected_aggregates:
            if aggregate in boundary:
                continue
            if any(str(item.external_execution_id) in imported_ids for item in aggregate.executions):
                # Keep the remaining facts in the plan: ProcessExecution... is
                # idempotent, and a partially imported logical trade still
                # needs to be completed safely.
                pass
            source_ids = aggregate_source_ids.get(id(aggregate), set())
            plan_facts.extend(item for item in facts if str(item.external_execution_id) in source_ids)
        # Baseline facts are deliberately separate in the model but imported
        # through the same processor so a later close attaches to the OPEN row.
        for aggregate in baseline:
            source_ids = aggregate_source_ids.get(id(aggregate), set())
            plan_facts.extend(item for item in facts if str(item.external_execution_id) in source_ids)
        unique = {str(item.external_execution_id): item for item in plan_facts}
        context["stage"] = "RENDER_PREVIEW"
        return preview, HistoricalImportPlan(
            selected_start=selection.selected_start,
            selected_end=selection.selected_end,
            supported_history_from=selection.supported_history_from,
            executions=tuple(sorted(unique.values(), key=lambda item: (item.executed_at, str(item.external_execution_id)))),
            logical_trades=logical_views,
            boundary_crossing=tuple(item for item in logical_views if item.boundary_crossing),
            baseline_open_trades=baseline_views,
            already_imported_execution_ids=tuple(sorted(imported_ids)),
            mode=selection.mode,
            already_imported_trade_count=len(imported_trade_ids),
            historical_instruments=tuple(getattr(self._source, "historical_instrument_identities", ())),
            planned_journal_trade_count=len(logical_views) + len(baseline_views),
        )

    async def _symbol(self, instrument_id) -> str:
        if self._instruments is not None and hasattr(self._instruments, "get_by_id"):
            instrument = await self._instruments.get_by_id(instrument_id)
            if instrument is not None:
                return instrument.symbol
        for identity in getattr(self._source, "historical_instrument_identities", ()):
            if identity.instrument_id == instrument_id:
                return identity.symbol
        return str(instrument_id)

    async def _view(self, aggregate, boundary: bool, baseline: bool, source_ids=()) -> LogicalTradePreview:
        return LogicalTradePreview(
            trade_id=aggregate.trade_id,
            account_id=aggregate.account_id,
            instrument_id=aggregate.instrument_id,
            opened_at=aggregate.opened_at,
            closed_at=aggregate.closed_at,
            status=aggregate.status.value,
            execution_count=aggregate.execution_count,
            symbol=await self._symbol(aggregate.instrument_id),
            boundary_crossing=boundary,
            baseline=baseline,
            external_execution_ids=tuple(sorted(source_ids)) or tuple(
                str(item.external_execution_id) for item in aggregate.executions
            ),
        )


class ImportHistoricalBybit:
    """Execute only a previously previewed plan after explicit confirmation."""

    def __init__(self, processor, journal_state_repository=None):
        self._processor = processor
        self._states = journal_state_repository

    async def execute(self, plan: HistoricalImportPlan, *, confirm_token: str | None = None) -> HistoricalImportResult:
        if not isinstance(plan, HistoricalImportPlan):
            raise TypeError("plan must be HistoricalImportPlan")
        if confirm_token != plan.token:
            raise PermissionError("historical import requires explicit confirmation of the preview")
        created_trade_ids = set()
        updated_trade_ids = set()
        errors = []
        baseline_trade_ids = set()
        baseline_external_ids = {
            str(execution)
            for item in plan.baseline_open_trades
            for execution in item.external_execution_ids
        }
        for fact in plan.executions:
            try:
                compatibility = check_normalized_bybit_execution(fact)
                if not compatibility.supported:
                    raise ValueError(f"Bybit execution is incompatible: {compatibility.reason}")
                identity = next((item for item in plan.historical_instruments if item.instrument_id == fact.instrument_id), None)
                historical_instrument = None if identity is None else Instrument(
                    identity.instrument_id, identity.symbol, f"{identity.symbol} (historical)", "BYBIT", "LINEAR", False
                )
                try:
                    result = await self._processor.execute(
                        fact,
                        historical_instrument=historical_instrument,
                        allow_historical_reversal=True,
                    )
                except TypeError as error:
                    if "historical_instrument" not in str(error) and "allow_historical_reversal" not in str(error):
                        raise
                    try:
                        result = await self._processor.execute(
                            fact,
                            historical_instrument=historical_instrument,
                        )
                    except TypeError as compatibility_error:
                        if "historical_instrument" not in str(compatibility_error):
                            raise
                        result = await self._processor.execute(fact)
                if result.trade_id is not None:
                    if result.trade_action.value in {"CREATED", "REVERSED"}:
                        created_trade_ids.add(result.trade_id)
                    elif result.trade_action.value in {"UPDATED", "CLOSED"}:
                        updated_trade_ids.add(result.trade_id)
                    baseline = str(fact.external_execution_id) in baseline_external_ids
                    if baseline:
                        baseline_trade_ids.add(result.trade_id)
                        if self._states is not None:
                            await self._states.save(JournalTradeStateRecord(
                                trade_id=result.trade_id,
                                account_id=fact.account_id,
                                state=JournalTradeState.BASELINE_PRE_TRACKING,
                                reason="open position before tracking_start_at",
                            ))
            except Exception as error:  # summary is safe; transaction processor rolls back each fact
                errors.append(f"{fact.external_execution_id}: {error}")
        updated_trade_ids -= created_trade_ids
        # A baseline lifecycle is a separate reconciliation bucket.  It may
        # be returned as CREATED for its first fill and CLOSED/UPDATED for a
        # later fill, but it must never be counted in those buckets as well.
        created_trade_ids -= baseline_trade_ids
        updated_trade_ids -= baseline_trade_ids
        created = len(created_trade_ids)
        updated = len(updated_trade_ids)
        planned = plan.planned_journal_trade_count or len(plan.logical_trades) + len(plan.baseline_open_trades)
        return HistoricalImportResult(
            added_trade_count=created,
            already_imported_trade_count=plan.already_imported_trade_count,
            processed_execution_count=len(plan.executions),
            errors=tuple(errors),
            planned_journal_trades=planned,
            created=created,
            updated=updated,
            already_existing=plan.already_imported_trade_count,
            baseline=len(baseline_trade_ids),
            skipped=max(0, planned - created - updated - plan.already_imported_trade_count - len(baseline_trade_ids) - len(errors)),
        )


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _dedupe_normalized_facts(facts):
    """Keep one canonical fact per external exchange execution identity."""
    by_external_id = {}
    for fact in facts:
        external_id = str(fact.external_execution_id)
        previous = by_external_id.get(external_id)
        if previous is not None and previous != fact:
            raise ValueError(f"conflicting duplicate exchange execution: {external_id}")
        by_external_id[external_id] = fact
    return tuple(sorted(by_external_id.values(), key=lambda item: (item.executed_at, str(item.external_execution_id))))


_SENSITIVE_RE = re.compile(r"(?i)\b(api[_ -]?key|api[_ -]?secret|authorization|signature|auth[_ -]?headers?)\b")


def _safe_detail(error: Exception) -> str:
    detail = " ".join(str(error).split())
    if not detail:
        return type(error).__name__
    if _SENSITIVE_RE.search(detail):
        return "exception detail redacted"
    return detail[:500]
