"""Pure impulse signal -> shared Robot protective plan -> original virtual exchange."""
from __future__ import annotations

import unittest
from decimal import Decimal as D

from robot_entry_flow_evidence import (
    FlowTransition, OpenInterestChange, recognize_impulse_signal,
    plan_impulse_protected_entry,
)
from research.historical_market_replay import Candle
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.wedge_backtest import run_verified_impulse_chunks
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from research.simulator_v2.wedge_visual_replay import WedgeVisualReplay

M = 60_000


def candle(i, o="100", h="100.5", l="99.5", c="100"):
    return Candle(start_ms=i * M, interval_ms=M, open=D(o), high=D(h), low=D(l), close=D(c), volume=D("100"))


def flow(at):
    return FlowTransition(
        known_at_ms=at, current_delta_fraction=D("0.8"), current_price_change_bps=D("30"),
        buy_wave_accelerating=True, sell_wave_accelerating=False,
        sell_impact_fading=False, buy_impact_fading=False,
        bid_refill_observed=None, ask_refill_observed=None,
        sell_absorption_candidate=None, buy_absorption_candidate=None,
    )


def risk(quantity="10", max_risk="100"):
    return SimWedgeRiskSettings(
        tick_size=D("0.1"), contracts_per_working_volume=D(quantity),
        quantity_step=D("1"), minimum_quantity=D("1"),
        max_notional_usdt=D("10000"), max_risk_usdt=D(max_risk),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )


def session(run="impulse_fixture"):
    return VirtualReplaySession(
        simulation_run_id=run, symbol="BTCUSDT", initial_balance=D("1000"),
    )


def chunk():
    bars = (candle(0), candle(1,"100","103","99","102"),
            candle(2,"102","103","101","102"),
            candle(3,"102","115","101","114"), candle(4))
    return HistoryChunk(
        symbol="BTCUSDT", start_ms=0, end_ms=5*M,
        source_id="LOCAL_PINNED_TRADE_FIXTURE", candles=bars,
        sha256=_checksum(_rows(bars)),
    )


def observed(active, bar):
    return flow(bar.end_ms) if bar.start_ms==M else None


