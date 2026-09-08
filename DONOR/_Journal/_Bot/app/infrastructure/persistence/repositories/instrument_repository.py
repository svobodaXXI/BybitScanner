"""SQLAlchemy adapter for the human-readable Instrument catalog."""

from sqlalchemy import case, func, or_, select, update

from app.application.ports.repositories import InstrumentRepository
from app.core.instruments.instrument import Instrument
from app.core.instruments.instrument_id import InstrumentId

from ..mappers import instrument_from_orm, instrument_to_orm
from ..models.instrument import InstrumentORM
from ._common import require_session


class SqlAlchemyInstrumentRepository(InstrumentRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def search(self, query: str, *, limit: int = 20) -> tuple[Instrument, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")
        normalized = query.strip().upper()
        pattern = f"%{normalized}%"
        statement = (
            select(InstrumentORM)
            .where(
                InstrumentORM.active.is_(True),
                or_(
                    InstrumentORM.symbol.ilike(pattern),
                    InstrumentORM.name.ilike(pattern),
                    InstrumentORM.exchange.ilike(pattern),
                    InstrumentORM.market.ilike(pattern),
                ),
            )
            .order_by(
                case((func.upper(InstrumentORM.symbol) == normalized, 0), else_=1),
                InstrumentORM.symbol.asc(),
                InstrumentORM.name.asc(),
                InstrumentORM.id.asc(),
            )
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return tuple(instrument_from_orm(model) for model in result.scalars().all())

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        if not isinstance(instrument_id, InstrumentId):
            raise TypeError("instrument_id must be InstrumentId")
        model = await self._session.scalar(select(InstrumentORM).where(InstrumentORM.id == instrument_id.value))
        return None if model is None else instrument_from_orm(model)

    async def get_by_ids(self, instrument_ids) -> tuple[Instrument, ...]:
        """Bulk-load the human-readable identities for one bounded trade page."""
        ids = tuple(instrument_ids)
        if any(not isinstance(item, InstrumentId) for item in ids):
            raise TypeError("instrument_ids must contain InstrumentId values")
        if not ids:
            return ()
        result = await self._session.execute(
            select(InstrumentORM)
            .where(InstrumentORM.id.in_([item.value for item in ids]))
            .order_by(InstrumentORM.symbol.asc(), InstrumentORM.id.asc())
        )
        return tuple(instrument_from_orm(model) for model in result.scalars().all())

    async def get_by_exchange_symbol(
        self,
        exchange: str,
        symbol: str,
        *,
        active_only: bool = True,
    ) -> tuple[Instrument, ...]:
        if not isinstance(exchange, str) or not exchange.strip():
            raise ValueError("exchange must be a non-empty string")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        statement = (
            select(InstrumentORM)
            .where(
                func.upper(InstrumentORM.exchange) == exchange.strip().upper(),
                func.upper(InstrumentORM.symbol) == symbol.strip().upper(),
            )
            .order_by(InstrumentORM.id.asc())
        )
        if active_only:
            statement = statement.where(InstrumentORM.active.is_(True))
        result = await self._session.execute(statement)
        return tuple(instrument_from_orm(model) for model in result.scalars().all())

    async def save(self, instrument: Instrument) -> None:
        """Explicit infrastructure-only bootstrap/upsert hook; never called by Telegram."""
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        existing = await self._session.scalar(select(InstrumentORM).where(InstrumentORM.id == instrument.instrument_id.value))
        if existing is None:
            existing = await self._session.scalar(
                select(InstrumentORM).where(
                    func.upper(InstrumentORM.symbol) == instrument.symbol,
                    func.upper(InstrumentORM.exchange) == instrument.exchange,
                    func.upper(InstrumentORM.market) == instrument.market,
                )
            )
        if existing is None:
            self._session.add(instrument_to_orm(instrument))
        else:
            existing.symbol = instrument.symbol
            existing.name = instrument.name
            existing.exchange = instrument.exchange
            existing.market = instrument.market
            existing.active = instrument.active
        await self._session.flush()

    async def deactivate_missing(self, exchange: str, market: str, active_symbols) -> int:
        """Mark catalog entries absent from an explicit sync inactive, never delete."""
        symbols = tuple(item.strip().upper() for item in active_symbols if isinstance(item, str) and item.strip())
        if not symbols:
            return 0
        result = await self._session.execute(
            update(InstrumentORM)
            .where(
                func.upper(InstrumentORM.exchange) == exchange.strip().upper(),
                func.upper(InstrumentORM.market) == market.strip().upper(),
                ~func.upper(InstrumentORM.symbol).in_(symbols),
                InstrumentORM.active.is_(True),
            )
            .values(active=False)
        )
        await self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)
