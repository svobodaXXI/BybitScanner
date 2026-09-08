"""Infrastructure errors translated from Bybit transport/API failures."""


class BybitError(RuntimeError):
    """Base class for safe, secret-free Bybit adapter errors."""


class BybitAuthenticationError(BybitError):
    """Bybit rejected authentication or API-key permissions."""


class BybitRateLimitError(BybitError):
    """Bybit or an intermediary rate-limited the request."""


class BybitRequestError(BybitError):
    """Transient or otherwise unsuccessful HTTP transport failure."""


class BybitPayloadError(BybitError):
    """Malformed or semantically unsupported Bybit response/payload."""


class BybitInstrumentMappingError(BybitPayloadError):
    """A Bybit symbol has no unique active Journal instrument mapping."""
