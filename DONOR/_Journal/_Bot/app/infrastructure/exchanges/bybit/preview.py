"""CLI for a sanitized, read-only historical Bybit import preview."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime

from app.application import PreviewHistoricalExecutionImport
from app.infrastructure.persistence.database import create_async_engine, create_session_factory, get_database_url
from app.infrastructure.persistence.repositories import SqlAlchemyInstrumentRepository

from .config import BybitSettings
from .execution_source import BybitExecutionSource


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def run(start_at: datetime, end_at: datetime | None, sample_limit: int) -> None:
    settings = BybitSettings.from_env()
    engine = create_async_engine(get_database_url())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            source = BybitExecutionSource(settings, SqlAlchemyInstrumentRepository(session))
            preview = await PreviewHistoricalExecutionImport(
                source, SqlAlchemyInstrumentRepository(session)
            ).execute(start_at=start_at, end_at=end_at, sample_limit=sample_limit)
            print(json.dumps({
                "execution_count": preview.execution_count,
                "symbol_count": preview.symbol_count,
                "first_executed_at": None if preview.first_executed_at is None else preview.first_executed_at.isoformat(),
                "last_executed_at": None if preview.last_executed_at is None else preview.last_executed_at.isoformat(),
                "counts_by_symbol": dict(preview.counts_by_symbol),
                "sample": [
                    {
                        "external_execution_id": row.external_execution_id,
                        "symbol": row.symbol,
                        "side": row.side,
                        "quantity": row.quantity,
                        "price": row.price,
                        "fee": row.fee,
                        "fee_currency": row.fee_currency,
                        "executed_at": row.executed_at.isoformat(),
                    }
                    for row in preview.sample
                ],
            }, indent=2))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview read-only Bybit Trade executions")
    parser.add_argument("--start", required=True, type=_parse_datetime, help="ISO-8601 UTC start")
    parser.add_argument("--end", type=_parse_datetime, help="ISO-8601 UTC end; defaults to now")
    parser.add_argument("--sample", type=int, default=0, help="number of sanitized sample rows")
    args = parser.parse_args()
    asyncio.run(run(args.start, args.end, args.sample))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
