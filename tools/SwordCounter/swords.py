"""SwordCounter S2: working-volume count ("swords") from the Bybit entry notional.

Rules
-----
- ``total_swords`` swords (default 20). Live, one sword (1 RO) = Account Equity / total swords,
  rounded half up to whole USDT (``count_swords_with_equity``); unknown or non-positive equity, or
  an RO that rounds to 0, makes the count unavailable instead of guessing.
- Working volume is the sum of ``size x avgPrice`` (USDT entry notional, not divided by leverage)
  over every open position from S1. ``positionValue`` (by mark price) and ``positionIM`` (margin)
  are not used for the count.
- used swords = ceil(total working volume / sword size); free = max(0, total - used).
  Over the limit is shown, not hidden: used may exceed the total while free stays 0.
- Exact Decimal arithmetic only.
- If the entry price of any open position is unknown, not positive, or not in USDT, the result is
  "Недоступно" with no numbers. A Bybit read error is "Нет соединения", never zero swords.

Value in another settle coin (e.g. USDC) is not converted: treating it as USDT would be a
guess, so the count is unavailable instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
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
    sword_size_usdt: Decimal | None   # None when the RO could not be derived
    positions_count: int | None    # None when positions could not be read
    occupied_margin_usdt: Decimal | None = None   # working volume: sum of size x avgPrice, USDT
    used_swords: int | None = None
    free_swords: int | None = None
    over_limit: bool | None = None
    unknown_margin_symbols: tuple[str, ...] = field(default=())
    reason: str = ""
    equity_usdt: Decimal | None = None   # Account Equity the RO was derived from (None: unknown)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]


def count_swords(positions: Iterable[OpenPosition], settings: SwordSettings) -> SwordCount:
    """Pure count over already-read open positions."""
    positions = tuple(positions)
    base = dict(total_swords=settings.total_swords, sword_size_usdt=settings.sword_size_usdt,
                positions_count=len(positions))
    unknown = tuple(p.symbol for p in positions if p.avg_price is None or p.size is None)
    if unknown:
        return SwordCount(STATUS_UNAVAILABLE, unknown_margin_symbols=unknown,
                          reason="entry notional (size x avgPrice) is unknown for: " + ", ".join(unknown), **base)
    other_coin = tuple(p.symbol for p in positions if p.settle_coin != MARGIN_COIN)
    if other_coin:
        return SwordCount(STATUS_UNAVAILABLE, unknown_margin_symbols=other_coin,
                          reason=f"entry notional is not in {MARGIN_COIN} for: " + ", ".join(other_coin), **base)
    negative = tuple(p.symbol for p in positions if p.avg_price <= 0 or p.size <= 0)
    if negative:
        return SwordCount(STATUS_UNAVAILABLE, unknown_margin_symbols=negative,
                          reason="non-positive size or avgPrice for: " + ", ".join(negative), **base)

    with localcontext() as ctx:
        ctx.prec = 200  # exact for any realistic margin; avoids rounding near a boundary
        occupied = sum((p.size * p.avg_price for p in positions), Decimal("0"))
        used = int((occupied / settings.sword_size_usdt).to_integral_value(rounding=ROUND_CEILING))
    return SwordCount(STATUS_OK, occupied_margin_usdt=occupied, used_swords=used,
                      free_swords=max(0, settings.total_swords - used),
                      over_limit=used > settings.total_swords, **base)


def ro_from_equity(equity: Decimal, total_swords: int) -> Decimal | None:
    """1 RO = Account Equity / total swords, ROUND_HALF_UP to whole USDT; None if not positive."""
    if not equity.is_finite() or equity <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 200
        ro = (equity / Decimal(total_swords)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return ro if ro > 0 else None


def count_swords_with_equity(fetch_positions: Callable[[], Iterable[OpenPosition]],
                             fetch_equity: Callable[[], Decimal], total_swords: int) -> SwordCount:
    """Read Account Equity and positions now; RO = equity / total swords. Never a guessed RO."""
    if isinstance(total_swords, bool) or not isinstance(total_swords, int) or total_swords <= 0:
        raise ValueError("total_swords must be a positive integer")
    failure = None
    try:
        equity = fetch_equity()
        positions = tuple(fetch_positions())
    except BybitPositionsError as error:
        failure = f"{type(error).__name__}: {error}"
    if failure is not None:
        return SwordCount(STATUS_NO_CONNECTION, total_swords=total_swords, sword_size_usdt=None,
                          positions_count=None, reason=failure)
    ro = ro_from_equity(equity, total_swords)
    if ro is None:
        why = ("Account Equity is not positive" if equity <= 0 else
               f"1 RO = {equity} / {total_swords} rounds to 0 USDT (minimum RO rule not agreed)")
        return SwordCount(STATUS_UNAVAILABLE, total_swords=total_swords, sword_size_usdt=None,
                          positions_count=len(positions), reason=why, equity_usdt=equity)
    result = count_swords(positions, SwordSettings(total_swords=total_swords, sword_size_usdt=ro))
    return replace(result, equity_usdt=equity)


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
