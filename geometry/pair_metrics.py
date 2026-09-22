"""
geometry.pair_metrics

Диагностические метрики пары
upper / lower geometry candidates.

Модуль только измеряет свойства пары.

Не отвечает за:
- Validation Gate;
- Geometry Ranking;
- Pattern classification;
- trading Score;
- signals.
"""


from .compression import calculate_compression


def line_value(
    line,
    index
):
    """
    Возвращает значение линии
    в указанном индексе.
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

    return (
        float(slope)
        * float(index)
        + float(intercept)
    )


def calculate_convergence_metrics(
    upper,
    lower,
    common_start,
    current_index
):
    """
    Измеряет движение upper/lower линий
    на общем наблюдаемом участке.

    Все движения нормализуются
    относительно цены инструмента.

    Никаких reject или ranking
    здесь не выполняется.
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

    if (
        upper_start_price is None
        or lower_start_price is None
    ):
        return None

    reference_price = (
        upper_start_price
        + lower_start_price
    ) / 2.0

    if reference_price == 0:
        return None

    upper_move_absolute = (
        abs(
            upper["slope"]
        )
        * common_span
    )

    lower_move_absolute = (
        abs(
            lower["slope"]
        )
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

    convergence_delta_percent = (
        upper_move_percent
        - lower_move_percent
    )

    if larger_move > 0:

        slope_balance = (
            smaller_move
            / larger_move
        )

    else:

        slope_balance = 0.0

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


def _is_leg_extreme(
    side,
    price,
    origin_index,
    end_index,
    candles,
    same_points,
    end_price=None
):
    """
    True when `price` is the most extreme `side` price in the leg
    origin_index < index <= end_index. Uses candle highs/lows when
    available, otherwise the confirmed same-side pivots plus the
    second anchor's own price: its bar traded at least there, so an
    opposite-side pivot beyond `price` also means the leg passed it.
    """

    if candles is not None:

        try:
            values = [
                float(value)
                for value in candles[side].iloc[
                    origin_index + 1:end_index + 1
                ]
            ]
        except Exception:
            return False

    else:

        values = [
            float(point["price"])
            for point in (same_points or [])
            if (
                isinstance(point, dict)
                and point.get("index") is not None
                and point.get("price") is not None
                and origin_index < point["index"] <= end_index
            )
        ]

        if end_price is not None:
            values.append(float(end_price))

    if side == "high":
        return all(value <= price for value in values)

    return all(value >= price for value in values)


def calculate_pair_metrics(
    upper_candidate,
    lower_candidate,
    current_index,
    highs=None,
    lows=None,
    candles=None
):
    """
    Собирает диагностические
    pair-level метрики.

    Метрики сходимости берутся
    из production compression engine.

    Не выполняет hard reject,
    кроме невозможности корректно
    вычислить сам набор метрик.
    """

    if (
        upper_candidate is None
        or lower_candidate is None
        or current_index is None
    ):
        return None

    upper_line = upper_candidate.get(
        "line"
    )

    lower_line = lower_candidate.get(
        "line"
    )

    if (
        upper_line is None
        or lower_line is None
    ):
        return None

    upper_anchor = upper_line.get(
        "anchor_index"
    )

    lower_anchor = lower_line.get(
        "anchor_index"
    )

    if (
        upper_anchor is None
        or lower_anchor is None
    ):
        return None

    common_start = max(
        upper_anchor,
        lower_anchor
    )

    common_span = (
        current_index
        - common_start
    )

    if common_span <= 0:
        return None

    anchor_distance = abs(
        upper_anchor
        - lower_anchor
    )

    anchor_balance = (
        1.0
        - min(
            anchor_distance
            / max(
                common_span,
                1
            ),
            1.0
        )
    )

    upper_structure_span = (
        upper_line.get(
            "structure_span",
            0
        )
    )

    lower_structure_span = (
        lower_line.get(
            "structure_span",
            0
        )
    )

    shared_structure_span = min(
        upper_structure_span,
        lower_structure_span
    )

    pair_compression = calculate_compression(
        upper_line,
        lower_line,
        common_start,
        current_index
    )

    if pair_compression is None:
        return None

    signed_start_width = (
        line_value(
            upper_line,
            common_start
        )
        -
        line_value(
            lower_line,
            common_start
        )
    )

    signed_current_width = (
        line_value(
            upper_line,
            current_index
        )
        -
        line_value(
            lower_line,
            current_index
        )
    )

    boundary_order_valid = (
        signed_start_width > 0
        and signed_current_width > 0
    )

    boundary_crossed = (
        signed_start_width > 0
        and signed_current_width <= 0
    )

    true_converging = (
        boundary_order_valid
        and signed_current_width
        < signed_start_width
    )

    convergence_metrics = (
        calculate_convergence_metrics(
            upper_line,
            lower_line,
            common_start,
            current_index
        )
    )

    if convergence_metrics is None:
        return None

    #
    # Anchor Sequence
    #

    upper_slope = upper_line.get(
        "slope",
        0
    )

    lower_slope = lower_line.get(
        "slope",
        0
    )

    anchor_family = "unknown"
    primary_anchor = None
    secondary_anchor = None
    expected_secondary_index = None
    sequence_valid = False

    if (
        upper_slope > 0
        and lower_slope > 0
    ):

        anchor_family = "rising"

    elif (
        upper_slope < 0
        and lower_slope < 0
    ):

        anchor_family = "falling"

    elif (
        upper_slope < 0
        and lower_slope > 0
    ):

        anchor_family = "triangle"

        sequence_valid = True

    if anchor_family in (
        "rising",
        "falling"
    ):

        #
        # Universal wedge anchor rule (owner authority; see
        # DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md): the first
        # anchor is the extreme ending the preceding directional
        # impulse, the second anchor is the next meaningful, confirmed
        # pivot on the opposite side of that SAME local episode.
        # Rising vs falling shape must never decide which anchor came
        # first -- only the anchors' own chronological order does.
        #

        opposite_points = []
        same_points = []
        primary_side = None
        primary_price = None
        secondary_price = None

        if upper_anchor < lower_anchor:

            # Preceding impulse UP: terminal HIGH (upper anchor) first,
            # next confirmed LOW (lower anchor) second.

            primary_anchor = upper_anchor
            secondary_anchor = lower_anchor
            opposite_points = lows
            same_points = highs
            primary_side = "high"
            primary_price = upper_line.get("anchor_price")
            secondary_price = lower_line.get("anchor_price")

        elif lower_anchor < upper_anchor:

            # Preceding impulse DOWN: terminal LOW (lower anchor)
            # first, next confirmed HIGH (upper anchor) second.

            primary_anchor = lower_anchor
            secondary_anchor = upper_anchor
            opposite_points = highs
            same_points = lows
            primary_side = "low"
            primary_price = lower_line.get("anchor_price")
            secondary_price = upper_line.get("anchor_price")

        # Equal anchor indices: no chronological first anchor exists;
        # primary_anchor stays None and the pair fails below.

        if primary_anchor is not None:

            next_opposite = sorted(
                point["index"]
                for point in (opposite_points or [])
                if (
                    isinstance(point, dict)
                    and point.get("index") is not None
                    and point["index"] > primary_anchor
                )
            )

            expected_secondary_index = (
                next_opposite[0]
                if next_opposite
                else None
            )

        # The second anchor must be the immediate next confirmed
        # opposite-side pivot after the first anchor -- not merely any
        # later opposite-side pivot skipped forward to from a
        # different, later episode.

        # The first anchor must END the preceding impulse: the impulse leg
        # starts at the last confirmed opposite-side pivot before it and
        # reverses into the second anchor, so no price on the first
        # anchor's side within that leg may exceed it. Strict price
        # comparison only -- no new threshold. Without a confirmed origin
        # the impulse is not established and the pair fails closed.
        # NOT covered: whether that leg is the directional impulse or only
        # a counter-trend swing (e.g. a lower high after a higher peak);
        # separating them needs an owner-defined swing criterion.

        impulse_origin_index = None
        first_anchor_terminal = False

        if (
            primary_anchor is not None
            and secondary_anchor is not None
            and primary_price is not None
        ):

            earlier_opposite = [
                point["index"]
                for point in (opposite_points or [])
                if (
                    isinstance(point, dict)
                    and point.get("index") is not None
                    and point["index"] < primary_anchor
                )
            ]

            if earlier_opposite:

                impulse_origin_index = max(earlier_opposite)

                first_anchor_terminal = _is_leg_extreme(
                    primary_side,
                    float(primary_price),
                    impulse_origin_index,
                    secondary_anchor,
                    candles,
                    same_points,
                    end_price=secondary_price
                )

        # Owner criterion for first anchor A (second anchor B, C = the next
        # confirmed pivot on A's side after B):
        #     abs(P[C] - P[B]) < abs(P[B] - P[A])
        # i.e. the second wave B->C is shorter than the first wave A->B.
        # This compares wave lengths only; it is NOT a ban on C passing
        # A's price (whether A ended the impulse is the separate
        # first_anchor_terminal check above). Otherwise A did
        # not end the impulse and is the wrong start; other pairs in the
        # pool are still evaluated under the same rule. Unconfirmed C:
        # the wedge is not confirmed.

        third_pivot_index = None
        swing_contraction_valid = False

        if (
            secondary_anchor is not None
            and primary_price is not None
            and secondary_price is not None
        ):

            later_same = sorted(
                (point["index"], float(point["price"]))
                for point in (same_points or [])
                if (
                    isinstance(point, dict)
                    and point.get("index") is not None
                    and point.get("price") is not None
                    and point["index"] > secondary_anchor
                )
            )

            if later_same:

                third_pivot_index, third_price = later_same[0]

                swing_contraction_valid = (
                    abs(third_price - float(secondary_price))
                    < abs(float(secondary_price) - float(primary_price))
                )

        sequence_valid = (
            secondary_anchor is not None
            and secondary_anchor
            == expected_secondary_index
            and first_anchor_terminal
            and swing_contraction_valid
        )

    else:

        impulse_origin_index = None
        first_anchor_terminal = None
        third_pivot_index = None
        swing_contraction_valid = None

    anchor_sequence = {
        "family":
            anchor_family,

        "primary_anchor":
            primary_anchor,

        "secondary_anchor":
            secondary_anchor,

        "expected_secondary_index":
            expected_secondary_index,

        "impulse_origin_index":
            impulse_origin_index,

        "first_anchor_terminal":
            first_anchor_terminal,

        "third_pivot_index":
            third_pivot_index,

        "swing_contraction_valid":
            swing_contraction_valid,

        "valid":
            sequence_valid
    }

    return {
        "common_start":
            common_start,

        "common_span":
            common_span,

        "anchor_distance":
            anchor_distance,

        "anchor_balance":
            anchor_balance,

        "shared_structure_span":
            shared_structure_span,

        "start_width":
            pair_compression.get(
                "start_width"
            ),

        "current_width":
            pair_compression.get(
                "end_width"
            ),

        "compression_percent":
            pair_compression.get(
                "compression_percent"
            ),

        "is_converging":
            pair_compression.get(
                "is_compressing",
                False
            ),

        "signed_start_width":
            signed_start_width,

        "signed_current_width":
            signed_current_width,

        "boundary_order_valid":
            boundary_order_valid,

        "boundary_crossed":
            boundary_crossed,

        "true_converging":
            true_converging,

        "anchor_sequence":
            anchor_sequence,

        **convergence_metrics
    }