"""Read-only Trading Diary D6.1 list projection.

The presentation layer consumes the existing TradeEpisode and D3 readiness
semantics. It never reconstructs executions independently and never mutates
Terminal authority.
"""

from __future__ import annotations

from typing import Iterable

from .analytics import DiaryReadiness, TradeAnalyticsRecord, pnl_from_episode
from .models import TradeEpisode


def project_trade_episode(
    episode: TradeEpisode,
    *,
    now_ms: int,
) -> dict[str, object]:
    """Project one episode without inventing unavailable Diary facts."""
    if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
        raise ValueError("now_ms must be a non-negative integer")

    pnl = pnl_from_episode(
        episode,
        funding=None,
        other_exchange_costs=None,
        manual_external_costs=None,
    )
    analytics = TradeAnalyticsRecord(episode=episode, pnl=pnl)

    end_ms = (
        episode.closed_at_ms
        if episode.closed_at_ms is not None
        else max(now_ms, episode.opened_at_ms)
    )

    return {
        "trade_episode_id": episode.trade_episode_id.value,
        "symbol": episode.position_key.symbol.value,
        "side": episode.side.value.upper(),
        "environment": episode.environment.value,
        "controller_origin": None,
        "opened_at_ms": episode.opened_at_ms,
        "closed_at_ms": episode.closed_at_ms,
        "opening_price": str(episode.opening_price.value),
        "average_entry": str(episode.average_entry.value),
        "exit_price": None,
        "open_quantity": str(episode.open_quantity.value),
        "pnl": (
            str(pnl.net_pnl)
            if analytics.readiness is DiaryReadiness.CLOSED_READY
            else None
        ),
        "holding_duration_ms": end_ms - episode.opened_at_ms,
        "readiness": analytics.readiness.value,
        "needs_attention": (
            analytics.readiness is DiaryReadiness.CLOSED_INCOMPLETE
        ),
        "missing_reasons": list(analytics.missing_reasons),
    }


def project_trade_episode_list(
    episodes: Iterable[TradeEpisode],
    *,
    now_ms: int,
) -> list[dict[str, object]]:
    """Return a deterministic newest-first D6.1 Trades list."""
    projected = [
        project_trade_episode(episode, now_ms=now_ms)
        for episode in episodes
    ]
    projected.sort(
        key=lambda item: (
            -int(item["opened_at_ms"]),
            str(item["trade_episode_id"]),
        )
    )
    return projected
