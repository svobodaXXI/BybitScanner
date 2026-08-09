"""
wedge.classifier

Интерпретация обнаруженной структуры.

Получает название паттерна и возвращает его
рыночную интерпретацию.

Не отвечает за:

- поиск структуры;
- геометрию;
- Validation;
- Score.
"""


def classify_structure(pattern):
    """
    Возвращает торговую интерпретацию
    уже определённого паттерна.
    """

    mapping = {

        "Falling Wedge": {
            "pattern": "Falling Wedge",
            "bias": "bullish",
            "reason": "Descending converging trendlines"
        },

        "Rising Wedge": {
            "pattern": "Rising Wedge",
            "bias": "bearish",
            "reason": "Ascending converging trendlines"
        },

        "Triangle Compression": {
            "pattern": "Triangle Compression",
            "bias": "neutral",
            "reason": "Opposing trendlines compression"
        }

    }

    return mapping.get(

        pattern,

        {
            "pattern": pattern,
            "bias": "neutral",
            "reason": "Structure not recognized"
        }

    )