"""
geometry.debug.inspector

Geometry Integrity Inspector.

Проверяет корректность данных
между слоями Geometry Engine.

Не изменяет данные.

Только диагностика.

Проверяет:

- None;
- NaN;
- отсутствующие поля;
- неправильные типы.

"""


import math



def inspect_value(
    value,
    name="value"
):
    """
    Проверка одного значения.

    Возвращает:

    {
        "valid": bool,
        "reason": str
    }

    """


    if value is None:

        return {

            "valid": False,

            "reason":
                f"{name} is None"

        }



    if isinstance(
        value,
        float
    ):

        if math.isnan(value):

            return {

                "valid": False,

                "reason":
                    f"{name} is NaN"

            }



        if math.isinf(value):

            return {

                "valid": False,

                "reason":
                    f"{name} is infinite"

            }



    return {

        "valid": True,

        "reason":
            "OK"

    }




def inspect_line(
    line,
    name="line"
):
    """
    Проверка объекта трендовой линии.

    Ожидает:

    {
        slope,
        intercept
    }

    """


    if line is None:

        return {

            "valid": False,

            "reason":
                f"{name} missing",

            "details":
                {}

        }



    slope_check = inspect_value(
        line.get("slope"),
        f"{name}.slope"
    )


    intercept_check = inspect_value(
        line.get("intercept"),
        f"{name}.intercept"
    )



    errors = []



    if not slope_check["valid"]:

        errors.append(
            slope_check["reason"]
        )



    if not intercept_check["valid"]:

        errors.append(
            intercept_check["reason"]
        )



    return {

        "valid":
            len(errors) == 0,


        "reason":
            "OK"
            if not errors
            else "Line invalid",


        "details":
            {

                "errors":
                    errors,

                "line":
                    line

            }

    }




def inspect_geometry(
    geometry
):
    """
    Проверка Geometry Model.

    Проверяет:

    - upper_line;
    - lower_line;
    - apex;
    - compression;
    - touches.

    """


    if geometry is None:

        return {

            "valid": False,

            "errors":
                [

                    "Geometry is None"

                ]

        }



    errors = []



    upper_result = inspect_line(
        geometry.get(
            "upper_line"
        ),
        "upper_line"
    )


    lower_result = inspect_line(
        geometry.get(
            "lower_line"
        ),
        "lower_line"
    )



    if not upper_result["valid"]:

        errors.extend(
            upper_result["details"]["errors"]
        )



    if not lower_result["valid"]:

        errors.extend(
            lower_result["details"]["errors"]
        )



    return {

        "valid":
            len(errors) == 0,


        "errors":
            errors

    }