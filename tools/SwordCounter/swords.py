"""SwordCounter S2: working-volume count ("swords") from Bybit occupied margin.

Rules
-----
- ``total_swords`` swords of ``sword_size_usdt`` each (default 20 x 5 USDT), both configurable.
- Occupied margin is the sum of ``positionIM`` over every open position from S1.
- used swords = ceil(total occupied margin / sword size); free = max(0, total - used).
  Over the limit is shown, not hidden: used may exceed the total while free stays 0.
- Exact Decimal arithmetic only.
- If the margin of any open position is unknown, not in USDT, or negative, the result is
  "Недоступно" with no numbers. A Bybit read error is "Нет соединения", never zero swords.

Margin in another settle coin (e.g. USDC) is not converted: treating it as USDT would be a
guess, so the count is unavailable instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from typing import Callable, Iterable

from tools.SwordCounter.bybit_positions import BybitPositionsError, OpenPosition

DEFAULT_TOTAL_SWORDS = 20
DEFAULT_SWORD_SIZE_USDT = Decimal("5")
MARGIN_COIN = "USDT"

STATUS_OK = "OK"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_NO_CONNECTION = "NO_CONNECTION"
STATUS_LABELS = {
    STATUS_OK: "Доступно",
    STATUS_UNAVAILABLE: "Недоступно",
    STATUS_NO_CONNECTION: "Нет соединения",
}


@dataclass(frozen=True)
class SwordSettings:
    total_swords: int = DEFAULT_TOTAL_SWORDS
    sword_size_usdt: Decimal = DEFAULT_SWORD_SIZE_USDT

    def __post_init__(self) -> None:
        total = self.total_swords
        if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
            raise ValueError("total_swords must be a positive integer")
        size = self.sword_size_usdt
        if isinstance(size, bool) or not isinstance(size, (Decimal, int, str)):
            raise ValueError("sword_size_usdt must be a positive USDT amount (Decimal, int or str)")
        try:
            size = Decimal(size.strip()) if isinstance(size, str) else Decimal(size)
        except InvalidOperation:
            raise ValueError("sword_size_usdt must be a positive USDT amount") from None
        if not size.is_finite() or size <= 0:
            raise ValueError("sword_size_usdt must be a positive USDT amount")
        object.__setattr__(self, "sword_size_usdt", size)


@dataclass(frozen=True)
class SwordCount:
    status: str
    total_swords: int
    sword_size_usdt: Decimal
    positions_count: int | None    # None when positions could not be read
    occupied_margin_usdt: Decimal | None = None
    used_swords: int | None = None
    free_swords: int | None = None
    over_limit: bool | None = None
    unknown_margin_symbols: tuple[str, ...] = field(default=())
    reason: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]


def count_swords(positions: Iterable[OpenPosition], settings: SwordSettings) -> SwordCount:
    """Pure count over already-read open positions."""
    positions = tuple(positions)
    base = dict(total_swords=settings.total_swords, sword_size_usdt=settings.sword_size_usdt,
                positions_count=len(positions))
    unknown = tuple(p.symbol for p in positions if p.position_im is None)
    if unknown:
        return SwordCount(STATUS_UNAVAILABLE, unknown_margin_symbols=unknown,
                          reason="margin (positionIM) is unknown for: " + ", ".join(unknown), **base)
    other_coin = tuple(p.symbol for p in positions if p.settle_coin != MARGIN_COIN)
    if other_coin:
        return SwordCount(STATUS_UNAVAILABLE, unknown_margin_symbols=other_coin,
                          reason=f"margin is not in {MARGIN_COIN} for: " + ", ".join(other_coin), **base)
    negative = tuple(p.symbol for p in positions if p.position_im < 0)
    if negative:
        return SwordCount(STATUS_UNAVAILABLE, unknown_margin_symbols=negative,
                          reason="negative margin (positionIM) for: " + ", ".join(negative), **base)

    with localcontext() as ctx:
        ctx.prec = 200  # exact for any realistic margin; avoids rounding near a boundary
        occupied = sum((p.position_im for p in positions), Decimal("0"))
        used = int((occupied / settings.sword_size_usdt).to_integral_value(rounding=ROUND_CEILING))
    return SwordCount(STATUS_OK, occupied_margin_usdt=occupied, used_swords=used,
                      free_swords=max(0, settings.total_swords - used),
                      over_limit=used > settings.total_swords, **base)


def count_swords_from_api(fetch_positions: Callable[[], Iterable[OpenPosition]],
                          settings: SwordSettings) -> SwordCount:
    """Read positions now (no cache) and count. A Bybit read failure is "Нет соединения"."""
    failure = None
    try:
        positions = tuple(fetch_positions())
    except BybitPositionsError as error:
        # S1 errors carry no secrets; keep the class and message for the operator.
        failure = f"{type(error).__name__}: {error}"
    if failure is not None:
        return SwordCount(STATUS_NO_CONNECTION, total_swords=settings.total_swords,
                          sword_size_usdt=settings.sword_size_usdt, positions_count=None, reason=failure)
    return count_swords(positions, settings)
