"""Explicit development/bootstrap entry point for catalog population.

Production startup deliberately does not seed or synchronize instruments. Callers
must provide reviewed ``Instrument`` objects and own the surrounding transaction.
"""

from collections.abc import Iterable

from app.core.instruments.instrument import Instrument

from .repositories.instrument_repository import SqlAlchemyInstrumentRepository


async def bootstrap_instruments(session, instruments: Iterable[Instrument]) -> None:
    repository = SqlAlchemyInstrumentRepository(session)
    for instrument in instruments:
        await repository.save(instrument)
