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
# Calendar periods use Moscow time, the same business clock as legacy TODAY.
# TODAY is retained as a backwards-compatible API alias for DAY.
_PERIODS = frozenset({"TODAY", "DAY", "WEEK", "MONTH", "YEAR", "ALL"})


def period_start_ms(*, period: str, now_ms: int) -> int:
    if period not in _PERIODS or type(now_ms) is not int or now_ms < 0:
        raise ValueError("invalid_finrez_period")
    if period == "ALL":
        return 0
    msk_now = (_EPOCH + timedelta(milliseconds=now_ms)).astimezone(_MSK)
    start = msk_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "WEEK":
        # Monday 00:00 MSK, not a rolling seven-day window.
        start -= timedelta(days=start.weekday())
    elif period == "MONTH":
        start = start.replace(day=1)
    elif period == "YEAR":
        start = start.replace(month=1, day=1)
    return int((start.astimezone(timezone.utc) - _EPOCH).total_seconds() * 1000)


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



def index_closed_episodes(
    episodes: Iterable[tuple[TradeEpisode, str]],
) -> list[dict[str, object]]:
    """Proven closed episode locators only; NOT faithful Robot execution replay.

    A full local replay requires independently verified original market history,
    order/fill prices, Robot decisions and strategy version. None are inferred.
    """
    rows: list[dict[str, object]] = []
    for episode, cohort in episodes:
        if episode.closed_at_ms is None:
            raise ValueError("open_episode_not_replayable")
        rows.append({
            "trade_episode_id": episode.trade_episode_id.value,
            "symbol": episode.position_key.symbol.value,
            "side": episode.side.value.upper(),
            "opened_at_ms": episode.opened_at_ms,
            "closed_at_ms": episode.closed_at_ms,
            "pnl_usdt": str(episode.realized_price_pnl - episode.execution_fees),
            "execution_count": len(episode.allocations),
            "cohort": cohort,
            "replay_evidence": "EPISODE_INDEX_ONLY",
        })
    return sorted(rows, key=lambda row: (-row["closed_at_ms"], row["trade_episode_id"]))


