"""
geometry.candidate

Candidate Line Generator

Создаёт возможные варианты трендовых линий
из Pivot точек.

Каждый кандидат автоматически проходит
через geometry.trendline.py.

Отвечает только за:
- генерацию комбинаций;
- построение линий;
- подготовку кандидатов.

Не отвечает за:
- клин;
- скоринг;
- сигналы.
"""


from itertools import combinations

from geometry.trendline import fit_trendline



def build_candidate_lines(
    points,
    size=4
):
    """
    Создаёт кандидаты трендовых линий.

    Parameters
    ----------
    points : list[dict]

        Pivot точки:

        {
            "index": int,
            "price": float
        }


    size : int

        Количество точек
        для одной линии.


    Returns
    -------

    list[dict]

        Кандидаты с готовыми линиями.

    """


    if not points:

        return []


    if len(points) < size:

        return []



    candidates = []



    for combo in combinations(
        points,
        size
    ):


        selected_points = list(
            combo
        )


        line = fit_trendline(
            selected_points
        )


        if line is None:

            continue



        candidates.append(
            {
                "points":
                    selected_points,

                "line":
                    line
            }
        )



    return candidates




def generate_candidates(
    points,
    size=4
):
    """
    Совместимость со старым API.

    Старое имя функции.
    """

    return build_candidate_lines(
        points,
        size
    )