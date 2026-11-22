"""Non-executing Box second-impulse flow research.

Join the shared market-flow features on observed contiguous windows. The caller
owns raw tape/book provenance, second-leg geometry and source integrity; these
DTOs cannot certify them. No runtime subscription, admission, candidate creation
or change to the original Box grid, STOP or TAKE.
"""
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException

from robot_entry_flow_evidence import FlowWindow, compare_flow_windows
from terminal.market_data.sustained_absorption import (
    AbsorptionObservation, RecoveryWindow,
)
from terminal.paper.ikigai_box_plan import (
    BoxReversalEntryPreview, IkigaiBoxPaperPlan, assess_box_reversal_entry,
)


@dataclass(frozen=True, slots=True)
class BoxFlowObservation:
    candidate_id: str
    state_revision: int
    snapshot_sha256: str
    symbol: str
    generation: int
    available_at_ms: int
    window: FlowWindow


@dataclass(frozen=True, slots=True)
class BoxBoundAbsorption:
    """Bind an independent fixed-level observation to the exact frozen Box."""

    candidate_id: str
    state_revision: int
    snapshot_sha256: str
    symbol: str
    generation: int
    available_at_ms: int
    observation: AbsorptionObservation


@dataclass(frozen=True, slots=True)
class BoxReversalFlowResearch:
    candidate_id: str
    state_revision: int
    symbol: str
    direction: str
    decision_ms: int
    opposing_impact_fading: bool
    absorption_candidate: bool | None
    initiative_flip_observed: bool
    status: str
    sustained_absorption_observed: bool = False
    source_complete: bool = field(default=False, init=False)
    trading_authorized: bool = field(default=False, init=False)


