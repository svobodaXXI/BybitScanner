"""GEO-U1 Slice B: pattern-neutral SHADOW envelope-pair diagnostics.

This module is deliberately disconnected from the production geometry engine,
winner and classifiers.  It pairs Slice A ``BoundaryConsensus`` values only
when an explicit report/test caller asks for shadow evidence.
"""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import NamedTuple

from .consensus_boundary import (
    BoundaryConsensus,
    BoundaryQuality,
    build_boundary_consensus,
)
from .touches import _atr_series, _atr_value_at


class PairQuality(NamedTuple):
    """Strongest-first lexicographic evidence, never a weighted score."""

    pair_valid: bool
    both_sides_materially_used: bool
    cross_boundary_traversals: int
    alternating_touches: int
    touch_balance: float
    opposite_boundary_reach_fraction: float
    meaningful_swings: int
    shared_support_coverage: float
    shared_support_span: int
    body_integrity_sides: int
    negative_mean_residual_sum: float
    negative_max_residual: float
    negative_excursion_count: int


@dataclass(frozen=True)
class EnvelopePairConsensus:
    upper_boundary: BoundaryConsensus
    lower_boundary: BoundaryConsensus
    upper_boundary_identity: tuple[str, tuple[int, ...]]
    lower_boundary_identity: tuple[str, tuple[int, ...]]
    common_episode_start: int
    common_episode_end: int
    width_at_start: float
    width_at_end: float
    width_change_ratio: float | None
    compression_ratio: float | None
    pair_valid: bool
    pair_invalid_reasons: tuple[str, ...]
    boundaries_cross_inside_episode: bool
    boundary_intersection_index: float | None
    minimum_signed_width: float
    touch_event_sequence: tuple[tuple[str, int, tuple[int, ...]], ...]
    alternating_touch_sequence: tuple[tuple[str, int], ...]
    alternating_touch_count: int
    upper_touch_count: int
    lower_touch_count: int
    touch_balance: float
    cross_boundary_traversal_count: int
    meaningful_swing_count: int
    opposite_boundary_reach_fraction: float
    first_two_sided_interaction: int | None
    last_two_sided_interaction: int | None
    shared_support_start: int | None
    shared_support_end: int | None
    shared_support_span: int
    shared_support_coverage_ratio: float
    quality_tuple: PairQuality


def _identity(boundary):
    return boundary.side, boundary.inlier_pivot_indices


def _historical_frame(candles, as_of_index, episode_start_index, episode_end_index):
    if (type(as_of_index) is not int or type(episode_start_index) is not int
            or type(episode_end_index) is not int
            or not 0 <= episode_start_index < episode_end_index <= as_of_index
            or as_of_index >= len(candles)):
        raise ValueError("episode/cutoff must be valid positional candle indices")
    frame = candles.iloc[:as_of_index + 1].copy(deep=True).reset_index(drop=True)
    for column in ("open", "high", "low", "close"):
        values = frame[column].astype(float)
        if not all(isfinite(value) and value > 0 for value in values):
            raise ValueError("historical OHLC must be finite and positive")
        frame[column] = values
    if ((frame.high < frame[["open", "close"]].max(axis=1)).any()
            or (frame.low > frame[["open", "close"]].min(axis=1)).any()):
        raise ValueError("historical OHLC body must be inside high/low")
    return frame


def _touch_events(upper, lower, start, end):
    events = []
    for boundary in (upper, lower):
        for cluster in boundary.touch_cluster_indices:
            inside = tuple(index for index in cluster if start <= index <= end)
            if inside:
                # The first confirmed contact orders the cluster.  The full
                # cluster remains visible and still counts exactly once.
                events.append((boundary.side, inside[0], inside))
    return tuple(sorted(events, key=lambda event: (
        event[1], 0 if event[0] == "upper" else 1, event[2]
    )))


def _alternating_events(events):
    """Collapse each consecutive same-side run to its last contact."""
    alternating = []
    for side, index, _cluster in events:
        event = (side, index)
        if alternating and alternating[-1][0] == side:
            alternating[-1] = event
        else:
            alternating.append(event)
    return tuple(alternating)


def _signed_width(upper, lower, index):
    return _line_value(upper, index) - _line_value(lower, index)


def _line_value(boundary, index):
    return boundary.slope * index + boundary.intercept


def _segment_evidence(
    frame, atr, upper, lower, source, destination, *,
    touch_band_atr, minimum_swing_width_fraction, minimum_swing_atr,
):
    source_side, source_index, _ = source
    destination_side, destination_index, _ = destination
    if destination_index <= source_index:
        return False, False

    departed = False
    reached_opposite = False
    for index in range(source_index, destination_index + 1):
        width = _signed_width(upper, lower, index)
        atr_value = atr[index]
        if width <= 0 or atr_value is None:
            continue
        close = float(frame.close.iloc[index])
        source_value = _line_value(
            upper if source_side == "upper" else lower, index
        )
        inward_distance = ((source_value - close) if source_side == "upper"
                           else (close - source_value))
        required_departure = max(
            minimum_swing_width_fraction * width,
            minimum_swing_atr * atr_value,
        )
        if inward_distance >= required_departure:
            departed = True

        if destination_side != source_side:
            destination_value = _line_value(
                upper if destination_side == "upper" else lower, index
            )
            if destination_side == "upper":
                reached = float(frame.high.iloc[index]) >= (
                    destination_value - touch_band_atr * atr_value
                )
            else:
                reached = float(frame.low.iloc[index]) <= (
                    destination_value + touch_band_atr * atr_value
                )
            reached_opposite = reached_opposite or reached
    return departed, reached_opposite


