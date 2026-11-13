"""Explain original event-time SIMULATION L2 fills episode by episode.

Pure presentation of immutable virtual fills and recorded order events:
no price inference, exchange-order assertion, ledger mutation, or IO.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from robot_entry_flow_evidence import ImpulseProtectedPlan

from research.simulator_v2.virtual_account import VirtualFill
from research.simulator_v2.virtual_exchange import OrderEvent

_FLAGS = {
    "DEPTH_UNPROVEN": "ENTRY_DEPTH_UNPROVEN",
    "STOP_TRIGGER_DEFERRED": "STOP_SETTLED_FROM_LATER_BOOK",
    "PARTIAL_TAKE_FILLED": "L2_PARTIAL_TAKE_SIMULATED",
    "STOP_AMENDED_BE": "BE_STOP_AMENDED_AFTER_PARTIAL",
    "PARTIAL_DEPTH_UNPROVEN": "PARTIAL_DEPTH_UNPROVEN",
}


def _receipt_kind(fill_id: str) -> tuple[str, str]:
    for suffix, kind in (
        ("_stop_fill", "STOP"),
        ("_take_fill", "TAKE"),
        ("_partial_fill", "PARTIAL"),
        ("_fill", "ENTRY"),
    ):
        if fill_id.endswith(suffix) and len(fill_id) > len(suffix):
            return fill_id[:-len(suffix)], kind
    raise ValueError("unknown historical L2 fill identity")


def episode_rows(
    fills: tuple[VirtualFill, ...], events: tuple[OrderEvent, ...],
    plans: Mapping[str, ImpulseProtectedPlan] | None = None,
) -> tuple[dict[str, object], ...]:
    """Return virtual episodes; never label model fills as exchange executions.

    Closed rows carry exact net PnL calculated from the immutable account
    receipt prices/fees. An open episode has net PnL=None (no fabricated exit).
    Flags are per originating order ID, not a guessed market timestamp range.
    """
    if (not isinstance(fills, tuple) or not isinstance(events, tuple)
            or (plans is not None and not isinstance(plans, Mapping))):
        raise TypeError("immutable virtual receipts, events and optional plans required")
    if len(fills) > 20_000 or len(events) > 50_000:
        raise ValueError("bounded virtual episode audit required")
    annotations: dict[str, set[str]] = {}
    first_stop_trigger: dict[str, int] = {}
    for event in events:
        if not isinstance(event, OrderEvent):
            raise ValueError("original virtual order events required")
        flag = _FLAGS.get(event.kind)
        if flag is not None:
            annotations.setdefault(event.order_id, set()).add(flag)
        if event.kind == "STOP_TRIGGER_DEFERRED":
            first_stop_trigger.setdefault(event.order_id, event.virtual_time_ms)

    entries: dict[str, VirtualFill] = {}
    partials: dict[str, VirtualFill] = {}
    exits: dict[str, tuple[VirtualFill, str]] = {}
    ordered: list[str] = []
    for fill in fills:
        if not isinstance(fill, VirtualFill):
            raise ValueError("original virtual fills required")
        order_id, kind = _receipt_kind(fill.fill_id)
        if kind == "ENTRY":
            if order_id in entries:
                raise ValueError("duplicate L2 episode entry")
            entries[order_id] = fill
            ordered.append(order_id)
            continue
        entry = entries.get(order_id)
        if entry is None or order_id in exits or fill.side == entry.side:
            raise ValueError("unpaired or inconsistent historical L2 exit")
        if kind == "PARTIAL":
            if (order_id in partials or not 0 < fill.quantity < entry.quantity
                    or fill.virtual_time_ms <= entry.virtual_time_ms):
                raise ValueError("invalid or duplicated partial L2 virtual fill")
            partials[order_id] = fill
        else:
            partial = partials.get(order_id)
            residual = entry.quantity - (partial.quantity if partial else 0)
            if (fill.quantity != residual
                    or fill.virtual_time_ms < (
                        partial.virtual_time_ms if partial else entry.virtual_time_ms
                    )):
                raise ValueError("unpaired or inconsistent historical L2 exit")
            exits[order_id] = (fill, kind)

    rows: list[dict[str, object]] = []
    for order_id in ordered:
        entry = entries[order_id]
        plan = plans.get(order_id) if plans is not None else None
        if plan is not None and (
            not isinstance(plan, ImpulseProtectedPlan)
            or plan.quantity != entry.quantity
            or (plan.signal.direction == "LONG") != (entry.side == "BUY")
            or plan.signal.known_at_ms > entry.virtual_time_ms
        ):
            raise ValueError("virtual episode mismatches original shared Robot plan")
        outcome = exits.get(order_id)
        partial = partials.get(order_id)
        flags = sorted(annotations.get(order_id, ()))
        if partial is not None and "L2_PARTIAL_TAKE_SIMULATED" not in flags:
            raise ValueError("partial receipt lacks original event evidence")
        if "BE_STOP_AMENDED_AFTER_PARTIAL" in flags and partial is None:
            raise ValueError("BE mutation without a proven virtual partial receipt")
        reason = outcome[1] if outcome is not None else "OPEN"
        if "STOP_SETTLED_FROM_LATER_BOOK" in flags and reason != "STOP":
            raise ValueError("deferred STOP missing its matched STOP exit")
        trigger = first_stop_trigger.get(order_id)
        if outcome is None:
            exit_ms = exit_price = exit_fee = gross = net = None
            exit_fill_id = None
            delay = None
        else:
            fill, _ = outcome
            exit_ms, exit_price = fill.virtual_time_ms, str(fill.price)
            exit_fee = str(fill.fee)
            direction = Decimal(1) if entry.side == "BUY" else Decimal(-1)
            gross_pnl: Decimal = (
                (fill.price - entry.price) * fill.quantity * direction
                + ((partial.price - entry.price) * partial.quantity * direction
                   if partial is not None else Decimal(0))
            )
            gross, net = str(gross_pnl), str(
                gross_pnl - entry.fee - fill.fee
                - (partial.fee if partial is not None else Decimal(0))
            )
            exit_fill_id = fill.fill_id
            delay = fill.virtual_time_ms - trigger if trigger is not None else None
            if delay is not None and not 0 < delay <= 250:
                raise ValueError("STOP settlement exceeds 250ms original model gate")
        rows.append({
            "order_id": order_id,
            "direction": "LONG" if entry.side == "BUY" else "SHORT",
            "entry_ms": entry.virtual_time_ms,
            "entry_price": str(entry.price),
            "entry_fee": str(entry.fee),
            "quantity": str(entry.quantity),
            "partial_quantity": str(partial.quantity) if partial is not None else None,
            "partial_price": str(partial.price) if partial is not None else None,
            "partial_ms": partial.virtual_time_ms if partial is not None else None,
            "partial_fee": str(partial.fee) if partial is not None else None,
            "signal_ms": plan.signal.known_at_ms if plan is not None else None,
            "planned_stop_price": str(plan.stop_price) if plan is not None else None,
            "planned_take_price": str(plan.take_price) if plan is not None else None,
            "signal_structural_extreme": (
                str(plan.signal.structural_extreme) if plan is not None else None
            ),
            "exit_reason": reason,
            "exit_ms": exit_ms,
            "exit_price": exit_price,
            "exit_fee": exit_fee,
            "gross_pnl_usdt": gross,
            "net_pnl_usdt": net,
            "stop_trigger_ms": trigger,
            "deferred_stop_ms": delay,
            "evidence_flags": flags,
            "model_certainty": (
                "CONDITIONAL_MODEL" if flags or outcome is None
                else "MODEL_ONLY_NOT_REAL_EXCHANGE_FILL"
            ),
            "entry_fill_id": entry.fill_id,
            "exit_fill_id": exit_fill_id,
        })
    return tuple(rows)
