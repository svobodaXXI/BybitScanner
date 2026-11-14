"""Checksum-pinned Bybit taker-tape auto-feed into the original Simulator Wedge run."""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from research.simulator_v2.taker_flow_archive import pinned_taker_minutes
from research.simulator_v2.trade_range import import_local_trade_range
from research.simulator_v2.wedge_backtest import run_cached_wedge_trade_range
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner, WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
from tests.test_simulator_v2_trade_archive import (
    END, START, UTC_DAY, records, write_archive,
)
from tests.test_simulator_v2_wedge_risk_flow import risk_settings

M = 60_000
SYMBOL = "BTCUSDT"


def config(cache, proofs, archive=None):
    return dict(
        cache_dir=cache, symbol=SYMBOL, proofs=proofs,
        latest_closed_boundary_ms=END, simulation_run_id="tape-paper",
        initial_balance=D("1000"),
        start_ms=START + 120 * M, end_inclusive_ms=START + 123 * M,
        scanner_config=WedgeScannerConfig(window_bars=50, mode="hunter", min_score=50),
        robot_config=SimWedgeRobotConfig(
            selected_patterns=frozenset({"Falling Wedge"}),
            tick_size=D("0.01"),
        ),
        risk_settings=risk_settings(), flow_archive_dir=archive,
    )


class PinnedTakerFlowReplayTests(TestCase):
    def test_reversed_raw_archive_feeds_shared_robot_virtual_entry_filter(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "raw"
            archive.mkdir()
            raw_rows = records()
            # 00:121: strong taker buyers + effective positive price response.
            raw_rows[2*121]["size"] = "20"
            raw_rows[2*121+1]["size"] = "1"
            path = write_archive(archive, list(reversed(raw_rows)))
            cache = root / "cache"
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=cache, symbol=SYMBOL,
                start_day=UTC_DAY, days=1,
                latest_closed_boundary_ms=END,
            )
            selected = pinned_taker_minutes(
                archive_dir=archive, symbol=SYMBOL, proofs=proofs,
                start_ms=START + 120*M, end_ms=START + 124*M,
                latest_closed_boundary_ms=END,
            )
            self.assertEqual(len(selected), 4)
            first = selected[START+121*M]
            self.assertEqual([p.side for p in first], ["Buy", "Sell"])
            self.assertEqual(first[0].size_base, D("20"))

            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                result = run_cached_wedge_trade_range(**config(cache, proofs, archive))
            report = result.to_payload()
            entry = report["paper_flow_entry"]
            self.assertEqual(entry["execution"], "EXISTING_PROTECTED_VIRTUAL_EXCHANGE")
            self.assertEqual(entry["oi_mode"], "OFF")
            self.assertEqual(entry["permitted_retests"], 0)
            self.assertEqual(result.report.virtual_fills, 0)
            self.assertEqual(result.report.total_net_pnl, D("0"))

            # Default candle-only behavior remains valid without a raw archive.
            path.unlink()
            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                without_raw = run_cached_wedge_trade_range(
                    **config(cache, proofs, None),
                )
            self.assertNotIn("paper_flow_entry", without_raw.to_payload())
            self.assertEqual(without_raw.report, result.report)
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                run_cached_wedge_trade_range(**config(cache, proofs, archive))

    def test_tampered_sha_and_side_free_archive_fail_closed(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "raw"
            archive.mkdir()
            path = write_archive(archive, records())
            cache = root / "cache"
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=cache, symbol=SYMBOL,
                start_day=UTC_DAY, days=1, latest_closed_boundary_ms=END,
            )
            write_archive(archive, records()[::-1])
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                pinned_taker_minutes(
                    archive_dir=archive, symbol=SYMBOL, proofs=proofs,
                    start_ms=START + 120*M, end_ms=START + 123*M,
                    latest_closed_boundary_ms=END,
                )

            rows = records()
            for row in rows:
                del row["side"]
            write_archive(archive, rows)
            proof_no_side = import_local_trade_range(
                archive_dir=archive, cache_dir=root / "cache-no-side",
                symbol=SYMBOL, start_day=UTC_DAY, days=1,
                latest_closed_boundary_ms=END,
            )
            with self.assertRaisesRegex(ValueError, "invalid Bybit public execution identity/time/side"):
                pinned_taker_minutes(
                    archive_dir=archive, symbol=SYMBOL,
                    proofs=proof_no_side, start_ms=START + 120*M,
                    end_ms=START + 123*M, latest_closed_boundary_ms=END,
                )
            self.assertTrue(path.is_file())

    def test_missing_focused_minute_and_memory_budget_fail_without_tape(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "raw"
            archive.mkdir()
            rows = [
                row for i, row in enumerate(records())
                if i // 2 != 122
            ]
            write_archive(archive, rows)
            # Pin directly to the raw file SHA to exercise the tape's own
            # integrity checks without pretending missing candles are valid.
            import hashlib
            from research.simulator_v2.trade_range import TradeDayProof
            path = archive / "BTCUSDT2026-10-01.csv.gz"
            proof = TradeDayProof(UTC_DAY, hashlib.sha256(path.read_bytes()).hexdigest(), "a"*64)
            with self.assertRaisesRegex(ValueError, "missing minutes"):
                pinned_taker_minutes(
                    archive_dir=archive, symbol=SYMBOL, proofs=(proof,),
                    start_ms=START + 120*M, end_ms=START + 124*M,
                    latest_closed_boundary_ms=END,
                )
            write_archive(archive, records())
            proof = TradeDayProof(UTC_DAY, hashlib.sha256(path.read_bytes()).hexdigest(), "a"*64)
            with patch("research.simulator_v2.taker_flow_archive.MAX_FOCUSED_PRINTS", 1):
                with self.assertRaisesRegex(ValueError, "bounded memory"):
                    pinned_taker_minutes(
                        archive_dir=archive, symbol=SYMBOL, proofs=(proof,),
                        start_ms=START + 120*M, end_ms=START + 124*M,
                        latest_closed_boundary_ms=END,
                    )
