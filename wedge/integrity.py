"""
wedge.integrity

Structure Integrity Layer.

ATR containment note (DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md):
`evaluate_containment_violations()` below owns the pattern-aware
interpretation of the direction-neutral raw body-breach data computed in
geometry/envelope_metrics.py:evaluate_body_zone_breaches(). This mirrors
how STRICT/EXCURSION roles are assigned only after the operational
pattern is known (see evaluate_directional_envelope()). Falling Wedge
only; Rising Wedge is a separate, unresolved future task.

Оценивает целостность уже найденной
и валидированной геометрической структуры.

Отвечает только за:
- распределение подтверждений границ;
- протяжённость подтверждений;
- наружные проколы;
- согласованность anchors;
- согласованность движения boundaries.

Не содержит:
- поиска линий;
- Validation;
- классификации паттерна;
- торговых сигналов;
- hard reject.

Version 1:
диагностический soft-score 0..20.
"""

from confirmation import calculate_atr
from geometry.envelope_metrics import ATR_PERIOD
from geometry.reversal_patterns import has_reversal_exception


DIRECTIONAL_BOUNDARY_ROLES = {
    "Falling Wedge": {
        "upper": "STRICT",
        "lower": "EXCURSION"
    },
    "Rising Wedge": {
        "upper": "EXCURSION",
        "lower": "STRICT"
    },
    "Triangle Compression": {
        "upper": "STRICT",
        "lower": "STRICT"
    }
}


def directional_boundary_roles(pattern):
    """Return Wedge-owned boundary roles after pattern determination."""

    roles = DIRECTIONAL_BOUNDARY_ROLES.get(
        pattern,
        {}
    )

    return dict(roles)


def evaluate_directional_envelope(
    geometry,
    pattern
):
    """Interpret existing pivot-envelope metrics without rejecting or scoring."""

    roles = directional_boundary_roles(
        pattern
    )

    envelope_metrics = (
        geometry.get(
            "envelope_metrics"
        )
        or {}
        if isinstance(geometry, dict)
        else {}
    )

    boundaries = {}
    strict_outside_count = 0
    excursion_outside_count = 0

    for side in (
        "upper",
        "lower"
    ):
        metrics = (
            envelope_metrics.get(side)
            or {}
        )
        role = roles.get(
            side,
            "UNASSIGNED"
        )
        outside_count = int(
            metrics.get(
                "outside_count",
                0
            )
            or 0
        )

        boundaries[side] = {
            "role": role,
            "metrics": metrics
        }

        if role == "STRICT":
            strict_outside_count += outside_count
        elif role == "EXCURSION":
            excursion_outside_count += outside_count

    warnings = []

    if strict_outside_count:
        warnings.append(
            "Strict boundary has pivot-envelope excursions"
        )

    if excursion_outside_count:
        warnings.append(
            "Excursion boundary has pivot-envelope excursions"
        )

    return {
        "status": (
            "DIAGNOSTIC"
            if roles
            else "UNAVAILABLE"
        ),
        "evaluation_mode": "DIAGNOSTIC_SOFT",
        "pattern": pattern,
        "boundaries": boundaries,
        "strict_sides": [
            side
            for side, role in roles.items()
            if role == "STRICT"
        ],
        "excursion_sides": [
            side
            for side, role in roles.items()
            if role == "EXCURSION"
        ],
        "strict_outside_count": strict_outside_count,
        "excursion_outside_count": excursion_outside_count,
        "hard_rejection": False,
        "score_effect": 0.0,
        "warnings": warnings
    }


CONTAINMENT_VIOLATION_EVALUATION_ENABLED = False


ZERO_CONTAINMENT_VIOLATIONS = {
    "upper_violations": 0,
    "lower_strict_violations": 0,
    "lower_flexible_unrecognized_breaches": 0,
}


