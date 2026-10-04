"""Pattern-neutral, diagnostic-only lifecycle of a consensus envelope pair.

This module is not imported by the selector or production Geometry. It reads
confirmed pivots from the decision-time candle prefix and never changes pair
admission, ranking, or historical boundary identity.
"""

from dataclasses import dataclass
from math import isfinite

from pivots import find_pivots

from .consensus_pair import EnvelopePairConsensus


CONTINUING = "CONTINUING_BILATERAL_STRUCTURE"
COMPLETED = "STRUCTURE_COMPLETED_OR_TRANSITIONED"
INTERNAL_DRIFT = "UNCONSTRAINED_INTERNAL_DRIFT"


@dataclass(frozen=True)
class LifecyclePivot:
    side: str  # upper | lower
    index: int
    relation: str  # INTERNAL | EXTERNAL | BOUNDARY_RELATIVE
    external_side: str | None = None  # above_upper | below_lower


@dataclass(frozen=True)
class LegacySupportGapDiagnostic:
    gap_bars: int
    gap_fraction: float
    stale_shared_support: bool | None


@dataclass(frozen=True)
class DerivedEnvelopeLifecycle:
    pair_identity_ref: tuple
    evidence_as_of_index: int
    lifecycle_state: str | None
    last_boundary_relative_event: tuple[str, int] | None
    post_boundary_event_chain: tuple[LifecyclePivot, ...]
    decisive_event: tuple[LifecyclePivot, ...] | None
    transition_reason: str | None
    ambiguity_trace: tuple[str, ...]
    legacy_support_gap_diagnostic: LegacySupportGapDiagnostic | None
    shadow_admission_disposition: str


def _line_value(boundary, index):
    return boundary.slope * index + boundary.intercept


def _legacy_gap(pair, cutoff, maximum_fraction):
    if pair.shared_support_end is None:
        gap = pair.common_episode_end - pair.common_episode_start
    else:
        gap = pair.common_episode_end - pair.shared_support_end
    span = pair.common_episode_end - pair.common_episode_start
    return LegacySupportGapDiagnostic(
        gap_bars=gap,
        gap_fraction=gap / span,
        stale_shared_support=(gap > maximum_fraction * span
                              if maximum_fraction is not None else None),
    )


