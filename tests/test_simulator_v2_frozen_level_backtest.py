"""End-to-end selected native levels: original Scanner + Robot + virtual fills.

No PAPER DB, private API, future candle, fabricated signal or dual owner.
"""
from dataclasses import replace
from decimal import Decimal as D
import unittest

from research.historical_market_replay import Candle
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.frozen_level_backtest import (
    FrozenLevelVisualReplay, run_verified_frozen_level_chunks,
)
from research.simulator_v2.frozen_level_observer import NativeFrozenLevelScanner
from research.simulator_v2.history import HistoryChunk
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from tests.test_simulator_v2_frozen_level_observer import BASE, DOUBLE_TOP_BARS

MINUTE = 60_000
RUN = "native_owner_one"


def source():
    bars = [
        Candle(
            start_ms=BASE + i * MINUTE, interval_ms=MINUTE,
            open=D(str(close)), high=D(str(hi)), low=D(str(lo)),
            close=D(str(close)), volume=D("1"),
        )
        for i, (hi, lo, close) in enumerate(DOUBLE_TOP_BARS)
    ]
    # The next M1 can hit both the entry and STOP. The existing virtual
    # exchange applies its pre-existing conservative STOP-FIRST policy.
    bars += [Candle(
        start_ms=BASE + len(bars) * MINUTE, interval_ms=MINUTE,
        open=D("95"), high=D("97"), low=D("93"),
        close=D("94"), volume=D("1"),
    ), Candle(
        start_ms=BASE + (len(bars) + 1) * MINUTE, interval_ms=MINUTE,
        open=D("94"), high=D("95"), low=D("93.5"),
        close=D("94"), volume=D("1"),
    )]
    return tuple(bars)


def history(rows=None):
    bars = rows or source()
    return HistoryChunk(
        symbol="LABUSDT", start_ms=BASE,
        end_ms=BASE + len(bars) * MINUTE,
        source_id="VERIFIED_LOCAL_DOUBLE_EXTREMUM_M1",
        candles=bars, sha256=_checksum(_rows(bars)),
    )


def risk():
    return SimWedgeRiskSettings(
        tick_size=D("0.01"), contracts_per_working_volume=D("1"),
        quantity_step=D("0.01"), minimum_quantity=D("0.01"),
        max_notional_usdt=D("1000"), max_risk_usdt=D("20"),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )


def run(selected=frozenset({"DOUBLE_TOP"}), chunk=None, visual=True):
    session = VirtualReplaySession(
        simulation_run_id=RUN, symbol="LABUSDT", initial_balance=D("1000"),
    )
    observer = NativeFrozenLevelScanner(
        symbol="LABUSDT", simulation_run_id=RUN,
        selected=selected, window_bars=50,
    )
    recorder = FrozenLevelVisualReplay(
        run_id=RUN, symbol="LABUSDT", start_ms=BASE,
        end_ms=BASE + len(source()) * MINUTE,
    ) if visual else None
    result = run_verified_frozen_level_chunks(
        session, [chunk or history()], start_ms=BASE,
        end_inclusive_ms=BASE + (len(source()) - 1) * MINUTE,
        scanner=observer, settings=risk(), visual_recorder=recorder,
    )
    replay = recorder.document(
        source_id=result.report.source_id, expected_fills=result.report.virtual_fills,
    ) if recorder is not None else None
    return result, replay, session


class NativeLevelHistoricalRunTests(unittest.TestCase):
    def test_double_top_runs_same_native_scanner_robot_stop_first_and_net_pnl(self):
        result, replay, session = run()
        payload = result.to_payload()
        self.assertEqual(payload["scenario_type"],
                         "ORIGINAL_FROZEN_LEVEL_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION")
        self.assertEqual(payload["scanner_level_observations"], 1)
        self.assertEqual(payload["native_robot_confirmations"], 1)
        self.assertEqual(payload["submitted_protected_limits"], 1)
        self.assertEqual(payload["virtual_fills"], 2)
        self.assertEqual(payload["stop_exits"], 1)
        self.assertEqual(payload["take_exits"], 0)
        native_stop = D("94.48") * D("1.015")  # original Robot limited_stop
        expected = (D("94.48") - native_stop) - (
            D("94.48") + native_stop
        ) * D("0.0006")
        self.assertEqual(result.report.realized_net_pnl, expected)
        self.assertLess(result.report.realized_net_pnl, 0)
        self.assertEqual(result.report.final_position_quantity, 0)
        self.assertIsNone(result.report.pending_order_id)
        self.assertEqual([e["kind"] for e in replay["events"] if e["kind"] != "CANDLE_CLOSED"],
                         ["ENTRY_SIGNAL", "ENTRY_FILLED", "EXIT_FILLED"])
        self.assertEqual(
            [e["reason"] for e in replay["events"] if e["kind"] == "EXIT_FILLED"],
            ["STOP"],
        )
        self.assertEqual(len([e for e in replay["events"] if e["kind"] == "CANDLE_CLOSED"]), 2)
        self.assertEqual(len(session.account.fills), 2)
        self.assertEqual([event["source"] for event in replay["events"]],
                         ["SIMULATION"] * len(replay["events"]))

    def test_unselected_double_top_never_enters_or_fabricates_trades(self):
        result, replay, _session = run(frozenset({"DOUBLE_BOTTOM"}))
        self.assertEqual(result.report.virtual_fills, 0)
        self.assertEqual(result.scanner_level_observations, 0)
        self.assertEqual(result.submitted_protected_limits, 0)
        self.assertEqual(result.report.realized_net_pnl, 0)
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" for e in replay["events"]))

    def test_corrupt_archive_fails_before_publishing_success(self):
        corrupt = replace(history(), sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "checksum"):
            run(chunk=corrupt)

    def test_no_trade_if_signal_is_on_final_selected_m1(self):
        session = VirtualReplaySession(
            simulation_run_id=RUN, symbol="LABUSDT", initial_balance=D("1000"),
        )
        scanner = NativeFrozenLevelScanner(
            symbol="LABUSDT", simulation_run_id=RUN,
            selected=frozenset({"DOUBLE_TOP"}), window_bars=50,
        )
        bars = source()[:9]
        result = run_verified_frozen_level_chunks(
            session, [history(bars)], start_ms=BASE,
            end_inclusive_ms=BASE + (len(bars) - 1) * MINUTE,
            scanner=scanner, settings=risk(),
        )
        self.assertEqual(result.scanner_level_observations, 1)
        self.assertEqual(result.submitted_protected_limits, 0)
        self.assertEqual(result.report.virtual_fills, 0)


if __name__ == "__main__":
    unittest.main()
