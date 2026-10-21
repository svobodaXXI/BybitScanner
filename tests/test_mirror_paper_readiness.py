"""MIRROR PAPER readiness: fail-closed R0 on unprovable obligations, explicit enablement, no LIVE path."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import unittest

import mirror_retest_robot as mirror
from terminal.domain.models import OrderId, OrderSide, Symbol
from tests import test_mirror_robot_box_cycle as cycle
from tests.test_mirror_robot_box_cycle import ACCOUNT_ID, NOW

OK_GATE = {"enabled": True, "data_available": True, "latched": False, "baseline_equity_usdt": "5000",
           "current_adjusted_equity_usdt": "5000", "block_pct": "-10"}          # headroom 500 USDT


class MirrorUnknownObligationTests(unittest.TestCase):
    """The R0 path is the real runtime one (``build_runtime_policy`` -> ``read_account_facts`` -> account limit);
    only the daily gate is pinned open, so the obligations alone decide. Harness: the MIRROR cycle fixture."""

    def setUp(self):
        self.h = cycle.MirrorBoxCycleTests("test_no_campaign_means_a_plain_box_attempt")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        h = self.h

        def real_policy():
            real = mirror.build_runtime_policy(database_path=h.db, account_id=ACCOUNT_ID,
                                               quantity_step=lambda symbol: Decimal("0.1"),
                                               daily_marks=lambda: ({}, 5000), environ={mirror.ENV_FLAG: "1"})
            return replace(real, candles=h.candles)

        h.policy = real_policy
        gate = patch("terminal.application.robot_autopilot_shadow._daily_loss_gate", lambda *a, **k: dict(OK_GATE))
        gate.start()
        self.addCleanup(gate.stop)

    def pending_entry(self, pattern, symbol="OTHERUSDT"):
        snapshot = ({"pattern": pattern, "symbol": symbol, "timeframe": "5"} if pattern != "L-shape" else
                    {"pattern": "L-shape", "symbol": symbol, "timeframe": "5", "l_shape": {"direction": "LONG"}})
        record, _ = self.h.store.create_robot_candidate(
            candidate_id=f"pending-{pattern}", trading_account_id=ACCOUNT_ID, symbol=Symbol(symbol),
            status="APPROVED", signal_snapshot=snapshot, approved_at_ms=2_000, updated_at_ms=2_000)
        self.h.store.create_paper_limit(
            client_action_id=f"pending-{pattern}-limit", request_fingerprint=f"fp-{pattern}",
            order_id=OrderId(f"pending-{pattern}-order"), order_link_id=f"pending-{pattern}-link",
            trading_account_id=ACCOUNT_ID, symbol=Symbol(symbol), side=OrderSide.BUY, price=Decimal("1"),
            quantity=Decimal("10"), created_at_ms=2_001)
        return record

    def decide(self, candidate):
        monitor = self.h.monitor()
        return monitor._mirror_attachment(self.h.store.get_robot_candidate(candidate.candidate_id))

    def test_proven_obligations_give_r0_and_attach(self):
        self.h.add_wedge()
        source, candidate = self.h.add_box()
        decision = self.decide(candidate)
        self.assertEqual(decision["decision"], mirror.ATTACHED, decision)
        self.assertEqual(Decimal(decision["r0_usdt"]), Decimal("57.51976"))   # min(500, 0.5 x potential)

    def test_pending_wedge_entry_defers_until_account_risk_is_known(self):
        self.h.add_wedge()
        self.pending_entry("Falling Wedge")
        source, candidate = self.h.add_box()
        decision = self.decide(candidate)
        self.assertEqual((decision["decision"], decision["reason"]),
                         (mirror.DEFERRED, "r0_wait:obligation_unknown"))

    def test_pending_l_shape_entry_defers_until_account_risk_is_known(self):
        self.h.add_wedge()
        self.pending_entry("L-shape")
        source, candidate = self.h.add_box()
        decision = self.decide(candidate)
        self.assertEqual((decision["decision"], decision["reason"]),
                         (mirror.DEFERRED, "r0_wait:obligation_unknown"))

    def test_unknown_obligation_never_creates_a_plain_box_order(self):
        self.h.add_wedge()
        self.pending_entry("Falling Wedge")
        source, candidate = self.h.add_box()
        monitor = self.h.monitor()
        for _ in range(4):
            monitor.tick()
        record = self.h.store.get_robot_candidate(candidate.candidate_id)
        self.assertEqual(record.status, "APPROVED")
        self.assertNotIn("mirror", record.robot_state.get("execution") or {})
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())
        self.assertEqual(self.h.market_submissions, [])

    def test_r0_retries_after_00_msk_equity_baseline_becomes_provable(self):
        self.h.add_wedge()
        source, candidate = self.h.add_box()
        gate = {**OK_GATE, "data_available": False, "latched": None,
                "baseline_equity_usdt": None, "current_adjusted_equity_usdt": None}
        with patch("terminal.application.robot_autopilot_shadow._daily_loss_gate", lambda *a, **k: dict(gate)):
            monitor = self.h.monitor()
            for _ in range(3):
                self.assertEqual(monitor.tick(), ())
            record = self.h.store.get_robot_candidate(candidate.candidate_id)
            self.assertEqual(record.status, "APPROVED")
            self.assertNotIn("mirror", record.robot_state.get("execution") or {})
            self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())

            gate.update(OK_GATE)
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))
            mirror_record = self.h.store.get_robot_candidate(candidate.candidate_id).robot_state["execution"]["mirror"]
            self.assertEqual(mirror_record["decision"], mirror.ATTACHED)
            self.assertEqual(Decimal(mirror_record["r0_usdt"]), Decimal("57.51976"))

    def test_known_daily_loss_latch_blocks_instead_of_waiting(self):
        self.h.add_wedge()
        source, candidate = self.h.add_box()
        gate = {**OK_GATE, "latched": True}
        with patch("terminal.application.robot_autopilot_shadow._daily_loss_gate", lambda *a, **k: dict(gate)):
            monitor = self.h.monitor()
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        record = self.h.store.get_robot_candidate(candidate.candidate_id)
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(record.robot_state["execution"]["mirror"]["decision"], mirror.BLOCKED)
        self.assertEqual(record.robot_state["execution"]["mirror"]["reason"], "r0_denied:daily_loss_latched")
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())

    def test_proven_account_headroom_exhaustion_still_blocks(self):
        self.h.add_wedge()
        source, candidate = self.h.add_box()
        gate = {**OK_GATE, "current_adjusted_equity_usdt": "4500"}
        with patch("terminal.application.robot_autopilot_shadow._daily_loss_gate", lambda *a, **k: dict(gate)):
            monitor = self.h.monitor()
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        record = self.h.store.get_robot_candidate(candidate.candidate_id)
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(record.robot_state["execution"]["mirror"]["reason"],
                         "r0_denied:daily_loss_headroom_exhausted")
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())

    def test_plain_box_with_unknown_obligations_and_no_campaign_trades_unchanged(self):
        self.pending_entry("Falling Wedge")                                   # no MIRROR Wedge on the Box symbol
        source, candidate = self.h.add_box()
        monitor = self.h.monitor()
        for _ in range(4):
            monitor.tick()
        record = self.h.store.get_robot_candidate(candidate.candidate_id)
        self.assertEqual(record.robot_state["execution"]["mirror"]["decision"], mirror.NOT_ATTACHED)
        exit1 = next(o for o in self.h.store.load_box_order_ownership(source.candidate_id)
                     if o.role == "EXIT" and o.slot == 1)
        order = self.h.store.get_paper_limit(exit1.order_id.value, ACCOUNT_ID)
        self.assertEqual((order.price, order.quantity), (Decimal("99.2"), Decimal("2")))   # full Box TAKE


class MirrorEnablementTests(unittest.TestCase):
    def test_only_the_exact_flag_enables_and_the_default_is_off(self):
        for env in ({}, {mirror.ENV_FLAG: ""}, {mirror.ENV_FLAG: "true"}, {mirror.ENV_FLAG: "1 "[:1] + "x"}):
            self.assertIsNone(mirror.build_runtime_policy(database_path="x", account_id=ACCOUNT_ID,
                                                          quantity_step=lambda s: Decimal("1"), environ=env))
        enabled_policy = mirror.build_runtime_policy(database_path="x", account_id=ACCOUNT_ID,
                                                     quantity_step=lambda s: Decimal("1"),
                                                     environ={mirror.ENV_FLAG: "1"})
        self.assertIsNotNone(enabled_policy)
        self.assertTrue(enabled_policy.candles._strict_availability)

    def test_runtime_reads_the_flag_from_its_own_environment(self):
        source = (Path(__file__).resolve().parents[1] / "terminal" / "runtime" / "paper_runtime.py").read_text(
            encoding="utf-8")
        call = source[source.index("mirror_policy=build_mirror_robot_policy("):]
        call = call[:call.index("),") + 2]
        self.assertNotIn("environ", call)                                     # os.environ at construction, no override
        self.assertIn("account_id=self._paper_account_id", call)

    def test_launcher_keeps_the_flag_but_forces_every_live_gate_off(self):
        from tools.runtime_intent import paper_safe_backend_env
        child = paper_safe_backend_env({mirror.ENV_FLAG: "1", "LIVE_MARKET_MUTATIONS_ENABLED": "true",
                                        "LIVE_MAINNET_AUTHORIZED": "true"})
        self.assertEqual(child[mirror.ENV_FLAG], "1")
        self.assertEqual(child["LIVE_MARKET_MUTATIONS_ENABLED"], "false")
        self.assertEqual(child["LIVE_MAINNET_AUTHORIZED"], "false")

    def test_mirror_has_no_live_execution_path(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("mirror_retest_robot.py", "mirror_retest_live_sources.py"):
            text = (root / name).read_text(encoding="utf-8")
            for forbidden in ("live_execution", "live_market", "LiveMarket", "live_limit", "bybit_v5_mutation",
                              "OPERATOR_TOKEN", "/v5/order", "set_trading_stop", "LIVE_"):
                self.assertNotIn(forbidden, text, f"{name}: {forbidden}")

    def test_box_owned_orders_are_paper_only_by_construction(self):
        from terminal.domain.models import TradingAccountId
        harness = cycle.MirrorBoxCycleTests("test_no_campaign_means_a_plain_box_attempt")
        harness.setUp()
        try:
            source, _ = harness.add_box()
            with self.assertRaises(ValueError):
                harness.store.create_box_owned_paper_limit(
                    source.candidate_id, role="EXIT", slot=1, client_action_id="x", request_fingerprint="y",
                    order_id=OrderId("z"), order_link_id="z", trading_account_id=TradingAccountId("bybit-live"),
                    symbol=source.symbol, side=OrderSide.SELL, price=Decimal("1"), quantity=Decimal("1"),
                    created_at_ms=NOW)
        finally:
            harness.doCleanups()


if __name__ == "__main__":
    unittest.main()
