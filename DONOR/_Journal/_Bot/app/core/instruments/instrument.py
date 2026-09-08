"""Human-readable instrument catalog entry."""

from dataclasses import dataclass

from .instrument_id import InstrumentId


@dataclass(frozen=True, slots=True)
class Instrument:
    """Stable catalog metadata for an internal InstrumentId."""

    instrument_id: InstrumentId
    symbol: str
    name: str
    exchange: str | None = None
    market: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise TypeError("instrument_id must be InstrumentId")
        symbol = self.symbol.strip().upper() if isinstance(self.symbol, str) else ""
        name = self.name.strip() if isinstance(self.name, str) else ""
        if not symbol:
            raise ValueError("symbol must not be empty")
        if not name:
            raise ValueError("name must not be empty")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "name", name)
        for field in ("exchange", "market"):
            value = getattr(self, field)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{field} must be non-empty when provided")
                object.__setattr__(self, field, value.strip().upper())
        if not isinstance(self.active, bool):
            raise TypeError("active must be bool")

    @property
    def label(self) -> str:
        context = " / ".join(item for item in (self.exchange, self.market) if item)
        return f"{self.symbol} — {self.name}" + (f" ({context})" if context else "")
