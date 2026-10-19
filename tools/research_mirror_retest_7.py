"""MIRROR RETEST-7: measured STOP slippage and the RETEST-6 trade book re-priced with it.

Offline research only. Step 1 reads ONLY a read-only copy of a PAPER database
(never the live ``paper_runtime.sqlite3``) and measures how far the recorded
fill of every ``STOP`` exit was from the recorded stop price. Step 2 re-runs
the unchanged RETEST-6 replay (cache-only, no network) with that adverse
fraction applied to every market-style exit (STOP trigger and the campaign
RETEST close). The fractions are empirical quantiles of the measured sample,
not trading parameters, and nothing here feeds a runtime.

    python -I tools/research_mirror_retest_7.py --paper-db-copy <copy.sqlite3> \
        --retest4 <r4 summary.json> --retest5 <r5 summary.json> \
        --klines <dir> --out <dir>
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import math
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.research_mirror_retest_6 as replay  # noqa: E402

LIVE_DB_NAME = "paper_runtime.sqlite3"
QUANTILES = (("P50", 0.50), ("P75", 0.75), ("P90", 0.90))


def adverse_fraction(direction: str, stop_price: Decimal, exit_price: Decimal) -> Decimal:
    """Adverse slippage of a STOP exit as a fraction of the stop price (negative = better fill)."""

    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    if not stop_price > 0 or not exit_price > 0:
        raise ValueError("prices must be positive")
    if direction == "LONG":
        return (stop_price - exit_price) / stop_price
    return (exit_price - stop_price) / stop_price


def quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated empirical quantile (type 7) of an ascending sample."""

    if not sorted_values:
        raise ValueError("empty sample")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def open_copy_readonly(path: Path) -> sqlite3.Connection:
    """Open a PAPER database *copy* read-only; refuse anything that looks like the live file."""

    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"paper db copy not found: {path}")
    if resolved.name == LIVE_DB_NAME and resolved.parent.name.lower() == "bybitscanner":
        raise SystemExit("refusing to read the live PAPER DB: pass a read-only copy")
    return sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)


def measure_stop_slippage(connection: sqlite3.Connection) -> dict:
    rows = connection.execute(
        "select trade_id, symbol, direction, stop_price, exit_price, entry_time_ms, exit_time_ms "
        "from robot_trades where exit_reason = 'STOP' and exit_price is not null "
        "order by exit_time_ms"
    ).fetchall()
    samples = []
    for trade_id, symbol, direction, stop, exit_price, entered, exited in rows:
        samples.append({
            "trade_id": trade_id, "symbol": symbol, "direction": direction,
            "adverse_fraction": float(adverse_fraction(direction, Decimal(stop), Decimal(exit_price))),
            "hold_minutes": round((exited - entered) / 60_000, 1),
        })
    values = sorted(item["adverse_fraction"] for item in samples)
    stats = {
        "n_stop_exits": len(samples),
        "adverse_fraction": {
            "min": values[0] if values else None, "max": values[-1] if values else None,
            **({name: quantile(values, q) for name, q in QUANTILES} if values else {}),
        },
        "better_than_stop": sum(value < 0 for value in values),
        "worse_than_1pct": sum(value > 0.01 for value in values),
        "other_exit_reasons": dict(connection.execute(
            "select exit_reason, count(*) from robot_trades group by exit_reason").fetchall()),
        "caveats": [
            "stop_price is the recorded protective stop of the trade; a stop moved after entry or a long hold "
            "can make the gap larger than a single stop-trigger slippage",
            "PAPER simulator fills, not exchange fills; EMERGENCY_CLOSE exits have no reference price and are excluded",
        ],
    }
    return {"stats": stats, "samples": samples}


def run_scenario(name: str, slippage: Decimal, args: argparse.Namespace) -> dict:
    out = args.out / f"scenario_{name}"
    replay.STOP_SLIPPAGE = slippage
    original_argv = sys.argv
    sys.argv = ["research_mirror_retest_6", "--retest4", str(args.retest4), "--retest5", str(args.retest5),
                "--klines", str(args.klines), "--out", str(out)]
    try:
        replay.main()
    finally:
        sys.argv = original_argv
        replay.STOP_SLIPPAGE = Decimal(0)
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-db-copy", type=Path, required=True)
    parser.add_argument("--retest4", type=Path, required=True)
    parser.add_argument("--retest5", type=Path, required=True)
    parser.add_argument("--klines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    with open_copy_readonly(args.paper_db_copy) as connection:
        measured = measure_stop_slippage(connection)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "slippage_samples.json").write_text(json.dumps(measured, indent=1), encoding="utf-8")

    fractions = measured["stats"]["adverse_fraction"]
    scenarios = {"ZERO": Decimal(0)}
    scenarios.update({name: Decimal(str(max(fractions[name], 0.0))) for name, _ in QUANTILES if name in fractions})
    scenarios["CEILING_0_5PCT"] = Decimal("0.005")   # documented late-admission market ceiling (RETEST-6)

    results = {}
    for name, slippage in scenarios.items():
        summary = run_scenario(name, slippage, args)
        results[name] = {
            "slippage_fraction": str(slippage),
            **{strategy: {key: summary[strategy][key] for key in
                          ("closed", "net_pnl_pct_wv_closed", "wins", "losses", "exits")}
               for strategy in ("BASE", "MIRROR")},
        }
    summary = {"slippage": measured["stats"], "scenarios": results}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
