"""CLI/admin diagnostic for supported Bybit history discovery.

It is read-only by default and prints no credentials or raw exchange rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

from app.application import DiscoverSupportedBybitHistory
from app.infrastructure.persistence.database import create_async_engine, create_session_factory, get_database_url
from app.infrastructure.persistence.repositories import SqlAlchemyExchangeImportSettingsRepository, SqlAlchemyInstrumentRepository

from .config import BybitSettings
from .execution_source import BybitExecutionSource


async def run(start_at: datetime, end_at: datetime | None) -> None:
    settings = BybitSettings.from_env()
    engine = create_async_engine(get_database_url())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            source = BybitExecutionSource(settings, SqlAlchemyInstrumentRepository(session))
            result = await DiscoverSupportedBybitHistory(
                source, SqlAlchemyExchangeImportSettingsRepository(session)
            ).execute(lookback_start=start_at, lookback_end=end_at)
            await session.commit()
            print(json.dumps({
                "status": result.status,
                "history_available_from": None if result.history_available_from is None else result.history_available_from.isoformat(),
                "first_executed_at": None if result.first_executed_at is None else result.first_executed_at.isoformat(),
                "last_executed_at": None if result.last_executed_at is None else result.last_executed_at.isoformat(),
                "execution_count": result.execution_count,
                "incompatible_count": result.incompatible_count,
                "last_incompatible_at": None if result.last_incompatible_at is None else result.last_incompatible_at.isoformat(),
                "incompatibilities": [
                    {
                        "execTime": item.exec_time.isoformat() if item.exec_time else None,
                        "symbol": item.symbol,
                        "side": item.side,
                        "execId": item.exec_id,
                        "reason_incompatible": item.reason_incompatible,
                    }
                    for item in result.incompatibilities
                ],
            }, indent=2))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover supported Bybit linear USDT Trade history")
    parser.add_argument("--start", type=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")), default=datetime(2025, 1, 1, tzinfo=timezone.utc))
    parser.add_argument("--end", type=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.start, args.end)) or 0)


if __name__ == "__main__":
    main()
