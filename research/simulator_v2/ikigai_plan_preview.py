"""Only ORIGINAL Box first-grid planner + risk, never an executable trade.

The native immutable PAPER-labelled plan is pure arithmetic and explicitly
execution_authorized=False. This wrapper cannot mutate PAPER or SIMULATION.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from terminal.paper.ikigai_box_plan import (
    BoxRiskAssessment, IkigaiBoxPaperPlan, assess_first_grid_risk,
    plan_approved_first_ikigai_box,
)
from research.simulator_v2.ikigai_observer import IkigaiObservation


@dataclass(frozen=True)
class BoxSimulationRiskTerms:
    tick_size: Decimal
    working_quantity: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    maximum_notional_usdt: Decimal
    maximum_loss_usdt: Decimal
    entry_fee_rate: Decimal
    exit_fee_rate: Decimal
    adverse_stop_slippage_per_unit: Decimal
    additional_cost_allowance_usdt: Decimal

    def __post_init__(self):
        for key in ("tick_size", "working_quantity", "quantity_step",
                    "minimum_quantity", "maximum_notional_usdt",
                    "maximum_loss_usdt"):
            x = getattr(self, key)
            if not isinstance(x, Decimal) or not x.is_finite() or x <= 0:
                raise ValueError("explicit positive SIMULATION " + key + " required")
        for key in ("entry_fee_rate", "exit_fee_rate"):
            x = getattr(self, key)
            if not isinstance(x, Decimal) or not x.is_finite() or not 0 <= x < 1:
                raise ValueError("invalid virtual fee")
        for key in ("adverse_stop_slippage_per_unit", "additional_cost_allowance_usdt"):
            x = getattr(self, key)
            if not isinstance(x, Decimal) or not x.is_finite() or x < 0:
                raise ValueError("explicit nonnegative allowance required")


@dataclass(frozen=True)
class BoxSimulationPreview:
    signal_id: str
    timeframe: str
    virtual_time_ms: int
    plan: IkigaiBoxPaperPlan
    risk: BoxRiskAssessment
    status: str = "PREVIEW_ONLY"


def preview_box_plan(
    observation: IkigaiObservation, *, terms: BoxSimulationRiskTerms,
) -> BoxSimulationPreview:
    if not isinstance(observation, IkigaiObservation) or not isinstance(
        terms, BoxSimulationRiskTerms
    ):
        raise TypeError("confirmed Box and explicit SIMULATION terms required")
    if observation.timeframe not in ("1m", "5m"):
        raise ValueError("unsupported Box timeframe")
    if observation.formation_id != (
        f"{observation.timeframe}:{observation.formation.direction}:"
        f"{observation.source_a_ms}:{observation.source_b_ms}"
    ) or observation.source_b_ms >= observation.available_at_ms:
        raise ValueError("Box timeframe or original anchor mismatch")
    f = observation.formation
    plan = plan_approved_first_ikigai_box(
        direction=f.direction, frozen_f1=Decimal(str(f.fibonacci_1_0)),
        frozen_f1618=Decimal(str(f.fibonacci_1_618)),
        working_quantity=terms.working_quantity, tick_size=terms.tick_size,
        entry_fee_rate=terms.entry_fee_rate,
        target_fee_rate=terms.exit_fee_rate, stop_fee_rate=terms.exit_fee_rate,
    )
    if plan.execution_authorized:
        raise ValueError("executable Box plan not permitted")
    if any(q < terms.minimum_quantity or q % terms.quantity_step
           for q in plan.limit_quantities):
        raise ValueError("virtual Box quantity does not match step or minimum")
    notional = sum((p * q for p, q in zip(
        plan.limit_prices, plan.limit_quantities)), Decimal(0))
    if notional > terms.maximum_notional_usdt:
        raise ValueError("Box full grid exceeds virtual notional limit")
    risk = assess_first_grid_risk(
        plan, maximum_allowed_loss_usdt=terms.maximum_loss_usdt,
        adverse_stop_slippage_per_unit=terms.adverse_stop_slippage_per_unit,
        additional_cost_allowance_usdt=terms.additional_cost_allowance_usdt,
    )
    if not risk.allowed:
        raise ValueError("Box full grid risk exceeds virtual loss limit")
    return BoxSimulationPreview(
        observation.formation_id, observation.timeframe,
        observation.available_at_ms, plan, risk,
    )
