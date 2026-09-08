import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.infrastructure.persistence.database import get_test_database_url
from app.config import load_environment
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.execution_fact import ExecutionFact
from app.application.use_cases.process_execution_and_update_trade import ProcessExecutionAndUpdateTrade, TradeAction
from app.application.dtos import GetTradeDetailsCommand
from app.application.use_cases.get_trade_details import GetTradeDetails
from app.application.automatic_market_data import (
    MarketDataPoint,
    MarketDataSnapshot,
    PostTradeMarketSnapshot,
)
from app.core.automatic_data import DEFAULT_AUTOMATIC_FACTOR_REGISTRY
from app.application.use_cases.process_execution_fact import ExecutionProcessingStatus
from app.infrastructure.persistence.mappers import execution_from_orm, execution_to_orm
from app.infrastructure.persistence.models import AccountORM, AutomaticFactorObservationORM, ExecutionORM, InstrumentORM, TradeORM
from app.infrastructure.persistence.repositories import (
    SqlAlchemyAutomaticFactorObservationRepository,
    SqlAlchemyCustomFieldRepository,
    SqlAlchemyExecutionRepository,
    SqlAlchemyTradeCustomValueRepository,
    SqlAlchemyTradeRepository,
)
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


def test_configured_postgres_test_database_is_migrated():
    load_environment()
    if not os.getenv("TEST_DATABASE_URL", "").strip():
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    async def verify():
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                trades = await connection.scalar(text("SELECT to_regclass('public.trades')"))
                instruments = await connection.scalar(text("SELECT to_regclass('public.instruments')"))
                automatic = await connection.scalar(text("SELECT to_regclass('public.automatic_factor_observations')"))
                layouts = await connection.scalar(text("SELECT to_regclass('public.statistics_layouts')"))
                take_profit = await connection.scalar(text("SELECT 1 FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'take_profit'"))
                history_settings = await connection.scalar(text("SELECT to_regclass('public.exchange_import_settings')"))
                journal_state = await connection.scalar(text("SELECT to_regclass('public.trade_journal_state')"))
                owners = await connection.scalar(text("SELECT to_regclass('public.owners')"))
                account_owners = await connection.scalar(text("SELECT to_regclass('public.account_owners')"))
                viewer_grants = await connection.scalar(text("SELECT to_regclass('public.telegram_viewer_grants')"))
                return revision, trades, instruments, automatic, layouts, take_profit, history_settings, journal_state, owners, account_owners, viewer_grants
        finally:
            await engine.dispose()

    revision, trades, instruments, automatic, layouts, take_profit, history_settings, journal_state, owners, account_owners, viewer_grants = asyncio.run(verify())
    assert revision == "0011_telegram_viewer_grants"
    assert trades == "trades"
    assert instruments == "instruments"
    assert automatic == "automatic_factor_observations"
    assert layouts == "statistics_layouts"
    assert take_profit == 1
    assert history_settings == "exchange_import_settings"
    assert journal_state == "trade_journal_state"
    assert owners == "owners"
    assert account_owners == "account_owners"
    assert viewer_grants == "telegram_viewer_grants"


def test_postgres_execution_insert_gets_utc_created_at_without_domain_created_at():
    load_environment()
    if not os.getenv("TEST_DATABASE_URL", "").strip():
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    account_id = AccountId.generate()
    execution = Execution(
        execution_id=ExecutionId.generate(),
        account_id=account_id,
        instrument_id=InstrumentId.generate(),
        side=ExecutionSide.BUY,
        quantity=Quantity("0.01"),
        price=Price("1019.55"),
        fee=Money("0.00367038", "USDT"),
        executed_at=datetime(2026, 9, 5, 5, 16, tzinfo=timezone.utc),
        exchange="BYBIT",
        external_execution_id=f"created-at-smoke-{execution_id_seed()}",
    )

    async def verify():
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                await session.begin()
                session.add(AccountORM(id=account_id.value, created_at=datetime.now(timezone.utc)))
                model = execution_to_orm(execution)
                session.add(model)
                await session.flush()
                loaded = await session.get(ExecutionORM, execution.execution_id.value)
                assert loaded is not None
                assert loaded.created_at is not None
                assert loaded.created_at.tzinfo is not None
                assert loaded.created_at.utcoffset().total_seconds() == 0
                assert loaded.executed_at == execution.executed_at
                assert execution_from_orm(loaded) == execution
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(verify())


def execution_id_seed() -> str:
    """Keep the smoke external id unique without exposing any secrets."""
    return str(ExecutionId.generate())


