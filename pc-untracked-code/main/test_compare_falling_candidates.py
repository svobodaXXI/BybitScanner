"""
test_compare_falling_candidates.py

Temporary diagnostic.

ACUUSDT 1m:
visual comparison of Falling Wedge
geometry candidates #1, #2 and #5.

Does not modify:
- production Geometry selection;
- Ranking;
- Validation;
- signals.
"""


import io
import os
from contextlib import redirect_stdout

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd

from analyzer import analyze_symbol
from bybit_api import get_candles

from geometry.candidate import (
    build_candidate_lines
)

from geometry.filter import (
    filter_candidates
)

from geometry.evaluation import (
    evaluate_candidate_pair
)

from geometry.ranking import (
    rank_geometry
)

from geometry.characterization import (
    analyze_characterization
)


SYMBOL = "ACUUSDT"
INTERVAL = "1"
LIMIT = 200

COMPARE_POSITIONS = (
    1,
    2,
    5
)

OUTPUT_DIR = os.path.join(
    "charts",
    "candidate_compare"
)


def prepare_chart_dataframe(
    df
):
    """
    Converts BybitScanner candle DataFrame
    into mplfinance-compatible format.

    Geometry still uses positional indices
    0..N-1. Only chart representation gets
    a DatetimeIndex.
    """

    if df is None or df.empty:
        return None

    required = {
        "time",
        "open",
        "high",
        "low",
        "close"
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:
        raise RuntimeError(
            f"MISSING_CANDLE_COLUMNS: "
            f"{sorted(missing)}"
        )

    chart_df = df.copy()

    chart_df.index = pd.to_datetime(
        chart_df["time"],
        unit="ms",
        errors="coerce"
    )

    chart_df = chart_df[
        ~chart_df.index.isna()
    ].copy()

    chart_df = chart_df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        }
    )

    numeric_columns = [
        "Open",
        "High",
        "Low",
        "Close"
    ]

    if "Volume" in chart_df.columns:
        numeric_columns.append(
            "Volume"
        )

    for column in numeric_columns:

        chart_df[column] = (
            pd.to_numeric(
                chart_df[column],
                errors="coerce"
            )
        )

    chart_df = chart_df.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close"
        ]
    )

    return chart_df


def calculate_line_values(
    line,
    length
):
    """
    Calculate trendline values in the same
    positional coordinate system used by
    Geometry Engine.
    """

    if line is None:
        return None

    slope = line.get(
        "slope"
    )

    intercept = line.get(
        "intercept"
    )

    if (
        slope is None
        or intercept is None
    ):
        return None

    x = np.arange(
        length
    )

    return (
        float(slope)
        * x
        +
        float(intercept)
    )


def collect_falling_candidates(
    highs,
    lows,
    current_index
):
    """
    Evaluate all valid Falling-family pairs.
    """

    upper_candidates = (
        filter_candidates(
            build_candidate_lines(
                highs
            )
        )
    )

    lower_candidates = (
        filter_candidates(
            build_candidate_lines(
                lows
            )
        )
    )

    falling = []

    for upper_candidate in upper_candidates:

        for lower_candidate in lower_candidates:

            geometry = (
                evaluate_candidate_pair(
                    upper_candidate,
                    lower_candidate,
                    highs=highs,
                    lows=lows,
                    current_index=current_index
                )
            )

            if geometry is None:
                continue

            validation = (
                getattr(
                    geometry,
                    "validation",
                    {}
                )
                or {}
            )

            if not validation.get(
                "valid",
                False
            ):
                continue

            characterization = (
                analyze_characterization(
                    geometry.upper_line,
                    geometry.lower_line
                )
            )

            if not characterization:
                continue

            if not (
                characterization.get(
                    "upper_direction"
                ) == "down"
                and
                characterization.get(
                    "lower_direction"
                ) == "down"
            ):
                continue

            geometry_score = (
                rank_geometry(
                    geometry
                )
            )

            falling.append(
                (
                    float(
                        geometry_score
                    ),
                    geometry
                )
            )

    falling.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return falling


