"""Optional read-only, exact-ID D2 context for a selected PAPER trade episode.

No guessed signal matches by symbol/time. D2's setup-instance link is the
ONLY supported join. D2 events are research decision observations, NOT the
complete Robot runtime journal. Feature/risk snapshot references are NOT
signal geometry. Never create, migrate or write a D2/PAPER database here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .decision_models import DecisionEventKind, SetupInstanceId
from .decision_store import DiaryDecisionStore, DiaryLinkageError, SCHEMA_VERSION
from .models import TradeEpisodeId


def _unproven(status: str) -> dict[str, object]:
    return {
        "status": status,
        "source": "TRADING_DIARY_D2",
        "geometry_status": "NOT_EXPORTED",
        "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
    }


def project_episode_d2_context_read_only(
    db_path: str | Path, *, trade_episode_id: str,
    account_id: str, symbol: str, side: str,
) -> dict[str, object]:
    """Read a pre-existing D2 link using SQLite read-only and an atomic D2 view.

    This independent D2 snapshot is NOT atomic with the PAPER executions
    snapshot; returned identities must match the selected episode explicitly.
    """
    if account_id != "paper" or side not in {"LONG", "SHORT"}:
        raise ValueError("unsupported_d2_episode_scope")
    path = Path(db_path)
    if not path.exists():
        return _unproven("D2_STORE_ABSENT")
    if not path.is_file():
        return _unproven("EVIDENCE_UNAVAILABLE")
    try:
        # The regular DiaryDecisionStore.open() initializes schemas and enters
        # a writer transaction. It is intentionally NOT used for this GET.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version != SCHEMA_VERSION:
                return _unproven("EVIDENCE_UNAVAILABLE")
            # Reuse the canonical D2 typed readers. Do NOT call their writer open.
            store = DiaryDecisionStore(connection, path)
            link = store.get_trade_episode_link(TradeEpisodeId(trade_episode_id))
            if link is None:
                return _unproven("NO_EXACT_EPISODE_LINK")
            setup = store.get_setup_instance(link.setup_instance_id)
            plan = store.get_order_plan(link.order_plan_id)
            if (setup is None or plan is None
                    or plan.setup_instance_id != link.setup_instance_id
                    or plan.trading_account_id.value != account_id
                    or setup.symbol.value != symbol or plan.symbol.value != symbol
                    or setup.direction.value.upper() != side or plan.side.value.upper() != side
                    or not (setup.created_at_ms <= plan.created_at_ms <= link.linked_at_ms)):
                return _unproven("CONFLICTING_D2_LINK")
            events = store.load_decision_events(setup.setup_instance_id)
            if not 2 <= len(events) <= 1000:
                return _unproven("INCOMPLETE_D2_DECISIONS")
            for event in events:
                DiaryDecisionStore._validate_event_against_setup(event, setup)
                if event.occurred_at_ms < setup.created_at_ms:
                    return _unproven("CONFLICTING_D2_LINK")
            event_by_id = {event.decision_event_id: event for event in events}
            strategy = event_by_id.get(plan.strategy_decision_event_id)
            risk = event_by_id.get(plan.risk_decision_event_id)
            if (strategy is None or risk is None or
                    strategy.kind is not DecisionEventKind.STRATEGY or
                    risk.kind is not DecisionEventKind.RISK or
                    strategy.occurred_at_ms > risk.occurred_at_ms or
                    risk.occurred_at_ms > plan.created_at_ms):
                return _unproven("CONFLICTING_D2_LINK")
            text_values = [
                setup.setup_instance_id.value, setup.setup_id, setup.pattern,
                setup.timeframe, setup.entry_mode, setup.strategy_version,
                *(e.reason_code for e in events),
                *(e.previous_state or "" for e in events),
                *(e.next_state for e in events),
            ]
            if any(len(value) > 256 for value in text_values):
                return _unproven("EVIDENCE_UNAVAILABLE")

            return {
                "status": "EXACT_D2_LINK",
                "source": "TRADING_DIARY_D2",
                "consistency": "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
                "geometry_status": "NOT_EXPORTED",
                "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
                "setup": {
                    "setup_instance_id": setup.setup_instance_id.value,
                    "setup_id": setup.setup_id,
                    "symbol": setup.symbol.value,
                    "direction": setup.direction.value.upper(),
                    "timeframe": setup.timeframe,
                    "pattern": setup.pattern,
                    "strategy_version": setup.strategy_version,
                    "entry_mode": setup.entry_mode,
                    "origin": setup.origin.value.upper(),
                    "created_at_ms": setup.created_at_ms,
                    "has_feature_snapshot_ref": any(e.feature_snapshot_ref for e in events),
                },
                "order_plan_id": plan.order_plan_id.value,
                "linked_at_ms": link.linked_at_ms,
                "decisions": [
                    {
                        "decision_event_id": e.decision_event_id.value,
                        "kind": e.kind.value,
                        "previous_state": e.previous_state,
                        "next_state": e.next_state,
                        "reason_code": e.reason_code,
                        "controller": e.controller.value.upper(),
                        "origin": e.origin.value.upper(),
                        "occurred_at_ms": e.occurred_at_ms,
                    }
                    for e in events
                ],
            }
    except (sqlite3.Error, OSError, ValueError, TypeError, DiaryLinkageError):
        # An optional observational store must not turn corrupt evidence into
        # apparently proven context, nor suppress proven execution facts.
        return _unproven("EVIDENCE_UNAVAILABLE")
