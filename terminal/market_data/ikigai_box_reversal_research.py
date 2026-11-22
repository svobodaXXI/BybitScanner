"""Non-executing Box second-impulse flow research.

Join the shared market-flow features on observed contiguous windows. The caller
owns raw tape/book provenance, second-leg geometry and source integrity; these
DTOs cannot certify them. No runtime subscription, admission, candidate creation
or change to the original Box grid, STOP or TAKE.
"""
from dataclasses import dataclass, field

from robot_entry_flow_evidence import FlowWindow, compare_flow_windows


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
    source_complete: bool = field(default=False, init=False)
    trading_authorized: bool = field(default=False, init=False)


def observe_box_reversal_flow(
    record,
    observations: tuple[BoxFlowObservation, ...],
    *,
    decision_ms: int,
    max_source_age_ms: int,
) -> BoxReversalFlowResearch | None:
    """Compare three completed windows for a previously confirmed Box host.

    First transition: opposing aggression persists but has less price impact;
    positive refill evidence makes this only an absorption CANDIDATE.
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
            or not win.end_ms <= obs.available_at_ms <= decision_ms
            or (generation is not None and obs.generation != generation)
            or (previous is not None and obs.available_at_ms < previous.available_at_ms)
        ):
            return None
        generation, previous = obs.generation, obs
    if decision_ms - observations[-1].window.end_ms > max_source_age_ms:
        return None
    early, fade, flip = observations
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

    if fading and absorption is True and reverse_wave:
        status = "HANDOFF_CANDIDATE"
    elif fading and absorption is True:
        status = "ABSORPTION_CANDIDATE"
    elif fading:
        status = "EXHAUSTION_OBSERVED"
    else:
        status = "WAIT_EXHAUSTION"
    return BoxReversalFlowResearch(
        candidate_id, revision, symbol, direction, decision_ms,
        fading, absorption, reverse_wave, status,
    )
