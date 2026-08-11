"""
test_anchor_trendline.py

Diagnostic Anchor-Based Pattern Pairing v4.

Purpose:
- build trendlines through real pivot anchors;
- reject trivial short structures by bar span;
- validate basic Falling Wedge slope geometry;
- evaluate upper/lower boundaries as one structure;
- measure normalized convergence strength;
- compare identical rules on API3USDT and TWTUSDT.

Production code is NOT modified.
"""

from itertools import product


# ============================================================
# SETTINGS
# ============================================================

TOLERANCE_PERCENT = 0.6

MIN_CONFIRMATIONS = 2

MIN_LINE_SPAN = 30

TOP_LINES_PER_SIDE = 20

TOP_OUTPUT_LINES = 10

TOP_OUTPUT_PAIRS = 5


# ============================================================
# TRENDLINE
# ============================================================


def line_value(line, index):
    return (
        line["slope"]
        * index
        + line["intercept"]
    )


def build_anchor_candidates(
    points,
    tolerance_percent=TOLERANCE_PERCENT,
    min_confirmations=MIN_CONFIRMATIONS,
    min_line_span=MIN_LINE_SPAN
):
    """
    Build trendlines through pairs
    of real pivots.

    Candidate requirements:
    - two real anchors;
    - sufficient bar span;
    - enough pivot confirmations.
    """

    candidates = []

    if not points or len(points) < 2:
        return candidates

    for anchor_pos in range(
        len(points) - 1
    ):

        anchor = points[anchor_pos]

        for second_pos in range(
            anchor_pos + 1,
            len(points)
        ):

            second = points[second_pos]

            anchor_span = (
                second["index"]
                - anchor["index"]
            )

            if (
                anchor_span
                < min_line_span
            ):
                continue

            slope = (
                second["price"]
                - anchor["price"]
            ) / anchor_span

            intercept = (
                anchor["price"]
                - slope
                * anchor["index"]
            )

            evaluated_points = points[
                anchor_pos + 1:
            ]

            confirmations = 0
            confirmed_indices = []
            errors_percent = []

            for point in evaluated_points:

                predicted = (
                    slope
                    * point["index"]
                    + intercept
                )

                if predicted == 0:
                    continue

                error_percent = (
                    abs(
                        point["price"]
                        - predicted
                    )
                    / abs(predicted)
                    * 100
                )

                errors_percent.append(
                    error_percent
                )

                if (
                    error_percent
                    <= tolerance_percent
                ):
                    confirmations += 1

                    confirmed_indices.append(
                        point["index"]
                    )

            if (
                confirmations
                < min_confirmations
            ):
                continue

            support_ratio = (
                confirmations
                / len(evaluated_points)
            )

            structure_span = (
                points[-1]["index"]
                - anchor["index"]
            )

            mean_error_percent = (
                sum(errors_percent)
                / len(errors_percent)
                if errors_percent
                else float("inf")
            )

            candidates.append(
                {
                    "anchor_index":
                        anchor["index"],

                    "anchor_price":
                        anchor["price"],

                    "second_index":
                        second["index"],

                    "second_price":
                        second["price"],

                    "anchor_span":
                        anchor_span,

                    "structure_span":
                        structure_span,

                    "slope":
                        slope,

                    "intercept":
                        intercept,

                    "confirmations":
                        confirmations,

                    "evaluated_points":
                        len(evaluated_points),

                    "support_ratio":
                        support_ratio,

                    "mean_error_percent":
                        mean_error_percent,

                    "confirmed_indices":
                        confirmed_indices
                }
            )

    candidates.sort(
        key=lambda item: (
            item["confirmations"],
            item["structure_span"],
            item["anchor_span"],
            item["support_ratio"],
            -item["mean_error_percent"]
        ),
        reverse=True
    )

    return candidates


# ============================================================
# APEX
# ============================================================


def calculate_apex(
    upper,
    lower
):
    denominator = (
        upper["slope"]
        - lower["slope"]
    )

    if abs(denominator) < 1e-12:
        return None

    index = (
        lower["intercept"]
        - upper["intercept"]
    ) / denominator

    price = line_value(
        upper,
        index
    )

    return {
        "index": index,
        "price": price
    }


