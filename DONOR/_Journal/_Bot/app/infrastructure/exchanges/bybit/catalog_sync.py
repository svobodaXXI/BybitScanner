"""Command-line entry point for the explicit Bybit catalog sync."""

from __future__ import annotations

import asyncio
import logging

from app.infrastructure.persistence.database import create_async_engine, create_session_factory, get_database_url

from .config import BybitSettings
from .instrument_catalog import BybitInstrumentCatalogSource, BybitInstrumentCatalogSync


async def run() -> None:
    settings = BybitSettings.from_env()
    engine = create_async_engine(get_database_url())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            async with session.begin():
                summary = await BybitInstrumentCatalogSync(
                    BybitInstrumentCatalogSource(settings)
                ).execute(session)
        print(
            "BYBIT_CATALOG_SYNC "
            f"fetched={summary.fetched} upserted={summary.upserted} "
            f"deactivated={summary.deactivated} pages={summary.pages}"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())
