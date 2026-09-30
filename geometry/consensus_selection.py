"""GEO-U1 Slice C: SHADOW pair selection + terminal width evidence.

Disconnected from the production engine, winner and classifiers. It ranks the
Slice B ``EnvelopePairConsensus`` candidates with explicit gates and a
lexicographic tuple (never one aggregate score) and reports terminal-window
width evidence. It assigns NO family label (Wedge/Triangle/Compression/
Broadening); the terminal trend vocabulary is a width fact, not a pattern.
All thresholds are explicit SHADOW parameters, not calibrated production values.
"""

from dataclasses import asdict, dataclass
from math import fsum, isfinite
from statistics import median
from typing import NamedTuple

from .consensus_boundary import build_boundary_consensus
from .consensus_pair import (
    EnvelopePairConsensus,
    _historical_frame,
    build_envelope_pair_consensus,
    _signed_width,
)


class SelectionQuality(NamedTuple):
    """Strongest-first lexicographic evidence, never a weighted score."""

    admissible: bool
    pair_valid: bool
    both_sides_materially_used: bool
    cross_boundary_traversals: int
    alternating_touches: int
    touch_balance: float
    opposite_boundary_reach_fraction: float
    meaningful_swings: int
    shared_support_coverage: float
    shared_support_span: int
    negative_support_gap_bars: int
    body_integrity_sides: int
    negative_mean_residual_sum: float
    negative_max_residual: float
    negative_excursion_count: int
    terminal_width_trend_persistent: bool


@dataclass(frozen=True)
class TerminalCompressionEvidence:
    """Width facts over the terminal window; no pattern family."""

    window_start: int | None
    window_end: int
    window_bars: int
    segments: int
    # Width trend vocabulary: PERSISTENT_COMPRESSION | EXPANSION |
    # NO_PERSISTENT_WIDTH_TREND | INSUFFICIENT_WINDOW | NON_POSITIVE_WIDTH
    terminal_width_trend: str
    terminal_width_series: tuple[float, ...]      # mean line width per segment
    terminal_width_min: float | None
    terminal_width_max: float | None
    terminal_compression_ratio: float | None     # line width end / window start
    terminal_width_slope: float | None           # OLS width slope per bar
    terminal_relative_width_slope: float | None  # slope / window-start width
    line_contracting_steps: int
    line_expanding_steps: int
    realized_segment_ranges: tuple[float, ...]   # max high - min low per segment
    realized_contraction_ratio: float | None     # last / first segment range
    realized_contracting_steps: int
    shifted_window_compression_ok: bool | None   # same test, window ends 1 bar earlier
    full_window_compression_ok: bool | None
    persistent_compression: bool
    expansion: bool
    last_bar_range_ratio: float | None
    single_bar_narrowing_only: bool


@dataclass(frozen=True)
class SelectionTraceRow:
    upper_boundary_identity: tuple[str, tuple[int, ...]]
    lower_boundary_identity: tuple[str, tuple[int, ...]]
    admissible: bool
    rejection_reasons: tuple[str, ...]
    terminal_width_trend: str
    quality_tuple: SelectionQuality


@dataclass(frozen=True)
class ShadowPairSelection:
    mode: str
    selection_status: str            # SELECTED | NO_ADMISSIBLE_PAIR | NO_CANDIDATES
    admissible: bool
    selected_pair_identity: tuple | None
    selected_pair: EnvelopePairConsensus | None
    rejection_reasons: tuple[str, ...]
    terminal: TerminalCompressionEvidence | None
    quality_fields: tuple[str, ...]
    final_quality_tuple: SelectionQuality | None
    candidate_count: int
    admissible_count: int
    rejected_count: int
    runner_up_identity: tuple | None
    runner_up_quality_tuple: SelectionQuality | None
    deciding_component: str | None   # first field where winner != runner-up
    selection_trace: tuple[SelectionTraceRow, ...]
    parameters: tuple[tuple[str, float | int], ...]


def _identity(pair):
    return pair.upper_boundary_identity, pair.lower_boundary_identity


def _window_measures(frame, pair, first, last, segments):
    size = (last - first + 1) // segments
    line, realized = [], []
    for k in range(segments):
        lo = first + k * size
        hi = lo + size
        widths = [_signed_width(pair.upper_boundary, pair.lower_boundary, i)
                  for i in range(lo, hi)]
        line.append(fsum(widths) / len(widths))
        realized.append(float(frame.high.iloc[lo:hi].max()
                              - frame.low.iloc[lo:hi].min()))
    return tuple(line), tuple(realized)


