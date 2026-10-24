"""Temporary ad-hoc test harness — NOT part of the tracked codebase.

Reuses main.main() completely unmodified; monkeypatches main.get_symbols()
to exclude any symbol starting with 'A' or 'B', to work around main.py's
observed tendency to stop partway through an alphabetical full-universe scan
before reaching those symbols in two prior sessions today.
"""

import main as scanner_main
from bybit_api import get_symbols as _real_get_symbols

_full_symbols = _real_get_symbols()
_filtered_symbols = [s for s in _full_symbols if not s.upper().startswith(("A", "B"))]

print(f"Full universe: {len(_full_symbols)}; excluding A/B-prefixed: {len(_filtered_symbols)} remain")

scanner_main.get_symbols = lambda: _filtered_symbols

if __name__ == "__main__":
    scanner_main.main()
