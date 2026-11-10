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

from .models import AllocationRole, TradeEpisode
from .scoped_statistics_archive import ORIGINS, StatisticsScopeError
from .scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import TradingAccountId

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



def _classified_finrez_episodes(
    snapshot: PaperSourceSnapshot, *, account_id: str,
) -> tuple[tuple[TradeEpisode, ...], tuple[TradeEpisode, ...], tuple[TradeEpisode, ...]]:
    """Classify whole episodes, not individual fills or split economic PnL.

    A robot-opened episode finished by a proven manual CLOSE is reported only
    as a distinct intervention cohort, never as an autonomous robot result.
    Unknown origin, manual increases, reversed ownership and other mixed
    episodes remain unavailable rather than guessed.
    """
    robot: list[TradeEpisode] = []
    manual: list[TradeEpisode] = []
    assisted: list[TradeEpisode] = []
    seen_ids: set[str] = set()
    for episode in snapshot.episodes:
        if not isinstance(episode, TradeEpisode):
            raise StatisticsScopeError("invalid_trade_episode")
        if episode.position_key.trading_account_id != TradingAccountId(account_id):
            raise StatisticsScopeError("cross_account_statistics_evidence")
        if episode.trade_episode_id.value in seen_ids:
            raise StatisticsScopeError("duplicate_trade_episode")
        seen_ids.add(episode.trade_episode_id.value)

        attributed: list[str] = []
        for allocation in episode.allocations:
            if (allocation.execution_key.trading_account_id != TradingAccountId(account_id)
                    or allocation.trade_episode_id != episode.trade_episode_id):
                raise StatisticsScopeError("cross_account_statistics_evidence")
            mapped = ORIGINS.get(snapshot.origins.get(allocation.execution_key))
            if mapped is None:
                raise StatisticsScopeError("unattributed_statistics_evidence")
            attributed.append(mapped)

        owners = set(attributed)
        if owners == {"ROBOT"}:
            robot.append(episode)
        elif owners == {"MANUAL"}:
            manual.append(episode)
        elif (
            episode.is_closed
            and owners == {"ROBOT", "MANUAL"}
            and attributed[0] == "ROBOT"
            and episode.allocations[0].role in {AllocationRole.OPEN, AllocationRole.REVERSAL_OPEN}
            and attributed[-1] == "MANUAL"
            and episode.allocations[-1].role is AllocationRole.CLOSE
            and all(
                controller == "ROBOT"
                or allocation.role in {AllocationRole.REDUCE, AllocationRole.CLOSE}
                for controller, allocation in zip(attributed, episode.allocations)
            )
        ):
            assisted.append(episode)
        else:
            raise StatisticsScopeError("mixed_controller_trade_episode")
    return tuple(robot), tuple(manual), tuple(assisted)


def project_paper_ticker_pnl(
    snapshot: PaperSourceSnapshot, *, account_id: str, owner: str,
    period: str, now_ms: int,
) -> dict[str, object]:
    """Use the existing strict execution-origin attribution before summing."""
    if account_id != "paper" or owner not in {"ROBOT", "MANUAL"}:
        raise ValueError("unsupported_finrez_scope")
    robot, manual, assisted = _classified_finrez_episodes(
        snapshot, account_id=account_id,
    )
    start_ms, tickers = aggregate_ticker_pnl(
        robot if owner == "ROBOT" else manual, period=period, now_ms=now_ms,
    )
    _, manual_interventions = aggregate_ticker_pnl(
        assisted if owner == "ROBOT" else (), period=period, now_ms=now_ms,
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
        "manual_interventions": manual_interventions,
    }