def _steps(series, tolerance):
    contracting = sum(b <= a * (1 + tolerance) for a, b in zip(series, series[1:]))
    expanding = sum(b >= a * (1 - tolerance) for a, b in zip(series, series[1:]))
    return contracting, expanding


def _compression_ok(line, realized, line_ratio, max_ratio, tolerance):
    realized_ratio = realized[-1] / realized[0] if realized[0] > 0 else None
    steps = len(line) - 1
    return (line_ratio <= max_ratio
            and _steps(line, tolerance)[0] == steps
            and realized_ratio is not None
            and realized_ratio <= max_ratio
            and _steps(realized, tolerance)[0] == steps)


def terminal_compression_evidence(
    frame, pair, *, terminal_window_bars, terminal_segments,
    compression_max_ratio, expansion_min_ratio, segment_tolerance,
    single_bar_narrow_ratio,
):
    """Terminal-window width evidence for one pair on a historical frame.

    The window is the last ``terminal_window_bars`` bars of the episode, split
    into equal segments of >=3 bars. Compression is PERSISTENT only if, for the
    window AND the same window shifted one bar earlier: the line width ratio is
    <= compression_max_ratio with every segment step non-expanding, AND the
    realized price range (max high - min low per segment) contracts the same
    way. A single narrow last bar cannot shrink a >=3-bar segment range, and a
    result that flips under the one-bar shift is not persistent.
    """
    numeric = (compression_max_ratio, expansion_min_ratio, segment_tolerance,
               single_bar_narrow_ratio)
    if (type(terminal_window_bars) is not int or type(terminal_segments) is not int
            or terminal_segments < 2 or terminal_window_bars % terminal_segments
            or terminal_window_bars // terminal_segments < 3
            or not all(isfinite(v) for v in numeric)
            or not 0 < compression_max_ratio < 1 or expansion_min_ratio <= 1
            or not 0 <= segment_tolerance < 1 or single_bar_narrow_ratio <= 0):
        raise ValueError("invalid terminal compression parameters")
    end = pair.common_episode_end
    first = end - terminal_window_bars + 1
    base = dict(window_bars=terminal_window_bars, segments=terminal_segments,
                window_end=end)
    empty = dict(
        terminal_width_series=(), terminal_width_min=None, terminal_width_max=None,
        terminal_compression_ratio=None, terminal_width_slope=None,
        terminal_relative_width_slope=None, line_contracting_steps=0,
        line_expanding_steps=0, realized_segment_ranges=(),
        realized_contraction_ratio=None, realized_contracting_steps=0,
        shifted_window_compression_ok=None, full_window_compression_ok=None,
        persistent_compression=False, expansion=False,
        last_bar_range_ratio=None, single_bar_narrowing_only=False,
    )
    if first - 1 < pair.common_episode_start:
        return TerminalCompressionEvidence(
            window_start=None, terminal_width_trend="INSUFFICIENT_WINDOW",
            **base, **empty)
    widths = [_signed_width(pair.upper_boundary, pair.lower_boundary, i)
              for i in range(first - 1, end + 1)]
    if min(widths) <= 0:
        return TerminalCompressionEvidence(
            window_start=first, terminal_width_trend="NON_POSITIVE_WIDTH",
            **base, **empty)

    line, realized = _window_measures(frame, pair, first, end, terminal_segments)
    s_line, s_realized = _window_measures(
        frame, pair, first - 1, end - 1, terminal_segments)
    per_bar = widths[1:]
    ratio = per_bar[-1] / per_bar[0]
    shifted_ratio = widths[-2] / widths[0]
    full_ok = _compression_ok(line, realized, ratio, compression_max_ratio,
                              segment_tolerance)
    shifted_ok = _compression_ok(s_line, s_realized, shifted_ratio,
                                 compression_max_ratio, segment_tolerance)
    persistent = full_ok and shifted_ok
    contracting, expanding = _steps(line, segment_tolerance)
    expansion = (not persistent and ratio >= expansion_min_ratio
                 and expanding == terminal_segments - 1)

    xs = range(first, end + 1)
    mean_x = fsum(xs) / len(per_bar)
    mean_w = fsum(per_bar) / len(per_bar)
    slope = fsum((x - mean_x) * (w - mean_w) for x, w in zip(xs, per_bar)) / fsum(
        (x - mean_x) ** 2 for x in xs)

    ranges = [float(frame.high.iloc[i] - frame.low.iloc[i])
              for i in range(first, end + 1)]
    typical = median(ranges[:-1])
    last_ratio = ranges[-1] / typical if typical > 0 else None
    trend = ("PERSISTENT_COMPRESSION" if persistent else
             "EXPANSION" if expansion else "NO_PERSISTENT_WIDTH_TREND")
    return TerminalCompressionEvidence(
        window_start=first, terminal_width_trend=trend, **base,
        terminal_width_series=line, terminal_width_min=min(per_bar),
        terminal_width_max=max(per_bar), terminal_compression_ratio=ratio,
        terminal_width_slope=slope,
        terminal_relative_width_slope=slope / per_bar[0],
        line_contracting_steps=contracting, line_expanding_steps=expanding,
        realized_segment_ranges=realized,
        realized_contraction_ratio=(realized[-1] / realized[0]
                                    if realized[0] > 0 else None),
        realized_contracting_steps=_steps(realized, segment_tolerance)[0],
        shifted_window_compression_ok=shifted_ok,
        full_window_compression_ok=full_ok,
        persistent_compression=persistent, expansion=expansion,
        last_bar_range_ratio=last_ratio,
        single_bar_narrowing_only=(not persistent and last_ratio is not None
                                   and last_ratio <= single_bar_narrow_ratio),
    )


