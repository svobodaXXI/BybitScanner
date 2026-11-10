"""End-to-end local Wedge mode on checksum-pinned M1, not live Bybit trading.

Synthetic scanner formations prove plumbing; separately the public-trade
archive fixture proves exact cached provenance and UTC-minute window.
"""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.report import run_verified_chunks
from research.simulator_v2.trade_range import import_local_trade_range
from research.simulator_v2.wedge_backtest import (
    run_cached_wedge_trade_range, run_verified_wedge_chunks,
)
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner, WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from research.simulator_v2.session import VirtualReplaySession
from tests.test_simulator_v2_wedge_robot_observer import bar, fake_wedge
from tests.test_simulator_v2_wedge_risk_flow import (
    frozen_snapshot, make_session, risk_settings,
)
from tests.test_simulator_v2_trade_range import (
    START_DAY, START_MS, DAY_MS, SYMBOL, fixture_file,
)
from robot_protection import wedge_structural_extreme, wedge_frozen_reference_target

M = MINUTE_MS


def frozen_result(frame, *, pattern):
    raw = fake_wedge(frame, pattern)
    direction = "LONG" if pattern == "Falling Wedge" else "SHORT"
    geometry = frozen_snapshot()
    extreme = wedge_structural_extreme(geometry, direction)
    ref, take = wedge_frozen_reference_target(geometry, direction)
    return replace(
        raw, frozen_structural_extreme=extreme,
        frozen_reference_price=ref, frozen_target_price=take,
    )


def verified_chunk(candles):
    candles = tuple(candles)
    return HistoryChunk(
        symbol="BTCUSDT",
        start_ms=candles[0].start_ms,
        end_ms=candles[-1].end_ms,
        source_id="FIXTURE_WEDGE_NOT_REAL_DATA",
        candles=candles,
        sha256=_checksum(_rows(candles)),
    )