def evaluate_containment_violations(
    geometry,
    pattern,
    candles
):
    """
    Containment violation evaluation is temporarily disabled globally.
    The Falling Wedge implementation below is intentionally preserved
    for future recalibration and re-enable.

    Replaces the previous hard binary containment reject in
    wedge/detector.py:detect_structure() with graded violation counts
    consumed by signal/quality.py as a quality-tier penalty (never a
    detection-blocking gate).

    Rising Wedge and Triangle Compression are not yet covered by this
    decision (explicit non-goal: the mirrored Rising Wedge rule is a
    separate, unresolved future task) and always receive zero violations
    here — this is a real, currently-accepted gap, not an oversight: those
    patterns temporarily have no containment mechanism at all until a
    future mirrored decision is authorized.
    """

    if not CONTAINMENT_VIOLATION_EVALUATION_ENABLED:
        return dict(ZERO_CONTAINMENT_VIOLATIONS)

    if pattern != "Falling Wedge":
        return dict(ZERO_CONTAINMENT_VIOLATIONS)

    envelope_metrics = (
        geometry.get("envelope_metrics")
        or {}
        if isinstance(geometry, dict)
        else {}
    )

    breaches = envelope_metrics.get("body_zone_breaches") or {}

    upper_indices = breaches.get("upper_body_breach_indices") or []
    lower_strict_indices = breaches.get("lower_body_breach_early_indices") or []
    lower_late_indices = breaches.get("lower_body_breach_late_indices") or []

    if candles is None:
        # The upper/lower-strict counts are already resolved index lists
        # from evaluate_body_zone_breaches() and need no further candle
        # lookup. Only the late-zone reversal-pattern exception needs
        # candles; without them, the decision's own default applies — a
        # body breach IS a violation unless a pattern is positively
        # established, so an unverifiable exception counts as a violation
        # rather than being silently excused.
        return {
            "upper_violations": len(upper_indices),
            "lower_strict_violations": len(lower_strict_indices),
            "lower_flexible_unrecognized_breaches": len(lower_late_indices),
            "lower_flexible_excused_indices": [],
        }

    atr_series = None

    if lower_late_indices:
        try:
            atr_series = calculate_atr(candles, period=ATR_PERIOD)
        except Exception:
            atr_series = None

    unrecognized_late_indices = []
    excused_late_indices = []

    for index in lower_late_indices:

        atr_value = None

        if atr_series is not None:
            try:
                candidate = atr_series.iloc[index]
                if candidate == candidate:
                    atr_value = float(candidate)
            except Exception:
                atr_value = None

        if has_reversal_exception(candles, index, atr_value):
            excused_late_indices.append(index)
        else:
            unrecognized_late_indices.append(index)

    return {
        "upper_violations": len(upper_indices),
        "lower_strict_violations": len(lower_strict_indices),
        "lower_flexible_unrecognized_breaches": len(unrecognized_late_indices),
        "lower_flexible_excused_indices": excused_late_indices,
    }


def _clamp(
    value,
    minimum=0.0,
    maximum=1.0
):
    try:
        value = float(value)
    except (
        TypeError,
        ValueError
    ):
        return minimum

    return max(
        minimum,
        min(
            value,
            maximum
        )
    )


