"""Bounded native MIRROR confirmation -> original Robot protection, no PAPER side effects."""
from decimal import Decimal as D
import unittest

import mirror_scanner
from mirror_levels.levels import SOURCE_SWING_ZONE, horizontal_level
from mirror_levels.tracker import new_record, track
from research.historical_market_replay import Candle
from research.simulator_v2.frozen_level_adapter import (
    FrozenLevelSimulationBlocked, preview_native_frozen_level,
)
from research.simulator_v2.mirror_native_adapter import preview_confirmed_standalone_mirror
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings

NOW = 6_000_000
STEP = 60_000
SYMBOL = "BTCUSDT"
RUN = "native_mirror_only"


def row(start, step, o, h, lo, c):
    return {
        "open_time_ms": start, "close_time_ms": start + step,
        "open": o, "high": h, "low": lo, "close": c, "closed": True,
    }


def frames():
    m5 = [
        row(NOW - 4*300_000, 300_000, 111, 112, 99, 100),
        row(NOW - 3*300_000, 300_000, 100, 102, 98, 100),
        row(NOW - 2*300_000, 300_000, 100, 101, 98, 99),
        row(NOW - 300_000, 300_000, 99, 101, 97, 100.5),
    ]
    minute = [row(NOW - 20*STEP+i*STEP, STEP, 100, 100.4, 99.6, 100)
              for i in range(15)]
    minute += [
        row(NOW - 5*STEP, STEP, 99, 99.2, 97.7, 98),
        row(NOW - 4*STEP, STEP, 97.8, 100, 97.6, 99.7),
        row(NOW - 3*STEP, STEP, 99.7, 100.7, 99.4, 100.5),
        row(NOW - 2*STEP, STEP, 100.5, 100.9, 100.1, 100.2),
        row(NOW - STEP, STEP, 100.2, 100.6, 100.1, 100.5),
    ]
    return {"5": m5, "1": minute}


def original_native_level_record():
    level = horizontal_level(
        symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE,
        pattern=None, side="lower", price=110,
        anchor_time_ms=NOW-9*300_000,
        confirmed_at_ms=NOW-5*300_000,
        touches=2,
    )
    native = track(level, [frames()["5"][0]],
                   record=new_record(level), atr_at=lambda _: 3)
    assert native["status"] == mirror_scanner.STATUS_UNTESTED
    assert mirror_scanner._judge_breakout(level, native,
                                         NOW-3*300_000, 300_000) is None
    # These are the exact native Scanner eligibility fields after its gate.
    native.update(candidate=True, lifecycle=mirror_scanner.LIFECYCLE_TRACKING,
                  rejection=None)
    return level, native


def settings():
    return SimWedgeRiskSettings(
        tick_size=D("0.01"), contracts_per_working_volume=D("1"),
        quantity_step=D("0.01"), minimum_quantity=D("0.01"),
        max_notional_usdt=D("1000"), max_risk_usdt=D("20"),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )


class NativeMirrorAdapterTests(unittest.TestCase):
    def test_existing_naked_breakout_and_engulfing_confirmation_to_original_robot(self):
        level, native = original_native_level_record()
        result = preview_confirmed_standalone_mirror(
            symbol=SYMBOL, simulation_run_id=RUN,
            level=level, native_record=native, frames=frames(),
            virtual_time_ms=NOW, settings=settings(),
        )
        self.assertEqual(result.preview.pattern, "MIRROR")
        self.assertEqual(result.source_timeframe, "1")
        self.assertEqual(result.confirmed_at_ms, NOW-2*STEP)
        self.assertEqual(result.preview.protected.entry.limit_price, D("100.52"))
        self.assertEqual(result.preview.protected.entry.quantity, D("1"))
        # Original Robot: 1-tick structural buffer and the 1.5% STOP cap.
        self.assertEqual(result.preview.protected.stop_price,
                         D("100.52") * D("0.985"))
        self.assertEqual(result.preview.protected.take_price, D("110"))
        self.assertGreaterEqual(result.preview.native_net_reward_risk, D("2"))
        self.assertGreater(result.preview.worst_case_loss_usdt,
                           D("100.52") * D("0.015"))
        # Deterministic local-only id; repeated import cannot mint a new order.
        self.assertEqual(result.candidate_id, preview_confirmed_standalone_mirror(
            symbol=SYMBOL, simulation_run_id=RUN, level=level,
            native_record=native, frames=frames(),
            virtual_time_ms=NOW, settings=settings(),
        ).candidate_id)

    def test_only_causal_closed_native_history_and_candidate_pass(self):
        level, native = original_native_level_record()
        basic = dict(symbol=SYMBOL, simulation_run_id=RUN, level=level,
                     native_record=native, frames=frames(),
                     virtual_time_ms=NOW, settings=settings())
        for change in (
            {"native_record": {**native, "candidate": None}},
            {"native_record": {**native, "lifecycle": mirror_scanner.LIFECYCLE_DONE}},
            {"symbol": "OTHERUSDT"},
            {"frames": {**frames(), "1": frames()["1"][:-1]}},
            {"frames": {**frames(), "5": frames()["5"][:-1]}},
            {"frames": {**frames(), "1": [*frames()["1"][:-1],
               {**frames()["1"][-1], "closed": False}]}},
            {"frames": {**frames(), "1": [*frames()["1"][:-1],
               {**frames()["1"][-1], "open_time_ms": NOW+STEP}]}},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(FrozenLevelSimulationBlocked):
                preview_confirmed_standalone_mirror(**{**basic, **change})
        with self.assertRaises(FrozenLevelSimulationBlocked):
            preview_confirmed_standalone_mirror(**{
                **basic, "settings": SimWedgeRiskSettings(
                    tick_size=D("0.01"), contracts_per_working_volume=D("1"),
                    quantity_step=D("0.01"), minimum_quantity=D("0.01"),
                    max_notional_usdt=D("1000"), max_risk_usdt=D("0.1"),
                    entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
                ),
            })

    def test_mirror_cannot_use_generic_frozen_adapter_without_native_proof(self):
        level, native = original_native_level_record()
        preview = preview_confirmed_standalone_mirror(
            symbol=SYMBOL, simulation_run_id=RUN, level=level,
            native_record=native, frames=frames(),
            virtual_time_ms=NOW, settings=settings(),
        )
        self.assertEqual(preview.preview.pattern, "MIRROR")
        # No public/raw interface to enable MIRROR via a hand-written candidate.
        import robot_l_shape
        candidate = {"candidate_id": "raw_mirror", "status": "APPROVED",
                     "symbol": SYMBOL, "timeframe": "1",
                     "signal_snapshot": mirror_scanner._standalone_snapshot(
                         SYMBOL, mirror_scanner._standalone_confirmations(
                             level, native.copy(), frames(), NOW,
                         )[0]["terms"],
                     )}
        state, _ = robot_l_shape.initialize_state(candidate)
        with self.assertRaises(FrozenLevelSimulationBlocked):
            preview_native_frozen_level(
                candidate, state, settings=settings(), virtual_time_ms=NOW,
            )


if __name__ == "__main__":
    unittest.main()
