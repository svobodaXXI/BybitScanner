"""Read-only, controller-attributed ticker PnL for the first Finrez screen.

PnL here is *known-cost-adjusted realized* PnL: price PnL minus persisted
execution fees. It is not full equity or an assertion that all external costs
(funding etc.) are known. Open positions are intentionally excluded.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

from .models import TradeEpisode
from .scoped_statistics_archive import _attributed_episodes
from .scoped_statistics_reporter import PaperSourceSnapshot

_MSK = ZoneInfo("Europe/Moscow")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_PERIODS = frozenset({"TODAY", "ALL"})


def period_start_ms(*, period: str, now_ms: int) -> int:
    if period not in _PERIODS or type(now_ms) is not int or now_ms < 0:
        raise ValueError("invalid_finrez_period")
    if period == "ALL":
        return 0
    msk_now = (_EPOCH + timedelta(milliseconds=now_ms)).astimezone(_MSK)
    msk_midnight = msk_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((msk_midnight.astimezone(timezone.utc) - _EPOCH).total_seconds() * 1000)


def aggregate_ticker_pnl(
    episodes: Iterable[TradeEpisode], *, period: str, now_ms: int,
) -> tuple[int, list[dict[str, object]]]:
    """Rank closed episodes by close timestamp, never by entry or device time."""
    start_ms = period_start_ms(period=period, now_ms=now_ms)
    totals: dict[str, tuple[Decimal, int]] = {}
    for episode in episodes:
        closed_at = episode.closed_at_ms
        if closed_at is None or not (start_ms <= closed_at <= now_ms):
            continue
        # TradeEpisode guarantees finite, allocation-derived Decimal amounts.
        pnl = episode.realized_price_pnl - episode.execution_fees
        if not pnl.is_finite():
            raise ValueError("invalid_finrez_pnl")
        symbol = episode.position_key.symbol.value
        total, count = totals.get(symbol, (Decimal("0"), 0))
        totals[symbol] = (total + pnl, count + 1)
    ranked = sorted(totals.items(), key=lambda item: (-item[1][0], item[0]))
    return start_ms, [
        {"symbol": symbol, "pnl_usdt": str(total), "trade_count": count}
        for symbol, (total, count) in ranked
    ]


def project_paper_ticker_pnl(
    snapshot: PaperSourceSnapshot, *, account_id: str, owner: str,
    period: str, now_ms: int,
) -> dict[str, object]:
    """Use the existing strict execution-origin attribution before summing."""
    if account_id != "paper" or owner not in {"ROBOT", "MANUAL"}:
        raise ValueError("unsupported_finrez_scope")
    attributed = _attributed_episodes(
        account_id, owner, snapshot.episodes, snapshot.origins,
    )
    start_ms, tickers = aggregate_ticker_pnl(
        attributed, period=period, now_ms=now_ms,
    )
    return {
        "account_id": account_id,
        "owner": owner,
        "period": period,
        "period_start_ms": start_ms,
        "as_of_ms": now_ms,
        "source_revision": snapshot.source_revision,
        "source": "PAPER_EXECUTIONS_ATTRIBUTED",
        "pnl_basis": "REALIZED_PRICE_MINUS_EXECUTION_FEES",
        "tickers": tickers,
    }