def observe_box_reversal_flow(
    record,
    observations: tuple[BoxFlowObservation, ...],
    *,
    decision_ms: int,
    max_source_age_ms: int,
    fixed_band: BoxBoundAbsorption | None = None,
) -> BoxReversalFlowResearch | None:
    """Compare three completed windows for a previously confirmed Box host.

    First transition: opposing aggression persists but has less price impact.
    A positive single-window refill ratio is only a provisional observation;
    it NEVER unlocks a handoff. Exact-host, completed, persistent, print-linked
    fixed-level evidence must also survive a depth/quote-break check.
    Second transition: an accelerating taker wave in the reversal direction.
    Missing, empty, stale, mixed owner or mixed generation evidence is UNKNOWN
    (None). A wall or a low-volume pause is not passive absorption.
    No inference of a microlevel reclaim, true extremum, or executable entry.
    """
    if (type(decision_ms) is not int or decision_ms < 0
            or type(max_source_age_ms) is not int or max_source_age_ms < 0
            or not isinstance(observations, tuple) or len(observations) != 3):
        return None
    try:
        snapshot, state = record.signal_snapshot, record.robot_state
        identity = snapshot["identity"]
        direction, symbol = identity["direction"], identity["symbol"]
        candidate_id, revision = record.candidate_id, record.state_revision
        digest = record.snapshot_sha256
        source_id = snapshot["source_box_candidate_id"]
        known = snapshot["decision_time_ms"]
        approved = record.approved_at_ms
        if (
            record.status != "APPROVED" or state["phase"] != "BOX_ENTRY_READY"
            or record.trading_account_id.value != "paper"
            or snapshot["pattern"] != "IKIGAI_BOX" or snapshot["environment"] != "PAPER"
            or snapshot["execution_authorized"] is not False
            or direction not in ("LONG", "SHORT")
            or snapshot["plan"]["direction"] != direction
            or not isinstance(symbol, str) or not symbol or record.symbol.value != symbol
            or not isinstance(source_id, str) or not source_id.startswith("box-plan-")
            or source_id != state["source_box_candidate_id"]
            or candidate_id != "box-robot-" + source_id.removeprefix("box-plan-")
            or type(revision) is not int or revision < 1
            or not isinstance(digest, str) or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
            or type(known) is not int or type(approved) is not int
            or not 0 <= known <= approved <= decision_ms
        ):
            return None
    except (AttributeError, KeyError, TypeError):
        return None

    previous = None
    generation = None
    for obs in observations:
        if not isinstance(obs, BoxFlowObservation):
            return None
        win = obs.window
        if (
            obs.candidate_id != candidate_id or type(obs.state_revision) is not int
            or obs.state_revision != revision or obs.snapshot_sha256 != digest
            or obs.symbol != symbol
            or type(obs.generation) is not int or obs.generation < 0
            or type(obs.available_at_ms) is not int
            or not isinstance(win, FlowWindow) or win.price_source != "TRADE"
            or win.total_notional <= 0 or win.start_ms < known
            # A frozen candle's "decision_time_ms" is its Bybit OPEN time.
            # Do not credit pre-approval trades to an APPROVED Robot host.
            or win.start_ms < approved
            or not win.end_ms <= obs.available_at_ms <= decision_ms
            or (generation is not None and obs.generation != generation)
            or (previous is not None and obs.available_at_ms < previous.available_at_ms)
        ):
            return None
        generation, previous = obs.generation, obs
    if decision_ms - observations[-1].window.end_ms > max_source_age_ms:
        return None
    early, fade, flip = observations

    # Research-only #1259 join. Never attribute fills to aggregate L2 depth
    # or infer the original candidate identity from symbol/time alone.
    sustained = False
    if fixed_band is not None:
        if not isinstance(fixed_band, BoxBoundAbsorption):
            return None
        metric = fixed_band.observation
        if not isinstance(metric, AbsorptionObservation):
            return None
        if (
            fixed_band.candidate_id != candidate_id
            or type(fixed_band.state_revision) is not int
            or fixed_band.state_revision != revision
            or fixed_band.snapshot_sha256 != digest
            or fixed_band.symbol != symbol
            or type(fixed_band.generation) is not int
            or fixed_band.generation != generation
            or type(fixed_band.available_at_ms) is not int
            or not fade.window.end_ms <= fixed_band.available_at_ms <= flip.available_at_ms
            or metric.symbol != symbol or metric.direction != direction
            or type(metric.generation) is not int or metric.generation != generation
            or type(metric.decision_ms) is not int
            or metric.decision_ms != fade.window.end_ms
            or metric.source_complete is not False
            or metric.trading_authorized is not False
            or not isinstance(metric.windows, tuple) or len(metric.windows) < 2
            or metric.windows[0].start_ms != fade.window.start_ms
            or metric.windows[-1].end_ms != fade.window.end_ms
            or not isinstance(metric.frozen_levels, tuple)
            or len(metric.frozen_levels) != 5
        ):
            return None
        for i, part in enumerate(metric.windows):
            if (
                not isinstance(part, RecoveryWindow)
                or type(part.start_ms) is not int or type(part.end_ms) is not int
                or part.start_ms >= part.end_ms
                or (i and part.start_ms != metric.windows[i-1].end_ms)
            ):
                return None
            values = (
                part.opposing_notional, part.compatible_print_notional,
                part.compatible_recovery_notional,
            )
            if any(
                not isinstance(v, Decimal) or not v.is_finite() or v < 0
                for v in values
            ) or not (
                part.compatible_recovery_notional
                <= part.compatible_print_notional
                <= part.opposing_notional
            ):
                return None
        depth_values = (
            metric.initial_depth_notional, metric.minimum_depth_notional,
            metric.final_depth_notional,
        )
        if (
            any(not isinstance(v, Decimal) or not v.is_finite() or v < 0
                for v in depth_values)
            or metric.initial_depth_notional <= 0
            or any(not isinstance(p, Decimal) or not p.is_finite() or p <= 0
                   for p in metric.frozen_levels)
            or not isinstance(metric.adverse_quote_break, bool)
        ):
            return None
        sustained = (
            metric.repeated_recovery_observed
            and metric.minimum_depth_notional > 0
            and not metric.adverse_quote_break
            and sum(
                w.opposing_notional > 0 and w.compatible_recovery_notional > 0
                for w in metric.windows
            ) >= 2
        )
    try:
        exhaustion = compare_flow_windows(
            early.window, fade.window, decision_ms=fade.available_at_ms,
        )
        initiative = compare_flow_windows(
            fade.window, flip.window, decision_ms=flip.available_at_ms,
        )
    except (TypeError, ValueError):
        return None
    if direction == "LONG":
        fading = exhaustion.sell_impact_fading
        absorption = exhaustion.sell_absorption_candidate
        reverse_wave = initiative.buy_wave_accelerating
    else:
        fading = exhaustion.buy_impact_fading
        absorption = exhaustion.buy_absorption_candidate
        reverse_wave = initiative.sell_wave_accelerating

    qualified = sustained and absorption is not False
    if fading and qualified and reverse_wave:
        status = "HANDOFF_CANDIDATE"
    elif fading and qualified:
        status = "ABSORPTION_CANDIDATE"
    elif fading and absorption is True:
        status = "WAIT_SUSTAINED_ABSORPTION"
    elif fading:
        status = "EXHAUSTION_OBSERVED"
    else:
        status = "WAIT_EXHAUSTION"
    return BoxReversalFlowResearch(
        candidate_id, revision, symbol, direction, decision_ms,
        fading, absorption, reverse_wave, status, qualified,
    )


@dataclass(frozen=True, slots=True)
class BoxSecondLegExtreme:
    """Source-supplied second-leg extreme; construction is NOT geometry proof."""

    candidate_id: str
    state_revision: int
    snapshot_sha256: str
    symbol: str
    generation: int
    event_ms: int
    available_at_ms: int
    price: Decimal


@dataclass(frozen=True, slots=True)
class BoxReversalHandoffPreview:
    flow: BoxReversalFlowResearch
    economics: BoxReversalEntryPreview | None
    status: str
    source_complete: bool = field(default=False, init=False)
    trading_authorized: bool = field(default=False, init=False)


