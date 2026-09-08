"""Persistence-neutral application errors."""


class ApplicationError(ValueError):
    """Base class for meaningful application-layer failures."""


class AccountNotFoundError(ApplicationError):
    """The requested account does not exist."""


class TradeNotFoundError(ApplicationError):
    """The requested trade does not exist."""


class TradeAlreadyClosedError(ApplicationError):
    """A close operation was requested for a trade that is not open."""


class CustomFieldNotFoundError(ApplicationError):
    """The requested custom-field definition does not exist."""


class CustomFieldNotManualError(ApplicationError):
    """Manual input was requested for an automatically populated field."""


class CustomFieldNotApplicableError(ApplicationError):
    """The custom field is not active or does not match the collection context."""


class InvalidCustomFieldValueError(ApplicationError):
    """A manual custom-field value violates its definition or option catalog."""


class PersistenceIntegrityError(ValueError):
    """Persisted data violates a Domain or relational integrity invariant."""


class DuplicateExecutionError(PersistenceIntegrityError):
    """An execution identity is already present."""


class ExecutionFactConflictError(PersistenceIntegrityError):
    """An external execution identity was replayed with different facts."""


class InvalidExecutionFactError(ApplicationError):
    """A normalized external execution fact is not importable."""


class InstrumentMappingNotFoundError(ApplicationError):
    """The normalized fact points to no existing Journal instrument."""


class AmbiguousOpenTradeError(ApplicationError):
    """More than one OPEN Trade could match an execution."""


class UnsupportedPositionReversalError(ApplicationError):
    """Current aggregation policy cannot safely process an over-close reversal."""


class UnsafeHistoricalBoundaryError(ApplicationError):
    """Historical import needs an explicit acknowledgement of a mid-position boundary."""


class HistoricalPreviewError(ApplicationError):
    """Safe preview failure that retains the detailed cause in chained logs."""

    def __init__(self, stage: str, code: str, detail: str = "") -> None:
        self.stage = stage
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class DuplicateTradeCustomValueError(PersistenceIntegrityError):
    """A historical trade/field/version value already exists."""


class MarketDataUnavailableError(ApplicationError):
    """The provider cannot currently supply the requested normalized snapshot."""


class MarketDataMappingError(ApplicationError):
    """An instrument cannot be mapped to the provider's market identity."""


class MarketDataPayloadError(ApplicationError):
    """Provider output cannot be normalized into MarketDataContext."""


class CustomFieldSemanticMutationError(PersistenceIntegrityError):
    """A persisted custom field's semantic definition was changed."""


__all__ = [
    "AccountNotFoundError",
    "ApplicationError",
    "CustomFieldNotApplicableError",
    "CustomFieldNotFoundError",
    "CustomFieldNotManualError",
    "CustomFieldSemanticMutationError",
    "DuplicateExecutionError",
    "ExecutionFactConflictError",
    "InstrumentMappingNotFoundError",
    "InvalidExecutionFactError",
    "AmbiguousOpenTradeError",
    "UnsupportedPositionReversalError",
    "UnsafeHistoricalBoundaryError",
    "HistoricalPreviewError",
    "DuplicateTradeCustomValueError",
    "InvalidCustomFieldValueError",
    "MarketDataMappingError",
    "MarketDataPayloadError",
    "MarketDataUnavailableError",
    "PersistenceIntegrityError",
    "TradeAlreadyClosedError",
    "TradeNotFoundError",
]
