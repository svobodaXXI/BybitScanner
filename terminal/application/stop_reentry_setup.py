"""Pure qualification of a fresh *logical* STOP-reentry setup (#592).

A STOP does not generate an entry. Another pattern (e.g. engulfing ->
double-bottom -> L-shape) may qualify only when the originating strategy has
independently confirmed it from CLOSED candles and it retains the campaign's
direction and thesis. The real Scanner handoff, Robot Admission, order
ownership, risk and STOP/TAKE are unchanged and remain mandatory.

DOUBLE_BOTTOM/TOP are intentionally *contract only*: this function does not
detect those patterns or make them robot-executable. Their own verified
detectors/adapters must exist before a candidate can reach canonical Admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Existing Robot-capable producer names plus the future shared candle and
# double-extremum adapters. Inclusion here does not enable a new producer.
ELIGIBLE_FAMILIES = frozenset({
    "IKIGAI_BOX", "Falling Wedge", "Rising Wedge",
    "L-shape", "MIRROR", "CANDLE_REVERSAL", "DOUBLE_BOTTOM", "DOUBLE_TOP",
})


@dataclass(frozen=True)
class LogicalSetup:
    signal_id: str
    previous_signal_id: str
    family: str
    direction: str
    campaign_direction: str
    last_stop_closed_at_ms: int
    formation_closed_at_ms: int
    confirmation_closed_at_ms: int
    closed_candle_proven: bool
    owning_strategy_entry_ready: bool
    same_frozen_thesis: bool
    # Only DOUBLE_BOTTOM/TOP use the neck test. These are the completed
    # confirmation candle CLOSE and a frozen, identified neckline.
    neckline: Decimal | None = None
    confirmation_close: Decimal | None = None


@dataclass(frozen=True)
class LogicalSetupDecision:
    outcome: str
    reason: str


def qualify_logical_reentry(setup: LogicalSetup) -> LogicalSetupDecision:
    """Pure gate; ALLOW means eligibility for further *canonical* checks only."""
    if (
        not isinstance(setup.signal_id, str)
        or not setup.signal_id.strip()
        or not isinstance(setup.previous_signal_id, str)
        or not setup.previous_signal_id.strip()
        or setup.signal_id == setup.previous_signal_id
    ):
        return LogicalSetupDecision("WAIT", "new_signal_identity_unverified")
    if setup.family not in ELIGIBLE_FAMILIES:
        return LogicalSetupDecision("WAIT", "pattern_adapter_not_verified")
    if setup.direction not in {"LONG", "SHORT"}:
        return LogicalSetupDecision("WAIT", "direction_unverified")
    if setup.direction != setup.campaign_direction:
        return LogicalSetupDecision("DENY", "opposite_direction_is_new_campaign")
    if setup.same_frozen_thesis is not True:
        return LogicalSetupDecision("DENY", "original_trade_thesis_invalid")
    if (
        type(setup.last_stop_closed_at_ms) is not int
        or type(setup.formation_closed_at_ms) is not int
        or type(setup.confirmation_closed_at_ms) is not int
        or setup.last_stop_closed_at_ms < 0
        or setup.formation_closed_at_ms < 0
        or setup.confirmation_closed_at_ms <= setup.last_stop_closed_at_ms
        or setup.formation_closed_at_ms > setup.confirmation_closed_at_ms
    ):
        return LogicalSetupDecision("WAIT", "post_stop_candle_time_unverified")
    if setup.closed_candle_proven is not True:
        return LogicalSetupDecision("WAIT", "confirmation_candle_not_closed")
    if setup.owning_strategy_entry_ready is not True:
        return LogicalSetupDecision("WAIT", "strategy_signal_unconfirmed")
    if setup.family in {"DOUBLE_BOTTOM", "DOUBLE_TOP"}:
        neck, close = setup.neckline, setup.confirmation_close
        if (
            not isinstance(neck, Decimal)
            or not isinstance(close, Decimal)
            or not neck.is_finite()
            or not close.is_finite()
            or neck <= 0 or close <= 0
        ):
            return LogicalSetupDecision("WAIT", "neckline_close_unverified")
        if setup.family == "DOUBLE_BOTTOM":
            if setup.direction != "LONG":
                return LogicalSetupDecision("DENY", "double_bottom_direction_mismatch")
            if close <= neck:
                return LogicalSetupDecision("WAIT", "neckline_not_confirmed_above")
        else:
            if setup.direction != "SHORT":
                return LogicalSetupDecision("DENY", "double_top_direction_mismatch")
            if close >= neck:
                return LogicalSetupDecision("WAIT", "neckline_not_confirmed_below")
    return LogicalSetupDecision("ALLOW", "fresh_setup_for_canonical_admission")
