"""Real H-017 reversal selection from OFFICIAL PUBLIC TRADE ARCHIVES.

Ten fixed seven-day GRASSUSDT windows, each with 72h earlier M5 warmup.
Reuse the existing strict read-only verifier, never invent candles or relax
the frozen-prior -> opposite confirmed 4-pivot proof gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from research.h017_real_bybit_readonly_acceptance import check

WINDOWS = (
    ("2026-08-22", "2026-08-29"),
    ("2026-08-27", "2026-09-03"),
    ("2026-07-08", "2026-07-15"),
    ("2026-07-22", "2026-07-29"),
    ("2026-08-05", "2026-08-12"),
    ("2026-08-12", "2026-08-19"),
    ("2026-09-08", "2026-09-15"),
    ("2026-09-22", "2026-09-29"),
    ("2026-10-06", "2026-10-13"),
    ("2026-10-20", "2026-10-27"),
)


def find_verified(output_json: Path) -> dict[str, object]:
    if output_json.exists():
        raise ValueError("refuse to overwrite existing research evidence")
    negative = []
    for start, end in WINDOWS:
        print("REAL_H1_WINDOW_CHECK " + start + " " + end, flush=True)
        try:
            # The existing acceptance checks true H1 OHLC, frozen prior,
            # next-open break and a genuinely published opposite H1 pair.
            # A JSON artifact is created ONLY after all those checks pass.
            report = check(
                start=start, end=end, require_complete_reversal=True,
                output_json=str(output_json),
            )
        except AssertionError as exc:
            if not str(exc).startswith("no complete REAL H1 sequence"):
                raise  # data, provenance or causal integrity must not be skipped
            negative.append(start)
            continue
        result = {
            "result": "REAL_H1_WINDOW_SELECTED_FOR_BROWSER_PROOF",
            "symbol": "GRASSUSDT", "start": start, "end": end,
            "source": report["market_data_source"],
            "closed_m5_bars": report["closed_m5_bars"],
            "h1_lines": report["closed_h1_wick_verified_lines"],
            "prior_breaks": report["closed_h1_prior_breaks"],
            "previous_negative_windows": negative,
            "artifact": output_json.name,
            "browser_proof_required": True,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return result
    print(json.dumps({
        "result": "BLOCKED_NO_REAL_COMPLETE_H1_WINDOW",
        "checked": [start for start, _ in WINDOWS],
        "source": "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
        "verified": False,
    }, sort_keys=True), flush=True)
    raise AssertionError("no independently verified real H1 reversal in bounded historical windows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bounded official trade-archive H1 reversal search")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    find_verified(Path(args.output_json))
