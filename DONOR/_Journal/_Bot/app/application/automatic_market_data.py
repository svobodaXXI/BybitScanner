"""Automatic trade snapshot contracts and lifecycle capture service.

The service deliberately stores observations through the generic Automatic
Data repository.  It does not add exploratory factors to ``trades`` and it
does not know anything about Bybit's wire format.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from decimal import Decimal
from typing import Mapping, Protocol, runtime_checkable

from app.core.automatic_data import (
    AutomaticFactorAvailability,
    AutomaticFactorDefinition,
    AutomaticFactorObservation,
    AutomaticFactorQuality,
    AutomaticFactorRegistry,
    AutomaticFactorSourceKind,
    AutomaticObservationValueType,
    CaptureSemantics,
    DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
)
from app.core.trades.enums import TradeStatus


@dataclass(frozen=True, slots=True)
class MarketDataPoint:
    """One normalized market value, including an explicit unavailable state."""

    value: Decimal | None
    unit: str | None = None
    currency: str | None = None
    quality_status: AutomaticFactorQuality = AutomaticFactorQuality.VALID
    availability_status: AutomaticFactorAvailability = AutomaticFactorAvailability.AVAILABLE
    source_timestamp: datetime | None = None
    provenance: Mapping[str, object] | str | None = None


@dataclass(frozen=True, slots=True)
class MarketDataSnapshot:
    """Exchange-neutral entry-time market snapshot."""

    instrument_id: object
    as_of: datetime
    points: Mapping[str, MarketDataPoint]
    provider_key: str = ""

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("market snapshot as_of must be timezone-aware")
        object.__setattr__(self, "as_of", self.as_of.astimezone(timezone.utc))
        object.__setattr__(self, "points", dict(self.points))


@dataclass(frozen=True, slots=True)
class PostTradeMarketContext:
    """Exchange-neutral facts required for a historical post-trade snapshot."""

    instrument_id: object
    direction: object
    opened_at: datetime
    closed_at: datetime | None
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", _utc(self.opened_at, "opened_at"))
        if self.closed_at is not None:
            object.__setattr__(self, "closed_at", _utc(self.closed_at, "closed_at"))
        object.__setattr__(self, "entry_price", Decimal(str(self.entry_price)))
        if self.exit_price is not None:
            object.__setattr__(self, "exit_price", Decimal(str(self.exit_price)))
        object.__setattr__(self, "quantity", Decimal(str(self.quantity)))


@dataclass(frozen=True, slots=True)
class PostTradeMarketSnapshot:
    """Exchange-neutral post-trade result; its window is not an entry snapshot."""

    instrument_id: object
    opened_at: datetime
    closed_at: datetime | None
    points: Mapping[str, MarketDataPoint]
    provider_key: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", _utc(self.opened_at, "opened_at"))
        if self.closed_at is not None:
            object.__setattr__(self, "closed_at", _utc(self.closed_at, "closed_at"))
        object.__setattr__(self, "points", dict(self.points))


@runtime_checkable
class AutomaticMarketDataProvider(Protocol):
    async def get_entry_snapshot(
        self,
        instrument_id,
        as_of: datetime,
        *,
        factor_ids: tuple[str, ...] = (),
    ) -> MarketDataSnapshot:
        """Return market values as of the trade's historical opened_at."""
        ...


