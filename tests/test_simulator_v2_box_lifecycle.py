"""Native Box Scanner -> Robot -> one SIMULATION exchange -> net PnL."""
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import tempfile
from unittest.mock import patch

from geometry.ikigai_box import IkigaiBoxFormation
from research.historical_market_replay import Candle
from research.simulator_v2.ikigai_observer import IkigaiScannerConfig
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms
from research.simulator_v2.box_backtest import run_verified_box_chunks
from research.simulator_v2.box_visual_replay import BoxVisualReplay
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk
from research.simulator_v2.robot_sandbox import ConnectedSimulationRobot, SimulationExecutionNotConnected
import robot_l_shape
from mirror_retest_robot import ATTACHED, SCANNER_SOURCE, STRATEGY_ID
from research.simulator_v2.session import VirtualReplaySession
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_box_plan_persistence import snapshot


def candle(index, *, op="100", high="101", low="99", close="100"):
    return Candle(
        start_ms=index * 60_000, interval_ms=60_000,
        open=D(op), high=D(high), low=D(low), close=D(close), volume=D("1"),
    )


def formation():
    return IkigaiBoxFormation(
        direction="LONG", impulse_start_index=1, impulse_end_index=2,
        box_start_index=3, box_end_index=7, second_start_index=8,
        as_of_index=31, anchor_start_index=1, anchor_end_index=2,
        anchor_start_price=112.94498381877023, anchor_end_price=100.,
        box_low=100., box_high=108., second_extreme=91.,
        fibonacci_1_0=100., fibonacci_1_618=92.,
        fibonacci_2_618=79.05501618122977,
    )


def terms():
    return BoxSimulationRiskTerms(
        tick_size=D("0.01"), working_quantity=D("8"),
        quantity_step=D("1"), minimum_quantity=D("1"),
        maximum_notional_usdt=D("1000"), maximum_loss_usdt=D("300"),
        entry_fee_rate=D("0.0002"), exit_fee_rate=D("0.0006"),
        adverse_stop_slippage_per_unit=D("0"),
        additional_cost_allowance_usdt=D("0"),
    )


