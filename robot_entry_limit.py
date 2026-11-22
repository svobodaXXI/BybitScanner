"""Robot v0.1 initial retest LIMIT orchestration over shared Terminal contracts.

This module does not execute or persist orders itself. It builds one deterministic
PAPER LIMIT command for a confirmed retest and hands that command to the existing
runtime ``create_limit`` capability exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any, Mapping, Protocol

from robot_state_machine import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    PHASE_RETEST_DETECTED,
    boundary_price,
)
from terminal.api.models import (
    ClientActionId,
    LimitCommandRequest,
    PaperLimitAmendRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
)
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import OrderSide


class RobotEntryLimitError(RuntimeError):
    """Raised when an initial retest LIMIT cannot be built safely."""


class PaperLimitSubmitter(Protocol):
    def create_limit(self, request: LimitCommandRequest): ...
    def amend_limit(self, request: PaperLimitAmendRequest): ...


REPRICE_CANDLES = 5


@dataclass(frozen=True, slots=True)
class InitialRetestLimitPlan:
    candidate_id: str
    direction: str
    retest_index: int
    boundary_price: Decimal
    request: LimitCommandRequest


@dataclass(frozen=True, slots=True)
class RetestLimitRepricePlan:
    candidate_id: str
    geometry_index: int
    boundary_price: Decimal
    request: PaperLimitAmendRequest


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotEntryLimitError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotEntryLimitError(f"{field} must be finite and positive")
    return number


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotEntryLimitError(f"{field} must be an integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotEntryLimitError(f"{field} must be an integer") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RobotEntryLimitError(f"{field} must be an integer")
    return int(number)


def _stable_client_action_id(candidate_id: str, retest_index: int) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0initial-retest-limit\0{retest_index}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-retest-limit-{digest}")


def _stable_reprice_action_id(
    candidate_id: str, order_id: str, geometry_index: int,
) -> ClientActionId:
    digest = hashlib.sha256(
        (
            f"{candidate_id}\0retest-limit-reprice\0"
            f"{order_id}\0{geometry_index}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-retest-reprice-{digest}")


def reprice_due(*, last_limit_index: int, current_index: int) -> bool:
    previous = _required_int(last_limit_index, "last_limit_index")
    current = _required_int(current_index, "current_index")
    if current < previous:
        raise RobotEntryLimitError("current_index precedes last_limit_index")
    return current - previous >= REPRICE_CANDLES


def _entry_side_and_price(
    snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    geometry_index: int,
    tick_size: Decimal,
) -> tuple[OrderSide, Decimal]:
    direction = str(state.get("direction", "")).strip().upper()
    if direction == DIRECTION_LONG:
        side = OrderSide.BUY
        boundary_side = "upper"
        offset_sign = Decimal("1")
        expected_pattern = "Falling Wedge"
    elif direction == DIRECTION_SHORT:
        side = OrderSide.SELL
        boundary_side = "lower"
        offset_sign = Decimal("-1")
        expected_pattern = "Rising Wedge"
    else:
        raise RobotEntryLimitError("unsupported Robot direction")
    if str(snapshot.get("pattern", "")).strip() != expected_pattern:
        raise RobotEntryLimitError("state direction differs from frozen pattern")

    index = _required_int(geometry_index, "geometry_index")
    tick = _positive_decimal(tick_size, "tick_size")
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=index),
        "frozen boundary price",
    )
    raw_limit_price = frozen_boundary + offset_sign * tick * Decimal("2")
    if raw_limit_price <= 0:
        raise RobotEntryLimitError("aggressive LIMIT price is not positive")
    return side, normalize_limit_price(raw_limit_price, tick, side)


def build_initial_retest_limit(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    tick_size: Decimal,
) -> InitialRetestLimitPlan:
    """Build the single initial 1 WV LIMIT created after retest detection.

    The frozen Scanner boundary is evaluated at the retest candle index. The
    requested price is two ticks through that boundary in the aggressive entry
    direction, then normalized with the shared Terminal price normalizer.
    """

    if not isinstance(candidate, Mapping):
        raise RobotEntryLimitError("candidate must be a mapping")
    if not isinstance(state, Mapping):
        raise RobotEntryLimitError("state must be a mapping")
    if candidate.get("status") != "APPROVED":
        raise RobotEntryLimitError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotEntryLimitError("initial retest LIMIT requires 1m candidate")
    if state.get("phase") != PHASE_RETEST_DETECTED:
        raise RobotEntryLimitError("initial retest LIMIT requires RETEST_DETECTED")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    if not candidate_id:
        raise RobotEntryLimitError("candidate_id is required")

    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotEntryLimitError("signal snapshot is missing")
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    if not symbol:
        raise RobotEntryLimitError("signal snapshot has no symbol")

    direction = str(state.get("direction", "")).strip().upper()
    retest_index = _required_int(state.get("retest_index"), "retest_index")
    breakout_index = _required_int(state.get("breakout_index"), "breakout_index")
    if retest_index <= breakout_index:
        raise RobotEntryLimitError("retest must occur after breakout")

    side, normalized_limit_price = _entry_side_and_price(
        snapshot,
        state,
        geometry_index=retest_index,
        tick_size=tick_size,
    )
    boundary_side = "upper" if direction == DIRECTION_LONG else "lower"
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=retest_index),
        "frozen boundary price",
    )

    request = LimitCommandRequest(
        client_action_id=_stable_client_action_id(candidate_id, retest_index),
        symbol=symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        sizing_reference_price=normalized_limit_price,
        limit_price=normalized_limit_price,
        time_in_force=TimeInForce.GTC,
    )
    return InitialRetestLimitPlan(
        candidate_id=candidate_id,
        direction=direction,
        retest_index=retest_index,
        boundary_price=frozen_boundary,
        request=request,
    )


def build_retest_limit_reprice(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    geometry_index: int,
    tick_size: Decimal,
    order_id: str,
) -> RetestLimitRepricePlan:
    """Amend the still-unfilled entry LIMIT to the current frozen boundary."""

    if not isinstance(candidate, Mapping) or candidate.get("status") != "APPROVED":
        raise RobotEntryLimitError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotEntryLimitError("retest LIMIT reprice requires 1m candidate")
    if not isinstance(state, Mapping) or state.get("phase") != PHASE_RETEST_DETECTED:
        raise RobotEntryLimitError("retest LIMIT reprice requires RETEST_DETECTED")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    snapshot = candidate.get("signal_snapshot")
    normalized_order_id = str(order_id).strip()
    if not candidate_id or not isinstance(snapshot, Mapping) or not normalized_order_id:
        raise RobotEntryLimitError("candidate identity, snapshot and order_id are required")

    index = _required_int(geometry_index, "geometry_index")
    geometry = snapshot.get("robot_geometry")
    if geometry is None:
        geometry = snapshot.get("geometry")
    apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
    if not isinstance(apex, Mapping):
        raise RobotEntryLimitError("signal snapshot has no frozen apex")
    try:
        apex_index = Decimal(str(apex.get("index")))
    except Exception as exc:
        raise RobotEntryLimitError("apex_index must be decimal-compatible") from exc
    if not apex_index.is_finite() or apex_index < 0:
        raise RobotEntryLimitError("apex_index must be finite and non-negative")
    if Decimal(index) >= apex_index:
        raise RobotEntryLimitError("reprice is forbidden at or after apex")

    _side, price = _entry_side_and_price(
        snapshot,
        state,
        geometry_index=index,
        tick_size=tick_size,
    )
    boundary_side = (
        "upper"
        if str(state.get("direction", "")).strip().upper() == DIRECTION_LONG
        else "lower"
    )
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=index),
        "frozen boundary price",
    )
    return RetestLimitRepricePlan(
        candidate_id=candidate_id,
        geometry_index=index,
        boundary_price=frozen_boundary,
        request=PaperLimitAmendRequest(
            client_action_id=_stable_reprice_action_id(
                candidate_id, normalized_order_id, index,
            ),
            symbol=str(snapshot.get("symbol", "")).strip().upper(),
            order_id=normalized_order_id,
            limit_price=price,
        ),
    )


def submit_retest_limit_reprice(
    submitter: PaperLimitSubmitter,
    plan: RetestLimitRepricePlan,
):
    return submitter.amend_limit(plan.request)


def submit_initial_retest_limit(
    submitter: PaperLimitSubmitter,
    plan: InitialRetestLimitPlan,
):
    """Submit exactly once through the shared PAPER LIMIT capability.

    No retry or fallback is performed here. Transport ambiguity remains owned by
    the shared execution lifecycle and later Robot reconciliation slices.
    """

    return submitter.create_limit(plan.request)


# The original protected Robot LIMIT owner remains the only execution path.
# This is a pure, unsubmitted quote for an earlier post-breakout Wedge entry.
# It MUST NOT be passed to create_limit without a separately validated durable
# owner/recovery path; existing retest LIMIT behavior remains unchanged.
@dataclass(frozen=True, slots=True)
class PostBreakoutImpulseLimitResearch:
    candidate_id: str
    state_revision: int
    breakout_known_at_ms: int
    decision_ms: int
    direction: str
    quoted_price: Decimal
    stop_price: Decimal
    take_price: Decimal
    planned_net_rr: Decimal
    worst_loss_per_base_usdt: Decimal
    request: LimitCommandRequest

    @property
    def trading_authorized(self) -> bool:
        return False


def build_post_breakout_wedge_impulse_limit_research(
    record,
    flow_receipt,
    book,
    *,
    tick_size: Decimal,
    now_ms: int,
    max_book_age_ms: int = 1000,
) -> PostBreakoutImpulseLimitResearch:
    """Quote a canonical Wedge entry BEFORE its former retest, without orders.

    Uses the actual READY book side instead of the old retest-boundary
    price. The existing frozen Robot STOP/TAKE and fee-aware RR are reused.
    Admission, position exposure, working-volume normalization, persistent
    intent, protected entry coverage, actual fills and risk budget MUST be
    proven independently by the existing execution owner BEFORE dispatch.
    """
    from robot_entry_flow_evidence import (
        canonical_host_breakout_known_at_ms,
        observe_post_breakout_impulse_timing,
    )
    import robot_protection
    from retest_account_risk import position_worst_case_loss_usdt
    from terminal.market_data.models import BookHealth, NormalizedOrderBook

    if (type(now_ms) is not int or now_ms <= 0
            or type(max_book_age_ms) is not int or max_book_age_ms <= 0
            or not isinstance(tick_size, Decimal)
            or not tick_size.is_finite() or tick_size <= 0):
        raise RobotEntryLimitError("invalid quote clock or tick size")
    try:
        snapshot, state = record.signal_snapshot, record.robot_state
        cid, rev, symbol = record.candidate_id, record.state_revision, record.symbol.value
    except AttributeError as error:
        raise RobotEntryLimitError("frozen candidate identity unavailable") from error
    if (record.status != "APPROVED" or not isinstance(snapshot, Mapping)
            or not isinstance(state, Mapping)
            or snapshot.get("pattern") not in ("Falling Wedge", "Rising Wedge")
            or snapshot.get("symbol") != symbol
            or state.get("phase") != "WAITING_RETEST"
            or state.get("retest_index") is not None
            or state.get("execution") not in (None, {})
            or type(rev) is not int or rev < 0
            or not isinstance(cid, str) or not cid):
        raise RobotEntryLimitError("not an unowned approved pre-retest Wedge")
    breakout_ms = canonical_host_breakout_known_at_ms(record)
    if breakout_ms is None:
        raise RobotEntryLimitError("original Wedge breakout is unproven")
    choice = observe_post_breakout_impulse_timing(
        record, flow_receipt, breakout_known_at_ms=breakout_ms,
        decision_ms=now_ms,
    )
    if choice is None or choice.outcome != "IMPULSE_ENTRY_RESEARCH":
        raise RobotEntryLimitError("candidate-bound directional flow not certified")
    if (not isinstance(book, NormalizedOrderBook)
            or book.symbol.value != symbol or book.health is not BookHealth.READY
            or type(book.received_at_ms) is not int
            or not 0 <= now_ms - book.received_at_ms <= max_book_age_ms
            or not book.bids or not book.asks
            or book.bids[0].price.value >= book.asks[0].price.value):
        raise RobotEntryLimitError("fresh executable two-sided book is not proven")
    for source_ms in (book.source_event_at_ms, book.source_matching_engine_cts_ms):
        if source_ms is not None and (
                type(source_ms) is not int or source_ms > now_ms):
            raise RobotEntryLimitError("book source clock is invalid")
    direction = state["direction"]
    side = OrderSide.BUY if direction == DIRECTION_LONG else OrderSide.SELL
    best_bid = book.bids[0].price.value
    best_ask = book.asks[0].price.value
    price = best_ask if side is OrderSide.BUY else best_bid
    if (not isinstance(price, Decimal) or price <= 0
            or not price.is_finite()
            or normalize_limit_price(price, tick_size, side) != price):
        raise RobotEntryLimitError("book price is not executable at the tick")
    geometry_index = state.get("geometry_cursor")
    index = _required_int(geometry_index, "geometry_cursor")
    if index < state["breakout_index"]:
        raise RobotEntryLimitError("Wedge cursor predates breakout")
    # The early entry is evaluated before the normal candle-state advance.
    # Use the current closed-M1 time slot in the frozen coordinate space,
    # not a stale lifecycle cursor. This projects geometry only; it does
    # not assert missing OHLC or advance the durable Robot state.
    from scanner_geometry_cursor import project_latest_geometry_index
    from robot_state_machine import resume_without_replay, PHASE_EXPIRED_AT_APEX

    latest_closed_start = now_ms // 60_000 * 60_000 - 60_000
    index = project_latest_geometry_index(
        snapshot, latest_closed_candle_time_ms=latest_closed_start,
    )
    resumed, _ = resume_without_replay(
        snapshot, state, latest_geometry_index=index,
    )
    if resumed["phase"] == PHASE_EXPIRED_AT_APEX:
        raise RobotEntryLimitError("Wedge apex reached before impulse entry")
    boundary_side = "upper" if side is OrderSide.BUY else "lower"
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=index),
        "frozen Wedge boundary",
    )
    # A quote merely touching or returning inside the pattern is NOT the
    # impulse-entry scenario; the exit-side best bid/ask must both clear it.
    if (side is OrderSide.BUY and best_bid <= frozen_boundary
            or side is OrderSide.SELL and best_ask >= frozen_boundary):
        raise RobotEntryLimitError("price no longer outside pattern realization boundary")
    structural = robot_protection.wedge_structural_extreme(snapshot, direction)
    reference, frozen_target = robot_protection.wedge_frozen_reference_target(
        snapshot, direction,
    )
    candidate = {
        "candidate_id": cid, "status": "APPROVED", "timeframe": "1",
        "signal_snapshot": snapshot,
    }
    protection = robot_protection.build_protection_plan(
        candidate, state, average_entry=price,
        structural_extreme=structural, tick_size=tick_size,
        frozen_signal_reference_price=reference,
        frozen_scanner_target_price=frozen_target,
    )
    # A one-base-unit fee ratio is quantity-invariant for the fixed stop/take;
    # this is a quote, NOT a proof of normalized 1 WV or total account risk.
    fee = Decimal("0.0006")
    rr = robot_protection.post_fill_net_rr(
        direction, average_entry=price, quantity=Decimal(1),
        entry_fee=price * fee, stop_price=protection.stop_price,
        take_price=protection.take_price, exit_fee_rate=fee,
    )
    # Post-fill native Wedge protection requires >=2 net RR. Do not issue a
    # marketable pre-retest LIMIT that the existing owner would immediately
    # emergency-close after filling.
    if rr < max(Decimal("2"), robot_protection.wedge_min_entry_rr()):
        raise RobotEntryLimitError("after-fee Wedge RR below post-fill owner floor")
    risk = position_worst_case_loss_usdt(
        direction=direction, quantity=Decimal(1), entry_price=price,
        stop_price=protection.stop_price, fee_rate=fee,
    )
    if risk is None or risk <= 0:
        raise RobotEntryLimitError("Wedge protective loss is not computable")
    # One stable initial-attempt action identity, independent of book refresh.
    # Owner-side persistence MUST freeze its price before ever dispatching.
    digest = hashlib.sha256(
        f"{cid}\0post-breakout-impulse-limit\0{state['breakout_index']}".encode("utf-8")
    ).hexdigest()[:32]
    request = LimitCommandRequest(
        client_action_id=ClientActionId(f"robot-impulse-limit-{digest}"),
        symbol=symbol, side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        sizing_reference_price=price, limit_price=price,
        time_in_force=TimeInForce.GTC,
    )
    return PostBreakoutImpulseLimitResearch(
        candidate_id=cid, state_revision=rev,
        breakout_known_at_ms=breakout_ms, decision_ms=now_ms,
        direction=direction, quoted_price=price,
        stop_price=protection.stop_price, take_price=protection.take_price,
        planned_net_rr=rr, worst_loss_per_base_usdt=risk,
        request=request,
    )



def build_post_breakout_l_shape_impulse_limit_research(
    record, flow_receipt, book, *,
    tick_size: Decimal,
    now_ms: int,
    max_book_age_ms: int = 1000,
) -> PostBreakoutImpulseLimitResearch:
    """Quote an original L-shape's post-breakout impulse before its retest.

    Does not create an order or confer admission. Reuses immutable horizontal
    geometry and the native L-shape STOP/TAKE. MIRROR is deliberately excluded:
    its source/first-retest campaign has different ownership constraints.
    """
    import robot_l_shape
    import robot_protection
    from retest_account_risk import position_worst_case_loss_usdt
    from robot_entry_flow_evidence import (
        canonical_host_breakout_known_at_ms,
        observe_post_breakout_impulse_timing,
    )
    from terminal.market_data.models import BookHealth, NormalizedOrderBook

    if (type(now_ms) is not int or now_ms <= 0
            or type(max_book_age_ms) is not int or max_book_age_ms <= 0
            or not isinstance(tick_size, Decimal)
            or not tick_size.is_finite() or tick_size <= 0):
        raise RobotEntryLimitError("invalid L-shape impulse quote clock or tick")
    try:
        snapshot, state = record.signal_snapshot, record.robot_state
        cid, rev, symbol = record.candidate_id, record.state_revision, record.symbol.value
    except AttributeError as error:
        raise RobotEntryLimitError("L-shape candidate identity unavailable") from error
    if (record.status != "APPROVED"
            or not isinstance(snapshot, Mapping)
            or not isinstance(state, Mapping)
            or snapshot.get("pattern") != "L-shape"
            or snapshot.get("symbol") != symbol
            or state.get("state_version") != robot_l_shape.STATE_VERSION
            or state.get("pattern") != "L-shape"
            or state.get("phase") != robot_l_shape.PHASE_WAITING_RETEST
            or state.get("retest_time_ms") is not None
            or state.get("execution") not in (None, {})
            or type(rev) is not int or rev < 0
            or not isinstance(cid, str) or not cid):
        raise RobotEntryLimitError("not an unowned, approved pre-retest L-shape")
    try:
        terms = robot_l_shape.frozen_terms(snapshot)
        if state.get("direction") != terms.direction:
            raise RobotEntryLimitError("L-shape direction differs from frozen plan")
        breakout_ms = canonical_host_breakout_known_at_ms(record)
    except robot_l_shape.RobotLShapeError as error:
        raise RobotEntryLimitError("invalid frozen L-shape geometry") from error
    if breakout_ms is None:
        raise RobotEntryLimitError("original L-shape breakout is unproven")
    choice = observe_post_breakout_impulse_timing(
        record, flow_receipt, breakout_known_at_ms=breakout_ms,
        decision_ms=now_ms,
    )
    if choice is None or choice.outcome != "IMPULSE_ENTRY_RESEARCH":
        raise RobotEntryLimitError("L-shape directional publicTrade is unproven")
    if (not isinstance(book, NormalizedOrderBook)
            or book.symbol.value != symbol or book.health is not BookHealth.READY
            or type(book.received_at_ms) is not int
            or not 0 <= now_ms - book.received_at_ms <= max_book_age_ms
            or not book.bids or not book.asks
            or book.bids[0].price.value >= book.asks[0].price.value):
        raise RobotEntryLimitError("L-shape book is not fresh, two-sided and READY")
    for source_ms in (book.source_event_at_ms, book.source_matching_engine_cts_ms):
        if source_ms is not None and (
                type(source_ms) is not int or source_ms > now_ms):
            raise RobotEntryLimitError("L-shape book source time is invalid")
    direction = terms.direction
    side = OrderSide.BUY if direction == DIRECTION_LONG else OrderSide.SELL
    bid, ask = book.bids[0].price.value, book.asks[0].price.value
    price = ask if side is OrderSide.BUY else bid
    if (not isinstance(price, Decimal) or not price.is_finite() or price <= 0
            or normalize_limit_price(price, tick_size, side) != price):
        raise RobotEntryLimitError("L-shape executable quote price is invalid")
    # A retest or move back INSIDE the frozen horizontal boundary is NOT an
    # impulsive realization-side entry, regardless of the observed taker wave.
    if (direction == DIRECTION_LONG and bid <= terms.reference
            or direction == DIRECTION_SHORT and ask >= terms.reference):
        raise RobotEntryLimitError("L-shape price has not cleared frozen boundary")
    payload = {
        "candidate_id": cid, "status": "APPROVED",
        "timeframe": "1", "signal_snapshot": snapshot,
    }
    protection = robot_protection.build_l_shape_protection_plan(
        payload, state, average_entry=price, tick_size=tick_size,
    )
    rr = robot_l_shape.net_reward_risk(
        direction, entry_price=price,
        stop_price=protection.stop_price, target_price=protection.take_price,
    )
    if rr < robot_l_shape.MIN_REWARD_RISK:
        raise RobotEntryLimitError("after-fee L-shape RR below native owner floor")
    fee = robot_l_shape.PAPER_ROBOT_FEE_RATE
    risk = position_worst_case_loss_usdt(
        direction=direction, quantity=Decimal("1"), entry_price=price,
        stop_price=protection.stop_price, fee_rate=fee,
    )
    if risk is None or risk <= 0:
        raise RobotEntryLimitError("L-shape protective loss is not computable")
    digest = hashlib.sha256(
        f"{cid}\0post-breakout-impulse-lshape-limit\0{terms.breakout_time_ms}".encode("utf-8")
    ).hexdigest()[:32]
    request = LimitCommandRequest(
        client_action_id=ClientActionId(f"robot-impulse-lshape-{digest}"),
        symbol=symbol, side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        sizing_reference_price=price, limit_price=price,
        time_in_force=TimeInForce.GTC,
    )
    return PostBreakoutImpulseLimitResearch(
        candidate_id=cid, state_revision=rev,
        breakout_known_at_ms=breakout_ms, decision_ms=now_ms,
        direction=direction, quoted_price=price,
        stop_price=protection.stop_price, take_price=protection.take_price,
        planned_net_rr=rr, worst_loss_per_base_usdt=risk, request=request,
    )


# A source-bound research quote remains NON-EXECUTABLE even after persistence.
# In particular, no caller may reconstruct an order request from this record
# and dispatch it without the dedicated protected owner/rollback lifecycle.
IMPULSE_QUOTE_VERSION = "POST_BREAKOUT_IMPULSE_RESEARCH_V1"
# Marketable GTC entry is valid only during the initiating taker wave.
# A timed-out order is fenced from matching, then cancelled by Robot owner.
IMPULSE_ENTRY_LIMIT_MAX_AGE_MS = 30_000


def freeze_post_breakout_impulse_quote(
    proposal: PostBreakoutImpulseLimitResearch,
    flow_receipt,
) -> dict[str, object]:
    """Freeze the research quote and source identity for restart-safe inspection.

    This is NOT a command intent. The canonical owner must independently
    preflight, freeze and persist its own submit intent before any entry order.
    """
    from robot_entry_flow_evidence import CandidateBoundFlowEvidence

    if (not isinstance(proposal, PostBreakoutImpulseLimitResearch)
            or not isinstance(flow_receipt, CandidateBoundFlowEvidence)
            or proposal.trading_authorized
            or proposal.candidate_id != flow_receipt.candidate_id
            or proposal.state_revision != flow_receipt.state_revision
            or proposal.direction != flow_receipt.direction
            or flow_receipt.decision_ms > proposal.decision_ms
            or proposal.quoted_price != proposal.request.limit_price
            or proposal.quoted_price != proposal.request.sizing_reference_price
            or flow_receipt.source_complete is not True
            or flow_receipt.receipt_cutoff_proven is not True
            or flow_receipt.transport_generation_proven is not True):
        raise RobotEntryLimitError("research quote and certified source diverge")
    return {
        "version": IMPULSE_QUOTE_VERSION,
        "candidate_id": proposal.candidate_id,
        "source_revision": proposal.state_revision,
        "direction": proposal.direction,
        "symbol": proposal.request.symbol,
        "source_sha256": flow_receipt.print_facts_sha256,
        "source_closed_at_ms": flow_receipt.closed_at_ms,
        "source_decision_ms": flow_receipt.decision_ms,
        "breakout_known_at_ms": proposal.breakout_known_at_ms,
        "decision_ms": proposal.decision_ms,
        "client_action_id": proposal.request.client_action_id.value,
        "entry_side": proposal.request.side.value,
        "quoted_price": str(proposal.quoted_price),
        "stop_price": str(proposal.stop_price),
        "take_price": str(proposal.take_price),
        "planned_net_rr": str(proposal.planned_net_rr),
        "worst_loss_per_base_usdt": str(proposal.worst_loss_per_base_usdt),
        "trading_authorized": False,
    }


def verify_frozen_post_breakout_impulse_quote(
    record, frozen: Mapping[str, object],
) -> bool:
    """Inspect a durable research quote without resurrecting trading authority.

    Frozen quote may be stale after restart or index advance. Its sole value is
    causal evidence: never send/restore orders from this return value.
    """
    from robot_entry_flow_evidence import canonical_host_breakout_known_at_ms

    if not isinstance(frozen, Mapping) or frozen.get("version") != IMPULSE_QUOTE_VERSION:
        return False
    if frozen.get("trading_authorized") is not False:
        return False
    try:
        state, snapshot = record.robot_state, record.signal_snapshot
        if not isinstance(state, Mapping) or not isinstance(snapshot, Mapping):
            return False
        direction = state.get("direction")
        if (
            record.status != "APPROVED"
            or frozen.get("candidate_id") != record.candidate_id
            or frozen.get("symbol") != record.symbol.value
            or frozen.get("direction") != direction
            or snapshot.get("symbol") != record.symbol.value
            or state.get("phase") not in ("WAITING_RETEST", "RETEST_DETECTED")
            or not isinstance(frozen.get("source_revision"), int)
            or isinstance(frozen.get("source_revision"), bool)
            or frozen["source_revision"] > record.state_revision
            or frozen["source_revision"] < 0
            or frozen.get("breakout_known_at_ms")
                != canonical_host_breakout_known_at_ms(record)
        ):
            return False
        signature = frozen.get("source_sha256")
        if (not isinstance(signature, str) or len(signature) != 64
                or any(ch not in "0123456789abcdef" for ch in signature.lower())):
            return False
        for key in ("source_closed_at_ms", "source_decision_ms", "decision_ms"):
            if type(frozen.get(key)) is not int or frozen[key] < 0:
                return False
        if not (
            frozen["breakout_known_at_ms"]
            <= frozen["source_closed_at_ms"]
            <= frozen["source_decision_ms"]
            <= frozen["decision_ms"]
        ):
            return False
        entry = _positive_decimal(frozen.get("quoted_price"), "quoted_price")
        stop = _positive_decimal(frozen.get("stop_price"), "stop_price")
        take = _positive_decimal(frozen.get("take_price"), "take_price")
        rr = _positive_decimal(frozen.get("planned_net_rr"), "planned_net_rr")
        loss = _positive_decimal(
            frozen.get("worst_loss_per_base_usdt"), "worst_loss_per_base_usdt",
        )
        if rr <= 0 or loss <= 0:
            return False
        if not (
            stop < entry < take if direction == DIRECTION_LONG
            else take < entry < stop if direction == DIRECTION_SHORT
            else False
        ):
            return False
        side = OrderSide.BUY.value if direction == DIRECTION_LONG else OrderSide.SELL.value
        if frozen.get("entry_side") != side:
            return False
        index = state.get("breakout_index")
        if type(index) is not int:
            return False
        digest = hashlib.sha256(
            f"{record.candidate_id}\0post-breakout-impulse-limit\0{index}".encode("utf-8")
        ).hexdigest()[:32]
        return frozen.get("client_action_id") == f"robot-impulse-limit-{digest}"
    except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError):
        return False


def verify_frozen_post_breakout_l_shape_quote(
    record, frozen: Mapping[str, object],
) -> bool:
    """Verify frozen exact L-shape intent without granting execution.

    The actual fill, normalized size, budget, exposure and protection remain
    independently owned by canonical PAPER Robot Admission/executor.
    """
    import robot_l_shape
    import robot_protection
    from retest_account_risk import position_worst_case_loss_usdt
    from robot_entry_flow_evidence import canonical_host_breakout_known_at_ms

    if (not isinstance(frozen, Mapping)
            or frozen.get("version") != IMPULSE_QUOTE_VERSION
            or frozen.get("trading_authorized") is not False):
        return False
    try:
        state, snapshot = record.robot_state, record.signal_snapshot
        if (record.status != "APPROVED"
                or not isinstance(state, Mapping)
                or not isinstance(snapshot, Mapping)
                or snapshot.get("pattern") != "L-shape"
                or snapshot.get("symbol") != record.symbol.value
                or state.get("state_version") != robot_l_shape.STATE_VERSION
                or state.get("pattern") != "L-shape"
                or state.get("phase") != robot_l_shape.PHASE_WAITING_RETEST
                or state.get("retest_time_ms") is not None):
            return False
        terms = robot_l_shape.frozen_terms(snapshot)
        if (state.get("direction") != terms.direction
                or state.get("breakout_time_ms") != terms.breakout_time_ms
                or frozen.get("candidate_id") != record.candidate_id
                or frozen.get("symbol") != record.symbol.value
                or frozen.get("direction") != terms.direction
                or type(frozen.get("source_revision")) is not int
                or not 0 <= frozen["source_revision"] <= record.state_revision
                or frozen.get("breakout_known_at_ms")
                    != canonical_host_breakout_known_at_ms(record)):
            return False
        sha = frozen.get("source_sha256")
        if (not isinstance(sha, str) or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha.lower())):
            return False
        for key in ("source_closed_at_ms", "source_decision_ms", "decision_ms"):
            if type(frozen.get(key)) is not int:
                return False
        if not (
            frozen["breakout_known_at_ms"] <= frozen["source_closed_at_ms"]
            <= frozen["source_decision_ms"] <= frozen["decision_ms"]
        ):
            return False
        entry = _positive_decimal(frozen.get("quoted_price"), "L-shape quote")
        stop = _positive_decimal(frozen.get("stop_price"), "L-shape STOP")
        take = _positive_decimal(frozen.get("take_price"), "L-shape TAKE")
        rr = _positive_decimal(frozen.get("planned_net_rr"), "L-shape RR")
        loss = _positive_decimal(frozen.get("worst_loss_per_base_usdt"), "L-shape risk")
        direction = terms.direction
        if (take != terms.target
                or rr < robot_l_shape.MIN_REWARD_RISK
                or loss <= 0
                or (direction == DIRECTION_LONG and not stop < entry < take)
                or (direction == DIRECTION_SHORT and not take < entry < stop)
                or (direction == DIRECTION_LONG and entry <= terms.reference)
                or (direction == DIRECTION_SHORT and entry >= terms.reference)):
            return False
        # Compare ALL frozen economics against native immutable L-shape terms.
        # Protective-side geometry alone is insufficient: otherwise a changed
        # STOP/RR/risk could be adopted after a restart.
        expected_stop = robot_protection.limited_stop(
            direction, entry_price=entry, preferred_stop=terms.stop,
        )
        expected_rr = robot_l_shape.net_reward_risk(
            direction, entry_price=entry,
            stop_price=expected_stop, target_price=terms.target,
        )
        expected_loss = position_worst_case_loss_usdt(
            direction=direction, quantity=Decimal("1"), entry_price=entry,
            stop_price=expected_stop,
            fee_rate=robot_l_shape.PAPER_ROBOT_FEE_RATE,
        )
        if (stop != expected_stop or rr != expected_rr
                or expected_loss is None or loss != expected_loss):
            return False
        side = OrderSide.BUY.value if direction == DIRECTION_LONG else OrderSide.SELL.value
        digest = hashlib.sha256(
            f"{record.candidate_id}\0post-breakout-impulse-lshape-limit\0{terms.breakout_time_ms}".encode("utf-8")
        ).hexdigest()[:32]
        return (
            frozen.get("entry_side") == side
            and frozen.get("client_action_id") == f"robot-impulse-lshape-{digest}"
        )
    except (AttributeError, KeyError, TypeError, ValueError,
            ArithmeticError, robot_l_shape.RobotLShapeError):
        return False
