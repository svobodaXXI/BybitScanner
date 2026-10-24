"""Temporary ad-hoc test harness — NOT part of the tracked codebase.

Reuses main.main() completely unmodified; monkeypatches main.get_symbols()
to a narrow list and wraps main.analyze_symbol()/geometry.evaluation's
validate_geometry() purely to capture, per symbol, which of the five
validation checks (slopes/apex/apex_quality/compression/touches) passed or
failed for the geometry candidate closest to being valid (fewest failed
checks). No production behavior is changed by the wrapping itself.
"""

import main as scanner_main
import geometry.evaluation as geometry_evaluation_mod

NARROW_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "LTCUSDT",
    "SUIUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "WIFUSDT",
    "1000PEPEUSDT",
    "INJUSDT",
]

scanner_main.get_symbols = lambda: NARROW_SYMBOLS

_current_symbol = {"value": None}
_captured = {}

_original_analyze_symbol = scanner_main.analyze_symbol


def _wrapped_analyze_symbol(symbol):
    _current_symbol["value"] = symbol
    _captured.setdefault(symbol, [])
    return _original_analyze_symbol(symbol)


scanner_main.analyze_symbol = _wrapped_analyze_symbol

_original_validate_geometry = geometry_evaluation_mod.validate_geometry


def _wrapped_validate_geometry(*args, **kwargs):
    result = _original_validate_geometry(*args, **kwargs)
    sym = _current_symbol["value"]
    if sym is not None:
        _captured.setdefault(sym, []).append(result)
    return result


geometry_evaluation_mod.validate_geometry = _wrapped_validate_geometry


if __name__ == "__main__":
    scanner_main.main()

    print()
    print("=" * 60)
    print("VALIDATION CHECK BREAKDOWN (best/closest-to-valid candidate per symbol)")
    print("=" * 60)

    for symbol in NARROW_SYMBOLS:
        calls = _captured.get(symbol, [])
        if not calls:
            print(f"{symbol:<15} NO GEOMETRY CANDIDATES EVALUATED")
            continue

        best = min(calls, key=lambda c: len(c.get("failed_checks", [])))
        checks = best.get("checks", {})
        parts = []
        for name in ("slopes", "apex", "apex_quality", "compression", "touches"):
            check = checks.get(name, {})
            ok = check.get("valid", False)
            parts.append(f"{name}={'PASS' if ok else 'FAIL '}")

        print(
            f"{symbol:<15} candidates={len(calls):<4} " + " ".join(parts)
        )
