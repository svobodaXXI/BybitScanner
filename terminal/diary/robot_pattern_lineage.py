"""Read-only, exact-entry Robot pattern attribution for non-Wedge episodes.

A saved Robot trade's pattern is not automatically a proven Diary episode.
The join requires one candidate's persisted entry order, its actual executions,
identical account/side/symbol, and controller-proven closed episode economics.
Ambiguity or legacy missing evidence leaves the existing UNKNOWN label.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping

from terminal.diary.models import AllocationRole
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import Origin

_WEDGES = frozenset({"Falling Wedge", "Rising Wedge"})


def _candidate_limit_order_ids(candidate: Mapping[str, object]) -> set[str]:
    raw = candidate.get("robot_state_json")
    if not isinstance(raw, str):
        return set()
    try:
        state = json.loads(raw)
        execution = state.get("execution") if isinstance(state, dict) else None
        if not isinstance(execution, dict):
            return set()
        one = execution.get("limit_order_id")
        many = execution.get("limit_order_ids")
        ids = ([] if one is None else [one]) + ([] if many is None else many)
        if not isinstance(ids, list) or not ids or any(
            not isinstance(i, str) or not i.strip() or len(i) > 256 for i in ids
        ):
            return set()
        return set(ids)
    except (ValueError, TypeError, AttributeError):
        return set()


def attach_verified_robot_pattern_signals(
    snapshot: PaperSourceSnapshot, report: dict[str, object],
) -> dict[str, object]:
    """Add exact-order non-Wedge host patterns to existing read-only Finrez rows.

    Does not replace Wedge's stricter exit proof, D2, or financial attribution.
    Only fully Robot-controlled economic episodes may receive this label.
    """
    evidence = getattr(snapshot, "wedge_evidence", None)
    rows = report.get("closed_episodes")
    if (report.get("account_id") != "paper" or report.get("owner") != "ROBOT"
            or report.get("source_revision") != getattr(snapshot, "source_revision", None)
            or not isinstance(rows, list) or evidence is None
            or not {"candidates", "trades", "robot_entries"}.issubset(evidence)):
        return report

    robot_orders = {
        o.get("order_id") for o in evidence["robot_entries"]
        if o.get("trading_account_id") == "paper" and o.get("origin") == "ROBOT"
        and isinstance(o.get("order_id"), str)
    }
    candidates: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for candidate in evidence["candidates"]:
        if (candidate.get("trading_account_id") == "paper"
                and isinstance(candidate.get("candidate_id"), str)
                and isinstance(candidate.get("symbol"), str)):
            candidates[candidate["candidate_id"]].append(candidate)

    # A persisted candidate -> ENTRY order relationship is independent
    # evidence. For Box it can also prove MARKET entry orders, which are not
    # necessarily part of the LIMIT-only robot_entry_orders registry.
    possible_owners: dict[str, set[str]] = defaultdict(set)
    for candidate_id, matches in candidates.items():
        if len(matches) != 1:
            continue
        for order in _candidate_limit_order_ids(matches[0]) & robot_orders:
            possible_owners[order].add(candidate_id)
    box_orders: dict[str, set[str]] = defaultdict(set)
    for link in evidence.get("box_entries", ()):
        if (link.get("trading_account_id") == "paper"
                and link.get("role") == "ENTRY"
                and isinstance(link.get("candidate_id"), str)
                and isinstance(link.get("order_id"), str)
                and len(candidates.get(link["candidate_id"], ())) == 1):
            box_orders[link["candidate_id"]].add(link["order_id"])
            possible_owners[link["order_id"]].add(link["candidate_id"])

    by_trade: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for trade in evidence["trades"]:
        if (trade.get("trading_account_id") == "paper"
                and isinstance(trade.get("candidate_id"), str)):
            by_trade[trade["candidate_id"]].append(trade)
    by_episode = {e.trade_episode_id.value: e for e in snapshot.episodes}
    # Do not select an arbitrary element when the immutable execution key
    # appears more than once in a malformed input.
    executions = {}
    for execution in snapshot.executions:
        if execution.dedup_key in executions:
            return report
        executions[execution.dedup_key] = execution

    enriched = []
    for row in rows:
        if (not isinstance(row, dict) or row.get("cohort") != "ROBOT"
                or "verified_signal" in row):
            enriched.append(row)
            continue
        episode = by_episode.get(row.get("trade_episode_id"))
        if (episode is None or episode.closed_at_ms is None
                or episode.position_key.trading_account_id.value != "paper"
                or episode.position_key.symbol.value != row.get("symbol")
                or episode.side.value.upper() != row.get("side")
                or episode.opened_at_ms != row.get("opened_at_ms")
                or episode.closed_at_ms != row.get("closed_at_ms")
                or len(episode.allocations) != row.get("execution_count")
                or str(episode.realized_price_pnl - episode.execution_fees) != row.get("pnl_usdt")
                or len(episode.allocations) < 2
                or episode.allocations[0].role is not AllocationRole.OPEN
                or episode.allocations[-1].role is not AllocationRole.CLOSE
                or any(snapshot.origins.get(a.execution_key) is not Origin.ROBOT
                       or a.role not in {
                           AllocationRole.OPEN, AllocationRole.INCREASE,
                           AllocationRole.REDUCE, AllocationRole.CLOSE,
                       } for a in episode.allocations)):
            enriched.append(row)
            continue
        openings = []
        valid = True
        for allocation in episode.allocations:
            fill = executions.get(allocation.execution_key)
            if (fill is None
                    or fill.dedup_key.trading_account_id.value != "paper"
                    or fill.symbol.value != row["symbol"]
                    or fill.exchange_timestamp_ms != allocation.occurred_at_ms
                    or fill.quantity.value != allocation.quantity
                    or fill.fee != allocation.fee):
                valid = False
                break
            if allocation.role in (AllocationRole.OPEN, AllocationRole.INCREASE):
                openings.append(fill.order_id.value)
        if not valid or not openings:
            enriched.append(row)
            continue
        # Every opening order must point to the *same unique candidate*.
        owner_sets = [possible_owners.get(order, set()) for order in openings]
        owner_ids = set.intersection(*owner_sets) if owner_sets else set()
        if len(owner_ids) != 1 or any(owners != owner_ids for owners in owner_sets):
            enriched.append(row)
            continue
        candidate_id = next(iter(owner_ids))
        trade_matches = by_trade.get(candidate_id, [])
        if len(trade_matches) != 1:
            enriched.append(row)
            continue
        trade = trade_matches[0]
        candidate = candidates[candidate_id][0]
        pattern = trade.get("pattern")
        timeframe = trade.get("source_timeframe")
        if (not isinstance(pattern, str) or not 1 <= len(pattern) <= 128
                or not pattern.strip() or pattern in _WEDGES
                or not isinstance(timeframe, str) or not 1 <= len(timeframe) <= 40
                or candidate.get("symbol") != row["symbol"]
                or trade.get("symbol") != row["symbol"]
                or trade.get("direction") != row["side"]
                or type(trade.get("signal_time_ms")) is not int
                or trade["signal_time_ms"] > episode.opened_at_ms
                or trade.get("entry_time_ms") != episode.opened_at_ms
                or trade.get("exit_time_ms") != episode.closed_at_ms
                or not isinstance(trade.get("trade_id"), str)
                or not trade["trade_id"]
                or (pattern == "IKIGAI_BOX"
                    and not set(openings).issubset(box_orders.get(candidate_id, set())))):
            enriched.append(row)
            continue
        setup = row.get("setup_context")
        if (isinstance(setup, dict) and setup.get("status") == "EXACT_D2_LINK"
                and isinstance(setup.get("setup"), dict)
                and setup["setup"].get("pattern") != pattern):
            enriched.append(row)
            continue
        enriched.append({**row, "verified_signal": {
            "trade_episode_id": row["trade_episode_id"],
            "source_revision": snapshot.source_revision,
            "candidate_id": candidate_id,
            "pattern": pattern,
            "source_timeframe": timeframe,
            "provenance": "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY",
            "evidence_scope": "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
            "status": "PROVEN",
        }})
    return {**report, "closed_episodes": enriched}
