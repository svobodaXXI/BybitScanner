"""
wedge package

Модули анализа графических структур:

- analyzer     : полный цикл анализа
- classifier   : определение типа структуры
- quality      : оценка качества
- scoring      : расчёт score
- result       : единый формат результата
"""


from .analyzer import analyze_wedge


__all__ = [

    "analyze_wedge"

]