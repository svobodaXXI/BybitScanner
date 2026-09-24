"""Read-only Box lot proof over the existing immutable execution journal."""

from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json

from terminal.domain.models import Category, OrderSide, PositionSide


class BoxOwnershipError(ValueError):
    """Ownership/exposure is not proven; callers must not authorize execution."""


@dataclass(frozen=True, slots=True)
class BoxExposureProof:
    candidate_id: str
    entry_quantity: Decimal
    exit_quantity: Decimal
    remaining_quantity: Decimal
    average_entry: Decimal | None
    position_version: int
    execution_ids: tuple[str, ...]
    execution_authorized: bool = field(default=False, init=False)


def journal_hash(fills) -> str:
    # Hash evidence, not a second journal or a mutable fill accumulator.
    rows = [(f.dedup_key.trading_account_id.value, f.dedup_key.category.value,
             f.dedup_key.exec_id.value, f.order_id.value, f.symbol.value,
             f.side.value, str(f.price.value), str(f.quantity.value), str(f.fee),
             f.exchange_timestamp_ms) for f in fills]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def prove_box_exposure(candidate, baseline, ownership, fills, position):
    """Require complete, unambiguous fills from the attested FLAT base.

    Equal timestamps cannot prove order; reject rather than use exec-id sorting.
    Projection version fences foreign writes that leave net quantity intact.
    This first-grid slice provides no replenishment or attempt reset.
    """
    if position is None or position.sync_state != "synced":
        raise BoxOwnershipError("actual position is missing or not reconciled")
    history = tuple(f for f in fills if f.exchange_timestamp_ms <= baseline["baseline_time_ms"])
    if (len(history) != baseline["baseline_execution_count"]
            or journal_hash(history) != baseline["baseline_execution_hash"]):
        raise BoxOwnershipError("baseline execution evidence changed or is incomplete")
    current = tuple(f for f in fills if f.exchange_timestamp_ms > baseline["baseline_time_ms"])
    if position.version != baseline["baseline_position_version"] + len(current):
        raise BoxOwnershipError("position version has an unexplained mutation or missing execution")
    plan = candidate.signal_snapshot["plan"]
    entry_side = OrderSide.BUY if plan["direction"] == "LONG" else OrderSide.SELL
    expected_side = PositionSide.LONG if entry_side is OrderSide.BUY else PositionSide.SHORT
    limits = tuple(Decimal(q) for q in plan["limit_quantities"])
    bound = sum(limits, Decimal(0))
    owners = {row["order_id"]: row for row in ownership}
    entry = exit_qty = remaining = Decimal(0)
    average = None
    by_slot = [Decimal(0)] * 4
    last_time = baseline["baseline_time_ms"]
    for fill in current:
        owner = owners.get(fill.order_id.value)
        if (owner is None or owner["candidate_id"] != candidate.candidate_id
                or fill.dedup_key.category is not Category.LINEAR
                or fill.dedup_key.trading_account_id != candidate.trading_account_id
                or fill.symbol != candidate.symbol):
            raise BoxOwnershipError("foreign execution or conflicting ownership")
        if fill.exchange_timestamp_ms <= last_time:
            raise BoxOwnershipError("execution chronology is ambiguous")
        last_time = fill.exchange_timestamp_ms
        qty = fill.quantity.value
        if owner["role"] == "ENTRY":
            if fill.side is not entry_side:
                raise BoxOwnershipError("owned entry direction mismatch")
            by_slot[owner["slot"] - 1] += qty
            if by_slot[owner["slot"] - 1] > limits[owner["slot"] - 1]:
                raise BoxOwnershipError("owned entry exceeds its frozen grid part")
            average = ((average or Decimal(0)) * remaining + fill.price.value * qty) / (remaining + qty)
            entry += qty
            remaining += qty
        else:
            if fill.side is entry_side or qty > remaining:
                raise BoxOwnershipError("owned exit reverses or exceeds the actual Box lot")
            exit_qty += qty
            remaining -= qty
            if not remaining:
                average = None
        if remaining > bound:
            raise BoxOwnershipError("owned exposure exceeds frozen grid")
    if (position.quantity.value != remaining
            or position.side is not (expected_side if remaining else PositionSide.FLAT)
            or (position.average_entry.value if position.average_entry else None) != average
            or position.updated_at_ms < last_time):
        raise BoxOwnershipError("actual position does not reconcile with owned entries minus exits")
    return BoxExposureProof(candidate.candidate_id, entry, exit_qty, remaining,
                            average, position.version,
                            tuple(f.dedup_key.exec_id.value for f in current))
