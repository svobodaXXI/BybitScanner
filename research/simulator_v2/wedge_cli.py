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
from research.simulator_v2.frozen_level_backtest import (
    FrozenLevelBacktestResult, run_cached_frozen_level_trade_range,
)

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
    "L_SHAPE": "L_SHAPE",
    "DOUBLE_TOP": "DOUBLE_TOP",
    "DOUBLE_BOTTOM": "DOUBLE_BOTTOM",
}
NATIVE_LEVEL_IDS = frozenset({"L_SHAPE", "DOUBLE_TOP", "DOUBLE_BOTTOM"})
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
) -> WedgeBacktestResult | BoxBacktestResult | FrozenLevelBacktestResult:
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
        raise ValueError("only implemented native Scanner/Robot strategies may trade")
    box_selected = "IKIGAI_BOX" in selected
    level_selected = set(selected) & NATIVE_LEVEL_IDS
    if (box_selected and len(selected) != 1) or (
        level_selected and len(level_selected) != len(selected)
    ):
        raise ValueError("native Robot families need separate single-owner symbol runs")
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
    if level_selected:
        return run_cached_frozen_level_trade_range(
            cache_dir=cache_dir, symbol=symbol, proofs=proofs,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
            simulation_run_id=config["simulation_run_id"],
            initial_balance=_decimal_string(config.get("initial_balance"), "initial_balance"),
            start_ms=start_ms, end_inclusive_ms=end_ms,
            selected=frozenset(level_selected),
            scanner_window_bars=scanner_config.window_bars,
            settings=settings,
            capture_replay=capture_replay,
            on_replay_events=on_replay_events,
        )
    if box_selected:
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
        robot_config=SimWedgeRobotConfig(
            selected_patterns=patterns, tick_size=settings.tick_size,
        ),
        risk_settings=settings,
        capture_replay=capture_replay,
        on_replay_events=on_replay_events,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline local Wedge/Box Bybit public-trade research; NO PAPER/LIVE",
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    args = parser.parse_args()
    from research.simulator_v2.history import last_closed_m1_boundary_ms
    try:
        config = _read_json(args.config, max_bytes=MAX_CONFIG_BYTES)
        manifest = _read_json(args.manifest, max_bytes=MAX_MANIFEST_BYTES)
        result = run_from_time_machine_config(
            config=config, manifest=manifest,
            cache_dir=args.cache_dir,
            latest_closed_boundary_ms=last_closed_m1_boundary_ms(),
        )
    except (ValueError, FileNotFoundError, TypeError, KeyError) as exc:
        parser.error(f"BLOCKED: {exc}")
    payload = result.to_payload()
    payload["risk_terms_source"] = config["risk"]["terms_source"]
    payload["risk_terms_status"] = "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED"
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