def derive_envelope_lifecycle(
    candles, pair: EnvelopePairConsensus, *, evidence_as_of_index: int,
    legacy_max_support_gap_fraction: float | None = None,
) -> DerivedEnvelopeLifecycle:
    """Interpret one fixed pair at a closed-candle cutoff, without admission.

    A completed internal or same-side external swing after the last boundary
    contact is decisive. Pivot confirmation uses the existing ``find_pivots``
    defaults on the historical prefix, including its right-hand candles.
    """
    if (type(evidence_as_of_index) is not int
            or not 0 <= pair.common_episode_start < pair.common_episode_end <= evidence_as_of_index
            or evidence_as_of_index >= len(candles)):
        raise ValueError("pair episode and evidence cutoff must be historical")
    if (legacy_max_support_gap_fraction is not None
            and (not isfinite(legacy_max_support_gap_fraction)
                 or legacy_max_support_gap_fraction < 0)):
        raise ValueError("legacy gap fraction must be nonnegative and finite")
    identity = (pair.upper_boundary_identity, pair.lower_boundary_identity)
    known_indices = (
        *pair.upper_boundary_identity[1], *pair.lower_boundary_identity[1],
        *(index for _, index, cluster in pair.touch_event_sequence
          for index in cluster),
    )
    if known_indices and max(known_indices) > evidence_as_of_index:
        raise ValueError("pair evidence extends beyond historical cutoff")

    prefix = candles.iloc[:evidence_as_of_index + 1].copy(deep=True)
    highs, lows = find_pivots(prefix)
    touches = {(side, index)
               for side, _first, cluster in pair.touch_event_sequence
               for index in cluster}
    last = pair.touch_event_sequence[-1] if pair.touch_event_sequence else None
    last_event = (last[0], last[1]) if last else None
    after = []
    if last_event is not None:
        for side, pivots in (("upper", highs), ("lower", lows)):
            for pivot in pivots:
                index = int(pivot["index"])
                if index <= last_event[1]:
                    continue
                price = float(pivot["price"])
                upper = _line_value(pair.upper_boundary, index)
                lower = _line_value(pair.lower_boundary, index)
                if (side, index) in touches:
                    relation = "BOUNDARY_RELATIVE"
                elif lower < price < upper:
                    relation = "INTERNAL"
                else:
                    relation = "EXTERNAL"
                external_side = None
                if relation == "EXTERNAL":
                    external_side = ("above_upper" if price >= upper
                                     else "below_lower")
                after.append(LifecyclePivot(side, index, relation, external_side))
    after.sort(key=lambda event: (event.index, event.side))
    chain = tuple(after)
    common = dict(
        pair_identity_ref=identity,
        evidence_as_of_index=evidence_as_of_index,
        last_boundary_relative_event=last_event,
        post_boundary_event_chain=chain,
        legacy_support_gap_diagnostic=(
            _legacy_gap(pair, evidence_as_of_index, legacy_max_support_gap_fraction)
            if pair.shared_support_end is not None else None),
    )
    if (not pair.pair_valid or pair.alternating_touch_count < 3
            or last_event is None):
        return DerivedEnvelopeLifecycle(
            lifecycle_state=None, decisive_event=None,
            transition_reason="BILATERAL_RECURRENCE_UNPROVEN",
            ambiguity_trace=("BILATERAL_RECURRENCE_UNPROVEN",),
            shadow_admission_disposition="DEFER_NEW_ADMISSION", **common)

    first_external_by_side = {}
    external_swing = None
    for event in chain:
        if event.relation != "EXTERNAL":
            continue
        opposite = "lower" if event.side == "upper" else "upper"
        previous = first_external_by_side.get((event.external_side, opposite))
        if previous is not None:
            external_swing = (previous, event)
            break
        first_external_by_side.setdefault((event.external_side, event.side), event)
    if external_swing is not None:
        return DerivedEnvelopeLifecycle(
            lifecycle_state=COMPLETED, decisive_event=external_swing,
            transition_reason="EXTERNAL_SWING_CHAIN_CONFIRMED",
            ambiguity_trace=(),
            shadow_admission_disposition="REJECT_OLD_PAIR", **common)
    if any(event.relation == "EXTERNAL" for event in chain):
        return DerivedEnvelopeLifecycle(
            lifecycle_state=None, decisive_event=None,
            transition_reason="EXTERNAL_TRANSITION_UNPROVEN",
            ambiguity_trace=("EXTERNAL_TRANSITION_UNPROVEN",),
            shadow_admission_disposition="DEFER_NEW_ADMISSION", **common)

    expected = "lower" if last_event[0] == "upper" else "upper"
    first = next((event for event in chain
                  if event.side == expected and event.relation == "INTERNAL"), None)
    second = next((event for event in chain
                   if first is not None and event.index > first.index
                   and event.side != first.side and event.relation == "INTERNAL"), None)
    if second is not None:
        return DerivedEnvelopeLifecycle(
            lifecycle_state=INTERNAL_DRIFT,
            decisive_event=(first, second),
            transition_reason="INTERNAL_SWING_CHAIN_CONFIRMED",
            ambiguity_trace=(),
            shadow_admission_disposition="REJECT_OLD_PAIR", **common)
    if first is not None:
        return DerivedEnvelopeLifecycle(
            lifecycle_state=None, decisive_event=None,
            transition_reason="INTERNAL_CHAIN_INCOMPLETE",
            ambiguity_trace=("OPPOSITE_INTERNAL_REVERSAL_UNCONFIRMED",),
            shadow_admission_disposition="DEFER_NEW_ADMISSION", **common)
    return DerivedEnvelopeLifecycle(
        lifecycle_state=CONTINUING,
        decisive_event=None,
        transition_reason="LAST_COMPLETED_SWING_BOUNDARY_RELATIVE",
        ambiguity_trace=(),
        shadow_admission_disposition="NO_STALE_LIFECYCLE_REJECTION", **common)