def print_candidate_metrics(
    position,
    score,
    geometry
):
    pair = (
        getattr(
            geometry,
            "pair_metrics",
            {}
        )
        or {}
    )

    envelope = (
        getattr(
            geometry,
            "envelope_metrics",
            {}
        )
        or {}
    )

    upper = (
        envelope.get(
            "upper"
        )
        or {}
    )

    lower = (
        envelope.get(
            "lower"
        )
        or {}
    )

    print()
    print(
        "=" * 68
    )

    print(
        f"CANDIDATE #{position}"
    )

    print("UPPER_LINE_RAW:", geometry.upper_line)
    print("LOWER_LINE_RAW:", geometry.lower_line)
    print("PAIR_METRICS_RAW:", pair)
    print("ENVELOPE_RAW:", envelope)

    print(
        "rank:",
        round(
            score,
            2
        )
    )

    print(
        "upper_anchor:",
        geometry.upper_line.get(
            "anchor_index"
        )
    )

    print(
        "lower_anchor:",
        geometry.lower_line.get(
            "anchor_index"
        )
    )

    print(
        "common_start:",
        pair.get(
            "common_start"
        )
    )

    print(
        "common_span:",
        pair.get(
            "common_span"
        )
    )

    print(
        "shared_span:",
        pair.get(
            "shared_structure_span"
        )
    )

    print(
        "anchor_balance:",
        pair.get(
            "anchor_balance"
        )
    )

    print(
        "slope_balance:",
        pair.get(
            "slope_balance"
        )
    )

    print(
        "UPPER:",
        "support=",
        upper.get(
            "support_count"
        ),
        "span=",
        upper.get(
            "support_span"
        ),
        "outside=",
        upper.get(
            "outside_count"
        )
    )

    print(
        "LOWER:",
        "support=",
        lower.get(
            "support_count"
        ),
        "span=",
        lower.get(
            "support_span"
        ),
        "outside=",
        lower.get(
            "outside_count"
        )
    )


def save_candidate_chart(
    chart_df,
    position,
    score,
    geometry
):
    upper_values = (
        calculate_line_values(
            geometry.upper_line,
            len(chart_df)
        )
    )

    lower_values = (
        calculate_line_values(
            geometry.lower_line,
            len(chart_df)
        )
    )

    upper_anchor = geometry.upper_line.get(
        "anchor_index",
        0
    )

    lower_anchor = geometry.lower_line.get(
        "anchor_index",
        0
    )

    upper_values = np.asarray(
        upper_values,
        dtype=float
    )

    lower_values = np.asarray(
        lower_values,
        dtype=float
    )

    upper_values[:max(int(upper_anchor), 0)] = np.nan
    lower_values[:max(int(lower_anchor), 0)] = np.nan


    if (
        upper_values is None
        or lower_values is None
    ):
        raise RuntimeError(
            "INVALID_LINE_VALUES"
        )

    addplots = [
        mpf.make_addplot(
            upper_values,
            width=2
        ),
        mpf.make_addplot(
            lower_values,
            width=2
        )
    ]

    title = (
        f"{SYMBOL} {INTERVAL}m | "
        f"Falling Candidate #{position} | "
        f"Rank {score:.2f}"
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        (
            f"{SYMBOL}_falling_"
            f"candidate_{position}.png"
        )
    )

    volume_enabled = (
        "Volume"
        in chart_df.columns
    )

    fig, axes = mpf.plot(
        chart_df,
        type="candle",
        style="charles",
        addplot=addplots,
        volume=volume_enabled,
        title=title,
        figsize=(14, 8),
        returnfig=True
    )

    fig.savefig(
        output_path,
        dpi=140,
        bbox_inches="tight"
    )

    plt.close(
        fig
    )

    print(
        "saved:",
        output_path
    )


