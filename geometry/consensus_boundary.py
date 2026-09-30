"""GEO-U1 Slice A: deterministic, boundary-only SHADOW diagnostics.

No production caller imports this module. No envelope, classifier or selector
is changed. Callers explicitly supply a local episode and experimental ATR
bands; these are report parameters, not calibrated production thresholds.
"""

from dataclasses import asdict, dataclass
from itertools import combinations
from math import fsum, isfinite
from typing import NamedTuple

from pivots import find_pivots
from .engine import GEOMETRY_MAX_BODY_BREACH_RUN
from .envelope_metrics import evaluate_formation_body_fit
from .pair_metrics import line_value
from .touches import _atr_series, _atr_value_at


class BoundaryQuality(NamedTuple):
    """Descending lexicographic evidence, never a weighted aggregate score."""

    body_integrity: bool
    distinct_touches: int
    support_coverage: float
    support_span: int
    negative_mean_residual: float
    negative_max_residual: float
    negative_excursion_count: int


@dataclass(frozen=True)
class BoundaryConsensus:
    side: str
    seed_anchor_indices: tuple[int, int]
    slope: float
    intercept: float
    inlier_pivot_indices: tuple[int, ...]
    touch_cluster_indices: tuple[tuple[int, ...], ...]
    touch_count_distinct: int
    support_span: int
    support_coverage_ratio: float
    mean_residual_atr: float
    max_residual_atr: float
    first_supported_pivot: int
    last_supported_pivot: int
    excursion_pivot_indices: tuple[int, ...]
    body_breach_runs: tuple[tuple[int, int], ...]
    max_consecutive_body_breaches: int
    body_integrity: bool
    quality_tuple: BoundaryQuality


def _historical_frame(candles, as_of_index, episode_start_index):
    if (type(as_of_index) is not int or type(episode_start_index) is not int
            or not 0 <= episode_start_index <= as_of_index < len(candles)):
        raise ValueError("episode/cutoff must be valid positional candle indices")
    # Slice BEFORE pivot discovery, ATR and validation. Future rows are unread.
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


def _seed_pairs(points):
    """All chronological same-side pairs; no pattern-specific slope gate."""
    return combinations(points, 2)


def _refit(points):
    """One centered OLS fit in canonical index order, using every inlier."""
    mean_x = fsum(p["index"] for p in points) / len(points)
    mean_y = fsum(p["price"] for p in points) / len(points)
    denominator = fsum((p["index"] - mean_x) ** 2 for p in points)
    slope = fsum((p["index"] - mean_x) * (p["price"] - mean_y)
                 for p in points) / denominator
    return {"slope": slope, "intercept": mean_y - slope * mean_x}


def _touch_clusters(indices, line, frame, atr, side, separation_atr):
    """Merge contacts until an intervening body retreats inward and returns.

    Distance uses the current ATR and fitted line at each intervening bar.
    Require the WHOLE body to move away (upper: body-high below resistance;
    lower: body-low above support). A wick poke or time gap alone is not a
    retest. The reset band must be wider than the inlier band (validated by
    the caller). This deliberately measures price separation, not bar counts.
    """
    clusters = [[indices[0]]]
    sign = 1 if side == "upper" else -1
    body = frame[["open", "close"]].max(axis=1) if side == "upper" else (
        frame[["open", "close"]].min(axis=1)
    )
    for previous, current in zip(indices, indices[1:]):
        separated = any(
            atr[index] is not None
            and sign * (line_value(line, index) - float(body.iloc[index]))
            > separation_atr * atr[index]
            for index in range(previous + 1, current)
        )
        if separated:
            clusters.append([])
        clusters[-1].append(current)
    return tuple(tuple(cluster) for cluster in clusters)