def evaluate_integrity(
    geometry
):
    """
    Оценивает целостность структуры.

    Максимум:
        boundary support : 6
        support span     : 6
        outside control  : 3
        anchor balance   : 3
        slope balance    : 2

    Total:
        20

    Hard reject не выполняется.
    """

    if not geometry:

        return {
            "status": "WEAK",
            "score": 0.0,
            "details": {},
            "warnings": [
                "Missing geometry data"
            ]
        }

    pair_metrics = (
        geometry.get(
            "pair_metrics"
        )
        or {}
    )

    envelope_metrics = (
        geometry.get(
            "envelope_metrics"
        )
        or {}
    )

    upper = (
        envelope_metrics.get(
            "upper"
        )
        or {}
    )

    lower = (
        envelope_metrics.get(
            "lower"
        )
        or {}
    )

    common_span = float(
        pair_metrics.get(
            "common_span",
            0
        )
        or 0
    )

    upper_support = int(
        upper.get(
            "support_count",
            0
        )
        or 0
    )

    lower_support = int(
        lower.get(
            "support_count",
            0
        )
        or 0
    )

    upper_span = float(
        upper.get(
            "support_span",
            0
        )
        or 0
    )

    lower_span = float(
        lower.get(
            "support_span",
            0
        )
        or 0
    )

    upper_outside = int(
        upper.get(
            "outside_count",
            0
        )
        or 0
    )

    lower_outside = int(
        lower.get(
            "outside_count",
            0
        )
        or 0
    )

    #
    # 1. Boundary support
    #
    # 2+2 = минимальная структура.
    # Дополнительные подтверждения
    # повышают уверенность постепенно.
    #

    support_score = 0.0

    support_score += min(
        upper_support,
        3
    )

    support_score += min(
        lower_support,
        3
    )

    #
    # 2. Support span
    #
    # Важно не только количество,
    # но и распределение контактов
    # по длине структуры.
    #

    if common_span > 0:

        upper_span_ratio = _clamp(
            upper_span
            /
            common_span
        )

        lower_span_ratio = _clamp(
            lower_span
            /
            common_span
        )

    else:

        upper_span_ratio = 0.0
        lower_span_ratio = 0.0

    span_score = (
        upper_span_ratio
        +
        lower_span_ratio
    ) * 3.0

    #
    # 3. Outside control
    #

    total_outside = (
        upper_outside
        +
        lower_outside
    )

    if total_outside == 0:

        outside_score = 3.0

    elif total_outside == 1:

        outside_score = 2.0

    elif total_outside == 2:

        outside_score = 1.0

    else:

        outside_score = 0.0

    #
    # 4. Anchor balance
    #

    anchor_balance = _clamp(
        pair_metrics.get(
            "anchor_balance",
            0.0
        )
    )

    anchor_score = (
        anchor_balance
        *
        3.0
    )

    #
    # 5. Slope balance
    #

    slope_balance = _clamp(
        pair_metrics.get(
            "slope_balance",
            0.0
        )
    )

    slope_score = (
        slope_balance
        *
        2.0
    )

    total = (
        support_score
        +
        span_score
        +
        outside_score
        +
        anchor_score
        +
        slope_score
    )

    total = round(
        min(
            total,
            20.0
        ),
        2
    )

    warnings = []

    if upper_support <= 2:
        warnings.append(
            "Upper boundary has minimal support"
        )

    if lower_support <= 2:
        warnings.append(
            "Lower boundary has minimal support"
        )

    if upper_span_ratio < 0.35:
        warnings.append(
            "Upper support is poorly distributed"
        )

    if lower_span_ratio < 0.35:
        warnings.append(
            "Lower support is poorly distributed"
        )

    if total_outside >= 3:
        warnings.append(
            "Too many boundary excursions"
        )

    if anchor_balance < 0.40:
        warnings.append(
            "Anchor positions are poorly balanced"
        )

    if total >= 15:

        status = "STRONG"

    elif total >= 10:

        status = "ACCEPTABLE"

    else:

        status = "WEAK"

    return {
        "status":
            status,

        "score":
            total,

        "details":
            {
                "support_score":
                    round(
                        support_score,
                        2
                    ),

                "span_score":
                    round(
                        span_score,
                        2
                    ),

                "outside_score":
                    round(
                        outside_score,
                        2
                    ),

                "anchor_score":
                    round(
                        anchor_score,
                        2
                    ),

                "slope_score":
                    round(
                        slope_score,
                        2
                    ),

                "upper_support":
                    upper_support,

                "lower_support":
                    lower_support,

                "upper_span_ratio":
                    round(
                        upper_span_ratio,
                        3
                    ),

                "lower_span_ratio":
                    round(
                        lower_span_ratio,
                        3
                    ),

                "total_outside":
                    total_outside,

                "anchor_balance":
                    round(
                        anchor_balance,
                        3
                    ),

                "slope_balance":
                    round(
                        slope_balance,
                        3
                    )
            },

        "warnings":
            warnings
    }