def _build_pair(
    frame, atr, upper, lower, *, episode_start_index, episode_end_index,
    touch_band_atr, minimum_swing_width_fraction, minimum_swing_atr,
    minimum_side_touch_clusters,
):
    start_width = _signed_width(upper, lower, episode_start_index)
    end_width = _signed_width(upper, lower, episode_end_index)
    slope_delta = upper.slope - lower.slope
    intersection = None
    if slope_delta != 0:
        intersection = (lower.intercept - upper.intercept) / slope_delta
        if not isfinite(intersection):
            intersection = None
    crossing = (intersection is not None
                and episode_start_index <= intersection <= episode_end_index)

    shared_start = max(
        episode_start_index, upper.first_supported_pivot, lower.first_supported_pivot
    )
    shared_end = min(
        episode_end_index, upper.last_supported_pivot, lower.last_supported_pivot
    )
    has_shared_support = shared_start <= shared_end
    shared_span = max(0, shared_end - shared_start) if has_shared_support else 0
    episode_span = episode_end_index - episode_start_index
    shared_coverage = shared_span / episode_span

    reasons = []
    if upper.side != "upper" or lower.side != "lower":
        reasons.append("SIDE_IDENTITY_MISMATCH")
    if start_width <= 0:
        reasons.append("BOUNDARY_ORDER_INVALID_AT_EPISODE_START")
    if end_width <= 0:
        reasons.append("BOUNDARY_ORDER_INVALID_AT_EPISODE_END")
    if crossing:
        reasons.append("BOUNDARIES_CROSS_INSIDE_EPISODE")
    if not has_shared_support:
        reasons.append("NO_SHARED_SUPPORT_INTERVAL")
    pair_valid = not reasons

    events = _touch_events(
        upper, lower, episode_start_index, episode_end_index
    )
    alternating = _alternating_events(events)
    meaningful_swings = 0
    traversals = 0
    interaction_indices = []
    for source, destination in zip(events, events[1:]):
        departed, reached = _segment_evidence(
            frame, atr, upper, lower, source, destination,
            touch_band_atr=touch_band_atr,
            minimum_swing_width_fraction=minimum_swing_width_fraction,
            minimum_swing_atr=minimum_swing_atr,
        )
        if departed:
            meaningful_swings += 1
        if departed and reached and source[0] != destination[0]:
            traversals += 1
            interaction_indices.extend((source[1], destination[1]))

    upper_count = sum(event[0] == "upper" for event in events)
    lower_count = sum(event[0] == "lower" for event in events)
    maximum_count = max(upper_count, lower_count)
    balance = min(upper_count, lower_count) / maximum_count if maximum_count else 0.0
    reach_fraction = traversals / meaningful_swings if meaningful_swings else 0.0
    both_used = (upper_count >= minimum_side_touch_clusters
                 and lower_count >= minimum_side_touch_clusters)
    mean_residual_sum = upper.mean_residual_atr + lower.mean_residual_atr
    max_residual = max(upper.max_residual_atr, lower.max_residual_atr)
    excursion_count = (len(upper.excursion_pivot_indices)
                       + len(lower.excursion_pivot_indices))
    quality = PairQuality(
        pair_valid,
        both_used,
        traversals,
        len(alternating),
        balance,
        reach_fraction,
        meaningful_swings,
        shared_coverage,
        shared_span,
        int(upper.body_integrity) + int(lower.body_integrity),
        -mean_residual_sum,
        -max_residual,
        -excursion_count,
    )
    return EnvelopePairConsensus(
        upper_boundary=upper,
        lower_boundary=lower,
        upper_boundary_identity=_identity(upper),
        lower_boundary_identity=_identity(lower),
        common_episode_start=episode_start_index,
        common_episode_end=episode_end_index,
        width_at_start=start_width,
        width_at_end=end_width,
        width_change_ratio=(end_width - start_width) / start_width
        if start_width != 0 else None,
        compression_ratio=end_width / start_width
        if start_width != 0 else None,
        pair_valid=pair_valid,
        pair_invalid_reasons=tuple(reasons),
        boundaries_cross_inside_episode=crossing,
        boundary_intersection_index=intersection,
        minimum_signed_width=min(start_width, end_width),
        touch_event_sequence=events,
        alternating_touch_sequence=alternating,
        alternating_touch_count=len(alternating),
        upper_touch_count=upper_count,
        lower_touch_count=lower_count,
        touch_balance=balance,
        cross_boundary_traversal_count=traversals,
        meaningful_swing_count=meaningful_swings,
        opposite_boundary_reach_fraction=reach_fraction,
        first_two_sided_interaction=min(interaction_indices)
        if interaction_indices else None,
        last_two_sided_interaction=max(interaction_indices)
        if interaction_indices else None,
        shared_support_start=shared_start if has_shared_support else None,
        shared_support_end=shared_end if has_shared_support else None,
        shared_support_span=shared_span,
        shared_support_coverage_ratio=shared_coverage,
        quality_tuple=quality,
    )


