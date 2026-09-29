"""Pure Box late-admission catch-up planning.

No persistence or order submission. Classifies the frozen P1..P4 slots against
one authoritative READY book and builds deterministic per-slot EXIT LIMIT specs
at the existing frozen common TAKE.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import uuid
from typing import Iterable

from terminal.api.models import ClientActionId, MarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.application.command_identity import CommandIdentityCandidate, CommandIdentityFactory
from terminal.domain.models import CommandId, OrderId, OrderSide
from terminal.market_data.models import BookHealth, NormalizedOrderBook
from terminal.persistence.sqlite_store import BoxOwnedPaperLimitSpec, RobotCandidateRecord


@dataclass(frozen=True, slots=True)
class BoxCatchupSlot:
    slot: int
    planned_price: Decimal
    quantity: Decimal
    entry_mode: str  # MARKET or LIMIT


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} is invalid") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _frozen_terms(candidate: RobotCandidateRecord):
    if candidate.status != "BOX_PLAN_ONLY":
        raise ValueError("BOX_PLAN_ONLY candidate is required")
    snapshot = candidate.signal_snapshot
    if (
        snapshot.get("pattern") != "IKIGAI_BOX"
        or snapshot.get("environment") != "PAPER"
        or snapshot.get("execution_authorized") is not False
        or snapshot.get("attempt") != 1
    ):
        raise ValueError("non-executable PAPER Box first attempt is required")
    identity = snapshot.get("identity")
    plan = snapshot.get("plan")
    if not isinstance(identity, dict) or not isinstance(plan, dict):
        raise ValueError("Box identity and plan are required")
    symbol = str(identity.get("symbol", "")).strip().upper()
    direction = str(identity.get("direction", "")).strip().upper()
    if symbol != candidate.symbol.value or direction not in {"LONG", "SHORT"}:
        raise ValueError("Box identity conflicts with candidate")
    prices = plan.get("limit_prices")
    quantities = plan.get("limit_quantities")
    if (
        not isinstance(prices, list)
        or not isinstance(quantities, list)
        or len(prices) != 4
        or len(quantities) != 4
    ):
        raise ValueError("Box first grid requires four frozen prices and quantities")
    return (
        direction,
        tuple(_decimal(value, "LIMIT price") for value in prices),
        tuple(_decimal(value, "LIMIT quantity") for value in quantities),
        _decimal(plan.get("take_price"), "frozen Box TAKE"),
    )


def classify_box_catchup_slots(
    candidate: RobotCandidateRecord,
    book: NormalizedOrderBook,
) -> tuple[BoxCatchupSlot, ...]:
    """Classify each frozen entry slot as MARKET-now or resting LIMIT.

    LONG uses the current executable ask: a buy slot is already crossed when
    best ask <= its frozen entry level. SHORT mirrors on the executable bid.
    The function never infers historical crossings from candles and never
    submits anything.
    """

    direction, prices, quantities, _take = _frozen_terms(candidate)
    if book.symbol != candidate.symbol or book.health is not BookHealth.READY:
        raise ValueError("authoritative READY book for Box symbol is required")

    levels = book.asks if direction == "LONG" else book.bids
    if not levels:
        raise ValueError("executable book side is empty")
    executable = _decimal(levels[0].price.value, "best executable price")

    result = []
    for slot, (price, quantity) in enumerate(zip(prices, quantities), start=1):
        crossed = executable <= price if direction == "LONG" else executable >= price
        result.append(BoxCatchupSlot(
            slot=slot,
            planned_price=price,
            quantity=quantity,
            entry_mode="MARKET" if crossed else "LIMIT",
        ))
    return tuple(result)



@dataclass(frozen=True, slots=True)
class BoxCatchupMarketPlan:
    slot: int
    quantity: Decimal
    best_price: Decimal
    request: MarketCommandRequest
    identity: CommandIdentityCandidate


def _market_digest(candidate_id: str, slot: int) -> str:
    return hashlib.sha256(
        f"box-catchup-market\\0{candidate_id}\\0{slot}".encode("utf-8")
    ).hexdigest()[:32]


def build_box_market_plans(
    candidate: RobotCandidateRecord,
    book: NormalizedOrderBook,
    *,
    slots: Iterable[int],
) -> tuple[BoxCatchupMarketPlan, ...]:
    """Build exact-slot PAPER MARKET requests; caller must preflight quantity.

    MarketCommandRequest has no base-quantity volume unit. To preserve the
    already-frozen slot quantity without widening that API, each request uses
    USDT notional = slot_quantity * current executable price. Canonical PAPER
    preflight must normalize back to exactly the same slot quantity; any other
    result is a fail-closed mismatch and must not be submitted.
    """

    direction, _prices, quantities, _take = _frozen_terms(candidate)
    classified = {item.slot: item for item in classify_box_catchup_slots(candidate, book)}
    normalized_slots = tuple(sorted(set(slots)))
    if any(type(slot) is not int or slot not in {1, 2, 3, 4} for slot in normalized_slots):
        raise ValueError("Box MARKET slots must be in 1..4")
    if any(classified[slot].entry_mode != "MARKET" for slot in normalized_slots):
        raise ValueError("Box MARKET plan requested for an uncrossed slot")

    levels = book.asks if direction == "LONG" else book.bids
    best_price = _decimal(levels[0].price.value, "best executable price")
    side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
    plans = []
    for slot in normalized_slots:
        quantity = quantities[slot - 1]
        digest = _market_digest(candidate.candidate_id, slot)
        deterministic_uuid = uuid.UUID(hex=digest)
        identity = CommandIdentityFactory(lambda value=deterministic_uuid: value).create()
        request = MarketCommandRequest(
            client_action_id=ClientActionId(f"box-market-{digest}"),
            symbol=candidate.symbol.value,
            side=side,
            volume=VolumeRequest(VolumeUnit.USDT, quantity * best_price),
            sizing_reference_price=best_price,
            slippage_type="Percent",
            slippage_value=Decimal("0.5"),
        )
        plans.append(BoxCatchupMarketPlan(
            slot=slot,
            quantity=quantity,
            best_price=best_price,
            request=request,
            identity=identity,
        ))
    return tuple(plans)

def build_box_exit_specs(
    candidate: RobotCandidateRecord,
    *,
    slots: Iterable[int],
    created_at_ms: int,
) -> tuple[BoxOwnedPaperLimitSpec, ...]:
    """Build one durable EXIT LIMIT identity per filled slot at common TAKE."""

    if type(created_at_ms) is not int or created_at_ms < 0:
        raise ValueError("created_at_ms must be a non-negative integer")
    direction, _prices, quantities, take = _frozen_terms(candidate)
    normalized_slots = tuple(sorted(set(slots)))
    if any(type(slot) is not int or slot not in {1, 2, 3, 4} for slot in normalized_slots):
        raise ValueError("Box EXIT slots must be in 1..4")

    side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
    specs = []
    for slot in normalized_slots:
        quantity = quantities[slot - 1]
        digest = hashlib.sha256(
            f"box-first-exit\0{candidate.candidate_id}\0{slot}".encode("utf-8")
        ).hexdigest()
        fingerprint = hashlib.sha256(
            f"{candidate.snapshot_sha256}\0EXIT\0{slot}\0{side.value}\0{take}\0{quantity}".encode("utf-8")
        ).hexdigest()
        specs.append(BoxOwnedPaperLimitSpec(
            slot=slot,
            client_action_id=f"box-exit-{digest}",
            request_fingerprint=fingerprint,
            order_id=OrderId(f"paper-box-exit-{digest}"),
            order_link_id=f"box-exit-{digest}",
            side=side,
            price=take,
            quantity=quantity,
            created_at_ms=created_at_ms,
        ))
    return tuple(specs)
