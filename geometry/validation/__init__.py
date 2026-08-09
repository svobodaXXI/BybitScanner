"""
geometry.validation

Пакет проверки качества геометрической структуры.
"""

from .geometry import validate_geometry
from .slopes import validate_slopes
from .apex import validate_apex
from .compression import validate_compression
from .touches import validate_touches


__all__ = [
    "validate_geometry",
    "validate_slopes",
    "validate_apex",
    "validate_compression",
    "validate_touches",
]