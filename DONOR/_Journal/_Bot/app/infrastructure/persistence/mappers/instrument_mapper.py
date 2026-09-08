"""Instrument catalog mapper."""

from datetime import datetime, timezone

from app.core.instruments.instrument import Instrument
from app.core.instruments.instrument_id import InstrumentId

from ..models.instrument import InstrumentORM


def instrument_to_orm(instrument: Instrument) -> InstrumentORM:
    if not isinstance(instrument, Instrument):
        raise TypeError("instrument must be Instrument")
    return InstrumentORM(
        id=instrument.instrument_id.value,
        symbol=instrument.symbol,
        name=instrument.name,
        exchange=instrument.exchange,
        market=instrument.market,
        active=instrument.active,
        created_at=datetime.now(timezone.utc),
    )


def instrument_from_orm(model: InstrumentORM) -> Instrument:
    if not isinstance(model, InstrumentORM):
        raise TypeError("model must be InstrumentORM")
    return Instrument(
        instrument_id=InstrumentId(model.id),
        symbol=model.symbol,
        name=model.name,
        exchange=model.exchange,
        market=model.market,
        active=model.active,
    )
