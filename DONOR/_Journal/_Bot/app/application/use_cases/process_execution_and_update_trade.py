"""Atomic normalized-execution ingestion and Trade snapshot orchestration."""

from dataclasses import dataclass, replace
from enum import StrEnum

from app.application.errors import AmbiguousOpenTradeError, UnsupportedPositionReversalError
from app.application.automatic_market_data import AutomaticTradeDataCapture
from app.application.ports.unit_of_work import UnitOfWork
from app.core.common.money import Money
from app.core.common.quantity import Quantity
from app.core.trades.enums import TradePnLSource, TradeStatus
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.execution_replay import validate_execution_replay
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade import Trade
from app.core.trades.trade_aggregation_service import TradeAggregationService
from app.core.trades.trade_id import TradeId

from .process_execution_fact import ExecutionProcessingStatus, ProcessExecutionFact


class TradeAction(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    CLOSED = "CLOSED"
    NONE = "NONE"
    REVERSED = "REVERSED"


@dataclass(frozen=True, slots=True)
class ProcessExecutionAndUpdateTradeResult:
    execution_status: ExecutionProcessingStatus
    execution_id: ExecutionId
    trade_id: TradeId | None
    trade_action: TradeAction


class ProcessExecutionAndUpdateTrade:
    """Apply one fact atomically across Execution and Trade repositories."""

    def __init__(self, uow_factory, *, automatic_data_provider=None, automatic_data_capture=None, entry_timezone=None) -> None:
        self._uow_factory = uow_factory
        self._automatic_capture = automatic_data_capture or AutomaticTradeDataCapture(
            automatic_data_provider, entry_timezone=entry_timezone
        )

    async def execute(
        self,
        fact: ExecutionFact,
        *,
        historical_instrument=None,
        allow_historical_reversal: bool = False,
    ) -> ProcessExecutionAndUpdateTradeResult:
        async with self._uow_factory() as uow:
            if historical_instrument is not None and await uow.instruments.get_by_id(fact.instrument_id) is None:
                await uow.instruments.save(historical_instrument)
            processor = ProcessExecutionFact(uow.executions, uow.accounts, uow.instruments)
            candidate, existing_execution = await processor.prepare(fact)
            if existing_execution is not None:
                replay = processor.replay_result(existing_execution, candidate)
                automatic_repository = getattr(uow, "automatic_data", None)
                if existing_execution.trade_id is not None and automatic_repository is not None:
                    existing_trade = await uow.trades.get_by_id(existing_execution.trade_id)
                    if existing_trade is not None:
                        changed = await self._automatic_capture.capture(existing_trade, automatic_repository)
                        if changed:
                            await uow.commit()
                return ProcessExecutionAndUpdateTradeResult(
                    replay.status,
                    replay.execution_id,
                    existing_execution.trade_id,
                    TradeAction.NONE,
                )

            selected_trade, prior_executions = await self._match_trade(uow, candidate)
            service = TradeAggregationService()
            if selected_trade is not None:
                for prior in sorted(prior_executions, key=lambda item: (item.executed_at, str(item.execution_id))):
                    service.apply(prior)
                if service.get(candidate.account_id, candidate.instrument_id) is None:
                    candidate = candidate.linked_to(selected_trade.trade_id)
                else:
                    current = service.get(candidate.account_id, candidate.instrument_id)
                    if current.trade_id != selected_trade.trade_id:
                        raise AmbiguousOpenTradeError("execution history points to a different OPEN Trade")
            try:
                if (
                    selected_trade is not None
                    and service.get(candidate.account_id, candidate.instrument_id) is not None
                    and _is_confirmed_bybit_reversal(
                        candidate,
                        service.get(candidate.account_id, candidate.instrument_id),
                        allow_historical_reversal=allow_historical_reversal,
                    )
                ):
                    old_aggregate, new_aggregate, close_execution, open_execution = _apply_confirmed_reversal(
                        service, candidate, allow_historical_reversal=allow_historical_reversal
                    )
                    old_trade = _trade_snapshot(old_aggregate, selected_trade, prior_executions)
                    new_trade = _trade_snapshot(new_aggregate, None, ())
                    validate_execution_replay(old_trade, old_aggregate.executions)
                    validate_execution_replay(new_trade, new_aggregate.executions)
                    await uow.trades.save(old_trade)
                    await uow.trades.save(new_trade)
                    await uow.executions.save(old_aggregate.executions[-1])
                    await uow.executions.save(new_aggregate.executions[-1])
                    automatic_repository = getattr(uow, "automatic_data", None)
                    if automatic_repository is not None:
                        await self._automatic_capture.capture(old_trade, automatic_repository)
                        await self._automatic_capture.capture(new_trade, automatic_repository)
                    await uow.commit()
                    return ProcessExecutionAndUpdateTradeResult(
                        ExecutionProcessingStatus.PROCESSED,
                        open_execution.execution_id,
                        new_trade.trade_id,
                        TradeAction.REVERSED,
                    )
                aggregate = service.apply(candidate)
            except ValueError as error:
                if "exceeds open quantity" in str(error):
                    raise UnsupportedPositionReversalError(
                        "position reversal is not supported by the current aggregation policy"
                    ) from error
                raise
            persisted_execution = aggregate.executions[-1]
            trade = _trade_snapshot(aggregate, selected_trade, prior_executions)
            if trade.pnl_source is TradePnLSource.EXECUTION_REPLAY:
                validate_execution_replay(trade, aggregate.executions)
            # The aggregate links the first execution to its newly generated
            # TradeId.  Persist the parent first so the Execution FK is valid
            # when the execution repository flushes.  Both writes remain in
            # the same UoW transaction and therefore roll back together.
            await uow.trades.save(trade)
            await uow.executions.save(persisted_execution)
            automatic_repository = getattr(uow, "automatic_data", None)
            if automatic_repository is not None:
                await self._automatic_capture.capture(trade, automatic_repository)
            await uow.commit()
            action = TradeAction.CREATED if selected_trade is None else (
                TradeAction.CLOSED if trade.status is TradeStatus.CLOSED else TradeAction.UPDATED
            )
            return ProcessExecutionAndUpdateTradeResult(
                ExecutionProcessingStatus.PROCESSED,
                persisted_execution.execution_id,
                trade.trade_id,
                action,
            )

    async def _match_trade(self, uow: UnitOfWork, execution: Execution):
        try:
            open_trades = await uow.trades.list_open(
                account_id=execution.account_id,
                instrument_id=execution.instrument_id,
                include_excluded=True,
            )
        except TypeError:
            # Compatibility with small in-memory repository doubles.  The
            # production SQLAlchemy repository supports this explicit ingest
            # option so BASELINE_PRE_TRACKING OPEN rows remain matchable.
            open_trades = await uow.trades.list_open(
                account_id=execution.account_id,
                instrument_id=execution.instrument_id,
            )
        # A historical fill must never be attached to a newer live position
        # merely because Bybit reused the same position reference.  This is
        # the lifecycle boundary that protects a healthy current OPEN Trade
        # during repair/backfill.
        open_trades = tuple(item for item in open_trades if execution.executed_at >= item.opened_at)
        if not open_trades:
            return None, ()
        if execution.position_id is not None:
            matches = []
            histories = {}
            for trade in open_trades:
                history = await uow.executions.list_by_trade(trade.trade_id)
                histories[trade.trade_id] = history
                if any(item.position_id == execution.position_id for item in history):
                    matches.append(trade)
            if len(matches) > 1:
                raise AmbiguousOpenTradeError("execution position reference matches multiple OPEN Trades")
            if len(matches) == 1:
                return matches[0], histories[matches[0].trade_id]
            return None, ()
        if len(open_trades) > 1:
            raise AmbiguousOpenTradeError("execution has no position reference and matches multiple OPEN Trades")
        trade = open_trades[0]
        return trade, await uow.executions.list_by_trade(trade.trade_id)


def _is_confirmed_bybit_reversal(
    execution: Execution,
    aggregate,
    *,
    allow_historical_reversal: bool = False,
) -> bool:
    """Only split an over-close when the exchange position identity proves it."""
    if execution.exchange != "BYBIT":
        return False
    if not allow_historical_reversal and not execution.position_id:
        return False
    opening_side = (
        execution.side.value == "BUY"
        if aggregate.direction.value == "LONG"
        else execution.side.value == "SELL"
    )
    return not opening_side and execution.quantity.value > aggregate.open_quantity.value


def _apply_confirmed_reversal(
    service: TradeAggregationService,
    execution: Execution,
    *,
    allow_historical_reversal: bool = False,
):
    """Apply one factual reversal as two internal trade-linked legs.

    The source fill remains one exchange fact.  The split IDs are internal
    persistence identities required by the current one-Trade-per-Execution FK:
    the close leg keeps the old Trade linked, while the residual leg opens the
    new opposite Trade and retains the source external execution ID for
    idempotent replay.
    """
    current = service.get(execution.account_id, execution.instrument_id)
    if current is None or not _is_confirmed_bybit_reversal(
        execution, current, allow_historical_reversal=allow_historical_reversal
    ):
        raise UnsupportedPositionReversalError("position reversal is not sufficiently identified")
    close_quantity = Quantity(current.open_quantity.value)
    residual_quantity = Quantity(execution.quantity.value - close_quantity.value)
    close_ratio = close_quantity.value / execution.quantity.value
    close_fee = execution.fee * close_ratio
    residual_fee = execution.fee - close_fee
    external_id = execution.external_execution_id or str(execution.execution_id)
    close_execution = replace(
        execution,
        quantity=close_quantity,
        fee=close_fee,
        external_execution_id=f"{external_id}:reversal-close",
        external_order_id=f"{execution.external_order_id or ''}::reversal-close",
    )
    open_execution = replace(
        execution,
        quantity=residual_quantity,
        fee=residual_fee,
        external_order_id=f"{execution.external_order_id or ''}::reversal-residual",
    )
    closed = service.apply(close_execution)
    opened = service.apply(open_execution)
    return closed, opened, close_execution, open_execution


def _trade_snapshot(aggregate, previous: Trade | None, prior_executions=()) -> Trade:
    """Project aggregation state through the Trade lifecycle APIs."""
    manual_fees = Money(0, aggregate.total_fees.currency) if previous is None else previous.fees
    expenses = () if previous is None else previous.expenses
    if previous is not None and prior_executions:
        execution_fee = Money(0, aggregate.total_fees.currency)
        for execution in aggregate.executions:
            execution_fee += execution.fee
        manual_fees = previous.fees - execution_fee
        if manual_fees.amount < 0:
            manual_fees = Money(0, aggregate.total_fees.currency)
    fees = aggregate.total_fees + manual_fees
    quantity = aggregate.open_quantity if aggregate.status is TradeStatus.OPEN else aggregate.realized_quantity
    if quantity.value <= 0:
        quantity = Quantity(aggregate.realized_quantity.value)
    trade = Trade.open(
        account_id=aggregate.account_id,
        instrument_id=aggregate.instrument_id,
        direction=aggregate.direction,
        entry_price=aggregate.average_entry,
        quantity=quantity,
        opened_at=aggregate.opened_at if previous is None else previous.opened_at,
        currency=fees.currency,
        trade_id=aggregate.trade_id,
        fees=fees,
        expenses=expenses,
        stop_price=None if previous is None else previous.stop_price,
        take_profit=None if previous is None else previous.take_profit,
        risk=None if previous is None else previous.risk,
        pnl_source=TradePnLSource.EXECUTION_REPLAY,
    )
    if aggregate.status is TradeStatus.CLOSED:
        trade.close_from_aggregation(
            aggregate.executions[-1].price,
            aggregate.closed_at,
            aggregate.realized_gross_pnl,
        )
    return trade
