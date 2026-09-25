"""Build deterministic first-grid PAPER order specs from a frozen Box plan.

Pure application adapter only: no admission, persistence, execution or runtime calls.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib

from terminal.domain.models import OrderId, OrderSide
from terminal.persistence.sqlite_store import BoxOwnedPaperLimitSpec, RobotCandidateRecord


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a frozen decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} is invalid") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def build_box_first_grid_specs(
    candidate: RobotCandidateRecord, *, created_at_ms: int,
) -> tuple[BoxOwnedPaperLimitSpec, ...]:
    """Translate one immutable BOX_PLAN_ONLY snapshot into four stable ENTRY specs."""
    if candidate.status != "BOX_PLAN_ONLY":
        raise ValueError("BOX_PLAN_ONLY candidate is required")
    if type(created_at_ms) is not int or created_at_ms < 0:
        raise ValueError("created_at_ms must be a non-negative integer")

    snapshot = candidate.signal_snapshot
    if (snapshot.get("pattern") != "IKIGAI_BOX"
            or snapshot.get("environment") != "PAPER"
            or snapshot.get("execution_authorized") is not False
            or snapshot.get("attempt") != 1):
        raise ValueError("non-executable PAPER Box first attempt is required")

    identity = snapshot.get("identity")
    plan = snapshot.get("plan")
    if not isinstance(identity, dict) or not isinstance(plan, dict):
        raise ValueError("Box identity and plan are required")
    symbol = identity.get("symbol")
    direction = identity.get("direction")
    if not isinstance(symbol, str) or not symbol or symbol != candidate.symbol.value:
        raise ValueError("Box symbol conflicts with candidate")
    if direction not in {"LONG", "SHORT"} or plan.get("direction") != direction:
        raise ValueError("Box direction conflicts with frozen plan")
    if plan.get("execution_authorized") is not False or plan.get("environment") != "PAPER":
        raise ValueError("frozen plan must remain non-executable PAPER")

    prices = plan.get("limit_prices")
    quantities = plan.get("limit_quantities")
    if not isinstance(prices, list) or not isinstance(quantities, list) or len(prices) != 4 or len(quantities) != 4:
        raise ValueError("Box first grid requires four frozen prices and quantities")

    side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
    specs = []
    for slot, (price_value, quantity_value) in enumerate(zip(prices, quantities), start=1):
        price = _decimal(price_value, "LIMIT price")
        quantity = _decimal(quantity_value, "LIMIT quantity")
        digest = hashlib.sha256(
            f"box-first-grid\0{candidate.candidate_id}\0{slot}".encode("utf-8")
        ).hexdigest()
        fingerprint = hashlib.sha256(
            f"{candidate.snapshot_sha256}\0{slot}\0{side.value}\0{price}\0{quantity}".encode("utf-8")
        ).hexdigest()
        specs.append(BoxOwnedPaperLimitSpec(
            slot=slot,
            client_action_id=f"box-entry-{digest}",
            request_fingerprint=fingerprint,
            order_id=OrderId(f"paper-box-entry-{digest}"),
            order_link_id=f"box-entry-{digest}",
            side=side,
            price=price,
            quantity=quantity,
            created_at_ms=created_at_ms,
        ))
    return tuple(specs)