def _classified_finrez_episodes(
    snapshot: PaperSourceSnapshot, *, account_id: str, period: str, now_ms: int,
) -> tuple[
    tuple[TradeEpisode, ...], tuple[TradeEpisode, ...], tuple[TradeEpisode, ...],
    tuple[TradeEpisode, ...], tuple[TradeEpisode, ...], int,
]:
    """Classify whole episodes, not individual fills or split economic PnL.

    A robot-opened episode finished by a proven manual CLOSE is reported only
    as a distinct intervention cohort, never as an autonomous robot result.
    Unknown origin is excluded as explicitly incomplete coverage rather than
    guessed. A proven robot OPEN with manual INCREASE(s) and robot CLOSE
    is a shared-management economic episode, never attributed to either
    controller's autonomous totals. Other fully proven mixed episodes with
    a valid OPEN/INCREASE/REDUCE/CLOSE lifecycle also belong to joint management.
    Incomplete origin, invalid lifecycle, or cross-account evidence stays blocked
    or explicitly excluded; per-controller realized PnL is never invented.
    """
    robot: list[TradeEpisode] = []
    manual: list[TradeEpisode] = []
    assisted: list[TradeEpisode] = []
    joint: list[TradeEpisode] = []
    unattributed: list[TradeEpisode] = []
    unattributed_execution_count = 0
    seen_ids: set[str] = set()
    start_ms = period_start_ms(period=period, now_ms=now_ms)
    for episode in snapshot.episodes:
        if not isinstance(episode, TradeEpisode):
            raise StatisticsScopeError("invalid_trade_episode")
        if episode.position_key.trading_account_id != TradingAccountId(account_id):
            raise StatisticsScopeError("cross_account_statistics_evidence")
        if episode.trade_episode_id.value in seen_ids:
            raise StatisticsScopeError("duplicate_trade_episode")
        seen_ids.add(episode.trade_episode_id.value)

        closed_at = episode.closed_at_ms
        if closed_at is None or not (start_ms <= closed_at <= now_ms):
            continue

        attributed: list[str] = []
        missing = 0
        for allocation in episode.allocations:
            if (allocation.execution_key.trading_account_id != TradingAccountId(account_id)
                    or allocation.trade_episode_id != episode.trade_episode_id):
                raise StatisticsScopeError("cross_account_statistics_evidence")
            mapped = ORIGINS.get(snapshot.origins.get(allocation.execution_key))
            if mapped is None:
                missing += 1
            else:
                attributed.append(mapped)

        if missing:
            unattributed.append(episode)
            unattributed_execution_count += missing
            continue

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
        elif (
            # This pattern has fully proven origin for *every* allocation:
            # ROBOT open, one or more MANUAL increases, ROBOT final close.
            # Increases change the shared average entry and cannot yield
            # independently provable per-controller realized price PnL.
            owners == {"ROBOT", "MANUAL"}
            and attributed[0] == "ROBOT"
            and episode.allocations[0].role in {AllocationRole.OPEN, AllocationRole.REVERSAL_OPEN}
            and attributed[-1] == "ROBOT"
            and episode.allocations[-1].role is AllocationRole.CLOSE
            and all(
                controller == "ROBOT" or allocation.role is AllocationRole.INCREASE
                for controller, allocation in zip(attributed, episode.allocations)
            )
        ):
            joint.append(episode)
        elif (
            # Fully attributable mixed owners may have a MANUAL OPEN followed
            # by a ROBOT increase/close, or alternating manual/robot adds,
            # reductions and final CLOSE. The net realized PnL is economic
            # for the entire episode, NOT separable by execution controller.
            # This is read-only classification; source allocations stay intact.
            episode.is_closed
            and owners == {"ROBOT", "MANUAL"}
            and len(episode.allocations) >= 2
            and episode.allocations[0].role in {AllocationRole.OPEN, AllocationRole.REVERSAL_OPEN}
            and episode.allocations[-1].role is AllocationRole.CLOSE
            and all(
                allocation.role in {AllocationRole.INCREASE, AllocationRole.REDUCE}
                for allocation in episode.allocations[1:-1]
            )
        ):
            joint.append(episode)
        else:
            raise StatisticsScopeError("mixed_controller_trade_episode")
    return (
        tuple(robot), tuple(manual), tuple(assisted), tuple(joint),
        tuple(unattributed), unattributed_execution_count,
    )