def _support_gap(pair):
    if pair.shared_support_end is None:
        return pair.common_episode_end - pair.common_episode_start
    return pair.common_episode_end - pair.shared_support_end


def _rejection_reasons(pair, gap, *, min_cross_boundary_traversals,
                       min_alternating_touches, min_touch_balance,
                       min_shared_support_coverage, max_support_gap_fraction):
    reasons = [f"PAIR_{reason}" for reason in pair.pair_invalid_reasons]
    if not pair.pair_valid and not reasons:
        reasons.append("PAIR_INVALID")
    if not pair.quality_tuple.both_sides_materially_used:
        reasons.append("SIDE_NOT_MATERIALLY_USED")
    if pair.cross_boundary_traversal_count < min_cross_boundary_traversals:
        reasons.append("INSUFFICIENT_CROSS_BOUNDARY_TRAVERSALS")
    if pair.alternating_touch_count < min_alternating_touches:
        reasons.append("INSUFFICIENT_ALTERNATING_TOUCHES")
    if pair.touch_balance < min_touch_balance:
        reasons.append("TOUCH_IMBALANCE")
    if pair.shared_support_coverage_ratio < min_shared_support_coverage:
        reasons.append("INSUFFICIENT_SHARED_SUPPORT")
    if gap > max_support_gap_fraction * (
            pair.common_episode_end - pair.common_episode_start):
        reasons.append("STALE_SHARED_SUPPORT")
    if pair.quality_tuple.body_integrity_sides < 2:
        reasons.append("BODY_INTEGRITY_FAILED")
    return tuple(reasons)


def _quality(pair, admissible, gap, terminal):
    q = pair.quality_tuple
    return SelectionQuality(
        admissible, q.pair_valid, q.both_sides_materially_used,
        q.cross_boundary_traversals, q.alternating_touches, q.touch_balance,
        q.opposite_boundary_reach_fraction, q.meaningful_swings,
        q.shared_support_coverage, q.shared_support_span, -gap,
        q.body_integrity_sides, q.negative_mean_residual_sum,
        q.negative_max_residual, q.negative_excursion_count,
        terminal.persistent_compression or terminal.expansion,
    )