@runtime_checkable
class PostTradeMarketDataProvider(Protocol):
    async def get_post_trade_snapshot(
        self,
        context: PostTradeMarketContext,
        *,
        factor_ids: tuple[str, ...] = (),
    ) -> PostTradeMarketSnapshot:
        """Return a historical post-trade market path snapshot."""
        ...


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AutomaticTradeDataCapture:
    """Capture built-in automatic factors for a Trade lifecycle transition."""

    def __init__(
        self,
        provider: AutomaticMarketDataProvider | None = None,
        registry: AutomaticFactorRegistry = DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
        *,
        entry_timezone: tzinfo | None = None,
    ) -> None:
        if not isinstance(registry, AutomaticFactorRegistry):
            raise TypeError("registry must be AutomaticFactorRegistry")
        if provider is not None and not isinstance(provider, AutomaticMarketDataProvider):
            raise TypeError("provider must implement AutomaticMarketDataProvider")
        if entry_timezone is not None and not isinstance(entry_timezone, tzinfo):
            raise TypeError("entry_timezone must be a tzinfo")
        self.provider = provider
        self.registry = registry
        self.entry_timezone = entry_timezone

    async def capture(self, trade, repository, *, captured_at: datetime | None = None) -> tuple[AutomaticFactorObservation, ...]:
        """Persist missing entry factors and close duration idempotently.

        A missing observation is eligible for a later retry.  A valid
        observation is immutable for its definition/calculation identity.
        """
        if repository is None:
            return ()
        existing = tuple(await repository.list_for_trade(trade.trade_id))
        by_identity = {
            (item.factor_id, item.definition_version, item.calculation_version, item.capture_semantics): item
            for item in existing
        }
        captured = _utc(captured_at or _now_utc(), "captured_at")
        result: list[AutomaticFactorObservation] = []

        entry_definitions = tuple(
            item for item in self.registry.list(active_only=True)
            if item.capture_semantics in {CaptureSemantics.AT_ENTRY, CaptureSemantics.PREVIOUS_CLOSED_BAR}
        )
        market_definitions = tuple(
            item for item in entry_definitions
            if item.source_kind is AutomaticFactorSourceKind.MARKET_DATA
        )
        missing_market_ids = tuple(
            item.factor_id for item in market_definitions
            if not _is_valid(by_identity.get(_identity(item)))
        )

        snapshot = None
        if missing_market_ids and self.provider is not None:
            try:
                snapshot = await self.provider.get_entry_snapshot(
                    trade.instrument_id,
                    trade.opened_at,
                    factor_ids=missing_market_ids,
                )
                if not isinstance(snapshot, MarketDataSnapshot):
                    raise TypeError("provider must return MarketDataSnapshot")
                if snapshot.instrument_id != trade.instrument_id:
                    raise ValueError("market snapshot instrument does not match Trade")
            except Exception as error:
                snapshot = _unavailable_snapshot(
                    trade.instrument_id,
                    trade.opened_at,
                    missing_market_ids,
                    provider_key=getattr(self.provider, "provider_key", ""),
                    reason=type(error).__name__,
                )

        for definition in entry_definitions:
            identity = _identity(definition)
            current = by_identity.get(identity)
            if _is_valid(current):
                continue
            if definition.source_kind is AutomaticFactorSourceKind.SYSTEM:
                observation = self._derived_entry_observation(definition, trade, captured)
            elif definition.source_kind is AutomaticFactorSourceKind.DERIVED:
                observation = self._derived_entry_observation(definition, trade, captured)
            elif snapshot is not None:
                point = snapshot.points.get(definition.factor_id)
                if point is None:
                    point = _missing_point(snapshot, definition.factor_id)
                observation = _market_observation(
                    definition, trade, captured, snapshot, point,
                )
            else:
                continue
            await repository.save(observation)
            result.append(observation)
            by_identity[identity] = observation

        post_market_definitions = tuple(
            item for item in self.registry.list(active_only=True)
            if item.capture_semantics is CaptureSemantics.POST_TRADE
            and item.source_kind is AutomaticFactorSourceKind.MARKET_DATA
        )
        post_snapshot = None
        if trade.status is TradeStatus.CLOSED and post_market_definitions:
            missing_post_ids = tuple(
                item.factor_id for item in post_market_definitions
                if not _is_valid(by_identity.get(_identity(item)))
            )
            if missing_post_ids and isinstance(self.provider, PostTradeMarketDataProvider):
                context = PostTradeMarketContext(
                    instrument_id=trade.instrument_id,
                    direction=trade.direction,
                    opened_at=trade.opened_at,
                    closed_at=trade.closed_at,
                    entry_price=trade.entry_price.value,
                    exit_price=None if trade.exit_price is None else trade.exit_price.value,
                    quantity=trade.quantity.value,
                )
                try:
                    post_snapshot = await self.provider.get_post_trade_snapshot(
                        context, factor_ids=missing_post_ids,
                    )
                    if not isinstance(post_snapshot, PostTradeMarketSnapshot):
                        raise TypeError("provider must return PostTradeMarketSnapshot")
                    if post_snapshot.instrument_id != trade.instrument_id:
                        raise ValueError("post-trade market snapshot instrument does not match Trade")
                except Exception as error:
                    post_snapshot = _unavailable_post_trade_snapshot(
                        context, missing_post_ids,
                        provider_key=getattr(self.provider, "provider_key", ""),
                        reason=type(error).__name__,
                    )

            if post_snapshot is not None:
                for definition in post_market_definitions:
                    identity = _identity(definition)
                    current = by_identity.get(identity)
                    if _is_valid(current):
                        continue
                    point = post_snapshot.points.get(definition.factor_id)
                    if point is None:
                        point = _missing_point(post_snapshot, definition.factor_id)
                    observation = _market_observation(
                        definition, trade, captured, post_snapshot, point,
                    )
                    await repository.save(observation)
                    result.append(observation)
                    by_identity[identity] = observation

        post_derived_definitions = tuple(
            item for item in self.registry.list(active_only=True)
            if item.capture_semantics is CaptureSemantics.POST_TRADE
            and item.source_kind is AutomaticFactorSourceKind.DERIVED
            and item.factor_id in _V5_FACTOR_IDS
        )
        if trade.status is TradeStatus.CLOSED and post_derived_definitions:
            v4_definition = self.registry.get("mfe_observed_1m_price_distance")
            v4_observation = (
                by_identity.get(_identity(v4_definition))
                if v4_definition is not None
                else None
            )
            for definition in post_derived_definitions:
                identity = _identity(definition)
                current = by_identity.get(identity)
                if _is_valid(current):
                    continue
                observation = _derive_exit_quality_observation(
                    definition, trade, captured, v4_definition, v4_observation,
                )
                await repository.save(observation)
                if current is None or _observation_changed(current, observation):
                    result.append(observation)
                by_identity[identity] = observation

        if trade.status is TradeStatus.CLOSED:
            definition = self.registry.get("holding_duration_seconds")
            if definition is not None and definition.active:
                identity = _identity(definition)
                current = by_identity.get(identity)
                if not _is_valid(current):
                    delta = trade.closed_at - trade.opened_at
                    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
                    observation = AutomaticFactorObservation(
                        trade_id=trade.trade_id,
                        factor_id=definition.factor_id,
                        definition_version=definition.definition_version,
                        calculation_version=definition.calculation_version,
                        value_type=definition.value_type,
                        value=Decimal(micros) / Decimal(1_000_000),
                        unit=definition.unit,
                        source_kind=definition.source_kind,
                        provider_key="SYSTEM",
                        capture_semantics=definition.capture_semantics,
                        captured_at=captured,
                        source_timestamp=trade.closed_at,
                        quality_status=AutomaticFactorQuality.VALID,
                        availability_status=AutomaticFactorAvailability.AVAILABLE,
                        provenance={"semantics": "closed_at - opened_at", "timezone": "UTC"},
                    )
                    await repository.save(observation)
                    result.append(observation)
        return tuple(result)

    def _derived_entry_observation(self, definition, trade, captured_at):
        opened_at = trade.opened_at.astimezone(self.entry_timezone or trade.opened_at.tzinfo)
        if definition.factor_id == "entry_hour":
            value = opened_at.hour
            provenance = {
                "timezone": _timezone_name(opened_at.tzinfo),
                "semantics": "legacy local-user hour of opened_at",
                "definition_version": definition.definition_version,
                "calculation_version": definition.calculation_version,
            }
        elif definition.factor_id == "entry_day_of_week":
            utc_opened_at = trade.opened_at.astimezone(timezone.utc)
            value = utc_opened_at.isoweekday()
            provenance = {"timezone": "UTC", "semantics": "ISO weekday Monday=1, Sunday=7"}
        else:
            raise ValueError(f"unsupported automatic derived factor: {definition.factor_id}")
        return AutomaticFactorObservation(
            trade_id=trade.trade_id,
            factor_id=definition.factor_id,
            definition_version=definition.definition_version,
            calculation_version=definition.calculation_version,
            value_type=AutomaticObservationValueType.INTEGER,
            value=value,
            unit=definition.unit,
            source_kind=definition.source_kind,
            provider_key="SYSTEM",
            capture_semantics=definition.capture_semantics,
            captured_at=captured_at,
            source_timestamp=trade.opened_at,
            provenance=provenance,
        )


