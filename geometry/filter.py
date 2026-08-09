"""
geometry.filter

Фильтрация кандидатов трендовых линий.

Отвечает только за:
- удаление плохих линий;
- сортировку кандидатов;
- ограничение количества вариантов.

Не отвечает за:
- клин;
- сигналы;
- торговый скоринг;
- построение линий.
"""


from .debug.logger import debug



def filter_candidates(
    candidates,
    max_lines=50,
    max_error=1.0
):
    """
    Фильтрует кандидатов трендовых линий.

    Parameters
    ----------
    candidates : list

        Список кандидатов:

        {
            "points": [...],
            "line": {
                "slope": float,
                "intercept": float,
                "error_mean": float,
                "error_max": float
            }
        }


    max_lines : int

        Максимальное количество
        оставляемых кандидатов.


    max_error : float

        Максимальная допустимая
        средняя ошибка линии.

        Для тестового Geometry Pipeline
        используется более мягкое значение.
        Финальная калибровка будет выполняться
        через реальные данные и Annotation Dataset.
    """


    if not candidates:

        return []



    filtered = []



    for candidate in candidates:


        if not isinstance(
            candidate,
            dict
        ):
            continue



        line = candidate.get(
            "line"
        )


        if not isinstance(
            line,
            dict
        ):
            continue



        error = line.get(
            "error_mean"
        )


        if error is None:

            continue



        try:

            error = float(
                error
            )

        except (
            TypeError,
            ValueError
        ):

            continue



        if error > max_error:

            debug(
                "FILTER REJECT",
                {
                    "error": error,
                    "max_error": max_error
                }
            )

            continue



        filtered.append(
            candidate
        )



    filtered.sort(

        key=lambda item:

            item.get(
                "line",
                {}
            ).get(
                "error_mean",
                999999
            )

    )



    return filtered[
        :max_lines
    ]