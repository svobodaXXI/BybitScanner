"""Read-only wedge pre-breakout confluence of candle patterns and taker exhaustion.

This module joins already-recognized CLOSED-candle observations with the shared
FlowTransition. It does NOT attest arc geometry, certify publicTrade/L2,
recognize candles from OHLC, admit a trade or create a Robot candidate.
Only a separate as-of producer may supply pattern observations. The authoritative
Robot entry/protection path is deliberately untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from robot_entry_flow_evidence import FlowTransition


# Existing project catalog: Trading Strategy §1.3 and geometry/reversal_patterns.
# DOJI is the owner's new indecision-only observation. Unlisted formations
# require a versioned catalog addition and a separate closed-OHLC recognizer.
_CANDLE_BIAS = {
    "BULLISH_ENGULFING": "LONG",
    "BEARISH_ENGULFING": "SHORT",
    "HAMMER": "LONG",
    "HANGING_MAN": "SHORT",
    "MORNING_STAR": "LONG",
    "EVENING_STAR": "SHORT",
    "DOJI": None,
}


@dataclass(frozen=True, slots=True)
class ClosedCandlePatternObservation:
    """As-of observation from a separate, versioned closed-candle detector.

    event_group identifies the underlying price event. Different patterns or
    timeframes describing that same event MUST share one group, not two votes.
    The producer, not this DTO, owns OHLC recognition and source authenticity.
    """
    name: str
    candidate_id: str
    state_revision: int
    symbol: str
    source_id: str
    pattern_version: str
    event_group: str
    closed_at_ms: int
    available_at_ms: int


@dataclass(frozen=True, slots=True)
class WedgeCandleExhaustionResearch:
    candidate_id: str
    state_revision: int
    symbol: str
    direction: str
    decision_ms: int
    opposing_flow_fading: bool | None
    candle_event_outcomes: tuple[tuple[str, str], ...]
    outcome: str
    # No pre-breakout arc geometry or market-source certification is furnished
    # by this combiner, so a result cannot be promoted into an executable order.
    arc_geometry_attested: bool = False
    source_complete: bool = False
    trading_authorized: bool = False


def observe_wedge_candle_exhaustion(
    record,
    flow: FlowTransition | None,
    candles: tuple[ClosedCandlePatternObservation, ...],
    *,
    decision_ms: int,
) -> WedgeCandleExhaustionResearch | None:
    """Join independent descriptions without inventing an early entry signal.

    Works only on the original APPROVED wedge before breakout. A known candle
    pattern never proves an arc or an actual absorption event; this is a
    descriptive research result for later exact-geometry/source causal replay.
    """
    if (type(decision_ms) is not int or decision_ms < 0
            or not isinstance(candles, tuple)):
        return None
    try:
        snapshot, state = record.signal_snapshot, record.robot_state
        if (record.status != "APPROVED"
                or not isinstance(snapshot, Mapping)
                or not isinstance(state, Mapping)):
            return None
        pattern = snapshot.get("pattern")
        direction = {"Falling Wedge": "LONG", "Rising Wedge": "SHORT"}.get(pattern)
        if (direction is None or state.get("phase") != "WAITING_BREAKOUT"
                or state.get("direction") != direction
                or state.get("pattern") != pattern):
            return None
        candidate_id, revision, symbol = (
            record.candidate_id, record.state_revision, record.symbol.value,
        )
        if (not isinstance(candidate_id, str) or not candidate_id
                or type(revision) is not int or revision < 0
                or not isinstance(symbol, str) or not symbol.endswith("USDT")):
            return None
    except (AttributeError, TypeError):
        return None

    grouped: dict[str, set[str]] = {}
    for item in candles:
        if not isinstance(item, ClosedCandlePatternObservation):
            continue
        bias = _CANDLE_BIAS.get(item.name, "UNSUPPORTED")
        if (bias == "UNSUPPORTED"
                or item.candidate_id != candidate_id
                or type(item.state_revision) is not int
                or item.state_revision != revision
                or item.symbol != symbol
                or not isinstance(item.source_id, str) or not item.source_id
                or not isinstance(item.pattern_version, str)
                or not item.pattern_version
                or not isinstance(item.event_group, str) or not item.event_group
                or type(item.closed_at_ms) is not int
                or type(item.available_at_ms) is not int
                or not 0 < item.closed_at_ms <= item.available_at_ms <= decision_ms):
            continue
        outcome = "INDECISION" if bias is None else (
            "SUPPORT" if bias == direction else "CONTRADICT"
        )
        grouped.setdefault(item.event_group, set()).add(outcome)

    def merge(votes: set[str]) -> str:
        if "SUPPORT" in votes and "CONTRADICT" in votes:
            return "CONFLICT"
        if "CONTRADICT" in votes:
            return "CONTRADICT"
        if "SUPPORT" in votes:
            return "SUPPORT"
        return "INDECISION"

    events = tuple((key, merge(votes)) for key, votes in sorted(grouped.items()))
    fading = None
    if isinstance(flow, FlowTransition) and flow.known_at_ms <= decision_ms:
        fading = (
            flow.sell_impact_fading if direction == "LONG"
            else flow.buy_impact_fading
        )

    states = {state for _, state in events}
    if fading and "SUPPORT" in states and not (
        "CONTRADICT" in states or "CONFLICT" in states
    ):
        outcome = "FLOW_FADE_WITH_CANDLE_CONTEXT_RESEARCH"
    elif fading and "INDECISION" in states:
        outcome = "FLOW_FADE_WITH_INDECISION_RESEARCH"
    elif fading:
        outcome = "FLOW_FADE_ONLY_RESEARCH"
    elif events:
        outcome = "CANDLE_CONTEXT_ONLY_RESEARCH"
    else:
        outcome = "NO_CAUSAL_CONFLUENCE"

    return WedgeCandleExhaustionResearch(
        candidate_id, revision, symbol, direction, decision_ms,
        fading, events, outcome,
    )