class OfflineWedgeBacktestTests(unittest.TestCase):
    def test_original_wedge_robot_generates_both_virtual_trade_roundtrips(self):
        for pattern, opening, retest, lo, hi in (
            ("Falling Wedge", "102", "101", "99.7", "105"),
            ("Rising Wedge", "98", "99", "95", "100.2"),
        ):
            with self.subTest(pattern=pattern):
                session = make_session(run=pattern.replace(" ", ""))
                minutes = [
                    bar(i) for i in range(250)
                ] + [
                    bar(250, closing=opening, low="97", high="103"),
                    bar(251, closing=retest, low="99", high="101"),
                    bar(252, closing="100", low="99.7", high="100.2"),
                    bar(253, closing="100", low=lo, high=hi),
                    bar(254),
                ]
                with patch.object(
                    session.wedge_scanner, "_evaluate",
                    side_effect=lambda *, frame, bars:
                        frozen_result(frame, pattern=pattern),
                ):
                    result = run_verified_wedge_chunks(
                        session, [verified_chunk(minutes)],
                        start_ms=250*M, end_inclusive_ms=254*M,
                    )
                self.assertEqual(result.report.scenario_type,
                                 "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION")
                self.assertEqual(result.market_warmup_start_ms, 0)
                self.assertEqual(result.requested_start_ms, 250*M)
                self.assertEqual(result.requested_end_inclusive_ms, 254*M)
                self.assertEqual(result.submitted_protected_limits, 1)
                self.assertEqual(result.stop_exits, 0)
                self.assertEqual(result.take_exits, 1)
                self.assertEqual(result.report.virtual_fills, 2)
                self.assertEqual(result.report.final_position_quantity, D("0"))
                self.assertGreater(result.report.realized_net_pnl, 0)
                self.assertEqual(result.report.minutes, 255)
                self.assertEqual(result.to_payload()["execution_model"],
                                 "SIMULATION_OHLC_STOP_FIRST_NOT_REAL_BYBIT_FILLS")
                self.assertEqual(result.archive_proofs, ())

    def test_no_virtual_trade_before_selected_start_even_with_previous_retest(self):
        session = make_session(run="late")
        bars = [
            bar(i) for i in range(250)
        ] + [
            bar(250, closing="102", low="97", high="103"),
            bar(251, closing="101", low="99", high="101"),
            bar(252, closing="100", low="99.7", high="100.2"),
            bar(253),
        ]
        with patch.object(
            session.wedge_scanner, "_evaluate",
            side_effect=lambda *, frame, bars:
                frozen_result(frame, pattern="Falling Wedge"),
        ):
            result = run_verified_wedge_chunks(
                session, [verified_chunk(bars)],
                start_ms=252*M, end_inclusive_ms=253*M,
            )
        self.assertEqual(result.submitted_protected_limits, 0)
        self.assertEqual(result.report.virtual_fills, 0)
        self.assertEqual(result.report.realized_net_pnl, 0)

    def test_verified_local_bybit_format_and_inclusive_minute_cutoff(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base/"archive"
            archive.mkdir()
            fixture_file(archive, START_DAY)
            cache = base/"sim-cache"
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=cache, symbol=SYMBOL,
                start_day=START_DAY, days=1,
                latest_closed_boundary_ms=START_MS+DAY_MS,
            )
            kwargs=dict(
                cache_dir=cache, symbol=SYMBOL,
                proofs=proofs, latest_closed_boundary_ms=START_MS+DAY_MS,
                simulation_run_id="minute-window", initial_balance=D("1000"),
                start_ms=START_MS+120*M,
                end_inclusive_ms=START_MS+254*M,
                scanner_config=WedgeScannerConfig(
                    window_bars=50, mode="hunter", min_score=50,
                ),
                robot_config=SimWedgeRobotConfig(
                    selected_patterns=frozenset({"Falling Wedge"}),
                    tick_size=D("0.01"),
                ),
                risk_settings=risk_settings(),
            )
            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                result = run_cached_wedge_trade_range(**kwargs)
            self.assertEqual(result.report.minutes, 255)
            self.assertEqual(result.market_warmup_start_ms, START_MS)
            self.assertEqual(result.requested_start_ms, START_MS+120*M)
            self.assertEqual(result.requested_end_inclusive_ms, START_MS+254*M)
            self.assertEqual(result.report.last_closed_ms, START_MS+255*M)
            self.assertEqual(result.report.virtual_fills, 0)
            self.assertEqual(result.report.total_net_pnl, D("0"))
            self.assertEqual(len(result.archive_proofs), 1)
            self.assertEqual(result.archive_proofs[0].m1_sha256, proofs[0].m1_sha256)
            self.assertTrue(result.report.source_id.startswith("BYBIT_PUBLIC_TRADES_RANGE_"))
            self.assertIn("raw_archive_sha256", result.to_payload()["archive_proofs"][0])
            archive.joinpath(f"{SYMBOL}{START_DAY.isoformat()}.csv.gz").unlink()
            # Cache remains sufficient, without touching the unavailable network.
            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                self.assertEqual(run_cached_wedge_trade_range(**kwargs).report, result.report)
            with self.assertRaisesRegex(ValueError,"outside pinned trade days"):
                with patch.object(ReadOnlyWedgeScanner,"_evaluate",return_value=None):
                    run_cached_wedge_trade_range(
                        **{**kwargs,"end_inclusive_ms":START_MS+DAY_MS},
                    )

    def test_full_multi_day_manifest_accepts_early_inclusive_end_and_exact_source_subset(self):
        from datetime import timedelta
        from research.simulator_v2.trade_range import _ordered_proofs
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "trades"
            archive.mkdir()
            fixture_file(archive, START_DAY)
            fixture_file(archive, START_DAY + timedelta(days=1))
            cache = base / "m1-cache"
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=cache, symbol=SYMBOL,
                start_day=START_DAY, days=2,
                latest_closed_boundary_ms=START_MS + 2*DAY_MS,
            )
            kwargs = dict(
                cache_dir=cache, symbol=SYMBOL, proofs=proofs,
                latest_closed_boundary_ms=START_MS + 2*DAY_MS,
                simulation_run_id="subset", initial_balance=D("1000"),
                start_ms=START_MS + 120*M,
                end_inclusive_ms=START_MS + 254*M,
                scanner_config=WedgeScannerConfig(window_bars=50, mode="hunter", min_score=50),
                robot_config=SimWedgeRobotConfig(
                    selected_patterns=frozenset({"Falling Wedge"}), tick_size=D("0.01"),
                ),
                risk_settings=risk_settings(),
            )
            # Only the selected first day may contribute to report identity.
            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                first = run_cached_wedge_trade_range(**kwargs)
            expected_source, _, _ = _ordered_proofs(
                proofs[:1], symbol=SYMBOL,
                latest_closed_boundary_ms=START_MS + 2*DAY_MS,
            )
            self.assertEqual(first.report.source_id, expected_source)
            self.assertEqual(first.archive_proofs, proofs[:1])
            self.assertEqual(first.report.minutes, 255)
            self.assertEqual(first.to_payload()["requested_minutes"], 135)
            self.assertEqual(first.report.last_closed_ms, START_MS + 255*M)
            self.assertEqual(first.report.virtual_fills, 0)
            # A corrupt/unselected future cache must NOT be silently read.
            cache_files = sorted(cache.glob("m1_*.json"))
            future = next(p for p in cache_files if str(START_MS + DAY_MS) in p.name)
            future.write_bytes(b"corrupt day not selected")
            with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                again = run_cached_wedge_trade_range(**kwargs)
            self.assertEqual(first.report, again.report)
            # But if the user explicitly selects the second day the same
            # corruption must block and cannot produce a success report.
            with self.assertRaises(ValueError):
                with patch.object(ReadOnlyWedgeScanner, "_evaluate", return_value=None):
                    run_cached_wedge_trade_range(
                        **{**kwargs,
                           "start_ms": START_MS + DAY_MS + 50*M,
                           "end_inclusive_ms": START_MS + DAY_MS + 80*M},
                    )

    def test_invalid_windows_missing_cache_and_foreign_data_fail_without_output(self):
        session = make_session(run="invalid")
        c = verified_chunk([bar(i) for i in range(5)])
        for start,end in ((0,-M),(-M,0),(30_000,60_000),(M,0)):
            with self.subTest(start=start,end=end), self.assertRaises(ValueError):
                run_verified_wedge_chunks(
                    session, [c], start_ms=start, end_inclusive_ms=end,
                )
        with self.assertRaisesRegex(ValueError, "does not reach"):
            run_verified_wedge_chunks(
                session, [c], start_ms=0,end_inclusive_ms=5*M,
            )
        with self.assertRaisesRegex(ValueError, "only internal virtual MARKET"):
            run_verified_chunks(
                make_session(run="schedule"),
                [c], order_schedule={M: "wrong"},
            )
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaisesRegex(ValueError, "expected 1..90"):
                run_cached_wedge_trade_range(
                    cache_dir=base, symbol=SYMBOL, proofs=(),
                    latest_closed_boundary_ms=START_MS+DAY_MS,
                    simulation_run_id="missing", initial_balance=D("1000"),
                    start_ms=START_MS, end_inclusive_ms=START_MS+M,
                    scanner_config=WedgeScannerConfig(window_bars=50,mode="hunter",min_score=50),
                    robot_config=SimWedgeRobotConfig(
                        selected_patterns=frozenset({"Falling Wedge"}),
                        tick_size=D("0.01"),
                    ),
                    risk_settings=risk_settings(),
                )


if __name__ == "__main__":
    unittest.main()
