"""JASMY exceptional handoff proof: synthetic SQLite and immutable fill evidence.

No signals, imports of live services, orders, production database or runtime.
"""
import sqlite3
from types import SimpleNamespace
from unittest import TestCase, mock

from terminal.domain.models import Category, PositionKey, TradingAccountId, Symbol
from tests.test_robot_nonrobot_close_proof import NonRobotCloseProofTests, ENTRY_ORDER
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked
from tools.jasmy_flat_handoff_proof import (
    CANDIDATE_ID, OLD_SHA, PROOF_LABEL, SYMBOL, TRADE_ID,
    prove_jasmy_legacy_flat,
)


def fixture():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE robot_runtime_state (trading_account_id TEXT, mode TEXT, recovery_status TEXT);
        CREATE TABLE robot_autopilot_state (trading_account_id TEXT, mode TEXT);
        CREATE TABLE position_projections (trading_account_id TEXT, symbol TEXT, side TEXT, quantity TEXT, sync_state TEXT);
        CREATE TABLE robot_trades (trading_account_id TEXT, trade_id TEXT, candidate_id TEXT, symbol TEXT, exit_time_ms INTEGER);
        CREATE TABLE robot_candidates (trading_account_id TEXT, candidate_id TEXT, symbol TEXT, status TEXT);
        CREATE TABLE paper_limit_orders (trading_account_id TEXT, status TEXT);
        CREATE TABLE trading_commands (trading_account_id TEXT, current_state TEXT);
        CREATE TABLE paper_protection_obligations (trading_account_id TEXT, status TEXT);
        CREATE TABLE reconciliation_checkpoints (trading_account_id TEXT, completed_at_ms INTEGER);
        INSERT INTO robot_runtime_state VALUES ('paper','ROBOT_RUNNING','RECONCILIATION_REQUIRED');
        INSERT INTO robot_autopilot_state VALUES ('paper','OFF');
        INSERT INTO position_projections VALUES ('paper','JASMYUSDT','Flat','0','synced');
        INSERT INTO position_projections VALUES ('paper','ICPUSDT','Flat','0','synced');
        INSERT INTO robot_trades VALUES
          ('paper','robot-trade-2a023e646fd8add8b5b30cd8','2a023e646fd8add8b5b30cd8','JASMYUSDT',NULL);
        INSERT INTO robot_candidates VALUES
          ('paper','2a023e646fd8add8b5b30cd8','JASMYUSDT','OPEN');
    """)
    p = {
        "expected_identity": "synthetic-paper-db",
        "backend": dict(
            ok=True, component="paper_backend", mode="paper",
            paper_live_safe=True, database_identity="synthetic-paper-db",
            build_sha=OLD_SHA, process_instance_id="mock-old-instance",
        ),
        "scanner": dict(mode="SCANNER_STOPPED"),
        "autopilot": dict(mode="OFF"),
        "protection": dict(
            healthy=True, unhealthy_symbols={}, covered_symbols=["JASMYUSDT"],
            armed_symbols=[], coverage_roles={"JASMYUSDT": "EXPOSURE"},
        ),
    }
    src = NonRobotCloseProofTests()
    src.setUp()
    trade = SimpleNamespace(**{
        **vars(src.trade), "entry_path": "LIMIT", "created_at_ms": 1793556278449,
    })
    candidate = SimpleNamespace(**{
        **vars(src.candidate), "trading_account_id": TradingAccountId("paper"),
        "robot_state": {"execution": {"limit_order_id": ENTRY_ORDER}},
    })
    store = mock.Mock()
    store.get_robot_trade.return_value = trade
    store.get_robot_candidate.return_value = candidate
    store.get_position_projection.return_value = src.position
    store.load_executions_for_symbol.return_value = (src.entry, src.close)
    store.load_executions_for_order.return_value = (src.entry,)
    store.get_paper_command_by_order_link.return_value = src.command
    return db, p, store


class JASMYLegacyGateTests(TestCase):
    def check(self, db, payload, store):
        with mock.patch("tools.jasmy_flat_handoff_proof.SQLiteStore", return_value=store):
            return prove_jasmy_legacy_flat(db, **payload)

    def test_exact_proven_flat_open_is_read_only_and_not_a_shutdown(self):
        db, payload, store = fixture()
        before = db.total_changes
        self.assertEqual(self.check(db, payload, store), PROOF_LABEL)
        self.assertEqual(db.total_changes, before)
        store.get_paper_command_by_order_link.assert_called_once()
        self.assertEqual(store.get_paper_command_by_order_link.call_args.args[1],
                         "tw_ce6b00000000000000000000000000000")

    def test_real_exposure_or_limit_or_other_orphan_never_passes(self):
        mutators = [
            lambda d, p: d.execute("UPDATE position_projections SET side='Long', quantity='1' WHERE symbol='ICPUSDT'"),
            lambda d, p: d.execute("INSERT INTO robot_trades VALUES ('paper','other','other','ICPUSDT',NULL)"),
            lambda d, p: d.execute("INSERT INTO robot_candidates VALUES ('paper','other','ICPUSDT','APPROVED')"),
            lambda d, p: d.execute("INSERT INTO paper_limit_orders VALUES ('paper','open')"),
            lambda d, p: d.execute("INSERT INTO trading_commands VALUES ('paper','submitting')"),
            lambda d, p: d.execute("INSERT INTO paper_protection_obligations VALUES ('paper','DISPATCHING')"),
            lambda d, p: d.execute("INSERT INTO reconciliation_checkpoints VALUES ('paper',NULL)"),
            lambda d, p: d.execute("UPDATE robot_runtime_state SET recovery_status='READY'"),
            lambda d, p: d.execute("UPDATE robot_autopilot_state SET mode='PAPER_AUTO'"),
            lambda d, p: p["backend"].update(build_sha="unknown"),
            lambda d, p: p["scanner"].update(mode="SCANNER_RUNNING"),
            lambda d, p: p["protection"].update(covered_symbols=['JASMYUSDT','ICPUSDT']),
        ]
        for i, mutate in enumerate(mutators):
            with self.subTest(case=i):
                db, payload, store = fixture()
                mutate(db, payload)
                with self.assertRaises(FlatRecoveryBlocked):
                    self.check(db, payload, store)

    def test_no_fabricated_proof_for_wrong_command(self):
        db, payload, store = fixture()
        store.get_paper_command_by_order_link.return_value = None
        with self.assertRaisesRegex(FlatRecoveryBlocked, "jasmy_immutable_close_proof_missing"):
            self.check(db, payload, store)
