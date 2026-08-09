"""
wedge.quality

Оценка качества геометрической структуры.

Отвечает только за:
- hard validation;
- soft warnings;
- качество структуры.

Не содержит:
- определения типа клина;
- score;
- торговых сигналов.
"""


def evaluate_quality(
    validation
):
    """
    Преобразует результат geometry.validation
    в понятную оценку качества.

    Логика:

    HARD FAIL:
        - нет validation;
        - нет обязательных данных.

    SOFT FAIL:
        - структура интересная,
          но есть предупреждения.

    PASS:
        - геометрия полностью подтверждена.

    """


    if not validation:

        return {

            "status":
                "INVALID",

            "quality":
                "bad",

            "warnings":
                [
                    "Missing validation data"
                ],

            "accepted":
                False

        }



    if validation.get(
        "valid"
    ):

        return {

            "status":
                "VALID",

            "quality":
                "good",

            "warnings":
                [],

            "accepted":
                True

        }



    failed_checks = validation.get(
        "failed_checks",
        []
    )


    warnings = []


    for check in failed_checks:


        if check == "apex":

            warnings.append(
                "Apex position is imperfect"
            )


        elif check == "compression":

            warnings.append(
                "Compression is weak"
            )


        elif check == "touches":

            warnings.append(
                "Not enough touches"
            )


        elif check == "slopes":

            warnings.append(
                "Trendline slopes are similar"
            )


        else:

            warnings.append(
                check
            )



    #
    # Критические случаи
    #

    critical = False


    checks = validation.get(
        "checks",
        {}
    )


    if not checks:

        critical = True



    #
    # Если нет ни одного подтверждения,
    # структура бесполезна
    #

    passed = 0


    for item in checks.values():

        if item.get(
            "valid"
        ):

            passed += 1



    if passed == 0:

        critical = True



    if critical:

        return {

            "status":
                "INVALID",

            "quality":
                "bad",

            "warnings":
                warnings,

            "accepted":
                False

        }



    #
    # Мягкий режим
    #

    return {

        "status":
            "WARNING",

        "quality":
            "acceptable",

        "warnings":
            warnings,

        "accepted":
            True

    }