def _frozen_decimal(value: object) -> Decimal:
    # Durable Box snapshots use exact decimal strings, never floats.
    if not isinstance(value, str):
        raise ValueError("expected frozen Decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("invalid frozen positive Decimal")
    return parsed


def _matches_frozen_plan(plan: IkigaiBoxPaperPlan, snapshot: dict) -> bool:
    if not isinstance(plan, IkigaiBoxPaperPlan):
        return False
    saved = snapshot["plan"]
    return (
        plan.environment == saved["environment"] == "PAPER"
        and plan.execution_authorized is False
        and saved["execution_authorized"] is False
        and plan.direction == saved["direction"] == snapshot["identity"]["direction"]
        and len(plan.limit_prices) == len(plan.limit_quantities) == 4
        and plan.limit_prices == tuple(map(_frozen_decimal, saved["limit_prices"]))
        and plan.limit_quantities == tuple(map(_frozen_decimal, saved["limit_quantities"]))
        and plan.frozen_f1 == _frozen_decimal(saved["frozen_f1"])
        and plan.frozen_f1618 == _frozen_decimal(saved["frozen_f1618"])
        and plan.take_price == _frozen_decimal(saved["take_price"])
        and plan.stop_price == _frozen_decimal(saved["stop_price"])
    )


def preview_box_reversal_handoff(
    record,
    observations: tuple[BoxFlowObservation, ...],
    plan: IkigaiBoxPaperPlan,
    extreme: BoxSecondLegExtreme,
    *,
    decision_ms: int,
    max_source_age_ms: int,
    quantity: Decimal,
    qty_step: Decimal,
    stop_buffer_ticks: int,
    adverse_entry_per_unit: Decimal,
    adverse_target_per_unit: Decimal,
    adverse_stop_per_unit: Decimal,
    additional_cost_allowance_usdt: Decimal,
    maximum_allowed_loss_usdt: Decimal,
    fixed_band: BoxBoundAbsorption | None = None,
) -> BoxReversalHandoffPreview | None:
    """Compose the existing flow and economics modules for one frozen host.

    The final completed window's last trade price is a hypothetical benchmark,
    NOT a current quote or fill. The caller must independently establish full
    second-leg geometry, extrema and tape/book provenance; the joined result
    never certifies those sources. Fees/tick and TAKE come from the original
    immutable plan. Invalid/mismatched observations return None, incomplete
    handoff returns a diagnostic without economics. No reclaim/pullback claim,
    execution, account mutation or independent signal.
    """
    flow = observe_box_reversal_flow(
        record, observations, decision_ms=decision_ms,
        max_source_age_ms=max_source_age_ms, fixed_band=fixed_band,
    )
    if flow is None:
        return None
    try:
        snapshot = record.signal_snapshot
        if not _matches_frozen_plan(plan, snapshot):
            return None
        if flow.status != "HANDOFF_CANDIDATE":
            return BoxReversalHandoffPreview(flow, None, "WAIT_HANDOFF")
        last = observations[-1]
        b_time = snapshot["identity"]["b_time_ms"]
        if (
            not isinstance(extreme, BoxSecondLegExtreme)
            or extreme.candidate_id != flow.candidate_id
            or type(extreme.state_revision) is not int
            or extreme.state_revision != flow.state_revision
            or extreme.snapshot_sha256 != record.snapshot_sha256
            or extreme.symbol != flow.symbol
            or type(extreme.generation) is not int
            or extreme.generation != last.generation
            or type(b_time) is not int or b_time < 0
            or type(extreme.event_ms) is not int
            or type(extreme.available_at_ms) is not int
            or not b_time <= extreme.event_ms <= last.window.end_ms
            or not extreme.event_ms <= extreme.available_at_ms <= decision_ms
            or not isinstance(extreme.price, Decimal)
            or not extreme.price.is_finite() or extreme.price <= 0
        ):
            return None
        sign = Decimal(1 if flow.direction == "LONG" else -1)
        # Endpoint observations cannot prove full extrema or target freshness;
        # they CAN disprove a claimed extreme or reveal an already spent Box.
        for observation in observations:
            for price in (observation.window.start_price, observation.window.end_price):
                if sign * (price - extreme.price) < 0:
                    return None
                if sign * (plan.take_price - price) <= 0:
                    return None
        inputs = snapshot["inputs"]
        fees = {}
        for name in ("entry_fee_rate", "target_fee_rate", "stop_fee_rate"):
            if not isinstance(inputs[name], str):
                return None
            fees[name] = Decimal(inputs[name])
        preview = assess_box_reversal_entry(
            plan, entry_price=last.window.end_price, second_extreme=extreme.price,
            quantity=quantity, qty_step=qty_step,
            tick_size=_frozen_decimal(inputs["tick_size"]),
            stop_buffer_ticks=stop_buffer_ticks, **fees,
            adverse_entry_per_unit=adverse_entry_per_unit,
            adverse_target_per_unit=adverse_target_per_unit,
            adverse_stop_per_unit=adverse_stop_per_unit,
            additional_cost_allowance_usdt=additional_cost_allowance_usdt,
            maximum_allowed_loss_usdt=maximum_allowed_loss_usdt,
        )
    except (AttributeError, KeyError, TypeError, ValueError, DecimalException):
        return None
    return BoxReversalHandoffPreview(flow, preview, preview.reason)
