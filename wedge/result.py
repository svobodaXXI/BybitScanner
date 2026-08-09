"""
wedge.result

Единый формат результата анализа клина.

Отвечает только за структуру данных.

Не содержит:

- математики;
- классификации;
- скоринга;
- торговой логики.

Версия:

- Geometry-first result format
- Legacy geometry compatibility
"""


def create_result(
    pattern="No wedge",
    reason="",
    score=0,
    geometry=None,
    validation=None,
    quality=None,
    warnings=None
):
    """
    Создаёт единый результат Wedge Layer.
    """

    return {
        "pattern": pattern,

        "reason": reason,

        "score": score,

        "geometry": geometry,

        "geometry_version": "v2",

        "validation": validation,

        "quality": (
            quality
            or
            {
                "status": "UNKNOWN"
            }
        ),

        "warnings": (
            warnings
            or
            []
        ),

        "score_breakdown": {}
    }


def attach_legacy_geometry(
    result,
    geometry
):
    """
    Добавляет legacy geometry fields
    для совместимости со старым
    форматом Wedge Result.

    Источником данных остаётся
    GeometryModel / его dict-представление.
    """

    if not isinstance(result, dict):
        return result

    if not isinstance(geometry, dict):
        return result

    upper_line = geometry.get(
        "upper_line",
        {}
    )

    lower_line = geometry.get(
        "lower_line",
        {}
    )

    compression = geometry.get(
        "compression",
        {}
    )

    touches = geometry.get(
        "touches",
        {}
    )

    if not isinstance(upper_line, dict):
        upper_line = {}

    if not isinstance(lower_line, dict):
        lower_line = {}

    if not isinstance(compression, dict):
        compression = {}

    if not isinstance(touches, dict):
        touches = {}

    result["high_slope"] = upper_line.get(
        "slope"
    )

    result["high_intercept"] = upper_line.get(
        "intercept"
    )

    result["low_slope"] = lower_line.get(
        "slope"
    )

    result["low_intercept"] = lower_line.get(
        "intercept"
    )

    result["compression"] = compression

    result["high_touches"] = touches.get(
        "upper_touches",
        0
    )

    result["low_touches"] = touches.get(
        "lower_touches",
        0
    )

    return result