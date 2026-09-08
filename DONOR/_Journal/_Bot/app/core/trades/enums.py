"""Trade domain enums."""

from enum import StrEnum


class TradeStatus(StrEnum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TradePnLSource(StrEnum):
    """The authoritative source used to validate a trade's realized PnL."""

    SNAPSHOT = "SNAPSHOT"
    EXECUTION_REPLAY = "EXECUTION_REPLAY"


class TradeDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


# Execution-side terminology is intentionally an alias of the existing
# BUY/SELL concept.  It must not be confused with TradeDirection (LONG/SHORT).
ExecutionSide = TradeSide


class TradingType(StrEnum):
    SINGLE_INSTRUMENT = "SINGLE_INSTRUMENT"
    SPREAD = "SPREAD"
    FUNDING = "FUNDING"


class EntryMethod(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ExitMethod(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