def build_boundary_consensus(
    candles, *, side, as_of_index, episode_start_index,
    inlier_band_atr, separation_atr,
):
    """Return immutable, strongest-first shadow boundaries for one side.

    Pivots use unchanged find_pivots defaults (including right confirmation and
    min_change) on the historical prefix. ATR(14) is the existing touches ATR;
    warm-up/zero-ATR pivots cannot supply ATR-normalized evidence and are skipped.
    Seeds lie inside the caller's explicit episode. OLS uses all seed inliers,
    once; if refit moves any member outside the band the seed is discarded,
    rather than silently claiming unsupported inliers or iterating to a fit.

    Equivalent inlier sets share one result with the lexicographically earliest
    seed. Quality ties use seed indices then inlier indices, independent of
    enumeration order. Residuals are measured on the FINAL line; excursions
    are outward non-inlier pivots inside its support interval. Body runs reuse
    the existing formation-body evaluator on first..last support, never after
    END. Body-invalid diagnostics remain visible with body_integrity=False;
    this function does not admit any production formation.
    """
    if side not in ("upper", "lower"):
        raise ValueError("side must be upper or lower")
    if (not isfinite(inlier_band_atr) or not isfinite(separation_atr)
            or not 0 < inlier_band_atr < separation_atr):
        raise ValueError("require finite 0 < inlier_band_atr < separation_atr")
    frame = _historical_frame(candles, as_of_index, episode_start_index)
    highs, lows = find_pivots(frame.copy(deep=True))
    series = _atr_series(frame)
    atr = [_atr_value_at(series, i) for i in range(len(frame))]
    atr = [v if v is not None and isfinite(v) and v > 0 else None for v in atr]
    points = sorted(
        (p for p in (highs if side == "upper" else lows)
         if p["index"] >= episode_start_index and atr[p["index"]] is not None),
        key=lambda p: p["index"],
    )
    by_support = {}
    sign = 1 if side == "upper" else -1
    for first, second in _seed_pairs(points):
        seed = (int(first["index"]), int(second["index"]))
        slope = (second["price"] - first["price"]) / (seed[1] - seed[0])
        seed_line = {"slope": slope, "intercept": first["price"] - slope * seed[0]}
        inliers = tuple(p for p in points if
                        abs(p["price"] - line_value(seed_line, p["index"]))
                        / atr[p["index"]] <= inlier_band_atr)
        if len(inliers) < 2:
            continue
        indices = tuple(int(p["index"]) for p in inliers)
        prior = by_support.get(indices)
        if prior is not None and prior.seed_anchor_indices <= seed:
            continue
        line = _refit(inliers)
        residuals = tuple(abs(p["price"] - line_value(line, p["index"]))
                          / atr[p["index"]] for p in inliers)
        if (not all(isfinite(v) for v in (*line.values(), *residuals))
                or max(residuals) > inlier_band_atr
                or min(line_value(line, i) for i in (indices[0], indices[-1])) <= 0):
            continue
        clusters = _touch_clusters(indices, line, frame, atr, side, separation_atr)
        span = indices[-1] - indices[0]
        coverage = span / max(1, as_of_index - episode_start_index)
        mean_residual = fsum(residuals) / len(residuals)
        excursions = tuple(int(p["index"]) for p in points
                           if indices[0] <= p["index"] <= indices[-1]
                           and sign * (p["price"] - line_value(line, p["index"]))
                           / atr[p["index"]] > inlier_band_atr)
        # The existing evaluator accepts two lines; only the requested side's
        # independent result is used. No upper/lower pair is constructed here.
        line["anchor_index"] = indices[0]
        body = evaluate_formation_body_fit(line, line, frame, indices[-1])[side]
        body_integrity = body["max_consecutive_breaches"] < GEOMETRY_MAX_BODY_BREACH_RUN
        quality = BoundaryQuality(
            body_integrity, len(clusters), coverage, span,
            -mean_residual, -max(residuals), -len(excursions),
        )
        by_support[indices] = BoundaryConsensus(
            side=side, seed_anchor_indices=seed,
            slope=line["slope"], intercept=line["intercept"],
            inlier_pivot_indices=indices, touch_cluster_indices=clusters,
            touch_count_distinct=len(clusters), support_span=span,
            support_coverage_ratio=coverage, mean_residual_atr=mean_residual,
            max_residual_atr=max(residuals), first_supported_pivot=indices[0],
            last_supported_pivot=indices[-1], excursion_pivot_indices=excursions,
            body_breach_runs=tuple(tuple(run) for run in body["breach_runs"]),
            max_consecutive_body_breaches=body["max_consecutive_breaches"],
            body_integrity=body_integrity, quality_tuple=quality,
        )
    return tuple(sorted(by_support.values(), key=lambda item: (
        tuple(-value for value in item.quality_tuple),
        item.seed_anchor_indices, item.inlier_pivot_indices,
    )))


def boundary_consensus_report(candles, **parameters):
    """JSON-compatible diagnostics to run BESIDE an unchanged production result.

    Requires the same explicit episode/cutoff/bands as build_boundary_consensus.
    Does not call or modify the current winner/selector. No runtime opt-in flag
    is added; the test/report caller invokes this helper explicitly.
    """
    return {
        "mode": "SHADOW_ONLY",
        "parameters": dict(parameters),
        "quality_fields": BoundaryQuality._fields,
        **{side: [asdict(item) for item in build_boundary_consensus(
            candles, side=side, **parameters,
        )] for side in ("upper", "lower")},
    }