def attach_verified_entry_notional_returns(
    snapshot: PaperSourceSnapshot, report: dict[str, object],
) -> dict[str, object]:
    """Optional *unlevered entry-notional* return on provenance-checked fills.

    This is NOT exchange ROI on initial margin, leveraged return, net equity,
    or all-cost net PnL: funding/external costs are not in the known-cost
    numerator. The denominator is the sum of actual OPEN/INCREASE allocated
    quantities times their immutable execution prices, never exit turnover,
    account equity, leverage or a guessed average entry.
    """
    rows = report.get("closed_episodes")
    if (report.get("account_id") != "paper"
            or report.get("source_revision") != snapshot.source_revision
            or not isinstance(rows, list) or not rows or not snapshot.executions):
        return report
    by_id = {e.trade_episode_id.value: e for e in snapshot.episodes}
    fills = {execution.dedup_key: execution for execution in snapshot.executions}
    if (len(by_id) != len(snapshot.episodes)
            or len(fills) != len(snapshot.executions)
            or any(x.dedup_key.trading_account_id.value != "paper" for x in snapshot.executions)):
        return report

    enriched: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            return report
        episode = by_id.get(row.get("trade_episode_id"))
        if (episode is None or not episode.is_closed or episode.closed_at_ms is None
                or episode.position_key.trading_account_id.value != "paper"
                or episode.position_key.symbol.value != row.get("symbol")
                or episode.side.value.upper() != row.get("side")
                or episode.opened_at_ms != row.get("opened_at_ms")
                or episode.closed_at_ms != row.get("closed_at_ms")
                or str(episode.realized_price_pnl - episode.execution_fees) != row.get("pnl_usdt")
                or len(episode.allocations) != row.get("execution_count")):
            return report

        entry_notional = Decimal("0")
        fees = Decimal("0")
        proven = True
        if (not episode.allocations
                or episode.allocations[0].role not in {AllocationRole.OPEN, AllocationRole.REVERSAL_OPEN}
                or episode.allocations[-1].role is not AllocationRole.CLOSE):
            enriched.append(row)
            continue
        for index, allocation in enumerate(episode.allocations):
            fill = fills.get(allocation.execution_key)
            is_entry = allocation.role in {
                AllocationRole.OPEN, AllocationRole.REVERSAL_OPEN, AllocationRole.INCREASE,
            }
            if (allocation.execution_key.trading_account_id.value != "paper"
                    or allocation.trade_episode_id != episode.trade_episode_id
                    or fill is None or fill.dedup_key.category != episode.position_key.category
                    or fill.symbol != episode.position_key.symbol
                    or fill.exchange_timestamp_ms != allocation.occurred_at_ms
                    or fill.quantity.value < allocation.quantity
                    or fill.price.value <= 0
                    or (index != 0 and allocation.role in {
                        AllocationRole.OPEN, AllocationRole.REVERSAL_OPEN,
                    })
                    or (index == 0 and not is_entry)
                    or (index < len(episode.allocations) - 1
                        and allocation.role is AllocationRole.CLOSE)
                    or (is_entry and fill.side.value != (
                        "Buy" if episode.side.value.upper() == "LONG" else "Sell"
                    ))
                    or (not is_entry and fill.side.value != (
                        "Sell" if episode.side.value.upper() == "LONG" else "Buy"
                    ))):
                proven = False
                break
            fees += allocation.fee
            if is_entry:
                entry_notional += fill.price.value * allocation.quantity
        if not proven or fees != episode.execution_fees or not entry_notional.is_finite() or entry_notional <= 0:
            enriched.append(row)
            continue

        # Decimal preserves the exact numerator/denominator. UI rounds only
        # the visible percentage; raw PnL and allocations are unchanged.
        net_known_cost_pnl = episode.realized_price_pnl - episode.execution_fees
        pct = (net_known_cost_pnl / entry_notional) * Decimal("100")
        if not pct.is_finite():
            enriched.append(row)
            continue
        enriched.append({
            **row,
            "pnl_pct": str(pct),
            "pnl_pct_basis": "KNOWN_COST_PNL_OVER_EXECUTED_ENTRY_NOTIONAL",
            "entry_notional_usdt": str(entry_notional),
        })
    return {**report, "closed_episodes": enriched}


def attach_verified_episode_patterns(
    snapshot: PaperSourceSnapshot, report: dict[str, object], *,
    d2_path: str | None,
) -> dict[str, object]:
    """Optional exact-ID labels, not an alteration of financial totals or cohorts.

    Both authorized episode identity and opening execution origin come from the
    already classified PAPER snapshot. One independent read-only D2 transaction
    supplies only links that satisfy the existing strict setup validator.
    """
    rows = report.get("closed_episodes")
    if not isinstance(rows, list) or not rows:
        return report
    from .episode_context import project_episode_d2_contexts_read_only

    by_id = {episode.trade_episode_id.value: episode for episode in snapshot.episodes}
    if len(by_id) != len(snapshot.episodes):
        return report
    requests: list[tuple[str, str, str, str, int]] = []
    controllers: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            return report
        episode_id = row.get("trade_episode_id")
        episode = by_id.get(episode_id)
        if (episode is None or episode.closed_at_ms is None
                or episode.position_key.trading_account_id.value != "paper"
                or episode.position_key.symbol.value != row.get("symbol")
                or episode.side.value.upper() != row.get("side")
                or episode.opened_at_ms != row.get("opened_at_ms")
                or episode.closed_at_ms != row.get("closed_at_ms")
                or not episode.allocations):
            return report
        first = episode.allocations[0]
        controller = ORIGINS.get(snapshot.origins.get(first.execution_key))
        if controller not in {"ROBOT", "MANUAL"}:
            continue
        controllers[episode_id] = controller
        requests.append((
            episode_id, episode.position_key.symbol.value, episode.side.value.upper(),
            controller, episode.opened_at_ms,
        ))
    contexts = project_episode_d2_contexts_read_only(
        d2_path, episodes=tuple(requests),
    )
    if not contexts:
        return report
    return {
        **report,
        "closed_episodes": [
            {**row, "opening_controller": controllers[row["trade_episode_id"]],
             "setup_context": contexts[row["trade_episode_id"]]}
            if row["trade_episode_id"] in contexts else row
            for row in rows
        ],
    }