def select_envelope_pair_shadow(
    candles, upper_candidates, lower_candidates, *, as_of_index,
    episode_start_index, episode_end_index, touch_band_atr,
    minimum_swing_width_fraction, minimum_swing_atr,
    minimum_side_touch_clusters=2,
    min_cross_boundary_traversals, min_alternating_touches, min_touch_balance,
    min_shared_support_coverage, max_support_gap_fraction,
    terminal_window_bars, terminal_segments, compression_max_ratio,
    expansion_min_ratio, segment_tolerance, single_bar_narrow_ratio,
):
    """Rank every Slice B pair; select the strongest admissible one (SHADOW).

    Order: admissible, then structural pair evidence, locality (support gap),
    body/residual evidence, and only last the terminal width trend being
    persistent in either direction (direction belongs to later classification).
    Final ties break by (upper identity, lower identity) ascending, so the
    result is independent of candidate order. Rows after ``as_of_index`` are
    sliced away before any computation.
    """
    if (not all(isfinite(v) for v in (
            min_touch_balance, min_shared_support_coverage,
            max_support_gap_fraction))
            or type(min_cross_boundary_traversals) is not int
            or type(min_alternating_touches) is not int
            or min_cross_boundary_traversals < 0 or min_alternating_touches < 0
            or not 0 <= min_touch_balance <= 1
            or not 0 <= min_shared_support_coverage <= 1
            or max_support_gap_fraction < 0):
        raise ValueError("invalid SHADOW selection gate parameters")
    frame = _historical_frame(
        candles, as_of_index, episode_start_index, episode_end_index)
    pairs = build_envelope_pair_consensus(
        candles, upper_candidates, lower_candidates, as_of_index=as_of_index,
        episode_start_index=episode_start_index,
        episode_end_index=episode_end_index, touch_band_atr=touch_band_atr,
        minimum_swing_width_fraction=minimum_swing_width_fraction,
        minimum_swing_atr=minimum_swing_atr,
        minimum_side_touch_clusters=minimum_side_touch_clusters,
    )
    gates = dict(
        min_cross_boundary_traversals=min_cross_boundary_traversals,
        min_alternating_touches=min_alternating_touches,
        min_touch_balance=min_touch_balance,
        min_shared_support_coverage=min_shared_support_coverage,
        max_support_gap_fraction=max_support_gap_fraction,
    )
    terminal_parameters = dict(
        terminal_window_bars=terminal_window_bars,
        terminal_segments=terminal_segments,
        compression_max_ratio=compression_max_ratio,
        expansion_min_ratio=expansion_min_ratio,
        segment_tolerance=segment_tolerance,
        single_bar_narrow_ratio=single_bar_narrow_ratio,
    )
    ranked = []
    for pair in pairs:
        gap = _support_gap(pair)
        reasons = _rejection_reasons(pair, gap, **gates)
        terminal = terminal_compression_evidence(
            frame, pair, **terminal_parameters)
        quality = _quality(pair, not reasons, gap, terminal)
        ranked.append((pair, reasons, terminal, quality))
    ranked.sort(key=lambda item: (
        tuple(-float(v) for v in item[3]), _identity(item[0])))

    trace = tuple(SelectionTraceRow(
        *_identity(pair), not reasons, reasons, terminal.terminal_width_trend,
        quality) for pair, reasons, terminal, quality in ranked)
    parameters = tuple(sorted({**gates, **terminal_parameters,
                               "touch_band_atr": touch_band_atr,
                               "minimum_swing_width_fraction":
                                   minimum_swing_width_fraction,
                               "minimum_swing_atr": minimum_swing_atr,
                               "minimum_side_touch_clusters":
                                   minimum_side_touch_clusters}.items()))
    admissible_count = sum(row.admissible for row in trace)
    common = dict(
        mode="SHADOW_ONLY", quality_fields=SelectionQuality._fields,
        candidate_count=len(ranked), admissible_count=admissible_count,
        rejected_count=len(ranked) - admissible_count,
        selection_trace=trace, parameters=parameters,
    )
    if not ranked:
        return ShadowPairSelection(
            selection_status="NO_CANDIDATES", admissible=False,
            selected_pair_identity=None, selected_pair=None,
            rejection_reasons=("NO_CANDIDATE_PAIRS",), terminal=None,
            final_quality_tuple=None, runner_up_identity=None,
            runner_up_quality_tuple=None, deciding_component=None, **common)

    top_pair, top_reasons, top_terminal, top_quality = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    deciding = None
    if runner is not None:
        deciding = next(
            (name for name, a, b in zip(
                SelectionQuality._fields, top_quality, runner[3]) if a != b),
            "IDENTITY_TIE_BREAK")
    return ShadowPairSelection(
        selection_status="SELECTED" if not top_reasons else "NO_ADMISSIBLE_PAIR",
        admissible=not top_reasons,
        selected_pair_identity=_identity(top_pair) if not top_reasons else None,
        selected_pair=top_pair if not top_reasons else None,
        rejection_reasons=top_reasons, terminal=top_terminal,
        final_quality_tuple=top_quality,
        runner_up_identity=_identity(runner[0]) if runner else None,
        runner_up_quality_tuple=runner[3] if runner else None,
        deciding_component=deciding, **common)


def shadow_selection_record(selection):
    """JSON-compatible record; the selected pair is kept as identities only."""
    record = asdict(selection)
    record["selected_pair"] = selection.selected_pair_identity
    return record


def consensus_selection_shadow_report(
    candles, *, as_of_index, episode_start_index, episode_end_index,
    inlier_band_atr, separation_atr, **selection_parameters,
):
    """Slice A boundaries -> Slice B pairs -> Slice C selection, beside production."""
    boundary = dict(as_of_index=as_of_index,
                    episode_start_index=episode_start_index,
                    inlier_band_atr=inlier_band_atr, separation_atr=separation_atr)
    selection = select_envelope_pair_shadow(
        candles,
        build_boundary_consensus(candles, side="upper", **boundary),
        build_boundary_consensus(candles, side="lower", **boundary),
        as_of_index=as_of_index, episode_start_index=episode_start_index,
        episode_end_index=episode_end_index, **selection_parameters)
    return shadow_selection_record(selection)
