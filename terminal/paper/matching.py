"""Deterministic PAPER market-order matching against normalized L2."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from terminal.domain.models import OrderSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook


class PaperBookUnavailable(RuntimeError):
    pass


class PaperInsufficientLiquidity(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PaperFill:
    price: Price
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class PaperMarketMatch:
    symbol: Symbol
    side: OrderSide
    requested_quantity: Quantity
    filled_quantity: Quantity
    vwap: Price
    fills: tuple[PaperFill, ...]


@dataclass(frozen=True, slots=True)
class PaperLimitMatch:
    symbol: Symbol
    side: OrderSide
    limit_price: Price
    requested_remaining_quantity: Quantity
    filled_quantity: Quantity
    remaining_quantity: Quantity
    vwap: Price
    fills: tuple[PaperFill, ...]

    @property
    def fully_filled(self) -> bool:
        return self.remaining_quantity.value == 0


def match_market_order(
    book: NormalizedOrderBook,
    *,
    side: OrderSide,
    quantity: Quantity,
) -> PaperMarketMatch:
    if book.health is not BookHealth.READY:
        raise PaperBookUnavailable(f"book is not READY: {book.health.value}")
    if quantity.value <= 0:
        raise ValueError("market quantity must be positive")

    levels = book.asks if side is OrderSide.BUY else book.bids
    remaining = quantity.value
    fills: list[PaperFill] = []

    for level in levels:
        if remaining <= 0:
            break
        take = min(remaining, level.quantity.value)
        if take <= 0:
            continue
        fills.append(PaperFill(level.price, Quantity(take)))
        remaining -= take

    if remaining > 0:
        raise PaperInsufficientLiquidity("normalized book cannot fill requested quantity")

    filled = sum((fill.quantity.value for fill in fills), Decimal("0"))
    notional = sum(
        (fill.price.value * fill.quantity.value for fill in fills),
        Decimal("0"),
    )
    vwap = notional / filled

    return PaperMarketMatch(
        symbol=book.symbol,
        side=side,
        requested_quantity=quantity,
        filled_quantity=Quantity(filled),
        vwap=Price(vwap),
        fills=tuple(fills),
    )


def match_limit_order(
    book: NormalizedOrderBook,
    *,
    side: OrderSide,
    limit_price: Price,
    remaining_quantity: Quantity,
) -> PaperLimitMatch | None:
    """Match one active PAPER Limit only against executable opposite L2 levels."""

    if book.health is not BookHealth.READY:
        raise PaperBookUnavailable(f"book is not READY: {book.health.value}")
    if remaining_quantity.value <= 0:
        raise ValueError("remaining limit quantity must be positive")

    levels = book.asks if side is OrderSide.BUY else book.bids
    remaining = remaining_quantity.value
    fills: list[PaperFill] = []

    for level in levels:
        executable = (
            level.price.value <= limit_price.value
            if side is OrderSide.BUY
            else level.price.value >= limit_price.value
        )
        if not executable:
            break
        take = min(remaining, level.quantity.value)
        if take <= 0:
            continue
        fills.append(PaperFill(level.price, Quantity(take)))
        remaining -= take
        if remaining == 0:
            break

    if not fills:
        return None

    filled = remaining_quantity.value - remaining
    notional = sum(
        (fill.price.value * fill.quantity.value for fill in fills),
        Decimal("0"),
    )
    return PaperLimitMatch(
        symbol=book.symbol,
        side=side,
        limit_price=limit_price,
        requested_remaining_quantity=remaining_quantity,
        filled_quantity=Quantity(filled),
        remaining_quantity=Quantity(remaining),
        vwap=Price(notional / filled),
        fills=tuple(fills),
    )
