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


    if upper_touches < 2:

        return {

            "valid":
                False,

            "reason":
                "Not enough upper line touches",

            "details":
                {

                    "upper_touches":
                        upper_touches,

                    "lower_touches":
                        lower_touches,

                    "total_touches":
                        total_touches

                }

        }


    if lower_touches < 2:

        return {

            "valid":
                False,

            "reason":
                "Not enough lower line touches",

            "details":
                {

                    "upper_touches":
                        upper_touches,

                    "lower_touches":
                        lower_touches,

                    "total_touches":
                        total_touches

                }

        }


    return {

        "valid":
            True,

        "reason":
            "Touch confirmation acceptable",

        "details":
            {

                "upper_touches":
                    upper_touches,

                "lower_touches":
                    lower_touches,

                "total_touches":
                    total_touches

            }

    }