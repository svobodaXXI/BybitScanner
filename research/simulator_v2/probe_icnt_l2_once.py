"""One bounded offline ICNT historical L2+trade Robot replay, without runtime IO.

Execution is local SIMULATION only. On any uncertainty, emit a BLOCKED receipt
instead of silently switching to OHLC or executing a second/repaired scenario.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

SYMBOL = "ICNTUSDT"
DAY = date(2026, 11, 10)
DAY_START_MS = 1794268800000
DAY_END_MS = 1794355200000
L2_SHA = "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df"
TRADE_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a"
M1_SHA = "8f0b7d83c81df43114d5cf89214eeaba7a454a519021df3b4628fca4ea09834b"
START_MS = DAY_START_MS + 8 * 3_600_000
END_INCLUSIVE_MS = DAY_START_MS + 8 * 3_600_000 + 15 * 60_000


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            h.update(chunk)
    return h.hexdigest()


def run(l2: Path, bundle: Path, output_dir: Path, repo: Path, code_sha: str,
        *, compare_partials: bool = False, capture_replay: bool = False) -> dict:
    if (not repo.is_dir() or not (repo / "AGENTS.md").is_file()
            or repo.is_symlink() or l2.is_symlink() or bundle.is_symlink()):
        raise ValueError("pinned local repository and original non-symlink archives required")
    installed = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if installed != code_sha:
        raise ValueError("pinned code SHA mismatch")
    if not l2.is_file() or digest(l2) != L2_SHA:
        raise ValueError("original L2 archive SHA mismatch")
    if not bundle.is_file():
        raise FileNotFoundError("original ICNT trade bundle missing")
    source_dir = output_dir / "raw"
    cache_dir = output_dir / "cache"
    if source_dir.exists() or cache_dir.exists():
        raise ValueError("output already contains input/cache; no overwrite")
    source_dir.mkdir()
    cache_dir.mkdir()
    raw_path = source_dir / "ICNTUSDT2026-11-10.csv.gz"
    if bundle.name.endswith(".csv.gz"):
        if digest(bundle) != TRADE_SHA:
            raise ValueError("trade gzip SHA mismatch")
        shutil.copyfile(bundle, raw_path)
    elif bundle.suffix == ".zip":
        with zipfile.ZipFile(bundle) as z:
            info = z.getinfo(raw_path.name)
            if not 0 < info.file_size <= 128_000_000:
                raise ValueError("trade bundle member invalid or oversized")
            with z.open(info) as src, raw_path.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1_048_576)
    else:
        raise ValueError("only pinned original trade ZIP or gzip supported")
    if digest(raw_path) != TRADE_SHA:
        raise ValueError("original trade archive SHA mismatch")

    sys.path.insert(0, str(repo))
    from research.simulator_v2.trade_range import import_local_trade_range
    from research.simulator_v2.wedge_backtest import run_cached_wedge_trade_range
    from research.simulator_v2.wedge_observer import WedgeScannerConfig
    from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
    from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
    from research.simulator_v2.virtual_exchange import L2PartialTakePolicy

    proof = import_local_trade_range(
        archive_dir=source_dir, cache_dir=cache_dir, symbol=SYMBOL,
        start_day=DAY, days=1, latest_closed_boundary_ms=DAY_END_MS,
    )
    if len(proof) != 1 or proof[0].raw_archive_sha256 != TRADE_SHA or proof[0].m1_sha256 != M1_SHA:
        raise ValueError("pinned original derived M1 proof mismatch")
    scanner = WedgeScannerConfig(window_bars=100, mode="hunter", min_score=50)
    robot = SimWedgeRobotConfig(
        selected_patterns=frozenset(("Falling Wedge", "Rising Wedge")),
        tick_size=Decimal("0.0001"),
    )
    risk = SimWedgeRiskSettings(
        tick_size=Decimal("0.0001"),
        contracts_per_working_volume=Decimal("1000"),
        quantity_step=Decimal("1"), minimum_quantity=Decimal("1"),
        max_notional_usdt=Decimal("1000"), max_risk_usdt=Decimal("50"),
        entry_fee_rate=Decimal("0.0006"), exit_fee_rate=Decimal("0.0006"),
    )
    if compare_partials and capture_replay:
        raise ValueError("one replay scenario per receipt; compare and visualization are distinct")
    policy_specs = [("BASE", None)]
    if compare_partials:
        policy_specs.extend((
            (f"{int(fraction * 100)}", L2PartialTakePolicy(
                potential_fraction=fraction,
                quantity_fraction=Decimal("0.25"),
                quantity_step=risk.quantity_step,
                tick_size=risk.tick_size,
            ))
            for fraction in (Decimal("0.25"), Decimal("0.50"), Decimal("0.75"))
        ))
    results = []
    for label, policy in policy_specs:
        try:
            result = run_cached_wedge_trade_range(
                cache_dir=cache_dir, symbol=SYMBOL, proofs=proof,
                latest_closed_boundary_ms=DAY_END_MS,
                simulation_run_id=f"icnt_l2_20261110_0800_0815_{label.lower()}",
                initial_balance=Decimal("1000"),
                start_ms=START_MS, end_inclusive_ms=END_INCLUSIVE_MS,
                scanner_config=scanner, robot_config=robot, risk_settings=risk,
                taker_fee_rate=Decimal("0.0006"), maker_fee_rate=Decimal("0.0002"),
                flow_archive_dir=source_dir, oi_mode="OFF", impulse_mode=True,
                l2_archive_path=l2, l2_archive_sha256=L2_SHA, l2_depth=200,
                l2_partial_take_policy=policy,
                capture_replay=capture_replay,
            )
            if result.execution_model != "SIMULATION_HISTORICAL_TAKER_L2_EVENT_TIME_NOT_REAL_BYBIT_FILLS":
                raise ValueError("L2-only execution provenance not proven")
            if label == "BASE" and (
                result.report.realized_net_pnl != Decimal("-2.15403408000")
                or len(result.l2_episodes) != 4
                or result.report.final_position_quantity != 0
            ):
                raise ValueError("baseline regression against owner-verified ICNT L2 run")
            results.append({
                "threshold_percent": label, "state": "CONDITIONAL_VIRTUAL_L2",
                "result": result.to_payload(),
            })
        except Exception as exc:
            if label == "BASE":
                raise
            results.append({
                "threshold_percent": label, "state": "BLOCKED",
                "reason": f"{type(exc).__name__}:{exc}",
                "no_fallback": True, "counterfactual_pnl_usdt": None,
            })
    if compare_partials:
        return {
            "state": "VIRTUAL_L2_PARTIAL_BE_COMPARISON_CONDITIONAL",
            "scenario": "SIMULATION_ONLY_THREE_FROZEN_THRESHOLDS",
            "code_sha": code_sha,
            "l2_sha256": L2_SHA, "trade_gzip_sha256": TRADE_SHA,
            "start_ms": START_MS, "end_inclusive_ms": END_INCLUSIVE_MS,
            "partial_share": "0.25",
            "baseline_realized_net_pnl_usdt": "-2.15403408000",
            "not_real_exchange_execution": True,
            "scenarios": results,
        }
    result = results[0]["result"]
    return {
        "state": (
            "VIRTUAL_L2_PROBE_CONDITIONAL"
            if result["l2_unproven_entry_depth_count"] or result["l2_deferred_stop_count"]
            else "VIRTUAL_L2_PROBE_COMPLETED"
        ),
        "scenario": "ONE_BOUNDED_LOCAL_SIMULATION_NOT_REAL_BYBIT_EXECUTIONS",
        "code_sha": code_sha,
        "l2_sha256": L2_SHA, "trade_gzip_sha256": TRADE_SHA,
        "start_ms": START_MS, "end_inclusive_ms": END_INCLUSIVE_MS,
        "execution_model": result["execution_model"],
        "result": result,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--l2", required=True, type=Path)
    p.add_argument("--trades", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--code-sha", required=True)
    p.add_argument("--compare-partials", action="store_true",
                   help="SIMULATION-only 25/50/75 percent potential thresholds")
    p.add_argument("--capture-replay", action="store_true",
                   help="one causal baseline L2 event-time visual replay; no alternative fills")
    args = p.parse_args()
    if not args.output.is_dir() or args.output.is_symlink():
        raise SystemExit("BLOCKED: new dedicated existing output directory required")
    target = args.output / "ICNT_L2_one_shot_result.json"
    if target.exists():
        raise SystemExit("BLOCKED: refusing to overwrite output")
    try:
        receipt = run(
            args.l2, args.trades, args.output, args.repo, args.code_sha,
            compare_partials=args.compare_partials,
            capture_replay=args.capture_replay,
        )
    except Exception as exc:
        receipt = {
            "state": "BLOCKED",
            "reason_type": type(exc).__name__, "reason": str(exc),
            "code_sha": args.code_sha, "l2_sha256": L2_SHA,
            "trade_gzip_sha256": TRADE_SHA,
            "start_ms": START_MS, "end_inclusive_ms": END_INCLUSIVE_MS,
            "no_ohlc_fallback": True, "no_retries": True,
            "no_trading_runtime": True,
        }
    target.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print("RESULT=" + str(target))
    print("STATUS=" + receipt["state"])
    if receipt["state"] == "BLOCKED":
        print("BLOCKER=" + receipt["reason_type"] + ":" + receipt["reason"])
    elif args.compare_partials:
        for scenario in receipt["scenarios"]:
            label = scenario["threshold_percent"]
            if scenario["state"] == "BLOCKED":
                print(f"SCENARIO_{label}=BLOCKED {scenario['reason']}")
                continue
            result = scenario["result"]
            print(
                f"SCENARIO_{label}=CONDITIONAL "
                f"net_usdt={result['realized_net_pnl']} "
                f"fills={result['virtual_fills']} "
                f"partial={result['l2_partial_take_fills']} "
                f"be_stop={result['l2_be_stop_amendments']} "
                f"entry_depth_unknown={result['l2_unproven_entry_depth_count']} "
                f"partial_depth_unknown={result['l2_partial_depth_unproven_count']} "
                f"position={result['final_position_quantity']}"
            )
        print("REAL_EXCHANGE_PARITY=UNPROVEN")
    else:
        result = receipt["result"]
        rows = result.get("l2_episodes", [])
        print("EPISODES=" + str(len(rows)))
        print("EXECUTION_CERTAINTY=" + str(result.get("execution_certainty")))
        for i, row in enumerate(rows, 1):
            flags = ",".join(row["evidence_flags"]) or "MODEL_ONLY"
            print(
                f"TRADE_{i}={row['direction']} "
                f"entry_ms={row['entry_ms']} entry={row['entry_price']} "
                f"exit_ms={row['exit_ms']} exit={row['exit_price']} "
                f"reason={row['exit_reason']} "
                f"stop={row['planned_stop_price']} take={row['planned_take_price']} "
                f"net_usdt={row['net_pnl_usdt']} flags={flags}"
            )
        print("NET_PNL_USDT=" + str(result["realized_net_pnl"]))
        print("PENDING_PROTECTION=" + str(result["pending_protection"]))
        if args.capture_replay:
            visual = result.get("replay")
            if not isinstance(visual, dict) or not isinstance(visual.get("events"), list):
                raise ValueError("historical L2 visual events missing from receipt")
            print("VISUAL_EVENTS=" + str(len(visual["events"])))
            print("VISUAL_EXECUTION_CLOCK=" + str(visual.get("execution_clock")))
            print("VISUAL_FILL_TIMES=" + ",".join(
                str(event["time_ms"]) for event in visual["events"]
                if event["kind"] in ("ENTRY_FILLED", "PARTIAL_FILLED", "EXIT_FILLED")
            ))


if __name__ == "__main__":
    main()
