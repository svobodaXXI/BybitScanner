"""Read-only, fail-closed Wedge candidate → order → execution → episode proof.

No ticker/time heuristics, no synthetic decisions, no PAPER/Robot mutations.
The source snapshot and optional wedge_evidence MUST be gathered in one
read-only SQLite transaction by load_paper_source_snapshot().
"""
from __future__ import annotations

import hashlib
import json

from terminal.diary.models import AllocationRole
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import Origin


class WedgeLineageUnproven(ValueError):
    """An exact durable Robot Wedge lineage link could not be established."""


def _deny(reason: str) -> None:
    raise WedgeLineageUnproven(reason)


def _one(items: list[dict], reason: str) -> dict:
    if len(items) != 1:
        _deny(reason)
    return items[0]


def _order_ids(candidate: dict) -> frozenset[str]:
    """Only immutable persisted candidate execution state may name an entry."""
    try:
        state = json.loads(candidate["robot_state_json"])
        execution = state["execution"]
        if not isinstance(execution, dict):
            raise ValueError("invalid execution state")
        one = execution.get("limit_order_id")
        many = execution.get("limit_order_ids")
        if many is not None and not isinstance(many, list):
            raise ValueError("invalid multi-order state")
        values = ([] if one is None else [one]) + ([] if many is None else many)
        if (not values or any(not isinstance(v, str) or not v.strip() for v in values)
                or len(values) != len(set(values))):
            raise ValueError("candidate entry ids missing or ambiguous")
        return frozenset(values)
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        _deny("wedge_candidate_entry_identity_unproven")


