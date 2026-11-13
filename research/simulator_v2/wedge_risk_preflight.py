"""Fail-closed virtual Wedge entry preflight using EXISTING Robot policy math.

No new strategy, trading admission, order submission, DB or network.
The original Wedge LIMIT request denotes 1 WORKING_VOLUME, not one contract.
The caller MUST supply a separately verified conversion to contracts, a
frozen Scanner structural extreme and immutable reference/target prices.
Absent provenance is a hard stop, not a request to infer these from OHLC.

Output is an *unsubmitted preview*, NOT an approved trade or protected fill.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from robot_entry_limit import InitialRetestLimitPlan
from robot_protection import (
    frozen_take_90, post_fill_net_rr, structural_stop, wedge_min_entry_rr,
)
from retest_account_risk import position_worst_case_loss_usdt
from terminal.api.models import VolumeUnit
from research.simulator_v2.virtual_exchange import LimitRequest

D = Decimal


class WedgePreflightBlocked(ValueError):
    """Missing frozen facts, insufficient risk capacity or failed Robot gate."""


@dataclass(frozen=True)
class FrozenWedgeRiskEvidence:
    """Must originate from the SAME immutable Scanner snapshot as the LIMIT."""

    candidate_id: str
    symbol: str
    pattern: Literal["Falling Wedge", "Rising Wedge"]
    observed_at_ms: int
    structural_extreme: Decimal
    frozen_signal_reference_price: Decimal
    frozen_scanner_target_price: Decimal

    def __post_init__(self) -> None:
        if (not self.candidate_id or not self.symbol
                or self.pattern not in ("Falling Wedge", "Rising Wedge")
                or type(self.observed_at_ms) is not int
                or self.observed_at_ms < 0):
            raise WedgePreflightBlocked("frozen Scanner provenance is invalid")
        for label in ("structural_extreme", "frozen_signal_reference_price",
                      "frozen_scanner_target_price"):
            value = getattr(self, label)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise WedgePreflightBlocked(f"missing finite frozen Scanner {label}")


@dataclass(frozen=True)
class SimWedgeRiskSettings:
    """Explicit local instrument/account terms; no broker credentials or PAPER."""

    tick_size: Decimal
    contracts_per_working_volume: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    max_notional_usdt: Decimal
    max_risk_usdt: Decimal
    entry_fee_rate: Decimal
    exit_fee_rate: Decimal

    def __post_init__(self) -> None:
        for label in ("tick_size", "contracts_per_working_volume", "quantity_step",
                      "minimum_quantity", "max_notional_usdt", "max_risk_usdt"):
            value = getattr(self, label)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise WedgePreflightBlocked(f"explicit positive {label} is required")
        for label in ("entry_fee_rate", "exit_fee_rate"):
            value = getattr(self, label)
            if (not isinstance(value, Decimal) or not value.is_finite()
                    or not D("0") <= value < D("1")):
                raise WedgePreflightBlocked(f"invalid {label}")


@dataclass(frozen=True)
class UnsubmittedProtectedWedgePreview:
    """Computed risk checks only; neither admission nor execution authority."""

    request: LimitRequest
    direction: str
    stop_price: Decimal
    take_price: Decimal
    projected_net_rr: Decimal
    worst_case_loss_usdt: Decimal
    minimum_rr: Decimal
    status: Literal["PREVIEW_ONLY"] = "PREVIEW_ONLY"


def preview_protected_wedge_limit(
    plan: InitialRetestLimitPlan,
    *,
    evidence: FrozenWedgeRiskEvidence | None,
    settings: SimWedgeRiskSettings | None,
    retest_closed_at_ms: int,
) -> UnsubmittedProtectedWedgePreview:
    """Evaluate actual native Wedge LIMIT/STOP/TAKE/RR on known frozen inputs.

    Projected entry fee is explicit and conservative; the native
    post_fill_net_rr formula is reused as a *preview* with that projected fee.
    Real post-fill admission/STOP-first protection must be checked separately.
    """
    if not isinstance(plan, InitialRetestLimitPlan):
        raise WedgePreflightBlocked("original Robot LIMIT plan required")
    if evidence is None:
        raise WedgePreflightBlocked("frozen Scanner extreme/reference/target missing")
    if settings is None:
        raise WedgePreflightBlocked("SIMULATION instrument/risk settings missing")
    if not isinstance(evidence, FrozenWedgeRiskEvidence) or not isinstance(settings, SimWedgeRiskSettings):
        raise WedgePreflightBlocked("unverified Wedge risk evidence or terms")
    if type(retest_closed_at_ms) is not int or retest_closed_at_ms < evidence.observed_at_ms:
        raise WedgePreflightBlocked("risk evidence originated after retest")
    request = plan.request
    direction = plan.direction
    if (plan.candidate_id != evidence.candidate_id
            or request.symbol != evidence.symbol
            or request.volume.unit != VolumeUnit.WORKING_VOLUME
            or request.volume.amount != D("1")
            or request.limit_price <= 0):
        raise WedgePreflightBlocked("LIMIT and frozen Scanner identity/working volume differ")
    if (direction, request.side.value, evidence.pattern) not in (
        ("LONG", "Buy", "Falling Wedge"),
        ("SHORT", "Sell", "Rising Wedge"),
    ):
        raise WedgePreflightBlocked("direction differs from frozen Wedge")
    entry = request.limit_price
    if entry % settings.tick_size:
        raise WedgePreflightBlocked("original LIMIT not aligned to instrument tick")
    quantity = request.volume.amount * settings.contracts_per_working_volume
    if quantity < settings.minimum_quantity or quantity % settings.quantity_step:
        raise WedgePreflightBlocked("1 WV has no valid attested contract quantity")
    if entry * quantity > settings.max_notional_usdt:
        raise WedgePreflightBlocked("SIMULATION notional budget exceeded")
    # The original Robot owns STOP/TAKE and fee-aware RR mathematics.
    stop = structural_stop(
        direction, average_entry=entry,
        structural_extreme=evidence.structural_extreme,
        tick_size=settings.tick_size,
    )
    take = frozen_take_90(
        direction,
        frozen_signal_reference_price=evidence.frozen_signal_reference_price,
        frozen_scanner_target_price=evidence.frozen_scanner_target_price,
    )
    worst_loss = position_worst_case_loss_usdt(
        direction=direction, quantity=quantity, entry_price=entry,
        stop_price=stop, fee_rate=max(settings.entry_fee_rate, settings.exit_fee_rate),
    )
    if worst_loss is None or worst_loss > settings.max_risk_usdt:
        raise WedgePreflightBlocked("STOP loss exceeds SIMULATION risk budget or is unknown")
    projected_entry_fee = entry * quantity * settings.entry_fee_rate
    try:
        rr = post_fill_net_rr(
            direction, average_entry=entry, quantity=quantity,
            entry_fee=projected_entry_fee, stop_price=stop, take_price=take,
            exit_fee_rate=settings.exit_fee_rate,
        )
    except (ValueError, ArithmeticError) as error:
        raise WedgePreflightBlocked("protective RR cannot be proven") from error
    floor = wedge_min_entry_rr()
    if not rr.is_finite() or rr < floor:
        raise WedgePreflightBlocked("Wedge net RR below current shared Robot floor")
    return UnsubmittedProtectedWedgePreview(
        request=LimitRequest(
            order_id=request.client_action_id.value,
            side="BUY" if direction == "LONG" else "SELL",
            quantity=quantity, limit_price=entry,
        ),
        direction=direction, stop_price=stop, take_price=take,
        projected_net_rr=rr, worst_case_loss_usdt=worst_loss, minimum_rr=floor,
    )
