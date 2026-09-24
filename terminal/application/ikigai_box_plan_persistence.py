"""Persist an already calculated Box plan without calculation or admission."""

from dataclasses import asdict
from decimal import Decimal
from typing import Mapping

from terminal.paper.ikigai_box_plan import IkigaiBoxPaperPlan
from terminal.persistence.sqlite_store import RobotCandidateRecord, SQLiteStore


def _json_values(value):
    """Keep Decimal precision and detach all containers; never stringify floats."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _json_values(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_values(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("Box snapshot requires explicit Decimal or JSON scalar values")


def persist_ikigai_box_plan(
    store: SQLiteStore,
    plan: IkigaiBoxPaperPlan,
    *,
    planner_version: str,
    identity: Mapping[str, object],
    decision_time_ms: int,
    anchor_a_price: Decimal,
    anchor_b_price: Decimal,
    frozen_f2618: Decimal,
    working_quantity: Decimal,
    tick_size: Decimal,
    entry_fee_rate: Decimal,
    target_fee_rate: Decimal,
    stop_fee_rate: Decimal,
    structural_stop: Decimal | None,
    created_at_ms: int,
) -> tuple[RobotCandidateRecord, bool]:
    """Adapt explicit frozen source inputs and a result to contract v1.

    The store owns canonicalization, identity, validation and duplicate/conflict
    handling. No plan is calculated or changed, and no execution is authorized.
    Identity must contain venue, market, symbol, timeframe, direction and A/B
    candle times as required by the existing persistence contract.
    """
    if not isinstance(plan, IkigaiBoxPaperPlan):
        raise ValueError("an already calculated IkigaiBoxPaperPlan is required")
    snapshot = _json_values({
        "contract_version": 1,
        "planner_version": planner_version,
        "pattern": "IKIGAI_BOX",
        "environment": plan.environment,
        "execution_authorized": plan.execution_authorized,
        "attempt": 1,
        "identity": dict(identity),
        "decision_time_ms": decision_time_ms,
        "anchors": {"a_price": anchor_a_price, "b_price": anchor_b_price},
        "fibonacci": {"f1": plan.frozen_f1, "f1618": plan.frozen_f1618,
                      "f2618": frozen_f2618},
        "inputs": {"working_quantity": working_quantity, "tick_size": tick_size,
                   "entry_fee_rate": entry_fee_rate, "target_fee_rate": target_fee_rate,
                   "stop_fee_rate": stop_fee_rate, "structural_stop": structural_stop},
        "plan": asdict(plan),
    })
    return store.save_box_plan_only(snapshot=snapshot, created_at_ms=created_at_ms)