def main():
    #
    # Get pivots through current
    # production analyzer.
    #

    with redirect_stdout(
        io.StringIO()
    ):
        outer = analyze_symbol(
            SYMBOL
        )

    if not isinstance(
        outer,
        dict
    ):
        raise RuntimeError(
            "ANALYZER_RESULT_INVALID"
        )

    highs = (
        outer.get(
            "highs"
        )
        or []
    )

    lows = (
        outer.get(
            "lows"
        )
        or []
    )

    #
    # Load same-size 1m candle window
    # for visualization.
    #

    df = get_candles(
        SYMBOL,
        INTERVAL,
        LIMIT
    )

    if df is None or df.empty:
        raise RuntimeError(
            "NO_CANDLES"
        )

    chart_df = (
        prepare_chart_dataframe(
            df
        )
    )

    if (
        chart_df is None
        or chart_df.empty
    ):
        raise RuntimeError(
            "CHART_DATA_EMPTY"
        )

    current_index = (
        len(df)
        - 1
    )

    raw_lower = build_candidate_lines(lows)
    filtered_lower = filter_candidates(raw_lower)

    print("RAW LOWER:", len(raw_lower))
    print("FILTERED LOWER:", len(filtered_lower))

    print("--- RAW LOWER TOP 20 BY ANCHOR RECENCY ---")
    for c in sorted(raw_lower, key=lambda x: x.get("anchor_index", -1), reverse=True)[:20]:
        line = c.get("line", {})
        print("anchor=", c.get("anchor_index"), "second=", c.get("second_index"), "span=", c.get("structure_span"), "conf=", c.get("confirmations"), "err=", line.get("error_mean"), "slope=", line.get("slope"))

    print("--- FILTERED LOWER ---")
    for c in filtered_lower:
        line = c.get("line", {})
        print("anchor=", c.get("anchor_index"), "second=", c.get("second_index"), "span=", c.get("structure_span"), "conf=", c.get("confirmations"), "err=", line.get("error_mean"), "slope=", line.get("slope"))

    print()
    print("--- RECENT LOWER PAIR DIAGNOSTIC ---")

    diagnostic_upper = filter_candidates(
        build_candidate_lines(highs)
    )

    diagnostic_lower = filter_candidates(
        build_candidate_lines(lows)
    )

    for lower_candidate in diagnostic_lower:

        lower_line = lower_candidate.get(
            "line",
            {}
        )

        lower_anchor = lower_line.get(
            "anchor_index",
            -1
        )

        if lower_anchor < 100:
            continue

        evaluated = 0
        surviving = 0
        falling_surviving = 0
        valid_falling = 0
        failed_counts = {}
        apex_quality_reasons = {}
        apex_quality_examples = {}
        best_valid_score = None
        best_valid_upper_anchor = None
        best_score = None
        best_upper_anchor = None

        for upper_candidate in diagnostic_upper:

            evaluated += 1

            geometry = evaluate_candidate_pair(
                upper_candidate,
                lower_candidate,
                highs=highs,
                lows=lows,
                current_index=current_index
            )

            if geometry is None:
                continue

            surviving += 1

            characterization = analyze_characterization(
                geometry.upper_line,
                geometry.lower_line
            )

            if not characterization:
                continue

            if not (
                characterization.get("upper_direction") == "down"
                and
                characterization.get("lower_direction") == "down"
            ):
                continue

            falling_surviving += 1

            validation = (
                getattr(
                    geometry,
                    "validation",
                    {}
                )
                or {}
            )

            validation_valid = validation.get(
                "valid",
                False
            )

            failed_checks = validation.get(
                "failed_checks",
                []
            ) or []

            if validation_valid:
                valid_falling += 1
            else:
                for failed_check in failed_checks:
                    failed_counts[failed_check] = (
                        failed_counts.get(
                            failed_check,
                            0
                        )
                        + 1
                    )


            apex_quality_check = (
                validation.get("checks", {})
                .get("apex_quality", {})
                or {}
            )

            if not apex_quality_check.get("valid", False):
                aq_reason = apex_quality_check.get(
                    "reason",
                    "UNKNOWN"
                )

                apex_quality_reasons[aq_reason] = (
                    apex_quality_reasons.get(
                        aq_reason,
                        0
                    )
                    + 1
                )

                if aq_reason not in apex_quality_examples:
                    apex_quality_examples[aq_reason] = (
                        apex_quality_check.get(
                            "details",
                            {}
                        )
                    )

            pair_score = rank_geometry(geometry)

            if (
                validation_valid
                and (
                    best_valid_score is None
                    or pair_score > best_valid_score
                )
            ):
                best_valid_score = pair_score
                best_valid_upper_anchor = (
                    geometry.upper_line.get(
                        "anchor_index"
                    )
                )

            if (
                best_score is None
                or pair_score > best_score
            ):
                best_score = pair_score
                best_upper_anchor = geometry.upper_line.get(
                    "anchor_index"
                )

        print(
            "LA=", lower_anchor,
            "L2=", lower_line.get("second_index"),
            "Lslope=", lower_line.get("slope"),
            "tested=", evaluated,
            "survive_eval=", surviving,
            "falling=", falling_surviving,
            "best_score=", (
                round(best_score, 2)
                if best_score is not None
                else None
            ),
            "best_UA=", best_upper_anchor,
            "valid_falling=", valid_falling,
            "failed=", failed_counts,
            "AQ_reasons=", apex_quality_reasons,
            "AQ_examples=", apex_quality_examples,
            "best_valid_score=", (
                round(best_valid_score, 2)
                if best_valid_score is not None
                else None
            ),
            "best_valid_UA=", best_valid_upper_anchor
        )

    print()

    falling = (
        collect_falling_candidates(
            highs,
            lows,
            current_index
        )
    )

    print(
        "FALLING CANDIDATES:",
        len(falling)
    ) 
    print("--- FALLING WITH RECENT LOWER ANCHOR >= 100 ---")

    recent = []

    for rank_pos, (pair_score, g) in enumerate(falling, 1):

        la = g.lower_line.get(
            "anchor_index",
            -1
        )

        if la >= 100:

            recent.append(
                (
                    rank_pos,
                    pair_score,
                    g
                )
            )

    for rank_pos, pair_score, g in recent[:20]:

        pm = getattr(
            g,
            "pair_metrics",
            {}
        ) or {}

        em = getattr(
            g,
            "envelope_metrics",
            {}
        ) or {}

        lo = em.get(
            "lower",
            {}
        ) or {}

        up = em.get(
            "upper",
            {}
        ) or {}

        print(
            "rankpos=", rank_pos,
            "score=", round(pair_score, 2),
            "UA=", g.upper_line.get("anchor_index"),
            "LA=", g.lower_line.get("anchor_index"),
            "L2=", g.lower_line.get("second_index"),
            "Lslope=", g.lower_line.get("slope"),
            "anchor_balance=", pm.get("anchor_balance"),
            "slope_balance=", pm.get("slope_balance"),
            "U_support=", up.get("support_count"),
            "L_support=", lo.get("support_count"),
            "L_span=", lo.get("support_span")
        )

    if (
        len(falling)
        <
        max(COMPARE_POSITIONS)
    ):
        raise RuntimeError(
            "NOT_ENOUGH_FALLING_CANDIDATES"
        )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    for position in COMPARE_POSITIONS:

        score, geometry = (
            falling[
                position - 1
            ]
        )

        print_candidate_metrics(
            position,
            score,
            geometry
        )

        save_candidate_chart(
            chart_df,
            position,
            score,
            geometry
        )


if __name__ == "__main__":
    main()
