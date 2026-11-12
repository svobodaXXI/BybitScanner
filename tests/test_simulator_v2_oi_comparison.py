"""One verified-source comparison; three independent protected virtual runs."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from research.simulator_v2.wedge_backtest import WedgeBacktestResult
from research.simulator_v2.wedge_cli import compare_oi_virtual_runs


def candidate(*, mode: str, run_id: str, source: str = "PINNED_SOURCE"):
    report = SimpleNamespace(
        symbol="BTCUSDT", source_id=source, chunk_sha256=("chunk-sha",),
        first_open_ms=0, last_closed_ms=600000,
        initial_balance=Decimal("1000"), namespace="SIMULATION",
        simulation_run_id=run_id,
        virtual_fills=2 if mode != "FALLING" else 0,
        total_fees=Decimal("0.1") if mode != "FALLING" else Decimal("0"),
        total_net_pnl=Decimal("3.8") if mode != "FALLING" else Decimal("0"),
        return_percent=Decimal("0.38") if mode != "FALLING" else Decimal("0"),
        max_drawdown_percent=Decimal("0.2") if mode != "FALLING" else Decimal("0"),
        final_position_quantity=Decimal("0"),
    )
    return WedgeBacktestResult(
        report=report, requested_start_ms=0, requested_end_inclusive_ms=540000,
        market_warmup_start_ms=0, scanner_wedge_observations=2,
        robot_retests_in_period=1, submitted_protected_limits=1 if mode != "FALLING" else 0,
        skipped_busy_entries=0, stop_exits=0,
        take_exits=1 if mode != "FALLING" else 0,
        pending_protection=False, archive_proofs=(),
        paper_flow_gate_enabled=True, paper_oi_mode=mode,
        paper_oi_sha256=("f"*64 if mode != "OFF" else None),
        paper_oi_rejected_retests=1 if mode == "FALLING" else 0,
    )


class ThreeWayOiVirtualComparisonTests(TestCase):
    def test_three_modes_share_source_but_keep_independent_runs_and_accounting(self):
        with TemporaryDirectory() as td:
            raw, oi = Path(td) / "trades", Path(td) / "BTCUSDT.csv"
            raw.mkdir()
            oi.write_text("fixture", encoding="utf-8")
            calls = []
            config = {"simulation_run_id": "owner_oi", "oi_mode": "FALLING"}

            def replay(**kwargs):
                mode = kwargs["config"]["oi_mode"]
                run_id = kwargs["config"]["simulation_run_id"]
                calls.append((mode, run_id))
                self.assertEqual(kwargs["flow_archive_dir"], raw)
                self.assertEqual(kwargs["oi_history_path"], oi)
                return candidate(mode=mode, run_id=run_id)

            with patch(
                "research.simulator_v2.wedge_cli.run_from_time_machine_config",
                side_effect=replay,
            ):
                result = compare_oi_virtual_runs(
                    config=config, manifest={}, cache_dir=Path(td),
                    latest_closed_boundary_ms=600000,
                    flow_archive_dir=raw, oi_history_path=oi,
                )
            self.assertEqual([row["oi_mode"] for row in result["cohorts"]],
                             ["OFF", "RISING", "FALLING"])
            self.assertEqual(len({r for _, r in calls}), 3)
            self.assertEqual(result["cohorts"][0]["total_net_pnl"], "3.8")
            self.assertEqual(result["cohorts"][2]["virtual_fills"], 0)
            self.assertEqual(result["cohorts"][2]["oi_rejected_retests"], 1)
            self.assertEqual(result["oi_source_sha256"], "f"*64)
            self.assertEqual(result["mode"], "THREE_WAY_PROTECTED_VIRTUAL_OI_COMPARISON")
            self.assertEqual(config["oi_mode"], "FALLING")  # unchanged owner input

    def test_mismatched_raw_source_is_rejected_instead_of_comparing_pnl(self):
        with TemporaryDirectory() as td:
            raw, oi = Path(td) / "trades", Path(td) / "BTCUSDT.csv"
            raw.mkdir()
            oi.write_text("fixture", encoding="utf-8")
            idx = 0

            def replay(**kwargs):
                nonlocal idx
                idx += 1
                return candidate(
                    mode=kwargs["config"]["oi_mode"],
                    run_id=kwargs["config"]["simulation_run_id"],
                    source="PINNED_SOURCE" if idx == 1 else "OTHER_SOURCE",
                )

            with patch(
                "research.simulator_v2.wedge_cli.run_from_time_machine_config",
                side_effect=replay,
            ):
                with self.assertRaisesRegex(ValueError, "different source"):
                    compare_oi_virtual_runs(
                        config={"simulation_run_id": "compare"},
                        manifest={}, cache_dir=Path(td),
                        latest_closed_boundary_ms=600000,
                        flow_archive_dir=raw, oi_history_path=oi,
                    )

    def test_missing_pinned_inputs_never_start_any_virtual_run(self):
        with TemporaryDirectory() as td:
            with patch(
                "research.simulator_v2.wedge_cli.run_from_time_machine_config"
            ) as replay:
                with self.assertRaisesRegex(ValueError, "requires local raw tape"):
                    compare_oi_virtual_runs(
                        config={"simulation_run_id": "compare"},
                        manifest={}, cache_dir=Path(td),
                        latest_closed_boundary_ms=600000,
                        flow_archive_dir=Path(td) / "missing",
                        oi_history_path=Path(td) / "missing.csv",
                    )
                replay.assert_not_called()