class EpisodeFactsNotFound(StatisticsScopeError):
    """Episode cannot be established in the requested controller scope."""


class EpisodeFactsSourceChanged(StatisticsScopeError):
    """The statistics index has changed since the selected episode was listed."""


def project_paper_closed_episode_facts(
    snapshot: PaperSourceSnapshot, *, account_id: str, owner: str,
    trade_episode_id: str, source_revision: int, now_ms: int,
) -> dict[str, object]:
    """Export only persisted fill evidence, by exact, controller-proven episode ID.

    Reuses the Finrez classifier; does NOT synthesize strategy decisions, candle
    history, order-intent chronology, exchange fills or Simulator PnL.
    """
    if account_id != "paper" or owner not in {"ROBOT", "MANUAL"}:
        raise ValueError("unsupported_episode_scope")
    if not isinstance(trade_episode_id, str) or (
        len(trade_episode_id) != 27
        or not trade_episode_id.startswith("te_")
        or any(ch not in "0123456789abcdef" for ch in trade_episode_id[3:])
    ):
        raise ValueError("invalid_trade_episode_id")
    if type(source_revision) is not int or source_revision < 1:
        raise ValueError("invalid_source_revision")
    if snapshot.source_revision != source_revision:
        raise EpisodeFactsSourceChanged("source_revision_changed")
    robot, manual, assisted, joint, _, _ = _classified_finrez_episodes(
        snapshot, account_id=account_id, period="ALL", now_ms=now_ms,
    )
    eligible: list[tuple[TradeEpisode, str]] = [
        (episode, owner) for episode in (robot if owner == "ROBOT" else manual)
    ]
    if owner == "ROBOT":
        eligible.extend((episode, "ROBOT_MANUAL_CLOSE") for episode in assisted)
    eligible.extend((episode, "JOINT_MANAGEMENT") for episode in joint)
    matches = [(e, cohort) for e, cohort in eligible if e.trade_episode_id.value == trade_episode_id]
    if len(matches) != 1:
        raise EpisodeFactsNotFound("episode_not_in_controller_scope")
    episode, cohort = matches[0]
    if not episode.is_closed or episode.closed_at_ms is None:
        raise EpisodeFactsNotFound("episode_not_closed")

    # Source-consistent execution facts were read in the SAME SQLite snapshot
    # as the allocations and controller origins; never join a later DB read.
    evidence = {}
    for execution in snapshot.executions:
        key = execution.dedup_key
        if key.trading_account_id != TradingAccountId(account_id):
            raise StatisticsScopeError("cross_account_execution_evidence")
        if key in evidence and evidence[key] != execution:
            raise StatisticsScopeError("conflicting_execution_evidence")
        evidence[key] = execution
    if not evidence:
        raise StatisticsScopeError("execution_evidence_not_available")
    allocations: list[dict[str, object]] = []
    total_fees = Decimal("0")
    for item in episode.allocations:
        execution = evidence.get(item.execution_key)
        controller = ORIGINS.get(snapshot.origins.get(item.execution_key))
        if (execution is None or controller is None
                or execution.symbol != episode.position_key.symbol
                or execution.exchange_timestamp_ms != item.occurred_at_ms
                or execution.quantity.value < item.quantity):
            raise StatisticsScopeError("episode_execution_evidence_mismatch")
        total_fees += item.fee
        allocations.append({
            "execution_id": item.execution_key.exec_id.value,
            "order_id": execution.order_id.value,
            "order_side": execution.side.value,
            "execution_price": str(execution.price.value),
            "allocated_quantity": str(item.quantity),
            "allocated_fee": str(item.fee),
            "occurred_at_ms": item.occurred_at_ms,
            "allocation_role": item.role.value,
            "controller": controller,
        })
    if len(allocations) != len(episode.allocations) or total_fees != episode.execution_fees:
        raise StatisticsScopeError("episode_allocation_fees_mismatch")
    return {
        "schema": "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
        "namespace": "PAPER_READ_ONLY",
        "source": "PAPER_EXECUTIONS_ATTRIBUTED",
        "source_revision": snapshot.source_revision,
        "account_id": account_id,
        "owner": owner,
        "cohort": cohort,
        "trade_episode_id": trade_episode_id,
        "symbol": episode.position_key.symbol.value,
        "side": episode.side.value.upper(),
        "opened_at_ms": episode.opened_at_ms,
        "closed_at_ms": episode.closed_at_ms,
        "realized_price_pnl_usdt": str(episode.realized_price_pnl),
        "known_execution_fees_usdt": str(episode.execution_fees),
        "pnl_usdt": str(episode.realized_price_pnl - episode.execution_fees),
        "pnl_basis": "REALIZED_PRICE_MINUS_EXECUTION_FEES",
        "replay_evidence": "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
        "execution_allocations": allocations,
    }


