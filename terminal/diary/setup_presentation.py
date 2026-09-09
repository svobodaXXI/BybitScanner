"""Read-only Trading Diary D6.3 setup and attention projections."""

from __future__ import annotations

from .decision_models import DecisionEventKind, SetupInstanceRecord
from .decision_store import DiaryDecisionStore


def project_setup_instance(
    store: DiaryDecisionStore,
    setup: SetupInstanceRecord,
) -> dict[str, object]:
    """Project one durable D2 setup without inventing missing evidence."""
    events = store.load_decision_events(setup.setup_instance_id)
    outcomes = tuple(
        event for event in events if event.kind is DecisionEventKind.SETUP_OUTCOME
    )
    latest_event = events[-1] if events else None
    latest_outcome = outcomes[-1] if outcomes else None
    links = store.load_trade_episode_links(setup.setup_instance_id)

    missing_evidence: list[str] = []
    if not events:
        missing_evidence.append("MISSING_DECISION_EVENTS")

    return {
        "setup_instance_id": setup.setup_instance_id.value,
        "setup_id": setup.setup_id,
        "symbol": setup.symbol.value,
        "timeframe": setup.timeframe,
        "pattern": setup.pattern,
        "direction": setup.direction.value.upper(),
        "strategy_version": setup.strategy_version,
        "hypothesis_id": setup.hypothesis_id,
        "entry_mode": setup.entry_mode,
        "origin": setup.origin.value.upper(),
        "created_at_ms": setup.created_at_ms,
        "status": latest_outcome.next_state if latest_outcome else "ADMITTED",
        "decision_state": latest_event.next_state if latest_event else None,
        "reason_code": latest_event.reason_code if latest_event else None,
        "controller": latest_event.controller.value.upper() if latest_event else None,
        "latest_decision_at_ms": (
            latest_event.occurred_at_ms if latest_event else None
        ),
        "trade_episode_ids": [link.trade_episode_id.value for link in links],
        "needs_attention": bool(missing_evidence),
        "missing_evidence": missing_evidence,
    }


def project_setup_list(store: DiaryDecisionStore) -> list[dict[str, object]]:
    """Return newest-first D6.3 setup observations from existing D2 evidence."""
    projected = [
        project_setup_instance(store, setup)
        for setup in store.load_setup_instances()
    ]
    projected.sort(
        key=lambda item: (
            -int(item["created_at_ms"]),
            str(item["setup_instance_id"]),
        )
    )
    return projected