# ============================================================
# FALLING WEDGE CONTRACT
# ============================================================


def validate_falling_wedge_slopes(
    upper,
    lower
):
    """
    Basic Falling Wedge slope contract.

    Both boundaries descend and
    the upper boundary descends faster:

        upper_slope < lower_slope < 0

    No minimum-angle rule is applied yet.
    """

    upper_slope = upper["slope"]
    lower_slope = lower["slope"]

    if upper_slope >= 0:
        return False

    if lower_slope >= 0:
        return False

    if upper_slope >= lower_slope:
        return False

    return True


# ============================================================
# NORMALIZED SLOPE DIAGNOSTICS
# ============================================================


def calculate_convergence_metrics(
    upper,
    lower,
    common_start,
    current_index
):
    """
    Measure line movement over the common
    observed structure in percentage terms.

    This makes slope strength comparable
    across instruments with different prices.

    No candidate is rejected here.
    """

    common_span = (
        current_index
        - common_start
    )

    if common_span <= 0:
        return None

    upper_start_price = line_value(
        upper,
        common_start
    )

    lower_start_price = line_value(
        lower,
        common_start
    )

    reference_price = (
        upper_start_price
        + lower_start_price
    ) / 2.0

    if reference_price == 0:
        return None

    upper_move_absolute = (
        abs(upper["slope"])
        * common_span
    )

    lower_move_absolute = (
        abs(lower["slope"])
        * common_span
    )

    upper_move_percent = (
        upper_move_absolute
        / abs(reference_price)
        * 100
    )

    lower_move_percent = (
        lower_move_absolute
        / abs(reference_price)
        * 100
    )

    #
    # How different are the two slope
    # magnitudes?
    #
    # 1.0 = equal magnitude.
    # Large values = one boundary is
    # much flatter than the other.
    #

    smaller_move = min(
        upper_move_percent,
        lower_move_percent
    )

    larger_move = max(
        upper_move_percent,
        lower_move_percent
    )

    if smaller_move > 0:

        slope_ratio = (
            larger_move
            / smaller_move
        )

    else:

        slope_ratio = float("inf")

    #
    # Relative convergence component:
    # how much faster the upper line
    # descends than the lower line.
    #

    convergence_delta_percent = (
        upper_move_percent
        - lower_move_percent
    )

    #
    # Diagnostic balance.
    #
    # 1.0 means equal movement magnitude.
    # Values approaching 0 mean one line
    # is nearly horizontal relative to
    # the other.
    #

    if larger_move > 0:

        slope_balance = (
            smaller_move
            / larger_move
        )

    else:

        slope_balance = 0.0

    #
    # Diagnostic convergence strength.
    #
    # This is deliberately NOT added to
    # ranking yet.
    #
    # It combines:
    # - amount of actual convergence;
    # - participation of both boundaries.
    #

    convergence_strength = (
        max(
            convergence_delta_percent,
            0.0
        )
        * slope_balance
    )

    return {
        "reference_price":
            reference_price,

        "upper_move_percent":
            upper_move_percent,

        "lower_move_percent":
            lower_move_percent,

        "slope_ratio":
            slope_ratio,

        "slope_balance":
            slope_balance,

        "convergence_delta_percent":
            convergence_delta_percent,

        "convergence_strength":
            convergence_strength
    }


# ============================================================
# PAIR EVALUATION
# ============================================================


