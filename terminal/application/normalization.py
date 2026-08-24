"""Decimal-only pre-trade normalization helpers with no exchange side effects."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from terminal.domain.models import OrderSide


class NormalizationError(ValueError):
    """Raised internally when deterministic numeric normalization is impossible."""


class WorkingVolumeOvershootError(NormalizationError):
    """Raised when nearest-step Working Volume sizing exceeds its overshoot limit."""


def require_positive_decimal(value: Decimal, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise NormalizationError(f"{field_name} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise NormalizationError(f"{field_name} must be finite and positive")
    return value


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    value = require_positive_decimal(value, "value")
    step = require_positive_decimal(step, "step")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def normalize_quantity(requested_notional: Decimal, reference_price: Decimal, qty_step: Decimal) -> tuple[Decimal, Decimal]:
    requested_notional = require_positive_decimal(requested_notional, "requested notional")
    reference_price = require_positive_decimal(reference_price, "reference price")
    raw_quantity = requested_notional / reference_price
    normalized_quantity = floor_to_step(raw_quantity, qty_step)
    return raw_quantity, normalized_quantity


def normalize_working_volume_market_quantity(
    requested_notional: Decimal,
    reference_price: Decimal,
    qty_step: Decimal,
    max_overshoot_ratio: Decimal = Decimal("0.10"),
) -> tuple[Decimal, Decimal]:
    requested_notional = require_positive_decimal(requested_notional, "requested notional")
    reference_price = require_positive_decimal(reference_price, "reference price")
    qty_step = require_positive_decimal(qty_step, "quantity step")
    if (
        not isinstance(max_overshoot_ratio, Decimal)
        or not max_overshoot_ratio.is_finite()
        or max_overshoot_ratio < 0
    ):
        raise NormalizationError("maximum overshoot ratio must be a finite non-negative Decimal")

    raw_quantity = requested_notional / reference_price
    floor_candidate = floor_to_step(raw_quantity, qty_step)
    if floor_candidate == raw_quantity:
        return raw_quantity, floor_candidate

    ceil_candidate = floor_candidate + qty_step
    if raw_quantity - floor_candidate <= ceil_candidate - raw_quantity:
        return raw_quantity, floor_candidate

    candidate_notional = ceil_candidate * reference_price
    overshoot_ratio = (candidate_notional - requested_notional) / requested_notional
    if overshoot_ratio > max_overshoot_ratio:
        raise WorkingVolumeOvershootError(
            "nearest Working Volume quantity exceeds maximum rounding overshoot"
        )
    return raw_quantity, ceil_candidate


def normalize_limit_price(price: Decimal, tick_size: Decimal, side: OrderSide) -> Decimal:
    price = require_positive_decimal(price, "limit price")
    tick_size = require_positive_decimal(tick_size, "tick size")
    rounding = ROUND_FLOOR if side is OrderSide.BUY else ROUND_CEILING
    return (price / tick_size).to_integral_value(rounding=rounding) * tick_size
