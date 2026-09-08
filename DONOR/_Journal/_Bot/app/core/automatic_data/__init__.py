"""Extensible contracts for automatic trade and market observations."""

from .definition import (
    AutomaticFactorCategory,
    AutomaticFactorDefinition,
    AutomaticFactorRegistry,
    AutomaticFactorSourceKind,
    AutomaticFactorValueType,
    AutomaticFactorBucketPolicy,
    CaptureSemantics,
    DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
)
from .observation import (
    AutomaticFactorAvailability,
    AutomaticFactorObservation,
    AutomaticFactorQuality,
    AutomaticObservationValueType,
)
from .ports import AutomaticFactorCalculator, AutomaticFactorProvider

__all__ = [
    "AutomaticFactorAvailability",
    "AutomaticFactorCalculator",
    "AutomaticFactorCategory",
    "AutomaticFactorDefinition",
    "AutomaticFactorObservation",
    "AutomaticFactorProvider",
    "AutomaticFactorQuality",
    "AutomaticObservationValueType",
    "AutomaticFactorRegistry",
    "AutomaticFactorSourceKind",
    "AutomaticFactorValueType",
    "AutomaticFactorBucketPolicy",
    "CaptureSemantics",
    "DEFAULT_AUTOMATIC_FACTOR_REGISTRY",
]
