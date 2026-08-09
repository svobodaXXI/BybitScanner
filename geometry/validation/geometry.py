"""
geometry.validation.geometry

Главный координатор проверки геометрии.

Validation Engine v2:

Собирает результаты всех проверок
и формирует единый диагностический отчёт.
"""


from .slopes import validate_slopes
from .apex import validate_apex
from .apex_quality import evaluate_apex_quality
from .compression import validate_compression
from .touches import validate_touches



def validate_geometry(
    upper_line,
    lower_line,
    apex,
    compression,
    touches,
    start_index,
    end_index
):
    """
    Главная проверка геометрии.

    Возвращает:

    {
        "valid": bool,

        "checks": {

            "name": {

                "valid": bool,
                "reason": str,
                "details": {}

            }

        },

        "failed_checks": []

    }

    """


    checks = {

        "slopes":

            validate_slopes(
                upper_line,
                lower_line
            ),



        "apex":

            validate_apex(
                upper_line,
                lower_line,
                apex,
                start_index,
                end_index
            ),



        "apex_quality":

            evaluate_apex_quality(
                upper_line,
                lower_line,
                apex,
                start_index,
                end_index
            ),



        "compression":

            validate_compression(
                compression
            ),



        "touches":

            validate_touches(
                touches
            )

    }



    failed_checks = []


    for name, result in checks.items():

        if not result.get(
            "valid",
            False
        ):

            failed_checks.append(
                name
            )



    return {

        "valid":

            len(
                failed_checks
            ) == 0,


        "checks":

            checks,


        "failed_checks":

            failed_checks

    }