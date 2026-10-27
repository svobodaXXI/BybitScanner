"""Safety proof for Robot reconcile: no OPEN trade may be silently forgotten.

All tests use synthetic store/owner objects. No PAPER database, backend,
orders, live processes, protected service controls or external I/O.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import RobotSynchronizePendingEntriesResponse
from terminal.application.robot_trade_ledger import prove_robot_open_trade_ledger
from terminal.domain.models import Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT = TradingAccountId("paper")


def candidate(name, symbol="BOTUSDT"):
    return SimpleNamespace(candidate_id=name, symbol=Symbol(symbol), status="OPEN")


def trade(name, symbol="BOTUSDT", trade_id=None):
    return SimpleNamespace(
        candidate_id=name, symbol=Symbol(symbol),
        trade_id=trade_id or "trade-" + name,
    )


def reconcile_fixture(candidates=(), trades=()):
    required = SimpleNamespace(
        mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
        reason="earlier uncertain close",
    )
    reconciling = SimpleNamespace(
        mode="ROBOT_RUNNING", recovery_status="RECONCILING", reason=None,
    )
    paused = SimpleNamespace(
        mode="ROBOT_RUNNING", recovery_status="PAUSED", reason=None,
    )
    store = SimpleNamespace(
        get_robot_runtime_state=Mock(side_effect=(required, reconciling)),
        load_active_robot_candidate_states=Mock(return_value=tuple(candidates)),
        load_unresolved_paper_protection_obligations=Mock(return_value=()),
        load_robot_candidates_by_status=Mock(return_value=tuple(candidates)),
        load_open_robot_trades=Mock(return_value=tuple(trades)),
        update_robot_runtime_state=Mock(return_value=paused),
    )
    sync = RobotSynchronizePendingEntriesResponse((), (), (), (), ())
    runtime = SimpleNamespace(
        _paper_account_id=ACCOUNT,
        store=store,
        _robot_recovery=SimpleNamespace(
            reconcile_required=Mock(return_value=SimpleNamespace(
                runtime_state=reconciling,
            )),
        ),
        robot_synchronize_pending_entries=Mock(return_value=sync),
        _robot_reconciliation_required_state=Mock(return_value=required),
        _dispatch_paper_protection_obligation=Mock(),
        _robot_full_close=Mock(),
        _robot_close_box_candidate=Mock(),
    )
    return runtime, store


class RobotTradeLedgerProofTests(unittest.TestCase):
    def test_empty_and_matching_ledgers_are_valid(self):
        self.assertTrue(prove_robot_open_trade_ledger((), ()).valid)
        self.assertTrue(prove_robot_open_trade_ledger(
            (candidate("c1"),), (trade("c1"),),
        ).valid)

    def test_orphan_trade_is_reported_by_trade_id(self):
        proof = prove_robot_open_trade_ledger((), (trade("lost", trade_id="t123"),))
        self.assertFalse(proof.valid)
        self.assertEqual(proof.invalid_trade_ids, ("t123",))
        self.assertEqual(proof.orphan_trade_ids, ("t123",))

    def test_missing_trade_reports_candidate_id(self):
        proof = prove_robot_open_trade_ledger((candidate("c1"),), ())
        self.assertEqual(proof.invalid_candidate_ids, ("c1",))
        self.assertFalse(proof.valid)

    def test_duplicate_trades_and_symbol_mismatch_are_not_proven(self):
        dup = prove_robot_open_trade_ledger(
            (candidate("c1"),),
            (trade("c1", trade_id="t1"), trade("c1", trade_id="t2")),
        )
        self.assertEqual(dup.invalid_trade_ids, ("t1", "t2"))
        mismatch = prove_robot_open_trade_ledger(
            (candidate("c1"),), (trade("c1", symbol="WRONGUSDT"),),
        )
        self.assertFalse(mismatch.valid)
        self.assertEqual(mismatch.invalid_candidate_ids, ("c1",))

    def test_two_distinct_candidates_on_same_net_symbol_fail(self):
        proof = prove_robot_open_trade_ledger(
            (candidate("c1"), candidate("c2")),
            (trade("c1"), trade("c2")),
        )
        self.assertFalse(proof.valid)
        self.assertEqual(proof.invalid_candidate_ids, ("c1", "c2"))


class RobotReconcileLedgerGateTests(unittest.TestCase):
    def test_orphan_trade_does_not_escape_into_paused(self):
        runtime, store = reconcile_fixture(trades=(trade("orphan", trade_id="t-orphan"),))
        result = PaperRuntime.robot_reconcile(runtime)
        self.assertFalse(result.success)
        self.assertEqual(result.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertEqual(result.unresolved_trade_ids, ("t-orphan",))
        self.assertIn("OPEN Robot candidate/trade ledger", result.reason)
        store.update_robot_runtime_state.assert_not_called()
        runtime._dispatch_paper_protection_obligation.assert_not_called()

    def test_missing_trade_is_reported_and_admission_remains_closed(self):
        runtime, store = reconcile_fixture(candidates=(candidate("c1"),))
        result = PaperRuntime.robot_reconcile(runtime)
        self.assertFalse(result.success)
        self.assertEqual(result.unresolved_candidate_ids, ("c1",))
        self.assertEqual(result.recovery_status, "RECONCILIATION_REQUIRED")
        store.update_robot_runtime_state.assert_not_called()

    def test_duplicate_trade_and_wrong_symbol_fail(self):
        for trades in (
            (trade("c1", trade_id="t1"), trade("c1", trade_id="t2")),
            (trade("c1", symbol="WRONGUSDT"),),
        ):
            with self.subTest(trades=trades):
                runtime, store = reconcile_fixture(
                    candidates=(candidate("c1"),), trades=trades,
                )
                result = PaperRuntime.robot_reconcile(runtime)
                self.assertFalse(result.success)
                self.assertTrue(result.unresolved_trade_ids)
                store.update_robot_runtime_state.assert_not_called()

    def test_clean_empty_ledger_keeps_existing_paused_success(self):
        runtime, store = reconcile_fixture()
        result = PaperRuntime.robot_reconcile(runtime)
        self.assertTrue(result.success)
        self.assertEqual(result.recovery_status, "PAUSED")
        self.assertEqual(result.unresolved_trade_ids, ())
        store.update_robot_runtime_state.assert_called_once()
        self.assertEqual(
            store.update_robot_runtime_state.call_args.kwargs["recovery_status"],
            "PAUSED",
        )

    def test_read_failure_preserves_required_fence(self):
        runtime, store = reconcile_fixture()
        store.load_open_robot_trades.side_effect = LookupError("trade ledger unreadable")
        result = PaperRuntime.robot_reconcile(runtime)
        self.assertFalse(result.success)
        self.assertEqual(result.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertIn("trade ledger unreadable", result.reason)
        store.update_robot_runtime_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
