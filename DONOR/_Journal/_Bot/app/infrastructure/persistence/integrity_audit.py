"""Read-only integrity audit for persisted journal Trades."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import os

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.trades.enums import TradePnLSource
from app.core.trades.execution_replay import validate_execution_replay
from app.infrastructure.persistence.database import create_async_engine, create_session_factory, get_database_url
from app.infrastructure.persistence.mappers import execution_from_orm, trade_from_orm
from app.infrastructure.persistence.models import ExecutionORM, InstrumentORM, TradeORM


def _load_local_env() -> None:
    env_file = Path(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


async def audit(account_id=None) -> dict:
    """Scan every Trade independently and never mutate the database."""
    engine = create_async_engine(get_database_url())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            statement = select(TradeORM).options(selectinload(TradeORM.expenses)).order_by(
                TradeORM.opened_at.desc(), TradeORM.id.desc()
            )
            if account_id is not None:
                statement = statement.where(TradeORM.account_id == account_id)
            trades = tuple((await session.execute(statement)).scalars().all())
            instruments = {
                item.id: item.symbol
                for item in (await session.execute(select(InstrumentORM))).scalars().all()
            }
            execution_result = await session.execute(
                select(ExecutionORM).order_by(ExecutionORM.executed_at.asc(), ExecutionORM.id.asc())
            )
            executions_by_trade = {}
            for model in execution_result.scalars().all():
                executions_by_trade.setdefault(model.trade_id, []).append(execution_from_orm(model))

            rows = []
            for model in trades:
                executions = tuple(executions_by_trade.get(model.id, ()))
                snapshot_result = "NOT_APPLICABLE"
                snapshot_error = None
                replay_result = "NOT_APPLICABLE"
                replay_error = None
                try:
                    trade = trade_from_orm(model)
                    try:
                        replace(trade, pnl_source=TradePnLSource.SNAPSHOT)
                        snapshot_result = "VALID"
                    except (TypeError, ValueError) as exc:
                        snapshot_result = "INVALID"
                        snapshot_error = str(exc)
                    if trade.pnl_source is TradePnLSource.EXECUTION_REPLAY:
                        try:
                            validate_execution_replay(trade, executions)
                            replay_result = "VALID"
                        except (TypeError, ValueError) as exc:
                            replay_result = "INVALID"
                            replay_error = str(exc)
                    result = "VALID" if (
                        replay_result == "VALID"
                        or replay_result == "NOT_APPLICABLE" and snapshot_result == "VALID"
                    ) else "INVALID"
                    error = replay_error or snapshot_error
                except (TypeError, ValueError) as exc:
                    result = "INVALID"
                    error = str(exc)
                rows.append({
                    "trade_id": str(model.id),
                    "symbol": instruments.get(model.instrument_id),
                    "status": model.status,
                    "pnl_source": model.pnl_source,
                    "execution_count": len(executions),
                    "external_execution_ids": [item.external_execution_id for item in executions],
                    "old_snapshot_validation": snapshot_result,
                    "execution_replay_validation": replay_result,
                    "economic_correction_required": result == "INVALID",
                    "result": result,
                    "error": error,
                })
            external_ids = [item.external_execution_id for values in executions_by_trade.values() for item in values]
            duplicate_ids = sorted({item for item in external_ids if item is not None and external_ids.count(item) > 1})
            return {
                "total_trades": len(rows),
                "valid_trades": sum(item["result"] == "VALID" for item in rows),
                "invalid_trades": sum(item["result"] == "INVALID" for item in rows),
                "total_executions": len(external_ids),
                "unique_external_execution_ids": len(set(external_ids)),
                "duplicate_external_execution_ids": duplicate_ids,
                "trades": rows,
            }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Trade execution-replay integrity audit")
    parser.add_argument("--account-id")
    args = parser.parse_args()
    _load_local_env()
    print(json.dumps(asyncio.run(audit(args.account_id)), indent=2, default=str))


if __name__ == "__main__":
    main()
