"""
structures/validation.py

Проверка качества структуры.

Отвечает только за:
- достаточно ли точек;
- корректна ли геометрия;
- достаточно ли касаний;
- соблюдает ли цена границы структуры.

Не определяет:
- название структуры;
- score;
- торговое решение.
"""


def validate_structure(
    geometry,
    price_check=None,
    min_touches=3
):
    """
    Проверяет пригодность структуры.
    """


    if geometry is None:

        return {

            "valid":
                False,

            "reason":
                "No geometry"

        }



    upper = geometry.get(
        "upper_line",
        {}
    )


    lower = geometry.get(
        "lower_line",
        {}
    )


    if not upper or not lower:

        return {

            "valid":
                False,

            "reason":
                "Missing trendlines"

        }



    if upper.get(
        "points",
        0
    ) < 2:

        return {

            "valid":
                False,

            "reason":
                "Not enough upper points"

        }



    if lower.get(
        "points",
        0
    ) < 2:

        return {

            "valid":
                False,

            "reason":
                "Not enough lower points"

        }



    touches = geometry.get(
        "touches",
        {}
    )


    total_touches = touches.get(
        "total_touches",
        0
    )


    if total_touches < min_touches:

        return {

            "valid":
                False,

            "reason":
                "Not enough touches"

        }



    # -------------------------
    # PRICE POSITION CHECK
    # -------------------------

    if price_check is not None:


        if price_check.get(
            "valid"
        ) is False:


            return {

                "valid":
                    False,

                "reason":
                    price_check.get(
                        "reason",
                        "Price breaks structure"
                    )

            }



    return {

        "valid":
            True,

        "reason":
            "Structure validation passed"

    }