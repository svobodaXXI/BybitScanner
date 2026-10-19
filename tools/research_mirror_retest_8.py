"""MIRROR RETEST-8: which RETEST-7 STOP outliers are a moved stop or a handling delay, not market slippage.

Offline research only. Reads ONLY a read-only copy of a PAPER database. For every ``STOP`` exit it joins the
trade to its protection obligation (``paper_protection_obligations``: the trigger price that was actually
latched, the observed exit price and the event/receive/latch timestamps) and classifies the gap:

* ``STOP_MOVED``    recorded ``stop_price`` differs from the latched trigger by more than ``STOP_MOVE_TOLERANCE``;
* ``HANDLING_DELAY`` the market event reached the obligation or the exit order late
                    (``event -> received`` plus ``latched -> exit`` above ``DELAY_MS``): the gap contains the
                    wait, not only the market;
* ``CLEAN_FAST``    neither: the gap is the trigger-to-fill distance of the PAPER fill model.

Thresholds are analysis labels, not trading rules; the report shows the result is insensitive to them.
With ``--reprice`` the CLEAN_FAST empirical quantiles are fed back through the unchanged RETEST-6 replay.

    python -I tools/research_mirror_retest_8.py --paper-db-copy <copy.sqlite3> --out <dir> \
        [--reprice --retest4 <r4> --retest5 <r5> --klines <dir>]
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research_mirror_retest_7 import (  # noqa: E402
    adverse_fraction,
    open_copy_readonly,
    quantile,
    run_scenario,
)

STOP_MOVE_TOLERANCE = Decimal("0.001")   # 0.1% of the recorded stop (observed maximum difference: 0.015%)
DELAY_MS = 2_000
CLASS_STOP_MOVED = "STOP_MOVED"
CLASS_HANDLING_DELAY = "HANDLING_DELAY"
CLASS_CLEAN_FAST = "CLEAN_FAST"
QUANTILES = (("P50", 0.50), ("P75", 0.75), ("P90", 0.90))


def handling_delay_ms(event_ms, received_ms, latched_ms, exit_ms) -> int | None:
    """Wait contained in the gap; None when a timestamp is missing (the exit is then not CLEAN_FAST)."""

    if None in (event_ms, received_ms, latched_ms, exit_ms):
        return None
    return max(received_ms - event_ms, 0) + max(exit_ms - latched_ms, 0)


def classify(
    *, direction: str, recorded_stop: Decimal, trigger_price: Decimal, exit_price: Decimal,
    delay_ms: int | None, delay_threshold_ms: int = DELAY_MS,
    stop_move_tolerance: Decimal = STOP_MOVE_TOLERANCE,
) -> dict:
    moved = abs(recorded_stop - trigger_price) / recorded_stop
    if moved > stop_move_tolerance:
        label = CLASS_STOP_MOVED
    elif delay_ms is None or delay_ms > delay_threshold_ms:
        label = CLASS_HANDLING_DELAY
    else:
        label = CLASS_CLEAN_FAST
    return {
        "class": label,
        "stop_vs_trigger_fraction": float(moved),
        "trigger_to_exit_adverse_fraction": float(adverse_fraction(direction, trigger_price, exit_price)),
        "handling_delay_ms": delay_ms,
    }


def load_stop_exits(connection) -> list[dict]:
    rows = connection.execute(
        "select t.trade_id, t.symbol, t.direction, t.stop_price, t.exit_price, t.exit_time_ms, "
        "o.trigger_price, o.source_event_at_ms, o.source_received_at_ms, o.latched_at_ms "
        "from robot_trades t join paper_protection_obligations o on o.trade_id = t.trade_id "
        "where t.exit_reason = 'STOP' and o.winning_leg = 'STOP' and t.exit_price is not null "
        "order by t.exit_time_ms").fetchall()
    return [
        {"trade_id": trade_id, "symbol": symbol, "direction": direction,
         **classify(direction=direction, recorded_stop=Decimal(stop), trigger_price=Decimal(trigger),
                    exit_price=Decimal(exit_price),
                    delay_ms=handling_delay_ms(event, received, latched, exited))}
        for trade_id, symbol, direction, stop, exit_price, exited, trigger, event, received, latched in rows
    ]


def summarize(items: list[dict]) -> dict:
    values = sorted(item["trigger_to_exit_adverse_fraction"] for item in items)
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": values[0], "max": values[-1],
            **{name: quantile(values, q) for name, q in QUANTILES}}


def report(items: list[dict]) -> dict:
    by_class = {label: [item for item in items if item["class"] == label]
                for label in (CLASS_STOP_MOVED, CLASS_HANDLING_DELAY, CLASS_CLEAN_FAST)}
    sensitivity = {}
    for threshold in (1_000, 2_000, 5_000):
        sensitivity[str(threshold)] = sum(
            1 for item in items
            if item["class"] != CLASS_STOP_MOVED
            and (item["handling_delay_ms"] is None or item["handling_delay_ms"] > threshold))
    return {
        "n_stop_exits": len(items),
        "classes": {label: {"count": len(group), "adverse": summarize(group)} for label, group in by_class.items()},
        "all": summarize(items),
        "delayed_count_by_threshold_ms": sensitivity,
        "max_stop_vs_trigger_fraction": max((item["stop_vs_trigger_fraction"] for item in items), default=None),
        "delay_threshold_ms": DELAY_MS,
        "stop_move_tolerance": str(STOP_MOVE_TOLERANCE),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-db-copy", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reprice", action="store_true")
    parser.add_argument("--retest4", type=Path)
    parser.add_argument("--retest5", type=Path)
    parser.add_argument("--klines", type=Path)
    args = parser.parse_args()

    with open_copy_readonly(args.paper_db_copy) as connection:
        items = load_stop_exits(connection)
    summary = report(items)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "classification.json").write_text(json.dumps(items, indent=1), encoding="utf-8")

    if args.reprice:
        if not (args.retest4 and args.retest5 and args.klines):
            raise SystemExit("--reprice needs --retest4 --retest5 --klines")
        clean = summary["classes"][CLASS_CLEAN_FAST]["adverse"]
        results = {}
        for name, _ in QUANTILES:
            slippage = Decimal(str(max(clean[name], 0.0)))
            scenario = run_scenario(f"CLEAN_{name}", slippage, args)
            results[name] = {
                "slippage_fraction": str(slippage),
                **{strategy: {key: scenario[strategy][key] for key in
                              ("closed", "net_pnl_pct_wv_closed", "wins", "losses", "exits")}
                   for strategy in ("BASE", "MIRROR")},
            }
        summary["clean_fast_repriced"] = results
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
