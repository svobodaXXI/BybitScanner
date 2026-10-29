"""Read-only STOP-reentry attempt projection on existing Robot Trading Diary facts.

The canonical PAPER DB robot_trades / robot_candidates and executions remain
authoritative. This module reuses the existing RobotStatisticsTrade read model;
it never reserves an attempt or grants entry. Binding identities must later
come from atomic canonical Robot admission, never from symbol/time guesses.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from terminal.statistics.models import PnlBasis, RobotStatisticsTrade


class ReentryDiaryEvidenceError(ValueError):
    """Durable trade/campaign attribution is incomplete or contradictory."""


@dataclass(frozen=True, slots=True)
class ReentryAttemptLink:
    campaign_id: str
    attempt_index: int  # original=1, first retry=2, second retry=3
    trade_id: str
    candidate_id: str


@dataclass(frozen=True, slots=True)
class ReentryAttemptView:
    attempt_index: int
    trade_id: str
    candidate_id: str
    pattern: str
    signal_time_ms: int
    entry_time_ms: int
    exit_time_ms: int
    exit_reason: str
    gross_pnl_usdt: Decimal
    fees_costs_usdt: Decimal | None
    known_cost_net_pnl_usdt: Decimal | None


@dataclass(frozen=True, slots=True)
class ReentryCampaignView:
    campaign_id: str
    trading_account_id: str
    symbol: str
    direction: str
    attempts: tuple[ReentryAttemptView, ...]
    gross_pnl_usdt: Decimal
    known_cost_net_pnl_usdt: Decimal | None
    cost_complete: bool
    stop_exits: int


def project_reentry_campaigns(
    trades: Iterable[RobotStatisticsTrade],
    links: Iterable[ReentryAttemptLink],
) -> tuple[ReentryCampaignView, ...]:
    """Strict Diary projection: never infer campaign linkage or missing fees.

    This validates *observed closed-trade* lineage only. Admission still needs
    live orders, current exposure, actual STOP fills and transactional fencing.
    """
    trade_by_id: dict[str, RobotStatisticsTrade] = {}
    for trade in trades:
        if trade.trade_id in trade_by_id:
            raise ReentryDiaryEvidenceError("duplicate trade identity")
        trade_by_id[trade.trade_id] = trade

    grouped: dict[str, list[tuple[ReentryAttemptLink, RobotStatisticsTrade]]] = {}
    used_trades: set[str] = set()
    used_candidates: set[tuple[str, str]] = set()
    for link in links:
        if (
            not isinstance(link.campaign_id, str) or not link.campaign_id.strip()
            or type(link.attempt_index) is not int
            or not 1 <= link.attempt_index <= 3
            or not isinstance(link.trade_id, str) or not link.trade_id.strip()
            or not isinstance(link.candidate_id, str) or not link.candidate_id.strip()
        ):
            raise ReentryDiaryEvidenceError("invalid attempt linkage")
        trade = trade_by_id.get(link.trade_id)
        if trade is None:
            raise ReentryDiaryEvidenceError("attempt trade is not a completed Diary trade")
        if trade.trade_id in used_trades:
            raise ReentryDiaryEvidenceError("trade attributed to multiple attempts")
        candidate_key = (trade.trading_account_id, link.candidate_id)
        if candidate_key in used_candidates:
            raise ReentryDiaryEvidenceError("candidate attributed to multiple attempts")
        if trade.candidate_id != link.candidate_id:
            raise ReentryDiaryEvidenceError("candidate link differs from Robot trade")
        used_trades.add(trade.trade_id)
        used_candidates.add(candidate_key)
        grouped.setdefault(link.campaign_id, []).append((link, trade))

    campaigns: list[ReentryCampaignView] = []
    for campaign_id, entries in sorted(grouped.items()):
        entries.sort(key=lambda item: item[0].attempt_index)
        indices = [link.attempt_index for link, _ in entries]
        if indices != list(range(1, len(entries) + 1)):
            raise ReentryDiaryEvidenceError("campaign attempt indexes are not contiguous")
        first = entries[0][1]
        if first.direction not in {"LONG", "SHORT"}:
            raise ReentryDiaryEvidenceError("unknown campaign direction")
        if not first.trading_account_id or not first.symbol:
            raise ReentryDiaryEvidenceError("missing account or symbol")
        previous: RobotStatisticsTrade | None = None
        attempts: list[ReentryAttemptView] = []
        for link, trade in entries:
            if (
                trade.trading_account_id != first.trading_account_id
                or trade.symbol != first.symbol
                or trade.direction != first.direction
            ):
                raise ReentryDiaryEvidenceError("cross-account/symbol/direction campaign")
            if (
                type(trade.entry_time_ms) is not int
                or type(trade.exit_time_ms) is not int
                or trade.exit_time_ms < trade.entry_time_ms
                or not isinstance(trade.realized_pnl_usdt, Decimal)
                or not trade.realized_pnl_usdt.is_finite()
            ):
                raise ReentryDiaryEvidenceError("invalid completed trade evidence")
            if previous is not None:
                if previous.exit_reason != "STOP":
                    raise ReentryDiaryEvidenceError("reentry after non-STOP trade")
                if trade.signal_time_ms <= previous.exit_time_ms:
                    raise ReentryDiaryEvidenceError("signal was not new after STOP")
                if trade.entry_time_ms <= previous.exit_time_ms:
                    raise ReentryDiaryEvidenceError("overlapping attempts")
            if trade.fees_costs_usdt is not None and (
                not isinstance(trade.fees_costs_usdt, Decimal)
                or not trade.fees_costs_usdt.is_finite()
                or trade.fees_costs_usdt < 0
            ):
                raise ReentryDiaryEvidenceError("invalid cost evidence")
            attempts.append(ReentryAttemptView(
                attempt_index=link.attempt_index,
                trade_id=trade.trade_id,
                candidate_id=trade.candidate_id,
                pattern=trade.pattern,
                signal_time_ms=trade.signal_time_ms,
                entry_time_ms=trade.entry_time_ms,
                exit_time_ms=trade.exit_time_ms,
                exit_reason=trade.exit_reason,
                gross_pnl_usdt=trade.pnl_usdt(PnlBasis.GROSS),
                fees_costs_usdt=trade.fees_costs_usdt,
                known_cost_net_pnl_usdt=trade.pnl_usdt(PnlBasis.KNOWN_COST_ADJUSTED),
            ))
            previous = trade
        cost_complete = all(item.known_cost_net_pnl_usdt is not None for item in attempts)
        campaigns.append(ReentryCampaignView(
            campaign_id=campaign_id,
            trading_account_id=first.trading_account_id,
            symbol=first.symbol,
            direction=first.direction,
            attempts=tuple(attempts),
            gross_pnl_usdt=sum((a.gross_pnl_usdt for a in attempts), Decimal("0")),
            known_cost_net_pnl_usdt=(
                sum((a.known_cost_net_pnl_usdt for a in attempts), Decimal("0"))
                if cost_complete else None
            ),
            cost_complete=cost_complete,
            stop_exits=sum(a.exit_reason == "STOP" for a in attempts),
        ))
    return tuple(campaigns)
