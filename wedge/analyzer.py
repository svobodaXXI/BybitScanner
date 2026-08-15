"""
wedge.analyzer

Главный координатор анализа структуры.

Соединяет:

Pivot точки
    ↓
Geometry Engine
    ↓
Detector
    ↓
Quality
    ↓
Classifier
    ↓
Scoring
    ↓
Result


Не содержит:
- своей математики;
- расчёта линий;
- поиска Pivot;
- определения типа структуры.


Architecture v2.4:

GeometryModel
    ↓
Detector
    ↓
Classifier
    ↓
Quality
    ↓
Score
    ↓
Result
"""


from geometry.engine import analyze_geometry


from .detector import detect_structure


from .result import (
    create_result,
    attach_legacy_geometry
)


from .classifier import classify_structure


from .quality import evaluate_quality


from .scoring import calculate_score
from .potential import calculate_potential_move



def _normalize_geometry(
    geometry
):
    """
    Приводит GeometryModel
    или dict к единому формату.

    Внутри Wedge Layer
    используется только dict-представление.

    Источник истины:

    GeometryModel
    """

    if geometry is None:

        return None

    if hasattr(
        geometry,
        "to_dict"
    ):

        return geometry.to_dict()

    if isinstance(
        geometry,
        dict
    ):

        return geometry

    return None



def analyze_wedge(
    highs,
    lows,
    current_index=None,
    candles=None
):
    """
    Полный анализ структуры.
    """

    #
    # 1. Geometry
    #

    geometry = analyze_geometry(
        highs,
        lows,
        current_index=current_index,
        candles=candles
    )

    geometry_data = _normalize_geometry(
        geometry
    )

    if geometry_data is None:

        return create_result(
            reason="Not enough geometry data"
        )

    #
    # 2. Detector
    #

    detection = detect_structure(
        geometry_data
    )

    if not detection["detected"]:

        validation = geometry_data.get(
            "validation"
        )

        result = create_result(

            pattern="No wedge",

            reason=detection["reason"],

            geometry=geometry_data,

            validation=validation

        )

        result["detection"] = detection

        result["geometry_mode"] = (
            geometry_data
            .get("pair_metrics", {})
            .get("geometry_mode", "NONE")
)

        return attach_legacy_geometry(
            result,
            geometry_data
        )

    #
    # 3. Quality
    #

    validation = geometry_data.get(
        "validation"
    )

    quality = evaluate_quality(
        validation
    )

    #
    # 4. Classifier
    #

    classification = classify_structure(

        detection["pattern"]

    )

    pattern = classification["pattern"]

    #
    # Structural Potential
    #

    potential = calculate_potential_move(
        pattern,
        geometry_data
    )

    #
    # 5. Score
    #

    score_data = calculate_score(

        pattern,

        geometry_data.get(
            "compression",
            {}
        ),

        geometry_data.get(
            "touches",
            {}
        ),

        quality

    )

    #
    # 6. Result
    #

    result = create_result(

        pattern=pattern,

        reason=classification["reason"],

        score=score_data["score"],

        geometry=geometry_data,

        validation=validation,

        quality=quality

    )

    result["score_breakdown"] = (
        score_data["score_breakdown"]
    )

    result["detection"] = detection

    result["potential"] = potential

    result["geometry_mode"] = (
        geometry_data
        .get("pair_metrics", {})
        .get("geometry_mode", "NONE")
)

    return attach_legacy_geometry(
        result,
        geometry_data
    )