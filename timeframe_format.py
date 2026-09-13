"""timeframe_format.py

Presentation-only Russian compact timeframe rendering (e.g. "1" -> "1м").

Не содержит:
- анализа;
- торговых решений.
"""

_UNIT_LABELS = {
    "D": "д",
    "W": "н",
    "M": "мес",
}


def format_timeframe_ru(timeframe):
    """Render a Bybit kline interval as a compact Russian label.

    Numeric intervals ("1", "5", "15", ...) become "<n>м" (minutes).
    "D"/"W"/"M" become "1д"/"1н"/"1мес". Anything else is returned unchanged.
    """

    text = str(timeframe).strip().upper()

    if text in _UNIT_LABELS:
        return f"1{_UNIT_LABELS[text]}"

    if text.isdigit():
        return f"{text}м"

    return text
