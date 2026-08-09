"""
wedge.py

Классификатор графических структур.

Геометрические расчёты выполняются
в модуле geometry.

Ответственность:

- анализ геометрической модели;
- определение типа структуры;
- формирование единого результата;
- совместимость со старыми модулями.
"""


from geometry.engine import analyze_geometry



def empty_result(reason):
    """
    Возвращает стандартный результат
    без найденного паттерна.
    """

    return {

        "pattern":
            "No wedge",

        "reason":
            reason,

        "score":
            0,

        "score_breakdown":
            {},

        "geometry":
            None,

        "validation":
            None,


        # legacy compatibility

        "high_slope":
            0,

        "high_intercept":
            0,

        "low_slope":
            0,

        "low_intercept":
            0,

        "compression":
            0,

        "high_touches":
            0,

        "low_touches":
            0

    }



def classify_structure(
    upper_slope,
    lower_slope
):
    """
    Определяет тип структуры
    по направлению трендовых линий.

    Только геометрия.

    Не использует:
    - score;
    - confirmation;
    - торговые правила.
    """



    # Falling Wedge

    if (

        upper_slope < 0

        and

        lower_slope < 0

        and

        lower_slope > upper_slope

    ):

        return {

            "pattern":
                "Falling Wedge",

            "reason":
                "Descending trendlines "
                "with bullish convergence"

        }



    # Rising Wedge

    if (

        upper_slope > 0

        and

        lower_slope > 0

        and

        lower_slope > upper_slope

    ):

        return {

            "pattern":
                "Rising Wedge",

            "reason":
                "Ascending trendlines "
                "with bearish convergence"

        }



    # Triangle Compression

    if (

        upper_slope < 0

        and

        lower_slope > 0

    ):

        return {

            "pattern":
                "Triangle Compression",

            "reason":
                "Opposing trendlines "
                "creating compression"

        }



    return {

        "pattern":
            "No wedge",

        "reason":
            "Trendlines do not form wedge structure"

    }



def calculate_score(
    compression,
    touches,
    pattern
):
    """
    Расчёт структурного Score.
    """


    score_breakdown = {

        "structure":
            0,

        "compression":
            0,

        "touches":
            0

    }



    if pattern != "No wedge":

        if pattern in (

            "Falling Wedge",

            "Rising Wedge"

        ):

            score_breakdown["structure"] = 40

        else:

            score_breakdown["structure"] = 30



    compression_value = compression.get(
        "compression_percent",
        0
    )



    if compression_value > 30:

        score_breakdown["compression"] = 25


    elif compression_value > 15:

        score_breakdown["compression"] = 15



    total_touches = touches.get(
        "total_touches",
        0
    )


    score_breakdown["touches"] = min(
        total_touches * 2,
        20
    )



    return {

        "score":
            sum(
                score_breakdown.values()
            ),

        "score_breakdown":
            score_breakdown

    }



def analyze_wedge(
    highs,
    lows
):
    """
    Полный анализ Pivot High / Pivot Low
    через Geometry Engine.
    """



    geometry = analyze_geometry(
        highs,
        lows
    )



    if geometry is None:

        return empty_result(
            "Not enough geometry data"
        )



    upper_line = geometry.get(
        "upper_line"
    )


    lower_line = geometry.get(
        "lower_line"
    )



    if (

        upper_line is None

        or

        lower_line is None

    ):

        result = empty_result(
            "Missing trendlines"
        )

        result["geometry"] = geometry

        return result



    validation = geometry.get(
        "validation",
        {}
    )



    if validation.get(
        "valid"
    ) is False:



        failed_checks = validation.get(
            "failed_checks",
            []
        )



        reason = (
            "Geometry validation failed"
        )



        if failed_checks:

            reason += ": " + ", ".join(
                failed_checks
            )



        result = empty_result(
            reason
        )


        result["geometry"] = geometry


        result["validation"] = validation


        return result



    high_slope = upper_line["slope"]

    low_slope = lower_line["slope"]



    classification = classify_structure(
        high_slope,
        low_slope
    )



    pattern = classification["pattern"]

    reason = classification["reason"]



    compression = geometry.get(
        "compression",
        {}
    )


    touches = geometry.get(
        "touches",
        {}
    )



    score_data = calculate_score(
        compression,
        touches,
        pattern
    )



    compression_value = compression.get(
        "compression_percent",
        0
    )



    return {

        "pattern":

            pattern,


        "reason":

            reason,


        "score":

            min(
                score_data["score"],
                100
            ),


        "score_breakdown":

            score_data["score_breakdown"],


        "geometry":

            geometry,


        "validation":

            validation,



        # legacy compatibility

        "high_slope":

            float(
                upper_line["slope"]
            ),


        "high_intercept":

            float(
                upper_line["intercept"]
            ),


        "low_slope":

            float(
                lower_line["slope"]
            ),


        "low_intercept":

            float(
                lower_line["intercept"]
            ),


        "compression":

            compression_value,


        "high_touches":

            touches.get(
                "upper_touches",
                0
            ),


        "low_touches":

            touches.get(
                "lower_touches",
                0
            )

    }