def _identity(definition: AutomaticFactorDefinition):
    return (definition.factor_id, definition.definition_version, definition.calculation_version, definition.capture_semantics)


def _is_valid(observation) -> bool:
    return observation is not None and observation.value is not None and observation.quality_status is AutomaticFactorQuality.VALID


def _observation_changed(current, replacement) -> bool:
    return any(
        getattr(current, name) != getattr(replacement, name)
        for name in (
            "value", "quality_status", "availability_status", "source_timestamp", "provenance",
        )
    )


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timezone_name(value: tzinfo | None) -> str:
    if value is timezone.utc:
        return "UTC"
    return getattr(value, "key", None) or str(value)


def _missing_point(snapshot, factor_id: str) -> MarketDataPoint:
    return MarketDataPoint(
        value=None,
        quality_status=AutomaticFactorQuality.MISSING,
        availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        source_timestamp=None,
        provenance={"factor_id": factor_id, "reason": "provider omitted factor"},
    )


def _unavailable_snapshot(instrument_id, as_of, factor_ids, *, provider_key, reason):
    return MarketDataSnapshot(
        instrument_id=instrument_id,
        as_of=as_of,
        provider_key=provider_key or "UNKNOWN",
        points={
            factor_id: MarketDataPoint(
                value=None,
                quality_status=AutomaticFactorQuality.MISSING,
                availability_status=AutomaticFactorAvailability.TEMPORARILY_UNAVAILABLE,
                source_timestamp=None,
                provenance={"reason": reason},
            )
            for factor_id in factor_ids
        },
    )