def evaluate_falling_wedge_pair(
    upper,
    lower,
    current_index
):
    """
    Evaluate two anchor-based lines
    as a Falling Wedge.

    Convergence metrics are collected,
    but they do NOT affect score yet.
    """

    if not validate_falling_wedge_slopes(
        upper,
        lower
    ):
        return None

    common_start = max(
        upper["anchor_index"],
        lower["anchor_index"]
    )

    common_span = (
        current_index
        - common_start
    )

    if common_span <= 0:
        return None

    start_upper = line_value(
        upper,
        common_start
    )

    start_lower = line_value(
        lower,
        common_start
    )

    current_upper = line_value(
        upper,
        current_index
    )

    current_lower = line_value(
        lower,
        current_index
    )

    start_width = (
        start_upper
        - start_lower
    )

    current_width = (
        current_upper
        - current_lower
    )

    if start_width <= 0:
        return None

    if current_width <= 0:
        return None

    compression = (
        1.0
        - (
            current_width
            / start_width
        )
    )

    if compression <= 0:
        return None

    apex = calculate_apex(
        upper,
        lower
    )

    if apex is None:
        return None

    apex_distance = (
        apex["index"]
        - current_index
    )

    apex_ratio = (
        apex_distance
        / common_span
        if common_span > 0
        else None
    )

    anchor_distance = abs(
        upper["anchor_index"]
        - lower["anchor_index"]
    )

    anchor_balance = (
        1.0
        - min(
            anchor_distance
            / max(common_span, 1),
            1.0
        )
    )

    total_confirmations = (
        upper["confirmations"]
        + lower["confirmations"]
    )

    average_support_ratio = (
        upper["support_ratio"]
        + lower["support_ratio"]
    ) / 2.0

    average_error = (
        upper["mean_error_percent"]
        + lower["mean_error_percent"]
    ) / 2.0

    shared_structure_span = min(
        upper["structure_span"],
        lower["structure_span"]
    )

    convergence_metrics = (
        calculate_convergence_metrics(
            upper,
            lower,
            common_start,
            current_index
        )
    )

    if convergence_metrics is None:
        return None

    #
    # Existing diagnostic score.
    #
    # IMPORTANT:
    # new convergence metrics below
    # do NOT influence this score.
    #

    score = 0.0

    score += (
        total_confirmations
        * 12.0
    )

    score += (
        average_support_ratio
        * 25.0
    )

    score += (
        min(
            shared_structure_span,
            120
        )
        * 0.30
    )

    score += (
        anchor_balance
        * 20.0
    )

    score += (
        min(
            compression,
            1.0
        )
        * 35.0
    )

    if apex_ratio is not None:

        if (
            0.0
            <= apex_ratio
            <= 1.0
        ):
            score += 30.0

        elif (
            1.0
            < apex_ratio
            <= 2.0
        ):
            score += 15.0

        elif (
            2.0
            < apex_ratio
            <= 3.0
        ):
            score += 5.0

        elif apex_ratio < 0:
            score -= min(
                abs(apex_ratio)
                * 20.0,
                40.0
            )

        else:
            score -= 15.0

    score -= (
        average_error
        * 10.0
    )

    #
    # Angular imbalance penalty
    #

    slope_balance = convergence_metrics[
        "slope_balance"
    ]

    angular_penalty = 0.0

    if slope_balance >= 0.60:

        angular_penalty = 0.0

    elif slope_balance >= 0.25:

        angular_penalty = (
            (0.60 - slope_balance)
            / 0.35
            * 15.0
        )

    elif slope_balance >= 0.10:

        angular_penalty = (
            15.0
            +
            (
                (0.25 - slope_balance)
                / 0.15
                * 20.0
            )
        )

    else:

        angular_penalty = (
            35.0
            +
            (
                (0.10 - slope_balance)
                / 0.10
                * 25.0
            )
        )

        angular_penalty = min(
            angular_penalty,
            60.0
        )

    score -= angular_penalty

    return {
        "score":
            score,

        "upper_anchor":
            upper["anchor_index"],

        "upper_second":
            upper["second_index"],

        "lower_anchor":
            lower["anchor_index"],

        "lower_second":
            lower["second_index"],

        "upper_confirmations":
            upper["confirmations"],

        "lower_confirmations":
            lower["confirmations"],

        "upper_evaluated":
            upper["evaluated_points"],

        "lower_evaluated":
            lower["evaluated_points"],

        "upper_support_ratio":
            upper["support_ratio"],

        "lower_support_ratio":
            lower["support_ratio"],

        "upper_structure_span":
            upper["structure_span"],

        "lower_structure_span":
            lower["structure_span"],

        "shared_structure_span":
            shared_structure_span,

        "common_start":
            common_start,

        "common_span":
            common_span,

        "anchor_distance":
            anchor_distance,

        "anchor_balance":
            anchor_balance,

        "upper_slope":
            upper["slope"],

        "lower_slope":
            lower["slope"],

        "start_width":
            start_width,

        "current_width":
            current_width,

        "compression":
            compression,

        "apex_index":
            apex["index"],

        "apex_price":
            apex["price"],

        "apex_distance":
            apex_distance,

        "apex_ratio":
            apex_ratio,

        "average_error_percent":
            average_error,

        "upper_move_percent":
            convergence_metrics[
                "upper_move_percent"
            ],

        "lower_move_percent":
            convergence_metrics[
                "lower_move_percent"
            ],

        "slope_ratio":
            convergence_metrics[
                "slope_ratio"
            ],

        "slope_balance":
            convergence_metrics[
                "slope_balance"
            ],

        "convergence_delta_percent":
            convergence_metrics[
                "convergence_delta_percent"
            ],

        "convergence_strength":
            convergence_metrics[
                "convergence_strength"
            ]
    }