def build_envelope_pair_consensus(
    candles, upper_candidates, lower_candidates, *, as_of_index,
    episode_start_index, episode_end_index, touch_band_atr,
    minimum_swing_width_fraction, minimum_swing_atr,
    minimum_side_touch_clusters=2,
):
    """Return every canonical upper/lower pairing, strongest first.

    ``candles`` may contain later rows, but everything after ``as_of_index`` is
    sliced before validation, ATR, or interaction analysis.  Thresholds are
    explicit shadow-report parameters and do not alter production settings.
    """
    numeric = (touch_band_atr, minimum_swing_width_fraction, minimum_swing_atr)
    if (not all(isfinite(value) and value > 0 for value in numeric)
            or type(minimum_side_touch_clusters) is not int
            or minimum_side_touch_clusters < 1):
        raise ValueError("shadow pair thresholds must be finite and positive")
    frame = _historical_frame(
        candles, as_of_index, episode_start_index, episode_end_index
    )
    series = _atr_series(frame)
    atr = [_atr_value_at(series, index) for index in range(len(frame))]
    atr = [value if value is not None and isfinite(value) and value > 0 else None
           for value in atr]

    uppers = tuple(sorted(upper_candidates, key=lambda item: (
        _identity(item), item.seed_anchor_indices
    )))
    lowers = tuple(sorted(lower_candidates, key=lambda item: (
        _identity(item), item.seed_anchor_indices
    )))
    for boundary in (*uppers, *lowers):
        evidence_indices = (
            *boundary.inlier_pivot_indices,
            *(index for cluster in boundary.touch_cluster_indices
              for index in cluster),
        )
        if (not evidence_indices or min(evidence_indices) < 0
                or max(evidence_indices) > as_of_index):
            raise ValueError("boundary evidence must stay inside historical cutoff")
    pairs = {}
    for upper in uppers:
        for lower in lowers:
            identity = (_identity(upper), _identity(lower))
            pairs[identity] = _build_pair(
                frame, atr, upper, lower,
                episode_start_index=episode_start_index,
                episode_end_index=episode_end_index,
                touch_band_atr=touch_band_atr,
                minimum_swing_width_fraction=minimum_swing_width_fraction,
                minimum_swing_atr=minimum_swing_atr,
                minimum_side_touch_clusters=minimum_side_touch_clusters,
            )
    return tuple(sorted(pairs.values(), key=lambda item: (
        tuple(-value for value in item.quality_tuple),
        item.upper_boundary_identity,
        item.lower_boundary_identity,
    )))


def consensus_envelope_shadow_report(
    candles, *, as_of_index, episode_start_index, episode_end_index,
    inlier_band_atr, separation_atr, touch_band_atr,
    minimum_swing_width_fraction, minimum_swing_atr,
    minimum_side_touch_clusters=2,
):
    """JSON-compatible Slice A + Slice B diagnostics beside production."""
    boundary_parameters = dict(
        as_of_index=as_of_index,
        episode_start_index=episode_start_index,
        inlier_band_atr=inlier_band_atr,
        separation_atr=separation_atr,
    )
    upper = build_boundary_consensus(candles, side="upper", **boundary_parameters)
    lower = build_boundary_consensus(candles, side="lower", **boundary_parameters)
    pair_parameters = dict(
        as_of_index=as_of_index,
        episode_start_index=episode_start_index,
        episode_end_index=episode_end_index,
        touch_band_atr=touch_band_atr,
        minimum_swing_width_fraction=minimum_swing_width_fraction,
        minimum_swing_atr=minimum_swing_atr,
        minimum_side_touch_clusters=minimum_side_touch_clusters,
    )
    pairs = build_envelope_pair_consensus(
        candles, upper, lower, **pair_parameters
    )
    pair_records = []
    for item in pairs:
        record = asdict(item)
        # The top-level arrays own the complete boundary diagnostics. Pair
        # records retain canonical references without duplicating the same
        # large boundary objects for every Cartesian pairing.
        record["upper_boundary"] = item.upper_boundary_identity
        record["lower_boundary"] = item.lower_boundary_identity
        pair_records.append(record)
    return {
        "mode": "SHADOW_ONLY",
        "boundary_parameters": boundary_parameters,
        "pair_parameters": pair_parameters,
        "boundary_quality_fields": BoundaryQuality._fields,
        "pair_quality_fields": PairQuality._fields,
        "upper": [asdict(item) for item in upper],
        "lower": [asdict(item) for item in lower],
        "pairs": pair_records,
    }
