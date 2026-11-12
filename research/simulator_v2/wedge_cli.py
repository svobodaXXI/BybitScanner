"""CLI/JSON boundary for Time Machine Wedge/Ikigai Box offline SIMULATION.

Inputs are untrusted *configuration*, NOT trading authorization.
All market candles are read from preverified Bybit PUBLIC TRADE-derived cache;
no downloader, account credentials, PAPER/LIVE or production Robot runtime.
Other strategies remain unsupported until their actual detector/Robot exists.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from research.simulator_v2.trade_range import TradeDayProof, _ordered_proofs
from robot_entry_flow_evidence import OI_MODES
from research.simulator_v2.wedge_backtest import (
    WedgeBacktestResult, run_cached_wedge_trade_range,
)
from research.simulator_v2.wedge_observer import WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from research.simulator_v2.box_backtest import (
    BoxBacktestResult, run_cached_box_trade_range,
)
from research.simulator_v2.ikigai_observer import IkigaiScannerConfig
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms

PROFILE_SCHEMA = "TIME_MACHINE_WEDGE_SIMULATION_V1"
MANIFEST_SCHEMA = "SIMULATOR_V2_PUBLIC_TRADES_DERIVED_M1_RANGE_V1"
RISK_FIELDS = (
    "tick_size", "contracts_per_working_volume", "quantity_step",
    "minimum_quantity", "max_notional_usdt", "max_risk_usdt",
    "entry_fee_rate", "exit_fee_rate",
)
SELECTABLE = {
    "WEDGE_FALLING": "Falling Wedge",
    "WEDGE_RISING": "Rising Wedge",
    "IKIGAI_BOX": "IKIGAI_BOX",
    "IMPULSE_FLOW": "IMPULSE_FLOW",
}
MAX_CONFIG_BYTES = 24_000
MAX_MANIFEST_BYTES = 125_000


def _read_json(path: Path, *, max_bytes: int) -> dict[str, Any]:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise ValueError("explicit local non-symlink input JSON required")
    with path.open("rb") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("SIMULATION config/manifest exceeds size bound")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("SIMULATION configuration must be a JSON object")
    return result


def parse_utc_minute(text: str) -> int:
    """Exact wall-clock UTC minute, independent of PC time zone and DST."""
    if not isinstance(text, str) or len(text) != 16:
        raise ValueError("UTC timestamp must be YYYY-MM-DDTHH:MM")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError("invalid UTC calendar date, hour or minute") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M") != text:
        raise ValueError("UTC timestamp not canonical")
    return int(parsed.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _decimal_string(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"explicit decimal string required for {label}")
    try:
        parsed = Decimal(value)
    except (ArithmeticError, ValueError) as exc:
        raise ValueError(f"invalid decimal in {label}") from exc
    if not parsed.is_finite():
        raise ValueError(f"non-finite numeric value in {label}")
    return parsed


def parse_manifest(
    manifest: Mapping[str, Any], *, latest_closed_boundary_ms: int,
) -> tuple[str, tuple[TradeDayProof, ...]]:
    """Validate exact persisted schema from public_trade_month_smoke.py."""
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("namespace") != "SIMULATION"
        or manifest.get("raw_trade_archives_embedded") is not False
    ):
        raise ValueError("not a verified public trade-derived M1 manifest")
    symbol = manifest.get("symbol")
    rows = manifest.get("day_provenance")
    if not isinstance(symbol, str) or not isinstance(rows, list):
        raise ValueError("manifest symbol/provenance missing")
    proofs: list[TradeDayProof] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid daily public trade provenance")
        try:
            proof = TradeDayProof(
                date.fromisoformat(row["utc_day"]),
                row["raw_archive_sha256"], row["m1_sha256"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid public trade provenance field") from exc
        if row != proof.to_payload(symbol=symbol):
            raise ValueError("public trade provenance URL/source/hash changed")
        proofs.append(proof)
    pinned = tuple(proofs)
    source_id, start_ms, end_ms = _ordered_proofs(
        pinned, symbol=symbol,
        latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if (
        type(manifest.get("days")) is not int
        or manifest["days"] != len(pinned)
        or manifest.get("start_day") != pinned[0].utc_day.isoformat()
        or type(manifest.get("start_ms")) is not int
        or type(manifest.get("end_ms")) is not int
        or manifest["start_ms"] != start_ms
        or manifest["end_ms"] != end_ms
        or manifest.get("source_id") != source_id
    ):
        raise ValueError("manifest does not match pinned daily source hashes")
    return symbol, pinned


def run_from_time_machine_config(
    *, config: Mapping[str, Any], manifest: Mapping[str, Any],
    cache_dir: Path, latest_closed_boundary_ms: int,
    capture_replay: bool = False,
    on_replay_events: Callable[[list[dict[str, object]]], None] | None = None,
    flow_archive_dir: Path | None = None,
    oi_history_path: Path | None = None,
) -> WedgeBacktestResult | BoxBacktestResult:
    """Dispatch one proven native strategy family into the shared exchange."""
    if not isinstance(config, Mapping) or (
        config.get("schema") != PROFILE_SCHEMA or config.get("namespace") != "SIMULATION"
    ):
        raise ValueError("invalid local strategy SIMULATION config schema")
    symbol, proofs = parse_manifest(
        manifest, latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if config.get("symbol") != symbol:
        raise ValueError("selected symbol differs from pinned Bybit source")
    selected = config.get("selected_strategies")
    if not isinstance(selected, list) or not selected or any(
        not isinstance(x, str) or x not in SELECTABLE for x in selected
    ) or len(set(selected)) != len(selected):
        raise ValueError("only implemented Wedge or Ikigai Box may trade")
    oi_mode = config.get("oi_mode", "OFF")
    if not isinstance(oi_mode, str) or oi_mode not in OI_MODES:
        raise ValueError("invalid OI research filter selection")
    impulse_selected = "IMPULSE_FLOW" in selected
    if impulse_selected and len(selected) != 1:
        raise ValueError("IMPULSE_FLOW trades must have isolated single-symbol strategy owner")
    if impulse_selected and flow_archive_dir is None:
        raise ValueError("IMPULSE_FLOW requires pinned original taker execution archive")
    box_selected = "IKIGAI_BOX" in selected
    if box_selected and len(selected) != 1:
        raise ValueError("Box and Wedge cannot share one symbol owner in the same run yet")
    patterns = frozenset(
        SELECTABLE[s] for s in selected if s != "IKIGAI_BOX"
    )
    scanner = config.get("scanner")
    risk = config.get("risk")
    if not isinstance(scanner, dict) or not isinstance(risk, dict):
        raise ValueError("explicit Scanner and virtual risk terms required")
    if set(scanner) != {"window_bars", "mode", "min_score"}:
        raise ValueError("exact original Scanner configuration required")
    if set(risk) != set(RISK_FIELDS) | {"terms_source"}:
        raise ValueError("exact local contract/risk fields required")
    if not isinstance(risk.get("terms_source"), str) or (
        not 1 <= len(risk["terms_source"]) <= 120
    ):
        raise ValueError("explicit risk assumptions provenance required")
    # The source string is recorded as a user-supplied research assumption.
    # It is never proof that Bybit instruments or available leverage agree.
    settings = SimWedgeRiskSettings(**{
        field: _decimal_string(risk[field], field) for field in RISK_FIELDS
    })
    score = scanner["min_score"]
    if type(score) not in (int, float):
        raise ValueError("numeric Scanner minimum score required")
    scanner_config = WedgeScannerConfig(
        window_bars=scanner["window_bars"], mode=scanner["mode"], min_score=score,
    )
    start_ms = parse_utc_minute(config.get("start_utc"))
    end_ms = parse_utc_minute(config.get("end_utc_inclusive"))
    if not isinstance(cache_dir, Path) or cache_dir.is_symlink():
        raise ValueError("dedicated local SIMULATION cache directory required")
    if flow_archive_dir is not None and (
        not isinstance(flow_archive_dir, Path) or flow_archive_dir.is_symlink()
    ):
        raise ValueError("explicit safe local taker archive directory required")
    if box_selected:
        if flow_archive_dir is not None or oi_mode != "OFF":
            raise ValueError("trade-flow and OI entry filters are available only for Wedge")
        return run_cached_box_trade_range(
            cache_dir=cache_dir, symbol=symbol, proofs=proofs,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
            simulation_run_id=config["simulation_run_id"],
            initial_balance=_decimal_string(config.get("initial_balance"), "initial_balance"),
            start_ms=start_ms, end_inclusive_ms=end_ms,
            scanner_config=IkigaiScannerConfig(
                window_bars=scanner_config.window_bars,
            ),
            terms=BoxSimulationRiskTerms(
                tick_size=settings.tick_size,
                working_quantity=settings.contracts_per_working_volume,
                quantity_step=settings.quantity_step,
                minimum_quantity=settings.minimum_quantity,
                maximum_notional_usdt=settings.max_notional_usdt,
                maximum_loss_usdt=settings.max_risk_usdt,
                entry_fee_rate=settings.entry_fee_rate,
                exit_fee_rate=settings.exit_fee_rate,
                adverse_stop_slippage_per_unit=Decimal("0"),
                additional_cost_allowance_usdt=Decimal("0"),
            ),
            capture_replay=capture_replay,
            on_replay_events=on_replay_events,
        )
    return run_cached_wedge_trade_range(
        cache_dir=cache_dir, symbol=symbol, proofs=proofs,
        latest_closed_boundary_ms=latest_closed_boundary_ms,
        simulation_run_id=config["simulation_run_id"],
        initial_balance=_decimal_string(config.get("initial_balance"), "initial_balance"),
        start_ms=start_ms, end_inclusive_ms=end_ms,
        scanner_config=scanner_config,
        robot_config=(None if impulse_selected else SimWedgeRobotConfig(
            selected_patterns=patterns, tick_size=settings.tick_size,
        )),
        risk_settings=settings,
        capture_replay=capture_replay,
        on_replay_events=on_replay_events,
        flow_archive_dir=flow_archive_dir,
        oi_mode=oi_mode,
        oi_history_path=oi_history_path,
        impulse_mode=impulse_selected,
    )



def compare_oi_virtual_runs(
    *, config: Mapping[str, Any], manifest: Mapping[str, Any],
    cache_dir: Path, latest_closed_boundary_ms: int,
    flow_archive_dir: Path, oi_history_path: Path,
) -> dict[str, object]:
    """Three sequential virtual Robot runs against EXACTLY the same pinned tape.

    Reuses the original Scanner/Robot, protected LIMIT, STOP/TAKE, fees and
    exchange. No alternate policy or order executor is added. This function
    NEVER fetches or repairs historical data and requires both authentic
    selected raw trades and a source-labeled local 5m OI file.
    """
    from research.simulator_v2.virtual_account import IDENTITY

    if (not isinstance(config, Mapping)
            or not isinstance(config.get("simulation_run_id"), str)
            or not IDENTITY.fullmatch(config["simulation_run_id"])
            or len(config["simulation_run_id"]) > 85):
        raise ValueError("safe base virtual run identity required")
    if (not isinstance(flow_archive_dir, Path) or flow_archive_dir.is_symlink()
            or not flow_archive_dir.is_dir()
            or not isinstance(oi_history_path, Path) or oi_history_path.is_symlink()
            or not oi_history_path.is_file()):
        raise ValueError("three-way virtual comparison requires local raw tape and 5m OI")
    source_key = None
    common_oi_sha = None
    cohorts = []
    for mode in ("OFF", "RISING", "FALLING"):
        candidate = run_from_time_machine_config(
            config={
                **config,
                "oi_mode": mode,
                "simulation_run_id": f"{config['simulation_run_id']}_oi_{mode.lower()}",
            },
            manifest=manifest, cache_dir=cache_dir,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
            flow_archive_dir=flow_archive_dir, oi_history_path=oi_history_path,
        )
        if not isinstance(candidate, WedgeBacktestResult):
            raise ValueError("three-way OI research requires original Wedge Robot")
        report = candidate.report
        if not candidate.paper_flow_gate_enabled or report.namespace != "SIMULATION":
            raise ValueError("comparison requires genuine protected virtual Robot entries")
        identity = (
            report.symbol, report.source_id, report.chunk_sha256,
            report.first_open_ms, report.last_closed_ms, report.initial_balance,
            candidate.requested_start_ms, candidate.requested_end_inclusive_ms,
            candidate.archive_proofs,
        )
        if source_key is None:
            source_key = identity
        elif identity != source_key:
            raise ValueError("OI cohorts used different source, period or virtual balance")
        sha = candidate.paper_oi_sha256
        if mode != "OFF":
            if not sha or (common_oi_sha is not None and sha != common_oi_sha):
                raise ValueError("OI cohorts used missing or mismatched OI history")
            common_oi_sha = sha
        cohorts.append({
            "oi_mode": mode,
            "simulation_run_id": report.simulation_run_id,
            "virtual_fills": report.virtual_fills,
            "submitted_protected_limits": candidate.submitted_protected_limits,
            "stop_exits": candidate.stop_exits, "take_exits": candidate.take_exits,
            "oi_rejected_retests": candidate.paper_oi_rejected_retests,
            "flow_rejected_retests": candidate.paper_flow_rejected_retests,
            "total_fees": str(report.total_fees),
            "total_net_pnl": str(report.total_net_pnl),
            "realized_net_pnl": str(report.realized_net_pnl),
            "unrealized_pnl": str(report.unrealized_pnl),
            "impulse_signals": candidate.impulse_signals,
            "impulse_risk_rejections": candidate.impulse_risk_rejections,
            "return_percent": str(report.return_percent),
            "max_drawdown_percent": str(report.max_drawdown_percent),
            "open_position_quantity": str(report.final_position_quantity),
            "pending_protection": candidate.pending_protection,
        })
    return {
        "namespace": "SIMULATION",
        "mode": "THREE_WAY_PROTECTED_VIRTUAL_OI_COMPARISON",
        "symbol": source_key[0], "trade_source_id": source_key[1],
        "oi_source_sha256": common_oi_sha,
        "requested_start_ms": source_key[6],
        "requested_end_inclusive_ms": source_key[7],
        "cohorts": cohorts,
        "claim": "RESEARCH_ONLY_NO_PROVEN_PROFITABILITY",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline local Wedge/Box Bybit public-trade research; NO PAPER/LIVE",
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--flow-archive-dir", type=Path, default=None,
                        help="optional pinned raw Bybit trades for Wedge virtual entries")
    parser.add_argument("--oi-history-csv", type=Path, default=None,
                        help="local {SYMBOL}.csv from historical Bybit 5m OI")
    parser.add_argument("--oi-mode", choices=sorted(OI_MODES), default="OFF")
    parser.add_argument("--compare-oi", action="store_true",
                        help="run OFF, RISING and FALLING with the SAME virtual Robot and source")
    args = parser.parse_args()
    from research.simulator_v2.history import last_closed_m1_boundary_ms
    try:
        config = _read_json(args.config, max_bytes=MAX_CONFIG_BYTES)
        manifest = _read_json(args.manifest, max_bytes=MAX_MANIFEST_BYTES)
        if args.compare_oi:
            if args.oi_mode != "OFF":
                raise ValueError("compare-oi selects all three OI modes itself")
            payload = compare_oi_virtual_runs(
                config=config, manifest=manifest, cache_dir=args.cache_dir,
                latest_closed_boundary_ms=last_closed_m1_boundary_ms(),
                flow_archive_dir=args.flow_archive_dir,
                oi_history_path=args.oi_history_csv,
            )
        else:
            result = run_from_time_machine_config(
                config={**config, "oi_mode": args.oi_mode}, manifest=manifest,
                cache_dir=args.cache_dir,
                latest_closed_boundary_ms=last_closed_m1_boundary_ms(),
                flow_archive_dir=args.flow_archive_dir,
                oi_history_path=args.oi_history_csv,
            )
            payload = result.to_payload()
    except (ValueError, FileNotFoundError, TypeError, KeyError) as exc:
        parser.error(f"BLOCKED: {exc}")
    payload["risk_terms_source"] = config["risk"]["terms_source"]
    payload["risk_terms_status"] = "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED"
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