def test_postgres_process_execution_respects_trade_fk_replay_and_atomic_rollback(monkeypatch):
    load_environment()
    if not os.getenv("TEST_DATABASE_URL", "").strip():
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    account_id = AccountId.generate()
    instrument_id = InstrumentId.generate()
    instrument = InstrumentORM(
        id=instrument_id.value,
        symbol="ZECUSDT",
        name="ZEC/USDT",
        exchange="BYBIT",
        market="LINEAR",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    external_prefix = f"postgres-fk-{ExecutionId.generate()}"

    def fact(side, quantity, price, external_id, at):
        return ExecutionFact(
            exchange="BYBIT",
            account_id=account_id,
            instrument_id=instrument_id,
            side=side,
            quantity=Quantity(quantity),
            price=Price(price),
            fee=Money("0.01", "USDT"),
            executed_at=datetime(2026, 9, 5, 5, at, tzinfo=timezone.utc),
            external_execution_id=f"{external_prefix}-{external_id}",
            position_id="postgres-position",
        )

    async def verify():
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as seed_session:
                async with seed_session.begin():
                    seed_session.add(AccountORM(id=account_id.value, created_at=datetime.now(timezone.utc)))
                    seed_session.add(instrument)

            processor = ProcessExecutionAndUpdateTrade(lambda: SqlAlchemyUnitOfWork(factory))
            first = await processor.execute(fact(ExecutionSide.BUY, "0.01", "1019.55", "buy", 16))
            assert first.execution_status is ExecutionProcessingStatus.PROCESSED
            assert first.trade_action is TradeAction.CREATED

            second = await processor.execute(fact(ExecutionSide.SELL, "0.01", "1009.28", "sell", 17))
            assert second.execution_status is ExecutionProcessingStatus.PROCESSED
            assert second.trade_action is TradeAction.CLOSED
            assert second.trade_id == first.trade_id

            async with factory() as check_session:
                trades = (await check_session.scalars(select(TradeORM).where(TradeORM.id == first.trade_id.value))).all()
                executions = (await check_session.scalars(select(ExecutionORM).where(ExecutionORM.account_id == account_id.value).order_by(ExecutionORM.executed_at))).all()
                assert len(trades) == 1
                assert len(executions) == 2
                assert all(item.trade_id == first.trade_id.value for item in executions)
                assert trades[0].status == "CLOSED"

            replay_first = await processor.execute(fact(ExecutionSide.BUY, "0.01", "1019.55", "buy", 16))
            replay_second = await processor.execute(fact(ExecutionSide.SELL, "0.01", "1009.28", "sell", 17))
            assert replay_first.execution_status is ExecutionProcessingStatus.ALREADY_PROCESSED
            assert replay_first.trade_action is TradeAction.NONE
            assert replay_second.execution_status is ExecutionProcessingStatus.ALREADY_PROCESSED
            assert replay_second.trade_action is TradeAction.NONE

            original_save = SqlAlchemyExecutionRepository.save

            async def fail_targeted_save(repository, execution):
                if execution.external_execution_id == f"{external_prefix}-rollback":
                    raise RuntimeError("forced execution persistence failure")
                return await original_save(repository, execution)

            monkeypatch.setattr(SqlAlchemyExecutionRepository, "save", fail_targeted_save)
            with pytest.raises(RuntimeError, match="forced execution persistence failure"):
                await processor.execute(fact(ExecutionSide.BUY, "0.02", "1000", "rollback", 18))

            async with factory() as check_session:
                trades = (await check_session.scalars(select(TradeORM).where(TradeORM.account_id == account_id.value))).all()
                executions = (await check_session.scalars(select(ExecutionORM).where(ExecutionORM.account_id == account_id.value))).all()
                assert len(trades) == 1
                assert len(executions) == 2
        finally:
            async with factory() as cleanup_session:
                async with cleanup_session.begin():
                    await cleanup_session.execute(delete(ExecutionORM).where(ExecutionORM.account_id == account_id.value))
                    await cleanup_session.execute(delete(TradeORM).where(TradeORM.account_id == account_id.value))
                    await cleanup_session.execute(delete(InstrumentORM).where(InstrumentORM.id == instrument_id.value))
                    await cleanup_session.execute(delete(AccountORM).where(AccountORM.id == account_id.value))
            await engine.dispose()

    asyncio.run(verify())


def test_postgres_execution_capture_is_versioned_and_idempotent():
    load_environment()
    if not os.getenv("TEST_DATABASE_URL", "").strip():
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    account_id = AccountId.generate()
    instrument_id = InstrumentId.generate()
    external_prefix = f"postgres-auto-{ExecutionId.generate()}"

    class Provider:
        provider_key = "TEST_MARKET"

        async def get_entry_snapshot(self, requested_instrument_id, as_of, *, factor_ids=()):
            return MarketDataSnapshot(
                requested_instrument_id, as_of,
                {factor_id: MarketDataPoint(
                    10 if factor_id == "funding_interval_minutes_inferred_at_entry" else Decimal("10"),
                    source_timestamp=as_of, provenance={"fixture": True},
                ) for factor_id in factor_ids},
                self.provider_key,
            )

        async def get_post_trade_snapshot(self, context, *, factor_ids=()):
            return PostTradeMarketSnapshot(
                context.instrument_id, context.opened_at, context.closed_at,
                {factor_id: MarketDataPoint(
                    Decimal("10"), source_timestamp=context.closed_at, provenance={"fixture": True},
                ) for factor_id in factor_ids},
                self.provider_key,
            )

    def fact(side, external_id, minute):
        return ExecutionFact(
            exchange="BYBIT", account_id=account_id, instrument_id=instrument_id,
            side=side, quantity=Quantity("0.01"), price=Price("100"),
            fee=Money("0.01", "USDT"),
            executed_at=datetime(2026, 9, 5, 5, minute, tzinfo=timezone.utc),
            external_execution_id=f"{external_prefix}-{external_id}", position_id="auto-position",
        )

    async def verify():
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as seed_session:
                async with seed_session.begin():
                    seed_session.add(AccountORM(id=account_id.value, created_at=datetime.now(timezone.utc)))
                    seed_session.add(InstrumentORM(
                        id=instrument_id.value, symbol="AUTOUSDT", name="Auto / USDT",
                        exchange="BYBIT", market="LINEAR", active=True,
                        created_at=datetime.now(timezone.utc),
                    ))

            processor = ProcessExecutionAndUpdateTrade(
                lambda: SqlAlchemyUnitOfWork(factory), automatic_data_provider=Provider()
            )
            opened = fact(ExecutionSide.BUY, "open", 16)
            closed = fact(ExecutionSide.SELL, "close", 17)
            first = await processor.execute(opened)
            await processor.execute(closed)
            await processor.execute(opened)
            await processor.execute(closed)

            async with factory() as check_session:
                observations = (await check_session.scalars(select(AutomaticFactorObservationORM).where(
                    AutomaticFactorObservationORM.trade_id == first.trade_id.value,
                ))).all()
                assert len(observations) == len(tuple(DEFAULT_AUTOMATIC_FACTOR_REGISTRY))
                assert {item.factor_id for item in observations} == {
                    definition.factor_id for definition in DEFAULT_AUTOMATIC_FACTOR_REGISTRY
                }
                duration = next(item for item in observations if item.factor_id == "holding_duration_seconds")
                assert duration.value_decimal == Decimal("60")
                assert duration.value_type == "DECIMAL"
                assert duration.definition_version == 2
                assert duration.calculation_version == "2"
                assert all(item.source_timestamp is not None for item in observations)
                efficiency = next(item for item in observations if item.factor_id == "exit_efficiency_pct_of_observed_mfe")
                assert efficiency.value_decimal == Decimal("0")
                assert efficiency.source_kind == "DERIVED"
                assert efficiency.capture_semantics == "POST_TRADE"
                assert efficiency.provenance is not None
                assert "exit_quality_from_observed_1m_mfe_v1" in efficiency.provenance

                details = await GetTradeDetails(
                    SqlAlchemyTradeRepository(check_session),
                    SqlAlchemyCustomFieldRepository(check_session),
                    SqlAlchemyTradeCustomValueRepository(check_session),
                    automatic_observation_repository=SqlAlchemyAutomaticFactorObservationRepository(check_session),
                ).execute(GetTradeDetailsCommand(first.trade_id))
                assert len(details.automatic_observations) == len(tuple(DEFAULT_AUTOMATIC_FACTOR_REGISTRY))
                assert next(
                    item for item in details.automatic_observations
                    if item.factor_id == "holding_duration_seconds"
                ).value == Decimal("60")
        finally:
            async with factory() as cleanup_session:
                async with cleanup_session.begin():
                    await cleanup_session.execute(delete(AutomaticFactorObservationORM).where(
                        AutomaticFactorObservationORM.trade_id.in_(
                            select(TradeORM.id).where(TradeORM.account_id == account_id.value)
                        )
                    ))
                    await cleanup_session.execute(delete(ExecutionORM).where(ExecutionORM.account_id == account_id.value))
                    await cleanup_session.execute(delete(TradeORM).where(TradeORM.account_id == account_id.value))
                    await cleanup_session.execute(delete(InstrumentORM).where(InstrumentORM.id == instrument_id.value))
                    await cleanup_session.execute(delete(AccountORM).where(AccountORM.id == account_id.value))
            await engine.dispose()

    asyncio.run(verify())
