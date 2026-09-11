"""
geometry.validation.touches

Проверка подтверждений линий.

Validation Engine v2:

Возвращает диагностический результат,
а не только True/False.
"""


def validate_touches(
    touches
):
    """
    Проверяет минимальное количество
    подтверждений трендовых линий.

    Условия:

    - данные касаний должны существовать;
    - верхняя линия должна иметь минимум
      2 подтверждения;
    - нижняя линия должна иметь минимум
      2 подтверждения.

    Возвращает:

    {
        "valid": bool,
        "reason": str,
        "details": dict
    }

    CR-SCANNER-GEOMETRY-002: the touch count threshold (>= 2 per side) is
    unchanged — this function does not own tolerance (geometry/touches.py
    does, via ATR-normalized touch_tolerance/violation_tolerance). The
    `details` dict additionally passes through the outlier/violation
    diagnostic counts from `touches` when present, for observability only;
    the valid/reason contract itself is unaffected.
    """


    if touches is None:

        return {

            "valid":
                False,

            "reason":
                "Missing touches data",

            "details":
                {}

        }


    upper_touches = int(
        touches.get(
            "upper_touches",
            0
        )
    )


    lower_touches = int(
        touches.get(
            "lower_touches",
            0
        )
    )


    total_touches = int(
        touches.get(
            "total_touches",
            upper_touches + lower_touches
        )
    )


    details = {

        "upper_touches":
            upper_touches,

        "lower_touches":
            lower_touches,

        "total_touches":
            total_touches,

        # Additive (CR-SCANNER-GEOMETRY-002): diagnostic only, does not
        # affect the valid/reason contract below.

        "upper_outlier_count":
            int(
                touches.get(
                    "upper_outlier_count",
                    0
                )
                or 0
            ),

        "lower_outlier_count":
            int(
                touches.get(
                    "lower_outlier_count",
                    0
                )
                or 0
            ),

        "upper_violation_count":
            int(
                touches.get(
                    "upper_violation_count",
                    0
                )
                or 0
            ),

        "lower_violation_count":
            int(
                touches.get(
                    "lower_violation_count",
                    0
                )
                or 0
            ),

    }


    if upper_touches < 2:

        return {

            "valid":
                False,

            "reason":
                "Not enough upper line touches",

            "details":
                details

        }


    if lower_touches < 2:

        return {

            "valid":
                False,

            "reason":
                "Not enough lower line touches",

            "details":
                details

        }


    return {

        "valid":
            True,

        "reason":
            "Touch confirmation acceptable",

        "details":
            details

    }
