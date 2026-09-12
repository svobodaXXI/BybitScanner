"""
geometry.debug

Diagnostic tools for Geometry Engine.

Не содержит:
- торговой логики;
- Score;
- Signal.

Назначение:
- проверка контрактов данных;
- поиск None;
- поиск nan;
- диагностика Geometry Model.
"""


from .inspector import (
    inspect_line,
    inspect_geometry,
    inspect_value
)


__all__ = [

    "inspect_line",

    "inspect_geometry",

    "inspect_value"

]