"""MIRROR RETEST-5: economic value of the ATR retest zone without manual labels.

Offline, cache-only re-run over the exact RETEST-4 boundaries
(DOCUMENTS/research/mirror_retest_4/summary.json manifest) and the cached
public klines; no network access, no runtime reads.

Entry-independent comparison of how the campaign remainder is closed at the
retest (rule 7): every policy closes the *same* position, so the exit-price
difference per unit does not depend on the unknown entry.

Policies (detection is always on a closed candle, execution is separate):
- PHYS_MARKET: zero-tolerance retest on 5m, ambiguous 5m touches settled by the
  1m candles inside them, closed at the next 1m open after the 5m close;
- PHYS_LIMIT: resting LIMIT at the line from the breakout close, filled only
  on a 1m trade-through, at the limit price;
- CAND_MARKET(period, k): owner grid zone, same refinement and execution as
  PHYS_MARKET.

Pre-registered decision (no selection on test): on train, pick the k > 0
candidate with the highest mean improvement vs PHYS_MARKET; it is eligible
only with mean > 0 and one-sided sign test p < 0.05. An eligible pick has a
proven advantage only if test mean > 0 and test sign-test p < 0.05.

Costs: only repository-documented values are used — fee 0.0006 per side
(robot_l_shape.PAPER_ROBOT_FEE_RATE, terminal/runtime/paper_runtime.py, same
for LIMIT and MARKET) and the 0.5% adverse-move cap
(terminal/application/robot_late_admission.MAX_LATE_ADMISSION_SLIPPAGE) as an
upper sensitivity bound. No spread value is documented; it is folded into the
market slippage scenario.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geometry.naked_retest import PHASE_RETEST_PROVEN, Boundary  # noqa: E402
from retest_calibration import (  # noqa: E402
    CalibrationCase,
    Candidate,
    evaluate_case,
    exit_improvement_bps,
    hold_excursions_bps,
    market_exit_after,
    resting_limit_exit_at_line,
    sign_test_p,
)
from tools.research_mirror_retest_4 import (  # noqa: E402
    ATR_PERIODS,
    COARSE_MS,
    FINE_MS,
    MULTIPLIERS,
    candles,
)

FEE_RATE = 0.0006           # documented PAPER per-side fee
SLIPPAGE_CAP = 0.005        # documented maximum adverse move, upper bound only
BOOTSTRAP = 2000


def load_cached(klines: Path, name: str) -> dict:
    path = klines / name
    if not path.exists():
        raise SystemExit(f"cache miss {path}: RETEST-5 is cache-only")
    return json.loads(path.read_text(encoding="utf-8"))


def net_vs_limit_bps(direction: str, market_price: float, limit_price: float, slippage: float) -> float:
    """Net per-unit improvement of a market exit over a resting-limit exit.

    The market exit pays ``slippage`` adversely; both exits pay FEE_RATE on
    their own notional (buy-back costs price*(1+f), sale yields price*(1-f)).
    """

    if direction == "UP":   # SHORT campaign: buy back
        paid = market_price * (1 + slippage) * (1 + FEE_RATE)
        return (limit_price * (1 + FEE_RATE) - paid) / limit_price * 1e4
    received = market_price * (1 - slippage) * (1 - FEE_RATE)
    return (received - limit_price * (1 - FEE_RATE)) / limit_price * 1e4


def describe(values: list[float], seed: int = 0) -> dict:
    if not values:
        return {"n": 0}
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP))
    return {
        "n": len(values), "mean": statistics.fmean(values), "median": statistics.median(values),
        "positive": sum(v > 0 for v in values), "negative": sum(v < 0 for v in values),
        "zero": sum(v == 0 for v in values), "sign_p": sign_test_p(values),
        "mean_ci95": [means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP) - 1]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retest4", type=Path, required=True, help="RETEST-4 summary.json")
    parser.add_argument("--klines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    r4 = json.loads(args.retest4.read_text(encoding="utf-8"))
    split = r4["split_as_of_ms"]
    grid = [Candidate(p, m) for p in ATR_PERIODS for m in MULTIPLIERS if m > 0]
    physical = Candidate(14, 0.0)  # k = 0: the ATR period is irrelevant

    rows, case_info = {f"{c.atr_period}x{c.multiplier}": [] for c in grid}, []
    for item in r4["manifest"]:
        cid = item["boundary_id"].split(":")[0]
        boundary = Boundary(item["boundary_id"], item["anchor_time_ms"], item["anchor_price"],
                            item["slope_per_ms"], item["as_of_ms"])
        coarse = candles(load_cached(args.klines, f"{cid}_5.json"), COARSE_MS)
        fine = (candles(load_cached(args.klines, f"{cid}_1_0.json"), FINE_MS)
                + candles(load_cached(args.klines, f"{cid}_1_1.json"), FINE_MS))
        fine.sort(key=lambda c: c["open_time_ms"])
        case = CalibrationCase(boundary, tuple(coarse))
        direction = item["breakout_direction"]
        half = "train" if item["as_of_ms"] < split else "test"

        raw = evaluate_case(case, physical)
        phys = evaluate_case(case, physical, fine)
        assert phys["breakout_direction"] == direction
        phys_exec = (market_exit_after(fine, phys["retest_close_time_ms"], FINE_MS)
                     if phys["outcome"] == PHASE_RETEST_PROVEN else None)
        limit_exec = resting_limit_exit_at_line(boundary, direction, fine, phys["breakout_close_time_ms"])
        breakout_bar = next(c for c in coarse if c["close_time_ms"] == phys["breakout_close_time_ms"])
        line_at_close = boundary.price_at(breakout_bar["close_time_ms"])
        case_info.append({
            "boundary_id": item["boundary_id"], "symbol": item["symbol"], "half": half,
            "direction": direction, "raw_outcome": raw["outcome"], "refined_outcome": phys["outcome"],
            "phys_market": phys_exec, "phys_limit": limit_exec,
            "potential_bps": abs(breakout_bar["close"] - line_at_close) / breakout_bar["close"] * 1e4,
        })

        for candidate in grid:
            out = evaluate_case(case, candidate, fine)
            cand_exec = (market_exit_after(fine, out["retest_close_time_ms"], FINE_MS)
                         if out["outcome"] == PHASE_RETEST_PROVEN else None)
            record = {"boundary_id": item["boundary_id"], "half": half, "outcome": out["outcome"],
                      "cand": cand_exec}
            if cand_exec and phys_exec:
                record["delta_bps"] = exit_improvement_bps(direction, cand_exec["price"], phys_exec["price"])
                record["lead_min"] = (phys_exec["time_ms"] - cand_exec["time_ms"]) / FINE_MS
                record["hold_mfe_bps"], record["hold_mae_bps"] = hold_excursions_bps(
                    direction, fine, cand_exec["time_ms"], phys_exec["time_ms"], cand_exec["price"])
                for s in (0.0, SLIPPAGE_CAP):
                    # both exits are MARKET: same slippage and fee on both sides
                    c_eff = cand_exec["price"] * (1 + s if direction == "UP" else 1 - s)
                    p_eff = phys_exec["price"] * (1 + s if direction == "UP" else 1 - s)
                    f = FEE_RATE if direction == "DOWN" else -FEE_RATE
                    record[f"delta_net_bps_s{s}"] = exit_improvement_bps(direction, c_eff * (1 - f), p_eff * (1 - f))
            if cand_exec and limit_exec:
                for s in (0.0, SLIPPAGE_CAP):
                    record[f"vs_limit_net_bps_s{s}"] = net_vs_limit_bps(direction, cand_exec["price"],
                                                                       limit_exec["price"], s)
            record["censored"] = bool(cand_exec) and not phys_exec
            rows[f"{candidate.atr_period}x{candidate.multiplier}"].append(record)

    results = {}
    for key, records in rows.items():
        entry = {}
        for half in ("all", "train", "test"):
            sel = [r for r in records if half == "all" or r["half"] == half]
            paired = [r for r in sel if "delta_bps" in r]
            differing = [r for r in paired if r["delta_bps"] != 0 or r["lead_min"] != 0]
            entry[half] = {
                "paired": len(paired), "censored": sum(r["censored"] for r in sel),
                "delta_bps": describe([r["delta_bps"] for r in paired]),
                "delta_net_bps_fee_slip_cap": describe([r[f"delta_net_bps_s{SLIPPAGE_CAP}"] for r in paired]),
                "differing_cases": len(differing),
                "lead_min_differing": describe([r["lead_min"] for r in differing]),
                "hold_mfe_bps_differing": describe([r["hold_mfe_bps"] for r in differing]),
                "hold_mae_bps_differing": describe([r["hold_mae_bps"] for r in differing]),
                "vs_limit_net_bps_s0": describe([r["vs_limit_net_bps_s0.0"] for r in sel if "vs_limit_net_bps_s0.0" in r]),
                "vs_limit_net_bps_cap": describe([r[f"vs_limit_net_bps_s{SLIPPAGE_CAP}"] for r in sel
                                                  if f"vs_limit_net_bps_s{SLIPPAGE_CAP}" in r]),
            }
        results[key] = entry

    eligible = [(v["train"]["delta_bps"]["mean"], k) for k, v in results.items()
                if v["train"]["delta_bps"].get("n") and v["train"]["delta_bps"]["mean"] > 0
                and (v["train"]["delta_bps"]["sign_p"] or 1) < 0.05]
    decision = {"rule": "train max mean delta_bps with mean>0 and sign_p<0.05; then test mean>0 and sign_p<0.05"}
    train_best = max(results, key=lambda k: results[k]["train"]["delta_bps"].get("mean", float("-inf")))
    decision["train_best_by_mean"] = train_best
    if eligible:
        pick = max(eligible)[1]
        test = results[pick]["test"]["delta_bps"]
        decision.update(selected=pick, proven=bool(test.get("n") and test["mean"] > 0
                                                   and (test["sign_p"] or 1) < 0.05))
    else:
        decision.update(selected=None, proven=False, reason="no k>0 candidate passes the train gate")

    phys_limit_vs_market = [exit_improvement_bps(c["direction"], c["phys_limit"]["price"], c["phys_market"]["price"])
                            for c in case_info if c["phys_limit"] and c["phys_market"]]
    summary = {
        "cases": len(case_info), "split_as_of_ms": split,
        "refinement": {
            "raw_unproven": sum(c["raw_outcome"] == "RETEST_UNPROVEN" for c in case_info),
            "refined_unproven": sum(c["refined_outcome"] == "RETEST_UNPROVEN" for c in case_info),
            "refined_proven": sum(c["refined_outcome"] == PHASE_RETEST_PROVEN for c in case_info),
            "phys_market_executed": sum(bool(c["phys_market"]) for c in case_info),
            "phys_limit_filled": sum(bool(c["phys_limit"]) for c in case_info),
        },
        "potential_bps": describe([c["potential_bps"] for c in case_info]),
        "phys_limit_vs_phys_market_gross_bps": describe(phys_limit_vs_market),
        "costs": {"fee_rate_per_side": FEE_RATE, "slippage_cap": SLIPPAGE_CAP,
                  "sources": ["robot_l_shape.py:47", "terminal/runtime/paper_runtime.py:708,717",
                              "terminal/application/robot_late_admission.py:36"]},
        "decision": decision, "results": results, "cases_detail": case_info,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("cases", "refinement", "potential_bps",
                                              "phys_limit_vs_phys_market_gross_bps", "decision")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
