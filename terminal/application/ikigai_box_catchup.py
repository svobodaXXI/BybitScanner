"""Pure Box late-admission catch-up planning.

No persistence or order submission. Classifies the frozen P1..P4 slots against
one authoritative READY book and builds deterministic per-slot EXIT LIMIT specs
at the existing frozen common TAKE. The frozen STOP offset is translated to the
actual aggregate average entry (IKIGAI_BOX_STRATEGY_SPEC.md, OFR-5 2026-09-30).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import uuid
from typing import Iterable, Mapping

from terminal.api.models import ClientActionId, MarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.application.command_identity import CommandIdentityCandidate, CommandIdentityFactory
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import CommandId, OrderId, OrderSide
from terminal.market_data.models import BookHealth, NormalizedOrderBook
from terminal.persistence.sqlite_store import (
    BoxOwnedPaperLimitSpec,
    BoxOwnedPaperMarketSpec,
    RobotCandidateRecord,
)


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


class BoxCatchupStopRejected(ValueError):
    """No translated Box STOP satisfies the frozen protection contract."""


@dataclass(frozen=True, slots=True)
class BoxCatchupPlan:
    """Immutable pre-submission catch-up plan; not an order or approval."""

    candidate_id: str
    direction: str
    slots: tuple[BoxCatchupSlot, ...]
    take_price: Decimal
    planned_average: Decimal
    planned_stop: Decimal
    stop_offset: Decimal
    tick_size: Decimal
    book_received_at_ms: int

    @property
    def market_slots(self) -> tuple[int, ...]:
        return tuple(item.slot for item in self.slots if item.entry_mode == "MARKET")

    @property
    def limit_slots(self) -> tuple[int, ...]:
        return tuple(item.slot for item in self.slots if item.entry_mode == "LIMIT")


@dataclass(frozen=True, slots=True)
class BoxTranslatedStop:
    actual_average_entry: Decimal
    stop_offset: Decimal
    raw_stop_price: Decimal
    stop_price: Decimal
    take_price: Decimal


def _fee_rate(value: object, name: str) -> Decimal:
    try:
        rate = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} is invalid") from exc
    if not rate.is_finite() or not Decimal(0) <= rate < Decimal(1):
        raise ValueError(f"{name} must be finite in [0, 1)")
    return rate


def _frozen_stop_terms(candidate: RobotCandidateRecord):
    direction, prices, _quantities, take = _frozen_terms(candidate)
    snapshot = candidate.signal_snapshot
    plan = snapshot["plan"]
    inputs = snapshot.get("inputs")
    full_position = plan.get("full_position")
    if not isinstance(inputs, dict) or not isinstance(full_position, dict):
        raise ValueError("Box inputs and planned full position are required")
    planned_average = _decimal(full_position.get("average_entry"), "planned Box average")
    planned_stop = _decimal(plan.get("stop_price"), "frozen Box STOP")
    tick = _decimal(inputs.get("tick_size"), "Box tick size")
    sign = Decimal(1 if direction == "LONG" else -1)
    stop_offset = sign * (planned_average - planned_stop)
    if stop_offset <= 0 or sign * (prices[3] - planned_stop) <= 0:
        raise ValueError("frozen Box STOP is not beyond P4 and the planned average")
    fees = tuple(
        _fee_rate(inputs.get(key), key)
        for key in ("entry_fee_rate", "target_fee_rate", "stop_fee_rate")
    )
    return direction, prices, take, planned_average, planned_stop, stop_offset, tick, fees


def plan_box_catchup(
    candidate: RobotCandidateRecord,
    book: NormalizedOrderBook,
) -> BoxCatchupPlan:
    """Freeze the per-slot MARKET/LIMIT split and the original STOP offset.

    Crossed slots keep their own identity and quantity for per-slot MARKET
    catch-up; uncrossed slots stay resting LIMITs at their frozen prices. Every
    slot shares the frozen common TAKE. The STOP itself is translated only
    from the VWAP of actually filled, Robot-owned entry exposure.
    """

    direction, _prices, take, average, stop, offset, tick, _fees = _frozen_stop_terms(candidate)
    return BoxCatchupPlan(
        candidate_id=candidate.candidate_id,
        direction=direction,
        slots=classify_box_catchup_slots(candidate, book),
        take_price=take,
        planned_average=average,
        planned_stop=stop,
        stop_offset=offset,
        tick_size=tick,
        book_received_at_ms=int(book.received_at_ms),
    )


def translate_box_catchup_stop(
    candidate: RobotCandidateRecord,
    *,
    actual_average_entry: Decimal,
) -> BoxTranslatedStop:
    """Move the frozen stop offset to the actual filled-exposure VWAP.

    actual_average_entry is the authoritative VWAP of ONLY already-filled,
    Robot-owned Box entry exposure; resting/unfilled slots never contribute
    their planned LIMIT prices. Callers re-invoke this after every additional
    owned fill. It is stateless on purpose: the absolute STOP may widen after a
    later fill (owner-frozen exception to never-widen), while the distance from
    VWAP stays the frozen offset.

    LONG: actual_average - offset; SHORT: actual_average + offset, where the
    offset comes from the frozen planned average and planned STOP. The result
    is tick-normalized outward. TAKE never moves. If the STOP is not strictly
    beyond P4 or fails the existing fee-aware net RR >= 2 contract at the
    actual average, fail closed; no alternative STOP rule is applied.
    """

    (
        direction, prices, take, _average, _stop, offset, tick,
        (entry_fee, target_fee, stop_fee),
    ) = _frozen_stop_terms(candidate)
    entry = _decimal(actual_average_entry, "actual Box average entry")
    sign = Decimal(1 if direction == "LONG" else -1)

    if sign * (take - entry) <= 0:
        raise BoxCatchupStopRejected("actual Box average is not on the loss side of frozen TAKE")
    raw_stop = entry - sign * offset
    if raw_stop <= 0:
        raise BoxCatchupStopRejected("translated Box STOP is not positive")
    outward = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
    stop = normalize_limit_price(raw_stop, tick, outward)
    if sign * (prices[3] - stop) <= 0:
        raise BoxCatchupStopRejected("translated Box STOP is not strictly beyond P4")

    reward = sign * (take - entry) - entry * entry_fee - take * target_fee
    risk = sign * (entry - stop) + entry * entry_fee + stop * stop_fee
    if reward <= 0 or risk <= 0 or Decimal(2) * risk > reward:
        raise BoxCatchupStopRejected(
            "translated Box STOP fails net RR >= 2 at the actual average"
        )
    return BoxTranslatedStop(
        actual_average_entry=entry,
        stop_offset=offset,
        raw_stop_price=raw_stop,
        stop_price=stop,
        take_price=take,
    )


@dataclass(frozen=True, slots=True)
class BoxCatchupMarketPlan:
    slot: int
    quantity: Decimal
    best_price: Decimal
    order_id: OrderId
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
            order_id=OrderId(f"paper-order-{identity.order_link_id}"),
            request=request,
            identity=identity,
        ))
    return tuple(plans)




def build_box_manual_close_market_plan(
    candidate: RobotCandidateRecord,
    book: NormalizedOrderBook,
    *,
    quantity: Decimal,
) -> BoxCatchupMarketPlan:
    """Build one stable owner-requested aggregate Box close (EXIT slot 0)."""
    direction, _prices, _quantities, _take = _frozen_terms(candidate)
    quantity = _decimal(quantity, "Box manual close quantity")
    if book.symbol != candidate.symbol or book.health is not BookHealth.READY:
        raise ValueError("authoritative READY book for Box symbol is required")
    levels = book.bids if direction == "LONG" else book.asks
    if not levels:
        raise ValueError("Box manual close executable book side is empty")
    best_price = _decimal(levels[0].price.value, "Box manual close price")
    side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
    digest = hashlib.sha256(
        f"box-manual-close\0{candidate.candidate_id}".encode("utf-8")
    ).hexdigest()[:32]
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
    return BoxCatchupMarketPlan(
        slot=0,
        quantity=quantity,
        best_price=best_price,
        order_id=OrderId(f"paper-order-{identity.order_link_id}"),
        request=request,
        identity=identity,
    )


def build_box_emergency_close_market_plan(
    candidate: RobotCandidateRecord,
    book: NormalizedOrderBook,
    *,
    quantity: Decimal,
) -> BoxCatchupMarketPlan:
    """Build one stable aggregate Box emergency-close MARKET plan (EXIT slot 0)."""
    direction, _prices, _quantities, _take = _frozen_terms(candidate)
    quantity = _decimal(quantity, "Box emergency close quantity")
    if book.symbol != candidate.symbol or book.health is not BookHealth.READY:
        raise ValueError("authoritative READY book for Box symbol is required")
    levels = book.bids if direction == "LONG" else book.asks
    if not levels:
        raise ValueError("Box emergency close executable book side is empty")
    best_price = _decimal(levels[0].price.value, "Box emergency close price")
    side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
    digest = hashlib.sha256(
        f"box-emergency-close\0{candidate.candidate_id}".encode("utf-8")
    ).hexdigest()[:32]
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
    return BoxCatchupMarketPlan(
        slot=0,
        quantity=quantity,
        best_price=best_price,
        order_id=OrderId(f"paper-order-{identity.order_link_id}"),
        request=request,
        identity=identity,
    )

def durable_box_market_intent(plan: BoxCatchupMarketPlan) -> dict[str, object]:
    """Serialize one exact per-slot MARKET request before mutation."""
    return {
        "slot": plan.slot,
        "quantity": str(plan.quantity),
        "best_price": str(plan.best_price),
        "order_id": plan.order_id.value,
        "client_action_id": plan.request.client_action_id.value,
        "command_id": plan.identity.command_id.value,
        "order_link_id": plan.identity.order_link_id,
        "symbol": plan.request.symbol,
        "side": plan.request.side.value,
        "volume_unit": plan.request.volume.unit.value,
        "volume_amount": str(plan.request.volume.amount),
        "sizing_reference_price": str(plan.request.sizing_reference_price),
        "slippage_type": plan.request.slippage_type,
        "slippage_value": str(plan.request.slippage_value),
    }


def restore_box_market_plan(intent: Mapping[str, object]) -> BoxCatchupMarketPlan:
    """Restore and verify a previously persisted per-slot MARKET request."""
    try:
        slot = int(intent["slot"])
    except Exception as exc:
        raise ValueError("Box MARKET intent slot is invalid") from exc
    if slot not in {0, 1, 2, 3, 4}:
        raise ValueError("Box MARKET intent slot is invalid")
    quantity = _decimal(intent.get("quantity"), "Box MARKET quantity")
    best_price = _decimal(intent.get("best_price"), "Box MARKET best price")
    digest = str(intent.get("client_action_id", "")).removeprefix("box-market-")
    if len(digest) != 32 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Box MARKET client action identity is invalid")
    deterministic_uuid = uuid.UUID(hex=digest)
    expected_identity = CommandIdentityFactory(lambda: deterministic_uuid).create()
    if (
        str(intent.get("command_id", "")) != expected_identity.command_id.value
        or str(intent.get("order_link_id", "")) != expected_identity.order_link_id
        or str(intent.get("order_id", ""))
        != f"paper-order-{expected_identity.order_link_id}"
    ):
        raise ValueError("Box MARKET durable identity changed")
    try:
        side = OrderSide(str(intent.get("side", "")))
        volume_unit = VolumeUnit(str(intent.get("volume_unit", "")))
    except ValueError as exc:
        raise ValueError("Box MARKET enum value is invalid") from exc
    if volume_unit is not VolumeUnit.USDT:
        raise ValueError("Box MARKET durable volume unit changed")
    request = MarketCommandRequest(
        client_action_id=ClientActionId(str(intent["client_action_id"])),
        symbol=str(intent.get("symbol", "")).strip().upper(),
        side=side,
        volume=VolumeRequest(volume_unit, _decimal(intent.get("volume_amount"), "Box MARKET notional")),
        sizing_reference_price=_decimal(
            intent.get("sizing_reference_price"), "Box MARKET sizing reference"
        ),
        slippage_type=str(intent.get("slippage_type", "")),
        slippage_value=_decimal(intent.get("slippage_value"), "Box MARKET slippage"),
    )
    if (
        request.sizing_reference_price != best_price
        or request.volume.amount != quantity * best_price
        or request.slippage_type != "Percent"
        or request.slippage_value != Decimal("0.5")
    ):
        raise ValueError("Box MARKET durable request changed")
    return BoxCatchupMarketPlan(
        slot=slot,
        quantity=quantity,
        best_price=best_price,
        order_id=OrderId(str(intent["order_id"])),
        request=request,
        identity=expected_identity,
    )

def build_box_market_ownership_specs(
    plans: Iterable[BoxCatchupMarketPlan],
) -> tuple[BoxOwnedPaperMarketSpec, ...]:
    """Project deterministic future PAPER MARKET ids into ownership specs."""
    ordered = tuple(sorted(plans, key=lambda item: item.slot))
    if len({item.slot for item in ordered}) != len(ordered):
        raise ValueError("duplicate Box MARKET slot")
    return tuple(
        BoxOwnedPaperMarketSpec(slot=item.slot, order_id=item.order_id)
        for item in ordered
    )


def ready_box_exit_slots(
    candidate: RobotCandidateRecord,
    proof,
) -> tuple[int, ...]:
    """Return fully-filled entry slots that do not yet own any exit quantity."""
    _direction, _prices, quantities, _take = _frozen_terms(candidate)
    entry_by_slot = getattr(proof, "entry_by_slot", None)
    exit_by_slot = getattr(proof, "exit_by_slot", None)
    if (
        not isinstance(entry_by_slot, tuple)
        or not isinstance(exit_by_slot, tuple)
        or len(entry_by_slot) != 4
        or len(exit_by_slot) != 4
    ):
        raise ValueError("Box ownership proof lacks per-slot quantities")
    ready = []
    for index, planned in enumerate(quantities):
        entered = entry_by_slot[index]
        exited = exit_by_slot[index]
        if entered < 0 or exited < 0 or exited > entered:
            raise ValueError("Box ownership proof has invalid slot quantities")
        if entered == planned and exited == 0:
            ready.append(index + 1)
    return tuple(ready)

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