def project_paper_ticker_pnl(
    snapshot: PaperSourceSnapshot, *, account_id: str, owner: str,
    period: str, now_ms: int,
) -> dict[str, object]:
    """Use the existing strict execution-origin attribution before summing."""
    if account_id != "paper" or owner not in {"ROBOT", "MANUAL"}:
        raise ValueError("unsupported_finrez_scope")
    robot, manual, assisted, joint, unattributed, unattributed_execution_count = (
        _classified_finrez_episodes(
            snapshot, account_id=account_id, period=period, now_ms=now_ms,
        )
    )
    start_ms, tickers = aggregate_ticker_pnl(
        robot if owner == "ROBOT" else manual, period=period, now_ms=now_ms,
    )
    _, manual_interventions = aggregate_ticker_pnl(
        assisted if owner == "ROBOT" else (), period=period, now_ms=now_ms,
    )
    # Shared economic episodes are exposed for both views, but are excluded
    # from BOTH scoped totals and must never be summed once per controller.
    _, joint_management = aggregate_ticker_pnl(
        joint, period=period, now_ms=now_ms,
    )
    selected = robot if owner == "ROBOT" else manual
    eligible: list[tuple[TradeEpisode, str]] = [
        (episode, owner) for episode in selected
    ]
    if owner == "ROBOT":
        eligible.extend((episode, "ROBOT_MANUAL_CLOSE") for episode in assisted)
    eligible.extend((episode, "JOINT_MANAGEMENT") for episode in joint)
    return {
        "closed_episodes": index_closed_episodes(eligible),
        "account_id": account_id,
        "owner": owner,
        "period": period,
        "period_start_ms": start_ms,
        "as_of_ms": now_ms,
        "source_revision": snapshot.source_revision,
        "source": "PAPER_EXECUTIONS_ATTRIBUTED",
        "pnl_basis": "REALIZED_PRICE_MINUS_EXECUTION_FEES",
        "attribution_coverage": {
            "status": "PARTIAL" if unattributed else "COMPLETE",
            "excluded_unattributed_episode_count": len(unattributed),
            "excluded_unattributed_execution_count": unattributed_execution_count,
        },
        "tickers": tickers,
        "manual_interventions": manual_interventions,
        "joint_management": joint_management,
    }