def _unavailable_post_trade_snapshot(context, factor_ids, *, provider_key, reason):
    return PostTradeMarketSnapshot(
        instrument_id=context.instrument_id,
        opened_at=context.opened_at,
        closed_at=context.closed_at,
        provider_key=provider_key or "UNKNOWN",
        points={
            factor_id: MarketDataPoint(
                value=None,
                quality_status=AutomaticFactorQuality.MISSING,
                availability_status=AutomaticFactorAvailability.TEMPORARILY_UNAVAILABLE,
                source_timestamp=None,
                provenance={"reason": reason},
            )
            for factor_id in factor_ids
        },
    )


def _market_observation(definition, trade, captured_at, snapshot, point):
    value_type = AutomaticObservationValueType(definition.value_type)
    return AutomaticFactorObservation(
        trade_id=trade.trade_id,
        factor_id=definition.factor_id,
        definition_version=definition.definition_version,
        calculation_version=definition.calculation_version,
        value_type=value_type,
        value=point.value,
        unit=point.unit or definition.unit,
        currency=point.currency,
        source_kind=definition.source_kind,
        provider_key=snapshot.provider_key or "UNKNOWN",
        capture_semantics=definition.capture_semantics,
        captured_at=captured_at,
        source_timestamp=point.source_timestamp,
        quality_status=point.quality_status,
        availability_status=point.availability_status,
        provenance=point.provenance,
    )


_V5_SEMANTIC = "exit_quality_from_observed_1m_mfe_v1"
_V5_FACTOR_IDS = frozenset({
    "exit_directional_move_price_signed",
    "exit_directional_move_pct_signed",
    "exit_efficiency_pct_of_observed_mfe",
    "profit_capture_pct_of_observed_mfe",
    "mfe_giveback_price_distance",
    "mfe_giveback_pct_of_observed_mfe",
    "mfe_giveback_pct_of_entry",
    "mfe_giveback_gross_pnl_usdt",
})
_V5_MFE_DEPENDENT = frozenset({
    "exit_efficiency_pct_of_observed_mfe",
    "profit_capture_pct_of_observed_mfe",
    "mfe_giveback_price_distance",
    "mfe_giveback_pct_of_observed_mfe",
    "mfe_giveback_pct_of_entry",
    "mfe_giveback_gross_pnl_usdt",
})
_V5_FORMULAS = {
    "exit_directional_move_price_signed": "D; LONG: X - E; SHORT: E - X",
    "exit_directional_move_pct_signed": "D / E * 100",
    "exit_efficiency_pct_of_observed_mfe": "D / M * 100",
    "profit_capture_pct_of_observed_mfe": "max(D, 0) / M * 100",
    "mfe_giveback_price_distance": "M - D",
    "mfe_giveback_pct_of_observed_mfe": "(M - D) / M * 100",
    "mfe_giveback_pct_of_entry": "(M - D) / E * 100",
    "mfe_giveback_gross_pnl_usdt": "(M - D) * Q; fees/funding/expenses excluded",
}