class ImpulseProtectedVirtualTests(unittest.TestCase):
    def test_scanner_signal_orders_at_close_and_fill_only_later_with_protection(self):
        active=session()
        plans={}
        recorder=WedgeVisualReplay(
            run_id="impulse_fixture", symbol="BTCUSDT",start_ms=0,end_ms=5*M,
            impulse_plans=plans,
        )
        result=run_verified_impulse_chunks(
            active, (chunk(),), start_ms=0,end_inclusive_ms=4*M,
            risk_settings=risk(),flow_on_close=observed,
            visual_recorder=recorder,impulse_plans=plans,
        )
        self.assertEqual(result.impulse_signals,1)
        self.assertEqual(result.submitted_protected_limits,1)
        self.assertEqual(result.report.virtual_fills,2)
        self.assertEqual(result.take_exits,1)
        self.assertEqual(result.stop_exits,0)
        self.assertGreater(result.report.realized_net_pnl,0)
        events=recorder.document(source_id=result.report.source_id, expected_fills=2)["events"]
        submitted=[e for e in events if e["kind"]=="ENTRY_SIGNAL"]
        entries=[e for e in events if e["kind"]=="ENTRY_FILLED"]
        self.assertEqual(submitted[0]["time_ms"],2*M)
        self.assertEqual(entries[0]["time_ms"],3*M)
        self.assertEqual(result.report.scenario_type,
                         "IMPULSE_FLOW_SHARED_ROBOT_PROTECTED_VIRTUAL_SIMULATION")

    def test_oi_blocks_real_virtual_order_not_just_a_marker(self):
        yes=run_verified_impulse_chunks(
            session("oi_yes"),(chunk(),),start_ms=0,end_inclusive_ms=4*M,
            risk_settings=risk(),flow_on_close=observed,oi_mode="RISING",
            oi_at_entry=lambda _ms:OpenInterestChange(2*M,D("1"),"RISING"),
        )
        no=run_verified_impulse_chunks(
            session("oi_no"),(chunk(),),start_ms=0,end_inclusive_ms=4*M,
            risk_settings=risk(),flow_on_close=observed,oi_mode="FALLING",
            oi_at_entry=lambda _ms:OpenInterestChange(2*M,D("1"),"RISING"),
        )
        self.assertEqual(yes.report.virtual_fills,2)
        self.assertEqual(no.report.virtual_fills,0)
        self.assertEqual(no.paper_oi_rejected_retests,1)
        self.assertEqual(no.report.total_net_pnl,D("0"))

    def test_risk_invalid_source_stale_and_non_tick_quantity_fail_closed(self):
        signal=recognize_impulse_signal(
            flow(2*M),closed_at_ms=2*M,candle_open=D("100"),
            candle_close=D("102"),candle_low=D("99"),candle_high=D("103"),
        )
        self.assertEqual(signal.direction,"LONG")
        with self.assertRaisesRegex(ValueError,"quantity"):
            plan_impulse_protected_entry(
                signal, tick_size=D("0.1"), quantity=D("0.5"),
                quantity_step=D("1"), minimum_quantity=D("1"),
                max_notional_usdt=D("10000"), max_risk_usdt=D("100"),
                entry_fee_rate=D("0.0006"),exit_fee_rate=D("0.0006"),
            )
        with self.assertRaisesRegex(ValueError,"same-close"):
            recognize_impulse_signal(
                flow(3*M),closed_at_ms=2*M,candle_open=D("100"),
                candle_close=D("102"),candle_low=D("99"),candle_high=D("103"),
            )
        blocked=run_verified_impulse_chunks(
            session("risk_blocked"),(chunk(),),start_ms=0,end_inclusive_ms=4*M,
            risk_settings=risk(max_risk="0.001"),flow_on_close=observed,
        )
        self.assertEqual(blocked.impulse_risk_rejections,1)
        self.assertEqual(blocked.report.virtual_fills,0)

    def test_diagnostic_trace_excludes_terminal_impulse_even_if_detected(self):
        original = chunk()
        # Source has an authentic-looking upward impulse at BOTH the first
        # tradable close and the final close. Terminal close has no next M1.
        bars = original.candles[:-1] + (candle(4, "100", "103", "99", "102"),)
        with_terminal = HistoryChunk(
            symbol="BTCUSDT", start_ms=0, end_ms=5*M,
            source_id=original.source_id, candles=bars,
            sha256=_checksum(_rows(bars)),
        )
        recognized_closes = []
        observed_closes = []

        def on_flow(_active, bar):
            if bar.start_ms in (M, 4*M):
                observed_closes.append(bar.end_ms)
                return flow(bar.end_ms)
            return None

        result = run_verified_impulse_chunks(
            session("terminal_trace"), (with_terminal,),
            start_ms=0, end_inclusive_ms=4*M,
            risk_settings=risk(), flow_on_close=on_flow,
            on_eligible_impulse_signal=lambda signal: recognized_closes.append(
                signal.known_at_ms
            ),
        )
        self.assertEqual(observed_closes, [2*M, 5*M])
        self.assertEqual(recognized_closes, [2*M])
        self.assertEqual(result.impulse_signals, 1)
        self.assertEqual(result.submitted_protected_limits, 1)

    def test_noncausal_flow_blocks_replay(self):
        with self.assertRaisesRegex(ValueError,"same-close"):
            run_verified_impulse_chunks(
                session("stale"),(chunk(),),start_ms=0,end_inclusive_ms=4*M,
                risk_settings=risk(),flow_on_close=lambda _,b:flow(b.end_ms+M),
            )

if __name__=="__main__":
    unittest.main()