# ============================================================
# PATTERN PAIRING
# ============================================================


def find_falling_wedge_pairs(
    highs,
    lows,
    current_index,
    top_lines_per_side=TOP_LINES_PER_SIDE
):
    upper_candidates = (
        build_anchor_candidates(
            highs
        )
    )

    lower_candidates = (
        build_anchor_candidates(
            lows
        )
    )

    upper_pool = upper_candidates[
        :top_lines_per_side
    ]

    lower_pool = lower_candidates[
        :top_lines_per_side
    ]

    pairs = []

    for upper, lower in product(
        upper_pool,
        lower_pool
    ):

        pair = (
            evaluate_falling_wedge_pair(
                upper,
                lower,
                current_index
            )
        )

        if pair is not None:
            pairs.append(pair)

    pairs.sort(
        key=lambda item:
            item["score"],
        reverse=True
    )

    return (
        upper_candidates,
        lower_candidates,
        pairs
    )


# ============================================================
# OUTPUT
# ============================================================


def print_line_candidate(
    number,
    line
):
    print(
        f'{number:>2}. '
        f'anchor={line["anchor_index"]} '
        f'second={line["second_index"]} '
        f'slope={line["slope"]:.8f} '
        f'confirmations='
        f'{line["confirmations"]}/'
        f'{line["evaluated_points"]} '
        f'support='
        f'{line["support_ratio"]:.3f} '
        f'anchor_span='
        f'{line["anchor_span"]} '
        f'structure_span='
        f'{line["structure_span"]} '
        f'error='
        f'{line["mean_error_percent"]:.3f}%'
    )


def print_pair(
    number,
    pair
):
    print()

    print(
        f"PAIR #{number}"
    )

    print(
        f'score='
        f'{pair["score"]:.2f}'
    )

    print(
        f'upper='
        f'{pair["upper_anchor"]}'
        f' -> '
        f'{pair["upper_second"]}'
        f' '
        f'slope='
        f'{pair["upper_slope"]:.8f}'
    )

    print(
        f'lower='
        f'{pair["lower_anchor"]}'
        f' -> '
        f'{pair["lower_second"]}'
        f' '
        f'slope='
        f'{pair["lower_slope"]:.8f}'
    )

    print(
        f'confirmations='
        f'{pair["upper_confirmations"]}'
        f'/'
        f'{pair["upper_evaluated"]}'
        f' + '
        f'{pair["lower_confirmations"]}'
        f'/'
        f'{pair["lower_evaluated"]}'
    )

    print(
        f'shared_structure_span='
        f'{pair["shared_structure_span"]}'
    )

    print(
        f'common_span='
        f'{pair["common_span"]}'
    )

    print(
        f'anchor_distance='
        f'{pair["anchor_distance"]}'
    )

    print(
        f'compression='
        f'{pair["compression"]:.3f}'
    )

    print(
        f'apex_index='
        f'{pair["apex_index"]:.2f}'
    )

    print(
        f'apex_distance='
        f'{pair["apex_distance"]:.2f}'
    )

    print(
        f'apex_ratio='
        f'{pair["apex_ratio"]:.3f}'
    )

    print(
        f'average_error='
        f'{pair["average_error_percent"]:.3f}%'
    )

    print(
        f'upper_move='
        f'{pair["upper_move_percent"]:.3f}%'
    )

    print(
        f'lower_move='
        f'{pair["lower_move_percent"]:.3f}%'
    )

    print(
        f'slope_ratio='
        f'{pair["slope_ratio"]:.3f}'
    )

    print(
        f'slope_balance='
        f'{pair["slope_balance"]:.3f}'
    )

    print(
        f'convergence_delta='
        f'{pair["convergence_delta_percent"]:.3f}%'
    )

    print(
        f'convergence_strength='
        f'{pair["convergence_strength"]:.3f}'
    )


