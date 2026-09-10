"""
signal.quality

Оценка качества торговой структуры.

Отвечает только за:
- классификацию качества сигнала;
- итоговый статус Setup.

Не содержит:
- поиска паттернов;
- Geometry;
- Confirmation;
- Telegram;
- торговых решений.
"""


# ---------------------------------------------------------------------------
# DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md Section 6 — approved
# severity weights and tier-downgrade scale. Initial working defaults, not
# calibrated against historical data yet.
# ---------------------------------------------------------------------------

CONTAINMENT_SEVERITY_WEIGHT_UPPER = 2
CONTAINMENT_SEVERITY_WEIGHT_LOWER_STRICT = 2
CONTAINMENT_SEVERITY_WEIGHT_LOWER_FLEXIBLE = 1

# severity <= this -> 1 downgrade step; <= CONTAINMENT_SEVERITY_TIER_2_MAX ->
# 2 steps; anything above -> 3 steps. severity == 0 -> 0 steps.
CONTAINMENT_SEVERITY_TIER_1_MAX = 2
CONTAINMENT_SEVERITY_TIER_2_MAX = 4

# Low to high; a downgrade moves an index toward 0 and never below it.
_QUALITY_TIER_ORDER = [
    "Weak Setup",
    "Watch",
    "B Setup",
    "A Setup",
    "Elite Setup",
]


def _containment_severity(containment_violations):

    violations = containment_violations or {}

    upper_violations = int(
        violations.get("upper_violations", 0) or 0
    )

    lower_strict_violations = int(
        violations.get("lower_strict_violations", 0) or 0
    )

    lower_flexible_violations = int(
        violations.get("lower_flexible_unrecognized_breaches", 0) or 0
    )

    return (
        CONTAINMENT_SEVERITY_WEIGHT_UPPER * upper_violations
        + CONTAINMENT_SEVERITY_WEIGHT_LOWER_STRICT * lower_strict_violations
        + CONTAINMENT_SEVERITY_WEIGHT_LOWER_FLEXIBLE * lower_flexible_violations
    )


def _containment_downgrade_steps(severity):

    if severity <= 0:
        return 0

    if severity <= CONTAINMENT_SEVERITY_TIER_1_MAX:
        return 1

    if severity <= CONTAINMENT_SEVERITY_TIER_2_MAX:
        return 2

    return 3


def _downgrade_tier(quality_name, steps):

    if steps <= 0 or quality_name not in _QUALITY_TIER_ORDER:
        return quality_name

    index = _QUALITY_TIER_ORDER.index(quality_name)

    return _QUALITY_TIER_ORDER[
        max(0, index - steps)
    ]


def evaluate_quality(
    pattern,
    geometry,
    confirmation,
    score,
    containment_violations=None
):
    """
    Оценивает качество найденной структуры.

    containment_violations (optional): counts from
    wedge/detector.py's features["containment_violations"], per
    DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md. Never blocks
    admission by itself; only downgrades the tier already earned below,
    per the approved severity/downgrade scale. Absent or all-zero counts
    leave the tier unchanged.

    Возвращает:

    {
        "quality": str,
        "reason": str
    }
    """



    if pattern == "No wedge":

        return {

            "quality": "Invalid",

            "reason":
                "Pattern not found"

        }



    if geometry is None:

        return {

            "quality": "Invalid",

            "reason":
                "Missing geometry"

        }



    validation = geometry.get(
        "validation",
        {}
    )


    if not validation.get(
        "valid",
        False
    ):

        return {

            "quality": "Invalid",

            "reason":
                "Geometry validation failed"

        }



    confirmation = confirmation or {}



    breakout = confirmation.get(
        "breakout",
        False
    )


    volume = confirmation.get(
        "volume",
        False
    )


    retest = confirmation.get(
        "retest",
        False
    )


    confirmation_score = confirmation.get(
        "confirmation_score",
        0
    )



    compression = geometry.get(
        "compression",
        {}
    )


    touches = geometry.get(
        "touches",
        {}
    )


    compression_value = compression.get(
        "compression_percent",
        0
    )


    total_touches = touches.get(
        "total_touches",
        0
    )



    # =========================
    # Elite Setup
    # =========================

    if (

        breakout

        and

        volume

        and

        retest

        and

        score >= 85

        and

        confirmation_score >= 25

        and

        total_touches >= 5

    ):

        base_quality = "Elite Setup"

        base_reason = "Strong structure with full confirmation"



    # =========================
    # A Setup
    # =========================

    elif (

        breakout

        and

        score >= 75

        and

        confirmation_score >= 15

    ):

        base_quality = "A Setup"

        base_reason = "Valid structure with breakout confirmation"



    # =========================
    # B Setup
    # =========================

    elif (

        score >= 60

        and

        compression_value >= 15

        and

        total_touches >= 4

    ):

        base_quality = "B Setup"

        base_reason = "Valid structure awaiting confirmation"



    # =========================
    # Watch
    # =========================

    elif score >= 50:

        base_quality = "Watch"

        base_reason = "Structure exists but quality is limited"



    else:

        base_quality = "Weak Setup"

        base_reason = "Insufficient confirmation or structure quality"



    # =========================
    # ATR Containment penalty (soft, tier-downgrade only)
    # =========================

    severity = _containment_severity(containment_violations)

    downgrade_steps = _containment_downgrade_steps(severity)

    if downgrade_steps <= 0:

        return {

            "quality": base_quality,

            "reason": base_reason

        }

    final_quality = _downgrade_tier(
        base_quality,
        downgrade_steps
    )

    return {

        "quality": final_quality,

        "reason":
            f"Downgraded from {base_quality} "
            f"due to containment violations (severity {severity})"

    }
