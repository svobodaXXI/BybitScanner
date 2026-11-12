"""Local 5m OI research input and genuine protected virtual Robot trade gate."""
from __future__ import annotations

import hashlib
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from robot_entry_flow_evidence import FlowTransition, OpenInterestChange
from research.simulator_v2.oi_history import load_oi_csv
from research.simulator_v2.wedge_backtest import run_verified_wedge_chunks
from tests.test_simulator_v2_wedge_backtest import (
    M, bar, frozen_result, verified_chunk,
)
from tests.test_simulator_v2_wedge_risk_flow import make_session

SOURCE = "Bybit V5 public open-interest API"


def sample_file(path: Path, *, source: str = SOURCE) -> None:
    rows = [
        "timestamp_ms,open_interest_base,source,native_interval",
        f"0,1000,{source},5min",
        f"300000,1010,{source},5min",
        f"600000,1000,{source},5min",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class PaperOpenInterestTests(TestCase):
    def test_source_labeled_oi_csv_has_stable_sha_and_bounded_fields(self):
        with TemporaryDirectory() as td:
            file = Path(td) / "BTCUSDT.csv"
            sample_file(file)
            points, sha = load_oi_csv(file, symbol="BTCUSDT")
            self.assertEqual(len(points), 3)
            self.assertEqual(sha, hashlib.sha256(file.read_bytes()).hexdigest())
            self.assertEqual(points[1].known_at_ms, 600000)
            with self.assertRaisesRegex(ValueError, "matching local OI"):
                load_oi_csv(file, symbol="ETHUSDT")
            sample_file(file, source="Unknown feed")
            with self.assertRaisesRegex(ValueError, "provenance"):
                load_oi_csv(file, symbol="BTCUSDT")

    def test_oi_changes_actual_virtual_protected_trades_and_pnl(self):
        candles = [bar(i) for i in range(250)] + [
            bar(250, closing="102", low="97", high="103"),
            bar(251, closing="101", low="99", high="101"),
            bar(252, closing="100", low="99.7", high="100.2"),
            bar(253, closing="100", low="99.7", high="105"),
            bar(254),
        ]
        def flow_after_close(_session, candle):
            return FlowTransition(
                known_at_ms=candle.end_ms, current_delta_fraction=D("0.8"),
                current_price_change_bps=D("20"), buy_wave_accelerating=True,
                sell_wave_accelerating=False, sell_impact_fading=False,
                buy_impact_fading=False, bid_refill_observed=None,
                ask_refill_observed=None, sell_absorption_candidate=None,
                buy_absorption_candidate=None,
            )

        def run(mode):
            session = make_session(run="oi-"+mode)
            with patch.object(
                session.wedge_scanner, "_evaluate",
                side_effect=lambda *, frame, bars: frozen_result(
                    frame, pattern="Falling Wedge",
                ),
            ):
                result = run_verified_wedge_chunks(
                    session, [verified_chunk(candles)],
                    start_ms=250*M, end_inclusive_ms=254*M,
                    flow_on_close=flow_after_close, oi_mode=mode,
                    oi_at_entry=(
                        lambda _at: OpenInterestChange(10*M, D("2"), "RISING")
                    ) if mode != "OFF" else None,
                    oi_source_sha256="a"*64 if mode != "OFF" else None,
                )
            return result

        baseline = run("OFF")
        accepted = run("RISING")
        blocked = run("FALLING")
        for passed in (baseline, accepted):
            self.assertEqual(passed.submitted_protected_limits, 1)
            self.assertEqual(passed.report.virtual_fills, 2)
            self.assertGreater(passed.report.realized_net_pnl, D("0"))
        self.assertEqual(blocked.submitted_protected_limits, 0)
        self.assertEqual(blocked.report.virtual_fills, 0)
        self.assertEqual(blocked.report.realized_net_pnl, D("0"))
        self.assertEqual(blocked.paper_oi_rejected_retests, 1)
        self.assertEqual(accepted.to_payload()["paper_flow_entry"]["oi_mode"], "RISING")
        self.assertEqual(blocked.to_payload()["paper_flow_entry"]["oi_mode"], "FALLING")

    def test_oi_cannot_run_without_verified_taker_flow(self):
        session = make_session()
        with self.assertRaisesRegex(ValueError, "requires authentic flow"):
            run_verified_wedge_chunks(
                session, [], start_ms=250*M, end_inclusive_ms=254*M,
                oi_mode="RISING", oi_at_entry=lambda _ms: None,
            )
