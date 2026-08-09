"""
geometry.evaluation

Оценка пары геометрических кандидатов.

Модуль отвечает только за:
- сбор геометрической модели;
- расчёт Apex;
- расчёт Compression;
- анализ Touches;
- Validation;
- создание GeometryModel.

Не отвечает за:
- выбор лучшего кандидата;
- паттерны;
- Score;
- сигналы.
"""


from .apex import calculate_apex
from .compression import calculate_compression
from .touches import analyze_touches
from .validation import validate_geometry
from .model import GeometryModel



def evaluate_candidate_pair(
    upper_candidate,
    lower_candidate
):
    """
    Оценивает пару линий
    верхнего и нижнего кандидата.

    Возвращает:

    GeometryModel
    """



    if (
        upper_candidate is None
        or lower_candidate is None
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



    upper_points = upper_candidate.get(
        "points",
        []
    )

    lower_points = lower_candidate.get(
        "points",
        []
    )



    if (
        not upper_points
        or not lower_points
    ):

        return None



    start_index = min(
        upper_points[0]["index"],
        lower_points[0]["index"]
    )


    end_index = max(
        upper_points[-1]["index"],
        lower_points[-1]["index"]
    )



    #
    # Apex
    #

    apex = calculate_apex(
        upper_line,
        lower_line
    )



    #
    # Compression
    #

    compression = calculate_compression(
        upper_line,
        lower_line,
        start_index,
        end_index
    )



    #
    # Touches
    #

    touches = analyze_touches(
        upper_line,
        lower_line,
        upper_points,
        lower_points
    )



    #
    # Validation
    #

    validation = validate_geometry(
        upper_line,
        lower_line,
        apex,
        compression,
        touches,
        start_index,
        end_index
    )



    #
    # Geometry Model Contract
    #

    return GeometryModel(

        upper_line=upper_line,

        lower_line=lower_line,

        apex=apex,

        compression=compression,

        touches=touches,

        validation=validation,

        candidate_points={

            "upper":
                upper_points,

            "lower":
                lower_points

        }

    )