def _derive_exit_quality_observation(definition, trade, captured_at, v4_definition, v4_observation):
    dependency = {
        "factor_id": "mfe_observed_1m_price_distance",
        "definition_version": None if v4_definition is None else v4_definition.definition_version,
        "calculation_version": None if v4_definition is None else v4_definition.calculation_version,
        "capture_semantics": None if v4_definition is None else v4_definition.capture_semantics.value,
        "source_timestamp": _iso(v4_observation.source_timestamp) if v4_observation is not None else None,
        "value": _provenance_value(v4_observation.value) if v4_observation is not None else None,
    }
    provenance = {
        "semantic": _V5_SEMANTIC,
        "dependency": dependency,
        "trade_facts": {
            "entry_price": _provenance_value(trade.entry_price.value),
            "exit_price": _provenance_value(None if trade.exit_price is None else trade.exit_price.value),
            "quantity": _provenance_value(trade.quantity.value),
            "direction": getattr(trade.direction, "value", trade.direction),
        },
        "formula": _V5_FORMULAS[definition.factor_id],
    }
    source_timestamp = trade.closed_at
    kwargs = {
        "trade_id": trade.trade_id,
        "factor_id": definition.factor_id,
        "definition_version": definition.definition_version,
        "calculation_version": definition.calculation_version,
        "value_type": AutomaticObservationValueType(definition.value_type),
        "unit": definition.unit,
        "source_kind": definition.source_kind,
        "provider_key": "DERIVED_AUTOMATIC_DATA",
        "capture_semantics": definition.capture_semantics,
        "captured_at": captured_at,
        "source_timestamp": source_timestamp,
    }

    direction = getattr(trade.direction, "value", trade.direction)
    if direction not in {"LONG", "SHORT"}:
        return AutomaticFactorObservation(
            **kwargs,
            value=None,
            quality_status=AutomaticFactorQuality.MISSING,
            availability_status=AutomaticFactorAvailability.NOT_APPLICABLE,
            provenance={**provenance, "reason": "unsupported trade direction"},
        )
    if trade.exit_price is None or v4_definition is None or not _is_valid(v4_observation):
        return AutomaticFactorObservation(
            **kwargs,
            value=None,
            quality_status=AutomaticFactorQuality.MISSING,
            availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
            provenance={**provenance, "reason": "current valid V4 MFE dependency is unavailable"},
        )

    entry_price = Decimal(str(trade.entry_price.value))
    exit_price = Decimal(str(trade.exit_price.value))
    quantity = Decimal(str(trade.quantity.value))
    mfe = Decimal(str(v4_observation.value))
    directional_move = exit_price - entry_price if direction == "LONG" else entry_price - exit_price
    if mfe < 0 and definition.factor_id in _V5_MFE_DEPENDENT:
        return _v5_error_observation(
            kwargs, {**provenance, "reason": "V4 MFE dependency is negative/corrupt"},
        )
    if directional_move > mfe and definition.factor_id in _V5_MFE_DEPENDENT:
        return _v5_error_observation(
            kwargs, {**provenance, "reason": "inconsistent dependency: D > M"},
        )
    if definition.factor_id == "exit_directional_move_price_signed":
        value = directional_move
    elif definition.factor_id == "exit_directional_move_pct_signed":
        if entry_price == 0:
            return _v5_missing_observation(kwargs, {**provenance, "reason": "entry price denominator is zero"})
        value = directional_move / entry_price * Decimal("100")
    elif definition.factor_id == "exit_efficiency_pct_of_observed_mfe":
        if mfe == 0:
            return _v5_missing_observation(kwargs, {**provenance, "reason": "MFE denominator is zero"})
        value = directional_move / mfe * Decimal("100")
    elif definition.factor_id == "profit_capture_pct_of_observed_mfe":
        if mfe == 0:
            return _v5_missing_observation(kwargs, {**provenance, "reason": "MFE denominator is zero"})
        value = max(directional_move, Decimal("0")) / mfe * Decimal("100")
    elif definition.factor_id == "mfe_giveback_price_distance":
        value = mfe - directional_move
    elif definition.factor_id == "mfe_giveback_pct_of_observed_mfe":
        if mfe == 0:
            return _v5_missing_observation(kwargs, {**provenance, "reason": "MFE denominator is zero"})
        value = (mfe - directional_move) / mfe * Decimal("100")
    elif definition.factor_id == "mfe_giveback_pct_of_entry":
        if entry_price == 0:
            return _v5_missing_observation(kwargs, {**provenance, "reason": "entry price denominator is zero"})
        value = (mfe - directional_move) / entry_price * Decimal("100")
    elif definition.factor_id == "mfe_giveback_gross_pnl_usdt":
        value = (mfe - directional_move) * quantity
    else:
        raise ValueError(f"unsupported exit-quality factor: {definition.factor_id}")
    return _v5_value_observation(kwargs, value, provenance)


def _v5_value_observation(kwargs, value, provenance):
    return AutomaticFactorObservation(
        **kwargs,
        value=value,
        quality_status=AutomaticFactorQuality.VALID,
        availability_status=AutomaticFactorAvailability.AVAILABLE,
        provenance=provenance,
    )


def _v5_missing_observation(kwargs, provenance):
    return AutomaticFactorObservation(
        **kwargs,
        value=None,
        quality_status=AutomaticFactorQuality.MISSING,
        availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        provenance=provenance,
    )


def _v5_error_observation(kwargs, provenance):
    return AutomaticFactorObservation(
        **kwargs,
        value=None,
        quality_status=AutomaticFactorQuality.ERROR,
        availability_status=AutomaticFactorAvailability.ERROR,
        provenance=provenance,
    )


def _iso(value):
    return None if value is None else value.isoformat()


def _provenance_value(value):
    return None if value is None else str(value)
