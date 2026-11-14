"""Analyzer public entrypoint; pure scoring may import without live config.

The Scanner call remains the identical analyzer.core.analyze_symbol function.
Do not load its config/network/chart/report imports for read-only research.
"""

__all__ = ["analyze_symbol"]


def __getattr__(name):
    if name == "analyze_symbol":
        from .core import analyze_symbol
        return analyze_symbol
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