def project_selected_paper_wedge(
    snapshot: PaperSourceSnapshot, *, account_id: str, owner: str,
    trade_episode_id: str, source_revision: int,
) -> dict[str, object]:
    """Prove exactly one completed Wedge episode, preserving actual fills/fees.

    Deliberately does not assert original signal geometry, candle completeness,
    historical fee schedule, or a full replay of Robot decisions.
    """
    if (account_id != "paper" or owner != "ROBOT"
            or type(source_revision) is not int
            or source_revision != snapshot.source_revision):
        _deny("wedge_paper_robot_revision_required")
    evidence = snapshot.wedge_evidence
    if evidence is None or set(evidence) != {
        "candidates", "trades", "robot_entries", "obligations",
    }:
        _deny("wedge_evidence_unavailable")
    episode = _one([
        e for e in snapshot.episodes
        if e.trade_episode_id.value == trade_episode_id and e.closed_at_ms is not None
    ], "wedge_episode_unavailable")
    allocations = episode.allocations
    if (len(allocations) < 2 or allocations[0].role is not AllocationRole.OPEN
            or allocations[-1].role is not AllocationRole.CLOSE
            or any(a.role not in {AllocationRole.OPEN, AllocationRole.INCREASE, AllocationRole.CLOSE}
                   for a in allocations)
            or any(a.role is AllocationRole.CLOSE for a in allocations[:-1])):
        _deny("wedge_episode_allocations_unproven")
    if any(snapshot.origins.get(a.execution_key) is not Origin.ROBOT for a in allocations):
        _deny("wedge_mixed_controller")
    actual = {}
    for execution in snapshot.executions:
        if execution.dedup_key.trading_account_id.value != "paper":
            _deny("wedge_cross_account_execution")
        eid = execution.dedup_key.exec_id.value
        if eid in actual:
            _deny("wedge_duplicate_execution")
        actual[eid] = execution
    rows = []
    for a in allocations:
        execution = actual.get(a.execution_key.exec_id.value)
        if (execution is None or execution.symbol != episode.position_key.symbol
                or execution.exchange_timestamp_ms != a.occurred_at_ms
                or execution.quantity.value != a.quantity or execution.fee != a.fee):
            _deny("wedge_partial_or_unmatched_execution")
        rows.append((a, execution))
    opening_order_ids = {e.order_id.value for a, e in rows[:-1]}
    if not opening_order_ids:
        _deny("wedge_entry_missing")
    # Robot origin alone never proves candidate ownership. Both a persisted
    # candidate-execution order ID and the durable Robot ENTRY ledger must agree.
    robot_orders = {
        row["order_id"] for row in evidence["robot_entries"]
        if row.get("trading_account_id") == "paper" and row.get("origin") == "ROBOT"
    }
    if not opening_order_ids.issubset(robot_orders):
        _deny("wedge_robot_entry_ownership_unproven")
    candidates = []
    for candidate in evidence["candidates"]:
        if candidate.get("trading_account_id") != "paper":
            continue
        ids = _order_ids(candidate) if candidate.get("robot_state_json") else frozenset()
        if ids & opening_order_ids:
            candidates.append((candidate, ids))
    if len(candidates) != 1 or candidates[0][1] != opening_order_ids:
        _deny("wedge_candidate_order_ambiguous")
    candidate, _ = candidates[0]
    trade = _one([
        t for t in evidence["trades"]
        if t.get("trading_account_id") == "paper"
        and t.get("candidate_id") == candidate.get("candidate_id")
    ], "wedge_robot_trade_unproven")
    if (trade.get("pattern") not in {"Falling Wedge", "Rising Wedge"}
            or trade.get("symbol") != episode.position_key.symbol.value
            or candidate.get("symbol") != trade.get("symbol")
            or trade.get("direction") != episode.side.value.upper()
            or not isinstance(trade.get("source_timeframe"), str)
            or not trade["source_timeframe"]
            or type(trade.get("signal_time_ms")) is not int
            or trade["signal_time_ms"] > episode.opened_at_ms
            or trade.get("exit_time_ms") != episode.closed_at_ms):
        _deny("wedge_trade_metadata_unproven")
    close_exec = rows[-1][1]
    winning = _one([
        w for w in evidence["obligations"]
        if w.get("trading_account_id") == "paper"
        and w.get("trade_id") == trade.get("trade_id")
        and w.get("status") == "RESOLVED"
        and w.get("winning_leg") in {"STOP", "TAKE"}
    ], "wedge_protection_exit_unproven")
    if (winning.get("winning_leg") != trade.get("exit_reason")
            or winning.get("exec_id") != close_exec.dedup_key.exec_id.value
            or winning.get("order_id") != close_exec.order_id.value):
        _deny("wedge_exit_execution_mismatch")
    fills = [{
        "execution_id": e.dedup_key.exec_id.value,
        "order_id": e.order_id.value,
        "order_side": e.side.value,
        "execution_price": str(e.price.value),
        "allocated_quantity": str(a.quantity),
        "allocated_fee": str(a.fee),
        "occurred_at_ms": a.occurred_at_ms,
        "allocation_role": a.role.value,
        "controller": "ROBOT",
    } for a, e in rows]
    payload = {
        "schema": "BYBITSCANNER_PAPER_WEDGE_LINEAGE_V1",
        "namespace": "PAPER_READ_ONLY",
        "source_revision": source_revision,
        "account_id": "paper",
        "trade_episode_id": trade_episode_id,
        "candidate_id": candidate["candidate_id"],
        "robot_trade_id": trade["trade_id"],
        "signal_pattern": trade["pattern"],
        "source_timeframe": trade["source_timeframe"],
        "signal_provenance": "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY",
        "exit_reason": winning["winning_leg"],
        "realized_price_pnl_usdt": str(episode.realized_price_pnl),
        "known_execution_fees_usdt": str(episode.execution_fees),
        "pnl_usdt": str(episode.realized_price_pnl - episode.execution_fees),
        "execution_allocations": fills,
        "decisions_coverage": "NOT_PROVIDED",
        "market_candles_coverage": "NOT_PROVIDED",
    }
    payload["source_sha256"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return payload


def attach_verified_wedge_signals(
    snapshot: PaperSourceSnapshot, report: dict[str, object],
) -> dict[str, object]:
    """Optional exact-ID Robot Wedge label, separate from D2 and financials."""
    if (report.get("account_id") != "paper" or report.get("owner") != "ROBOT"
            or report.get("source_revision") != snapshot.source_revision
            or snapshot.wedge_evidence is None):
        return report
    rows = report.get("closed_episodes")
    if not isinstance(rows, list):
        return report
    enriched = []
    for row in rows:
        if (not isinstance(row, dict) or row.get("cohort") != "ROBOT"
                or not isinstance(row.get("trade_episode_id"), str)):
            enriched.append(row)
            continue
        try:
            proof = project_selected_paper_wedge(
                snapshot, account_id="paper", owner="ROBOT",
                trade_episode_id=row["trade_episode_id"],
                source_revision=snapshot.source_revision,
            )
        except WedgeLineageUnproven:
            enriched.append(row)
            continue
        matches = [episode for episode in snapshot.episodes
                   if episode.trade_episode_id.value == row["trade_episode_id"]]
        if (len(matches) != 1
                or matches[0].position_key.symbol.value != row.get("symbol")
                or matches[0].side.value.upper() != row.get("side")
                or matches[0].opened_at_ms != row.get("opened_at_ms")
                or matches[0].closed_at_ms != row.get("closed_at_ms")
                or str(matches[0].realized_price_pnl - matches[0].execution_fees) != row.get("pnl_usdt")
                or len(matches[0].allocations) != row.get("execution_count")):
            enriched.append(row)
            continue
        enriched.append({**row, "verified_signal": {
            "trade_episode_id": proof["trade_episode_id"],
            "source_revision": proof["source_revision"],
            "candidate_id": proof["candidate_id"],
            "pattern": proof["signal_pattern"],
            "source_timeframe": proof["source_timeframe"],
            "provenance": proof["signal_provenance"],
            "evidence_scope": "EXACT_WEDGE_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
            "status": "PROVEN",
        }})
    return {**report, "closed_episodes": enriched}