def run_reference(
    symbol,
    highs,
    lows,
    current_index
):
    (
        upper_candidates,
        lower_candidates,
        pattern_pairs
    ) = find_falling_wedge_pairs(
        highs,
        lows,
        current_index
    )

    print()
    print("=" * 70)
    print(
        f"{symbol} TOP ANCHOR UPPER LINES"
    )
    print("=" * 70)

    if not upper_candidates:
        print(
            "No upper candidates."
        )

    else:
        for number, line in enumerate(
            upper_candidates[
                :TOP_OUTPUT_LINES
            ],
            start=1
        ):
            print_line_candidate(
                number,
                line
            )

    print()
    print("=" * 70)
    print(
        f"{symbol} TOP ANCHOR LOWER LINES"
    )
    print("=" * 70)

    if not lower_candidates:
        print(
            "No lower candidates."
        )

    else:
        for number, line in enumerate(
            lower_candidates[
                :TOP_OUTPUT_LINES
            ],
            start=1
        ):
            print_line_candidate(
                number,
                line
            )

    print()
    print("=" * 70)
    print(
        f"{symbol} FALLING WEDGE PAIRS"
    )
    print("=" * 70)

    if not pattern_pairs:
        print(
            "No valid Falling Wedge pairs."
        )

    else:
        for number, pair in enumerate(
            pattern_pairs[
                :TOP_OUTPUT_PAIRS
            ],
            start=1
        ):
            print_pair(
                number,
                pair
            )


# ============================================================
# REFERENCE DATA
# ============================================================


API3_HIGHS = [
    {"index": 13, "price": 0.1929},
    {"index": 85, "price": 0.1957},
    {"index": 97, "price": 0.2004},
    {"index": 103, "price": 0.2032},
    {"index": 114, "price": 0.1995},
    {"index": 153, "price": 0.1935},
    {"index": 171, "price": 0.1925},
    {"index": 195, "price": 0.1898},
]


API3_LOWS = [
    {"index": 6, "price": 0.1925},
    {"index": 64, "price": 0.1913},
    {"index": 112, "price": 0.1963},
    {"index": 123, "price": 0.1969},
    {"index": 138, "price": 0.1938},
    {"index": 147, "price": 0.1924},
    {"index": 159, "price": 0.1917},
    {"index": 169, "price": 0.1910},
    {"index": 181, "price": 0.1878},
    {"index": 187, "price": 0.1864},
]


TWT_HIGHS = [
    {"index": 44, "price": 0.3772},
    {"index": 110, "price": 0.3913},
    {"index": 123, "price": 0.3957},
    {"index": 157, "price": 0.3934},
    {"index": 168, "price": 0.3920},
    {"index": 193, "price": 0.3940},
]


TWT_LOWS = [
    {"index": 20, "price": 0.3765},
    {"index": 48, "price": 0.3751},
    {"index": 112, "price": 0.3875},
    {"index": 116, "price": 0.3891},
    {"index": 130, "price": 0.3913},
    {"index": 140, "price": 0.3928},
    {"index": 153, "price": 0.3890},
    {"index": 176, "price": 0.3878},
]


# ============================================================
# RUN
# ============================================================


if __name__ == "__main__":

    current_index = 199

    run_reference(
        "API3USDT",
        API3_HIGHS,
        API3_LOWS,
        current_index
    )

    run_reference(
        "TWTUSDT",
        TWT_HIGHS,
        TWT_LOWS,
        current_index
    )