class NativeBoxSimulationLifecycleTests(unittest.TestCase):
    def test_simulation_box_account_requires_explicit_private_store_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore.open(Path(directory) / "ordinary.sqlite3")
            try:
                with self.assertRaisesRegex(ValueError, "isolated SIMULATION"):
                    store.save_box_plan_only_for_account(
                        snapshot=snapshot(),
                        trading_account_id=TradingAccountId("simulation:forbidden"),
                        created_at_ms=3001,
                    )
            finally:
                store.close()

    def _detected_session(self, run_id):
        session = VirtualReplaySession(
            simulation_run_id=run_id, symbol="BTCUSDT",
            initial_balance=D("1000"),
            taker_fee_rate=D("0.0006"), maker_fee_rate=D("0.0002"),
            ikigai_scanner_config=IkigaiScannerConfig(
                window_bars=50, timeframes=("1m",),
            ),
        )
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=None):
            for index in range(31):
                session.step(candle(index))
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=formation()):
            session.step(candle(31))
        return session

    def test_native_mirror_limit_uses_same_private_robot_ledger_and_exchange(self):
        """One native MIRROR LIMIT, no alternate trading engine or PAPER account."""
        session = self._detected_session("native_mirror_limit")
        with ConnectedSimulationRobot(
            session, tick_size=D("0.01"), terms=terms(),
        ) as robot:
            frozen = {
                "direction": "LONG", "source_timeframe": "5",
                "breakout_time_ms": 1_500_000,
                "reference": "100", "target": "110", "stop": "99",
                "structural_stop": "99", "stop_kind": "FORMATION_EXTREME",
                "potential_percent": "10", "reward_risk": "4",
                "level_id": "lvl-local-native", "level_timeframe": "5",
                "level_source": "pattern_boundary", "level_pattern": "Falling Wedge",
                "level_side": "upper", "level_breakout_direction": "UP",
                "confirmation": {"kind": "ENGULFING", "timeframe": "5",
                                 "close_time_ms": 1_800_000},
            }
            candidate = {"candidate_id": "local-mirror-1", "status": "APPROVED",
                         "signal_snapshot": {"symbol": "BTCUSDT", "pattern": "MIRROR",
                                             "mirror_entry": frozen}}
            state, _ = robot_l_shape.initialize_state(candidate)
            state["execution"] = {"mirror": {
                "strategy_id": STRATEGY_ID, "decision": ATTACHED,
                "mode": "STANDALONE", "source": SCANNER_SOURCE,
                "mirror_level_id": frozen["level_id"], "one_wv_usdt": "250",
            }}
            now = robot.virtual_clock_ms()
            with self.assertRaisesRegex(SimulationExecutionNotConnected, "run-owned"):
                plan = robot_l_shape.build_initial_retest_limit(
                    candidate, state, tick_size=D("0.01"))
                robot._executor.create_limit(plan.request)
            record, created = robot._store.create_robot_candidate(
                candidate_id=candidate["candidate_id"],
                trading_account_id=robot.account_id, symbol=Symbol("BTCUSDT"),
                status="APPROVED", signal_snapshot=candidate["signal_snapshot"],
                approved_at_ms=now, updated_at_ms=now,
            )
            self.assertTrue(created)
            robot._store.save_robot_candidate_state(
                record.candidate_id, status="APPROVED", robot_state=state,
                expected_revision=record.state_revision, updated_at_ms=now,
            )
            robot._source_candidate_id = record.candidate_id
            first = robot._executor.create_limit(plan.request)
            second = robot._executor.create_limit(plan.request)
            self.assertEqual(first.order_id, second.order_id)
            self.assertEqual(second.reason_code, "already_exists")
            robot._synchronize_exchange()
            self.assertEqual(len(session.exchange.robot_limits), 1)
            order = session.exchange.robot_limits[0]
            self.assertEqual((order.request.side, order.request.price, order.request.quantity),
                             ("BUY", D("100.02"), D("2")))
            self.assertFalse(order.reduce_only)
            self.assertEqual(robot._store.get_paper_limit(first.order_id, robot.account_id).quantity,
                             D("2"))
            with self.assertRaisesRegex(SimulationExecutionNotConnected, "does not match"):
                robot._executor.create_limit(replace(plan.request, symbol="ETHUSDT"))
            with self.assertRaisesRegex(SimulationExecutionNotConnected, "amendment"):
                robot._executor.amend_limit(None)

    def test_p1_p4_take_fees_net_pnl_and_remaining_grid_semantics(self):
        session = self._detected_session("native_box_cycle")
        observation = session.ikigai_scanner.observations[-1]

        with ConnectedSimulationRobot(
            session, tick_size=D("0.01"), terms=terms(),
        ) as robot:
            preview = robot.admit(observation)
            self.assertEqual(preview.plan.limit_prices,
                             tuple(map(D, ("94", "93.2", "92.4", "91.6"))))
            self.assertEqual(len(session.exchange.robot_limits), 4)

            # Closed OHLC cannot prove several venue fills' intra-bar order.
            # The exchange therefore commits one adverse layer per later M1;
            # every untouched P2..P4 remains GTC beside the paired TAKE.
            entry_minutes = (
                candle(32, op="100", high="100", low="93.5", close="94"),
                candle(33, op="94", high="94.5", low="93.19", close="93.5"),
                candle(34, op="93.5", high="94", low="92.39", close="92.8"),
                candle(35, op="92.5", high="93", low="91.59", close="92"),
            )
            first_stop = None
            for index, minute in enumerate(entry_minutes, start=1):
                with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                           return_value=None):
                    session.step(minute)
                robot.after_committed_minute()
                if index == 1:
                    projected = session.exchange.robot_limits
                    self.assertEqual(sum(not item.reduce_only for item in projected), 3)
                    self.assertEqual(sum(item.reduce_only for item in projected), 1)
                    first_stop = session.exchange.robot_stop.stop_price
            self.assertEqual([fill.price for fill in session.account.fills],
                             list(preview.plan.limit_prices))
            self.assertEqual(len(session.exchange.robot_limits), 4)
            self.assertTrue(all(item.reduce_only for item in session.exchange.robot_limits))
            self.assertEqual(session.exchange.robot_stop.stop_price, first_stop)

            # Paired TAKEs follow the same conservative one-fill-per-M1 rule.
            # Native Robot finalizes only after the fourth actual exit receipt.
            for index in range(36, 40):
                with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                           return_value=None):
                    session.step(candle(index, op="95", high="100", low="94", close="99"))
                robot.after_committed_minute()

            final = session.account.snapshot(
                as_of_ms=session.virtual_time_ms, mark_price=D("99"),
            )
            entry_notional = sum(
                price * D("2") for price in preview.plan.limit_prices
            )
            exit_notional = preview.plan.take_price * D("8")
            expected_fees = (entry_notional + exit_notional) * D("0.0002")
            expected_gross = sum(
                (preview.plan.take_price - price) * D("2")
                for price in preview.plan.limit_prices
            )
            self.assertEqual(final.position_quantity, D("0"))
            self.assertEqual(final.realized_gross_pnl, expected_gross)
            self.assertEqual(final.fees, expected_fees)
            self.assertEqual(final.realized_net_pnl, expected_gross - expected_fees)
            self.assertEqual(session.exchange.robot_limits, ())
            self.assertIsNone(session.exchange.robot_stop)
            self.assertTrue(robot.can_admit)

            # A completed campaign releases the same native one-symbol owner;
            # the isolated ledger and exchange are reused for a later signal.
            next_formation = replace(
                formation(), impulse_start_index=9, impulse_end_index=10,
                box_start_index=11, box_end_index=15, second_start_index=16,
                as_of_index=40, anchor_start_index=9, anchor_end_index=10,
            )
            with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                       return_value=next_formation):
                session.step(candle(40))
            robot.admit(session.ikigai_scanner.observations[-1])
            self.assertEqual(len(session.exchange.robot_limits), 4)
            self.assertEqual(len(robot._source_candidate_ids), 2)

    def test_first_fill_native_stop_fees_and_net_pnl(self):
        session = self._detected_session("native_box_stop")
        observation = session.ikigai_scanner.observations[-1]
        with ConnectedSimulationRobot(
            session, tick_size=D("0.01"), terms=terms(),
        ) as robot:
            robot.admit(observation)
            with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                       return_value=None):
                session.step(candle(32, op="100", high="100", low="93.5", close="94"))
            robot.after_committed_minute()
            frozen_stop = session.exchange.robot_stop.stop_price
            self.assertEqual(sum(not item.reduce_only for item in session.exchange.robot_limits), 3)

            with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                       return_value=None):
                session.step(candle(33, op="94", high="95", low="90", close="91"))
            robot.after_committed_minute()

            final = session.account.snapshot(
                as_of_ms=session.virtual_time_ms, mark_price=D("91"),
            )
            expected_gross = (frozen_stop - D("94")) * D("2")
            expected_fees = (
                D("94") * D("2") * D("0.0002")
                + frozen_stop * D("2") * D("0.0006")
            )
            self.assertEqual(final.position_quantity, D("0"))
            self.assertEqual(final.realized_gross_pnl, expected_gross)
            self.assertEqual(final.fees, expected_fees)
            self.assertEqual(final.realized_net_pnl, expected_gross - expected_fees)
            self.assertEqual(session.exchange.robot_limits, ())
            self.assertIsNone(session.exchange.robot_stop)
            self.assertTrue(robot.can_admit)
            trade = robot._store.load_robot_trades_with_events_since(
                robot.account_id, 0,
            )[0]
            self.assertEqual(trade.exit_reason, "STOP")
            self.assertEqual(trade.fees_costs_usdt, expected_fees)

    def test_verified_chunk_runner_uses_same_native_cycle(self):
        candles = [candle(index) for index in range(32)] + [
            candle(32, op="100", high="100", low="93.5", close="94"),
            candle(33, op="94", high="94.5", low="93.19", close="93.5"),
            candle(34, op="93.5", high="94", low="92.39", close="92.8"),
            candle(35, op="92.5", high="93", low="91.59", close="92"),
            *(candle(index, op="95", high="100", low="94", close="99")
              for index in range(36, 40)),
        ]
        chunk = HistoryChunk(
            symbol="BTCUSDT", start_ms=0, end_ms=40 * 60_000,
            source_id="verified-test-source", candles=tuple(candles),
            sha256=_checksum(_rows(candles)),
        )
        session = VirtualReplaySession(
            simulation_run_id="box_runner", symbol="BTCUSDT",
            initial_balance=D("1000"), maker_fee_rate=D("0.0002"),
            taker_fee_rate=D("0.0006"),
            ikigai_scanner_config=IkigaiScannerConfig(
                window_bars=50, timeframes=("1m",),
            ),
        )

        def detector(frame):
            return formation() if len(frame) == 32 else None

        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   side_effect=detector):
            visual = BoxVisualReplay(
                run_id="box_runner", symbol="BTCUSDT",
                start_ms=0, end_ms=40 * 60_000,
            )
            result = run_verified_box_chunks(
                session, (chunk,), start_ms=0,
                end_inclusive_ms=39 * 60_000, terms=terms(),
                visual_recorder=visual,
            )
        self.assertEqual(result.scanner_box_observations, 1)
        self.assertEqual(result.admitted_box_candidates, 1)
        self.assertEqual(result.entry_fills, 4)
        self.assertEqual(result.take_exits, 4)
        self.assertEqual(result.stop_exits, 0)
        self.assertEqual(result.report.virtual_fills, 8)
        self.assertEqual(result.report.final_position_quantity, D("0"))
        replay = result.replay_document
        self.assertEqual(replay["market_data_source"],
                         "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M")
        self.assertEqual(sum(item["kind"] == "ENTRY_FILLED"
                             for item in replay["events"]), 4)
        self.assertEqual(sum(item["kind"] == "EXIT_FILLED"
                             for item in replay["events"]), 4)


if __name__ == "__main__":
    unittest.main()
