"""Fail-closed, read-only proof of Robot campaign -> Trading Diary episode lineage.

This projector is deliberately NOT a public replay endpoint. Its inputs must come
from one read-only PAPER SQLite snapshot together with the reconstructed Diary
episodes. In particular, an order controller, a symbol or matching timestamps
alone are never evidence of a campaign member. Currently only entry orders with
durable Box ownership can prove entry identity; other strategies remain unproven
until they expose their own exact durable entry linkage.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from terminal.diary.models import AllocationRole
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import Origin


class CampaignLineageUnproven(ValueError):
    """No complete, exact-ID mapping to immutable executions was established."""


def _deny(code: str) -> None:
    raise CampaignLineageUnproven(code)


def _one(rows: Sequence[Mapping[str, object]], code: str) -> Mapping[str, object]:
    if len(rows) != 1:
        _deny(code)
    return rows[0]


def prove_robot_campaign_episodes(
    snapshot: PaperSourceSnapshot, *, account_id: str,
    trade_episode_id: str, source_revision: int,
    campaign: Mapping[str, object],
    attempts: Sequence[Mapping[str, object]],
    trades: Sequence[Mapping[str, object]],
    entry_ownership: Sequence[Mapping[str, object]],
    obligations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Prove a CLOSED campaign using exact durable candidate/order/execution IDs.

    Does not fetch candles, invent historical decisions, infer a trade from ticker
    proximity, or change any PAPER/Robot state. The caller MUST load every
    argument from the same read-only database transaction. A missing or ambiguous
    join is a hard refusal, not a partial campaign.
    """
    if account_id != "paper" or not isinstance(trade_episode_id, str):
        _deny("campaign_paper_scope_required")
    if type(source_revision) is not int or source_revision != snapshot.source_revision:
        _deny("campaign_source_revision_changed")
    if (campaign.get("trading_account_id") != account_id
            or not isinstance(campaign.get("campaign_id"), str)
            or not campaign["campaign_id"]
            or campaign.get("direction") not in {"LONG", "SHORT"}
            or not isinstance(campaign.get("symbol"), str)):
        _deny("campaign_identity_unproven")
    if not attempts or len(attempts) > 3:
        _deny("campaign_attempts_unproven")

    ordered = sorted(attempts, key=lambda a: a.get("attempt_index", 0)
                     if type(a.get("attempt_index")) is int else -1)
    candidates: set[str] = set()
    for index, attempt in enumerate(ordered, 1):
        candidate = attempt.get("candidate_id")
        if (attempt.get("trading_account_id") != account_id
                or attempt.get("campaign_id") != campaign["campaign_id"]
                or type(attempt.get("attempt_index")) is not int
                or attempt["attempt_index"] != index
                or not isinstance(candidate, str) or not candidate
                or candidate in candidates):
            _deny("campaign_attempt_chain_unproven")
        candidates.add(candidate)
    if ordered[0]["candidate_id"] != campaign.get("first_candidate_id"):
        _deny("campaign_first_candidate_mismatch")
    if len(trades) != len(ordered):
        _deny("campaign_trade_count_mismatch")

    execution_by_id: dict[str, object] = {}
    for execution in snapshot.executions:
        if execution.dedup_key.trading_account_id.value != account_id:
            _deny("campaign_cross_account_execution")
        key = execution.dedup_key.exec_id.value
        if key in execution_by_id:
            _deny("campaign_duplicate_execution")
        execution_by_id[key] = execution

    mapped: list[dict[str, object]] = []
    seen_episodes: set[str] = set()
    previous_stop_exec: str | None = None
    previous_exit_at: int | None = None
    previous_winner: str | None = None

    for index, attempt in enumerate(ordered, 1):
        candidate = attempt["candidate_id"]
        trade = _one([t for t in trades if t.get("candidate_id") == candidate],
                     "campaign_trade_missing_or_ambiguous")
        if (trade.get("trading_account_id") != account_id
                or trade.get("symbol") != campaign["symbol"]
                or trade.get("direction") != campaign["direction"]
                or not isinstance(trade.get("trade_id"), str)
                or not trade["trade_id"]
                or not isinstance(trade.get("pattern"), str)
                or not 1 <= len(trade["pattern"]) <= 128
                or not isinstance(trade.get("source_timeframe"), str)
                or not 1 <= len(trade["source_timeframe"]) <= 20
                or type(trade.get("signal_time_ms")) is not int
                or type(trade.get("entry_time_ms")) is not int
                or type(trade.get("exit_time_ms")) is not int
                or not (0 <= trade["signal_time_ms"] <= trade["entry_time_ms"]
                        <= trade["exit_time_ms"])):
            _deny("campaign_robot_trade_unproven")
        if index > 1:
            if (previous_winner != "STOP"
                    or attempt.get("previous_stop_exec_id") != previous_stop_exec):
                _deny("campaign_stop_reentry_not_proven")
        elif attempt.get("previous_stop_exec_id") is not None:
            _deny("campaign_initial_attempt_has_stop")
        if previous_exit_at is not None and trade["entry_time_ms"] <= previous_exit_at:
            _deny("campaign_attempts_overlap")

        owned_orders = {
            row["order_id"] for row in entry_ownership
            if row.get("candidate_id") == candidate
            and row.get("trading_account_id") == account_id
            and row.get("role") == "ENTRY"
            and isinstance(row.get("order_id"), str)
        }
        if not owned_orders:
            _deny("campaign_exact_entry_ownership_missing")
        winner = _one([
            row for row in obligations
            if row.get("trade_id") == trade["trade_id"]
            and row.get("trading_account_id") == account_id
            and row.get("status") == "RESOLVED"
            and row.get("winning_leg") in {"STOP", "TAKE"}
        ], "campaign_resolved_exit_missing_or_ambiguous")
        exit_exec_id, exit_order_id = winner.get("exec_id"), winner.get("order_id")
        if not isinstance(exit_exec_id, str) or not isinstance(exit_order_id, str):
            _deny("campaign_exit_identity_missing")
        exit_execution = execution_by_id.get(exit_exec_id)
        if (exit_execution is None or exit_execution.order_id.value != exit_order_id
                or exit_execution.exchange_timestamp_ms != trade["exit_time_ms"]
                or trade.get("exit_reason") != winner["winning_leg"]):
            _deny("campaign_exit_execution_mismatch")
        eligible = []
        for episode in snapshot.episodes:
            if (episode.closed_at_ms is None or episode.position_key.trading_account_id.value != account_id
                    or episode.position_key.symbol.value != campaign["symbol"]
                    or episode.side.value.upper() != campaign["direction"]):
                continue
            alloc = episode.allocations
            if not alloc or alloc[-1].role is not AllocationRole.CLOSE:
                continue
            if alloc[-1].execution_key.exec_id.value != exit_exec_id:
                continue
            if not all(snapshot.origins.get(a.execution_key) is Origin.ROBOT for a in alloc):
                continue
            if any(a.role not in {AllocationRole.OPEN, AllocationRole.INCREASE, AllocationRole.CLOSE}
                   for a in alloc):
                continue
            open_allocations = alloc[:-1]
            if not open_allocations or open_allocations[0].role is not AllocationRole.OPEN:
                continue
            if any(a.role not in {AllocationRole.OPEN, AllocationRole.INCREASE}
                   or execution_by_id.get(a.execution_key.exec_id.value) is None
                   or execution_by_id[a.execution_key.exec_id.value].order_id.value not in owned_orders
                   for a in open_allocations):
                continue
            if episode.closed_at_ms != exit_execution.exchange_timestamp_ms:
                continue
            eligible.append(episode)
        episode = _one(eligible, "campaign_episode_link_missing_or_ambiguous")
        episode_id = episode.trade_episode_id.value
        if episode_id in seen_episodes:
            _deny("campaign_episode_reused")
        seen_episodes.add(episode_id)
        # Preserve full exact-Decimal execution provenance in the hashed
        # result; neither an aggregate PnL nor a ticker/time match is enough.
        allocations = []
        for allocation in episode.allocations:
            execution = execution_by_id[allocation.execution_key.exec_id.value]
            allocations.append({
                "execution_id": execution.dedup_key.exec_id.value,
                "order_id": execution.order_id.value,
                "order_side": execution.side.value,
                "execution_price": str(execution.price.value),
                "allocated_quantity": str(allocation.quantity),
                "allocated_fee": str(allocation.fee),
                "occurred_at_ms": allocation.occurred_at_ms,
                "allocation_role": allocation.role.value,
                "controller": "ROBOT",
            })
        mapped.append({
            "attempt_index": index,
            "candidate_id": candidate,
            "robot_trade_id": trade["trade_id"],
            "trade_episode_id": episode_id,
            "signal_time_ms": trade["signal_time_ms"],
            "signal_pattern": trade["pattern"],
            "signal_timeframe": trade["source_timeframe"],
            "signal_provenance": "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY",
            "opened_at_ms": episode.opened_at_ms,
            "closed_at_ms": episode.closed_at_ms,
            "exit_reason": winner["winning_leg"],
            "exit_execution_id": exit_exec_id,
            "realized_price_pnl_usdt": str(episode.realized_price_pnl),
            "known_execution_fees_usdt": str(episode.execution_fees),
            "pnl_usdt": str(episode.realized_price_pnl - episode.execution_fees),
            "execution_allocations": allocations,
        })
        previous_stop_exec = exit_exec_id
        previous_winner = winner["winning_leg"]
        previous_exit_at = episode.closed_at_ms
    if trade_episode_id not in seen_episodes:
        _deny("campaign_requested_episode_not_linked")
    # A resolved STOP at attempts 1/2 does not prove that the campaign cannot
    # re-enter later. A TAKE or the durable three-attempt maximum is terminal.
    if previous_winner != "TAKE" and len(ordered) != 3:
        _deny("campaign_terminal_state_unproven")
    if any(row.get("candidate_id") not in candidates for row in trades):
        _deny("campaign_foreign_trade")
    result: dict[str, object] = {
        "schema": "BYBITSCANNER_PAPER_CAMPAIGN_LINEAGE_V1",
        "namespace": "PAPER_READ_ONLY",
        "account_id": account_id,
        "source_revision": source_revision,
        "campaign_id": campaign["campaign_id"],
        "symbol": campaign["symbol"],
        "direction": campaign["direction"],
        "trade_episodes": mapped,
        "evidence_scope": "EXACT_ROBOT_CANDIDATE_BOX_ENTRY_AND_RESOLVED_PROTECTION_EXIT",
        "decisions_coverage": "NOT_PROVIDED",
        "market_candles_coverage": "NOT_PROVIDED",
    }
    # SHA-256 detects a changed serialization. It is NOT origin authentication.
    result["source_sha256"] = hashlib.sha256(json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return result



def project_selected_paper_campaign(
    snapshot: PaperSourceSnapshot, *, account_id: str, owner: str,
    trade_episode_id: str, source_revision: int,
) -> dict[str, object]:
    """Resolve a selected Diary episode to a fully proven, closed Robot campaign.

    Box entry ownership is the only currently supported exact entry join.
    Missing campaign or other native strategy provenance stays unavailable,
    rather than grouping all same-ticker episodes into one replay.
    """
    if account_id != "paper" or owner != "ROBOT":
        _deny("campaign_robot_paper_scope_required")
    if type(source_revision) is not int or source_revision != snapshot.source_revision:
        _deny("campaign_source_revision_changed")
    evidence = snapshot.campaign_evidence
    required = {"campaigns", "attempts", "trades", "entry_ownership", "obligations"}
    if evidence is None or set(evidence) != required:
        _deny("campaign_source_evidence_unavailable")
    selected = _one(
        [episode for episode in snapshot.episodes
         if episode.trade_episode_id.value == trade_episode_id],
        "campaign_selected_episode_unavailable",
    )
    if selected.closed_at_ms is None:
        _deny("campaign_selected_episode_not_closed")
    # This exact entry order is the only identity key used to discover the
    # campaign. Symbol/timing proximity never creates membership.
    execution_by_id = {
        item.dedup_key.exec_id.value: item for item in snapshot.executions
        if item.dedup_key.trading_account_id.value == "paper"
    }
    opening_order_ids = {
        execution_by_id[allocation.execution_key.exec_id.value].order_id.value
        for allocation in selected.allocations
        if allocation.role in {AllocationRole.OPEN, AllocationRole.INCREASE}
        and allocation.execution_key.exec_id.value in execution_by_id
    }
    if not opening_order_ids:
        _deny("campaign_selected_entry_missing")
    candidates = {
        row["candidate_id"] for row in evidence["entry_ownership"]
        if row.get("trading_account_id") == "paper"
        and row.get("role") == "ENTRY"
        and row.get("order_id") in opening_order_ids
    }
    candidate = _one([{"id": x} for x in candidates],
                     "campaign_entry_candidate_missing_or_ambiguous")["id"]
    attempt = _one([
        row for row in evidence["attempts"] if row.get("candidate_id") == candidate
        and row.get("trading_account_id") == "paper"
    ], "campaign_selected_attempt_unproven")
    campaign = _one([
        row for row in evidence["campaigns"]
        if row.get("campaign_id") == attempt.get("campaign_id")
        and row.get("trading_account_id") == "paper"
    ], "campaign_selected_campaign_unproven")
    attempts = [
        row for row in evidence["attempts"]
        if row.get("campaign_id") == campaign["campaign_id"]
        and row.get("trading_account_id") == "paper"
    ]
    candidate_ids = {row.get("candidate_id") for row in attempts}
    trades = [
        row for row in evidence["trades"]
        if row.get("candidate_id") in candidate_ids
        and row.get("trading_account_id") == "paper"
    ]
    trade_ids = {row.get("trade_id") for row in trades}
    return prove_robot_campaign_episodes(
        snapshot, account_id=account_id, trade_episode_id=trade_episode_id,
        source_revision=source_revision, campaign=campaign, attempts=attempts,
        trades=trades,
        entry_ownership=[
            row for row in evidence["entry_ownership"]
            if row.get("candidate_id") in candidate_ids
            and row.get("trading_account_id") == "paper"
        ],
        obligations=[
            row for row in evidence["obligations"]
            if row.get("trade_id") in trade_ids
            and row.get("trading_account_id") == "paper"
        ],
    )
