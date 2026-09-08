"""CLI for explicit, acknowledged historical Bybit Trade import."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from app.application import (
    HistoricalExecutionBackfill,
    HistoricalExecutionBackfillCommand,
    HistoricalExecutionBackfillSummary,
    ProcessExecutionAndUpdateTrade,
)
from app.infrastructure.persistence.database import create_async_engine, create_session_factory, get_database_url
from app.infrastructure.persistence.repositories import SqlAlchemyInstrumentRepository
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

from .config import BybitSettings
from .execution_source import BybitExecutionSource


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def render_import_summary(summary: HistoricalExecutionBackfillSummary) -> int:
    """Print a safe import summary and return the process exit status."""
    print(
        "BYBIT_HISTORICAL_IMPORT "
        f"fetched={summary.fetched} processed={summary.processed} "
        f"already_processed={summary.already_processed} "
        f"trades_created={summary.trades_created} "
        f"trades_updated={summary.trades_updated} "
        f"trades_closed={summary.trades_closed} errors={summary.errors}"
    )
    if summary.errors:
        for message in summary.error_messages:
            print(f"ERROR {message}")
    return 1 if summary.errors else 0


async def run(start_at: datetime, end_at: datetime | None, allow_unsafe_boundary: bool) -> int:
    settings = BybitSettings.from_env()
    engine = create_async_engine(get_database_url())
    try:
        factory = create_session_factory(engine)
        uow_factory = lambda: SqlAlchemyUnitOfWork(factory)
        async with factory() as catalog_session:
            source = BybitExecutionSource(settings, SqlAlchemyInstrumentRepository(catalog_session))
            processor = ProcessExecutionAndUpdateTrade(
                uow_factory,
                automatic_data_provider=source.market_data_provider,
                entry_timezone=ZoneInfo(os.getenv("JOURNAL_TIMEZONE", "UTC")),
            )
            summary = await HistoricalExecutionBackfill(source, processor).execute(
                HistoricalExecutionBackfillCommand(
                    start_at=start_at,
                    end_at=end_at,
                    allow_unsafe_boundary=allow_unsafe_boundary,
                )
            )
        return render_import_summary(summary)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import read-only Bybit Trade executions")
    parser.add_argument("--start", required=True, type=_parse_datetime, help="ISO-8601 UTC start")
    parser.add_argument("--end", type=_parse_datetime, help="ISO-8601 UTC end; defaults to now")
    parser.add_argument(
        "--allow-unsafe-boundary",
        action="store_true",
        help="acknowledge that start may be mid-position; preview first",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.start, args.end, args.allow_unsafe_boundary)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
