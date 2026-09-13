"""
geometry.debug.logger

Централизованный Debug Logger.

Используется только для диагностики.

Не влияет на:

- Geometry расчёты;
- Validation;
- Ranking;
- Wedge Layer;
- Signal Layer.
"""


DEBUG_ENABLED = True



def debug(
    section,
    *args
):
    """
    Централизованный вывод диагностики.

    Пример:

    debug(
        "GEOMETRY",
        "raw upper=",
        5
    )

    Результат:

    [DEBUG GEOMETRY] raw upper= 5
    """


    if not DEBUG_ENABLED:

        return


    print(
        f"[DEBUG {section}]",
        *args
    )