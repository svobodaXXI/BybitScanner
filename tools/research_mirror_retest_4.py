"""MIRROR RETEST-4: one bounded historical ATR-zone calibration experiment.

Offline research only. Reads frozen Scanner->Robot candidate snapshots
(read-only JSON files), fetches public Bybit market-data klines
(/v5/market/kline, no keys, no trading endpoints) into a separate research
directory, and evaluates the owner grid on real 5m candles against an
independent 1m physical-touch reference. Writes results only to --out.

    python -I tools/research_mirror_retest_4.py --candidates <dir> --out <dir>

Experiment parameters below are data-window choices for this experiment, not
trading rules: observation window after as-of and ATR warm-up length.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geometry.naked_retest import (  # noqa: E402
    PHASE_CAMPAIGN_ACTIVE,
    TERMINAL_PHASES,
    Boundary,
    NakedRetestError,
    initialize_state,
    process_closed_candle,
)
from retest_calibration import (  # noqa: E402
    LABEL_UNLABELED_NEAR_MISS,
    CalibrationCase,
    Candidate,
    causal_atr_series,
    evaluate_case,
    label_detection,
    reference_touch,
    summarize_labels,
)

ATR_PERIODS = (7, 14, 21, 28)                       # owner grid
MULTIPLIERS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)   # owner grid
PATTERNS = ("Falling Wedge", "Rising Wedge", "Triangle Compression")
COARSE_MS = 5 * 60_000
FINE_MS = 60_000
WARMUP_COARSE = 40              # > max ATR period
OBSERVE_MS = 24 * 3600_000      # observation window after as-of
SAMPLE_SIZE = 60
REQUEST_PAUSE_S = 0.5
KLINE_URL = "https://api.bybit.com/v5/market/kline"


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def load_candidates(directory: Path, now_ms: int) -> list[dict]:
    seen, rows = set(), []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        snap = record.get("signal_snapshot") or {}
        geo = snap.get("robot_geometry") or {}
        cursor = snap.get("scanner_geometry_cursor") or {}
        if str(record.get("timeframe")) != "5" or snap.get("pattern") not in PATTERNS:
            continue
        if not (geo.get("upper_line") and geo.get("lower_line")) or str(cursor.get("timeframe")) != "1":
            continue
        if str(geo.get("robot_coordinate_timeframe")) != "1":
            continue
        as_of = _ms(record["created_at"])
        if as_of + OBSERVE_MS + 15 * 60_000 > now_ms:
            continue
        key = (record["symbol"], snap.get("scanner_formation_id"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "candidate_id": record["candidate_id"], "symbol": record["symbol"],
            "pattern": snap["pattern"], "as_of_ms": as_of,
            "cursor_index": int(cursor["geometry_index"]),
            "cursor_time_ms": int(cursor["source_candle_time_ms"]),
            "upper": {k: float(geo["upper_line"][k]) for k in ("slope", "intercept")},
            "lower": {k: float(geo["lower_line"][k]) for k in ("slope", "intercept")},
            "apex_time_ms": int(cursor["source_candle_time_ms"])
            + int((float(geo["apex"]["index"]) - int(cursor["geometry_index"])) * FINE_MS),
        })
    rows.sort(key=lambda r: r["as_of_ms"])
    return rows


def select_sample(rows: list[dict]) -> list[dict]:
    """All BRUSDT (owner priority) + evenly spaced chronological others."""

    br = [r for r in rows if r["symbol"] == "BRUSDT"]
    others = [r for r in rows if r["symbol"] != "BRUSDT"]
    need = max(SAMPLE_SIZE - len(br), 0)
    step = max(len(others) / need, 1.0) if need else 1.0
    picked = [others[int(i * step)] for i in range(min(need, len(others)))]
    return sorted(br + picked, key=lambda r: r["as_of_ms"])


def boundaries(row: dict) -> list[Boundary]:
    out = []
    for side in ("upper", "lower"):
        line = row[side]
        anchor_price = line["slope"] * row["cursor_index"] + line["intercept"]
        out.append(Boundary(f"{row['candidate_id']}:{side}", row["cursor_time_ms"], anchor_price,
                            line["slope"] / FINE_MS, row["as_of_ms"]))
    return out


def fetch(symbol: str, interval: str, start: int, end: int, cache: Path) -> list[list]:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    query = urllib.parse.urlencode({"category": "linear", "symbol": symbol, "interval": interval,
                                    "start": start, "end": end, "limit": 1000})
    with urllib.request.urlopen(f"{KLINE_URL}?{query}", timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    time.sleep(REQUEST_PAUSE_S)
    if payload.get("retCode") != 0:
        raise RuntimeError(f"kline {symbol} {interval}: {payload.get('retMsg')}")
    rows = payload["result"]["list"]
    cache.write_text(json.dumps({"fetched_ms": int(time.time() * 1000), "rows": rows}), encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def candles(raw: dict, interval_ms: int) -> list[dict]:
    out = []
    for start, o, h, l, c, *_ in raw["rows"]:
        start = int(start)
        if start + interval_ms > raw["fetched_ms"]:
            continue  # not closed when fetched
        out.append({"open_time_ms": start, "close_time_ms": start + interval_ms, "open": float(o),
                    "high": float(h), "low": float(l), "close": float(c), "closed": True})
    out.sort(key=lambda c: c["open_time_ms"])
    return out


def breakout_of(boundary: Boundary, coarse: list[dict]):
    state, _ = initialize_state(boundary)
    for candle in coarse:
        state, _ = process_closed_candle(boundary, state, candle)
        if state["phase"] == PHASE_CAMPAIGN_ACTIVE or state["phase"] in TERMINAL_PHASES or state["data_blocked"]:
            break
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    klines = args.out / "klines"
    klines.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)

    pool = load_candidates(args.candidates, now_ms)
    sample = select_sample(pool)
    grid = [Candidate(p, m) for p in ATR_PERIODS for m in MULTIPLIERS]
    cases, skipped = [], []
    for row in sample:
        start = row["as_of_ms"] - WARMUP_COARSE * COARSE_MS
        end = row["as_of_ms"] + OBSERVE_MS
        try:
            coarse = candles(fetch(row["symbol"], "5", start, end,
                                   klines / f"{row['candidate_id']}_5.json"), COARSE_MS)
            fine = []
            for part, (a, b) in enumerate([(row["as_of_ms"], row["as_of_ms"] + 999 * FINE_MS),
                                           (row["as_of_ms"] + 1000 * FINE_MS, end)]):
                fine += candles(fetch(row["symbol"], "1", a, b,
                                      klines / f"{row['candidate_id']}_1_{part}.json"), FINE_MS)
        except Exception as exc:  # network / exchange data problems exclude the case
            skipped.append({"candidate_id": row["candidate_id"], "reason": f"fetch: {exc}"})
            continue
        for boundary in boundaries(row):
            try:
                state = breakout_of(boundary, coarse)
            except NakedRetestError as exc:
                skipped.append({"boundary_id": boundary.boundary_id, "reason": f"data: {exc}"})
                continue
            if state["data_blocked"]:
                skipped.append({"boundary_id": boundary.boundary_id, "reason": "coarse data gap"})
                continue
            if state["breakout"] is None:
                skipped.append({"boundary_id": boundary.boundary_id, "reason": "no naked breakout"})
                continue
            if state["breakout"]["open_time_ms"] >= row["apex_time_ms"]:
                skipped.append({"boundary_id": boundary.boundary_id, "reason": "breakout after apex"})
                continue
            ref = reference_touch(boundary, state["breakout"]["direction"],
                                  state["breakout"]["close_time_ms"], fine)
            cases.append({"row": row, "boundary": boundary, "coarse": coarse, "ref": ref,
                          "breakout": state["breakout"]})

    cases.sort(key=lambda c: c["row"]["as_of_ms"])
    split = cases[len(cases) // 2]["row"]["as_of_ms"] if cases else None
    results, sheet = {}, []
    atr_cache = {}
    for candidate in grid:
        per_case = []
        for case in cases:
            outcome = evaluate_case(CalibrationCase(case["boundary"], tuple(case["coarse"])), candidate)
            label = label_detection(outcome, case["ref"], COARSE_MS)
            half = "train" if case["row"]["as_of_ms"] < split else "test"
            per_case.append((half, label))
            if label[0] == LABEL_UNLABELED_NEAR_MISS:
                key = (case["boundary"].boundary_id, candidate.atr_period)
                if key not in atr_cache:
                    atr_cache[key] = causal_atr_series(case["coarse"], candidate.atr_period)
                index = next(i for i, c in enumerate(case["coarse"])
                             if c["close_time_ms"] == outcome["retest_close_time_ms"])
                bar = case["coarse"][index]
                lo, hi = (case["boundary"].price_at(bar["open_time_ms"]),
                          case["boundary"].price_at(bar["close_time_ms"]))
                gap = (bar["low"] - min(lo, hi)) if case["breakout"]["direction"] == "UP" \
                    else (max(lo, hi) - bar["high"])
                sheet.append({"boundary_id": case["boundary"].boundary_id, "symbol": case["row"]["symbol"],
                              "atr_period": candidate.atr_period, "multiplier": candidate.multiplier,
                              "detection_close_time_ms": outcome["retest_close_time_ms"],
                              "gap_price": gap, "gap_atr": gap / atr_cache[key][index],
                              "reference": case["ref"]["status"],
                              "reference_touch_close_time_ms": case["ref"].get("touch_close_time_ms"),
                              "owner_label": None})
        results[f"{candidate.atr_period}x{candidate.multiplier}"] = {
            "all": summarize_labels([label for _, label in per_case]),
            "train": summarize_labels([label for half, label in per_case if half == "train"]),
            "test": summarize_labels([label for half, label in per_case if half == "test"]),
        }

    reasons = {}
    for item in skipped:
        reasons[item["reason"].split(":")[0]] = reasons.get(item["reason"].split(":")[0], 0) + 1
    summary = {
        "generated_ms": now_ms,
        "pool_candidates": len(pool), "sampled_candidates": len(sample),
        "brusdt_candidates": sum(r["symbol"] == "BRUSDT" for r in sample),
        "boundaries_with_naked_breakout": len(cases),
        "brusdt_boundaries_with_naked_breakout": sum(c["row"]["symbol"] == "BRUSDT" for c in cases),
        "split_as_of_ms": split,
        "reference_status": {s: sum(c["ref"]["status"] == s for c in cases)
                             for s in {c["ref"]["status"] for c in cases}},
        "skipped_reasons": reasons,
        "results": results,
        "manifest": [{"boundary_id": c["boundary"].boundary_id, "symbol": c["row"]["symbol"],
                      "pattern": c["row"]["pattern"], "as_of_ms": c["row"]["as_of_ms"],
                      "anchor_time_ms": c["boundary"].anchor_time_ms,
                      "anchor_price": c["boundary"].anchor_price,
                      "slope_per_ms": c["boundary"].slope_per_ms,
                      "breakout_direction": c["breakout"]["direction"],
                      "breakout_close_time_ms": c["breakout"]["close_time_ms"],
                      "reference": c["ref"]} for c in cases],
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (args.out / "near_miss_labeling_sheet.json").write_text(json.dumps(sheet, indent=1), encoding="utf-8")
    (args.out / "skipped.json").write_text(json.dumps(skipped, indent=1), encoding="utf-8")
    events = {}
    for item in sheet:
        key = (item["boundary_id"], item["detection_close_time_ms"])
        event = events.setdefault(key, {**{k: item[k] for k in (
            "boundary_id", "symbol", "detection_close_time_ms", "gap_price", "reference",
            "reference_touch_close_time_ms")}, "fired_by": [], "owner_label": ""})
        event["fired_by"].append(f"{item['atr_period']}x{item['multiplier']}")
    lines = ["boundary_id,symbol,detection_close_utc,gap_price,reference,reference_touch_utc,"
             "lead_minutes,fired_by,owner_label(RETEST|NOT_RETEST)"]
    utc = lambda ms: "" if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
    for event in sorted(events.values(), key=lambda e: e["detection_close_time_ms"]):
        touch = event["reference_touch_close_time_ms"]
        lead = "" if touch is None else str((touch - event["detection_close_time_ms"]) // 60_000)
        lines.append(",".join([event["boundary_id"], event["symbol"], utc(event["detection_close_time_ms"]),
                               f"{event['gap_price']:.10g}", event["reference"], utc(touch), lead,
                               " ".join(event["fired_by"]), ""]))
    (args.out / "near_miss_events.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("results", "manifest")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
