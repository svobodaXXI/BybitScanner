"""Synthetic-only tests for dual Flat/OPEN owner evidence. No VPS or SQLite writes."""
import sqlite3
from types import SimpleNamespace
from unittest import TestCase, mock

from terminal.domain.models import PositionSide, Symbol, TradingAccountId
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked
from tools.paper_two_orphan_proof import PROOF_LABEL, prove_two_flat_orphans

ACCOUNT = TradingAccountId("paper")


def fixture():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE robot_runtime_state (trading_account_id TEXT, mode TEXT, recovery_status TEXT);
        CREATE TABLE robot_autopilot_state (trading_account_id TEXT, mode TEXT);
        CREATE TABLE position_projections (
          trading_account_id TEXT, symbol TEXT, side TEXT, quantity TEXT, sync_state TEXT
        );
        CREATE TABLE robot_trades (
          trading_account_id TEXT, trade_id TEXT, candidate_id TEXT,
          symbol TEXT, exit_time_ms INTEGER
        );
        CREATE TABLE robot_candidates (
          trading_account_id TEXT, candidate_id TEXT, symbol TEXT, status TEXT
        );
        CREATE TABLE paper_limit_orders (trading_account_id TEXT, status TEXT);
        CREATE TABLE trading_commands (trading_account_id TEXT, current_state TEXT);
        CREATE TABLE paper_protection_obligations (trading_account_id TEXT, status TEXT);
        CREATE TABLE reconciliation_checkpoints (trading_account_id TEXT, completed_at_ms INTEGER);
        INSERT INTO robot_runtime_state VALUES ('paper','ROBOT_RUNNING','PAUSED');
        INSERT INTO robot_autopilot_state VALUES ('paper','OFF');
        INSERT INTO position_projections VALUES ('paper','JASMYUSDT','Flat','0','synced');
        INSERT INTO position_projections VALUES ('paper','FLOWUSDT','Flat','0','synced');
        INSERT INTO robot_trades VALUES ('paper','trade-j','cand-j','JASMYUSDT',NULL);
        INSERT INTO robot_trades VALUES ('paper','trade-f','cand-f','FLOWUSDT',NULL);
        INSERT INTO robot_candidates VALUES ('paper','cand-j','JASMYUSDT','OPEN');
        INSERT INTO robot_candidates VALUES ('paper','cand-f','FLOWUSDT','OPEN');
    """)
    payload = dict(
        expected_identity="synthetic-db",
        backend=dict(
            ok=True, component="paper_backend", mode="paper",
            paper_live_safe=True, database_identity="synthetic-db",
            build_sha="synthetic-sha", process_instance_id="synthetic-instance",
        ),
        scanner=dict(mode="SCANNER_STOPPED"),
        autopilot=dict(mode="OFF"),
        protection=dict(healthy=True, unhealthy_symbols={},
                        covered_symbols=["JASMYUSDT", "FLOWUSDT"],
                        armed_symbols=[],
                        coverage_roles={"JASMYUSDT": "EXPOSURE", "FLOWUSDT": "EXPOSURE"}),
    )
    trades = {}
    candidates = {}
    positions = {}
    fills = {}
    for sym, tid, cid in (("JASMYUSDT", "trade-j", "cand-j"), ("FLOWUSDT", "trade-f", "cand-f")):
        symbol = Symbol(sym)
        trades[tid] = SimpleNamespace(
            trade_id=tid, candidate_id=cid, symbol=symbol,
            trading_account_id=ACCOUNT, entry_path="LIMIT",
        )
        candidates[cid] = SimpleNamespace(
            candidate_id=cid, symbol=symbol, trading_account_id=ACCOUNT,
            status="OPEN", robot_state={"execution": {"limit_order_id": "entry-" + tid}},
        )
        positions[sym] = SimpleNamespace(side=PositionSide.FLAT, quantity=SimpleNamespace(value=0))
        fills[sym] = [SimpleNamespace(order_id=SimpleNamespace(value="paper-order-tw_" + "a" * 33))]
    store = mock.Mock()
    store.get_robot_trade.side_effect = trades.get
    store.get_robot_candidate.side_effect = candidates.get
    store.get_position_projection.side_effect = lambda key: positions.get(key.symbol.value)
    store.load_executions_for_symbol.side_effect = lambda _account, symbol: fills[symbol.value]
    return conn, payload, store


def check(conn, payload, store, *, evidence=None):
    with (
        mock.patch("tools.paper_two_orphan_proof.SQLiteStore", return_value=store),
        mock.patch("tools.paper_two_orphan_proof.robot_entry_order_ids", return_value=(
            SimpleNamespace(value="entry-1"),)),
        mock.patch("tools.paper_two_orphan_proof.PaperRuntime._robot_entry_fees", return_value=0),
        mock.patch("tools.paper_two_orphan_proof.prove_nonrobot_robot_close", side_effect=evidence),
    ):
        return prove_two_flat_orphans(conn, **payload)


class DualOrphanPreflightTests(TestCase):
    def test_both_lots_need_independent_verified_close_evidence_read_only(self):
        conn, payload, store = fixture()
        before = conn.total_changes
        self.assertEqual(
            check(conn, payload, store, evidence=[object(), object()]), PROOF_LABEL,
        )
        self.assertEqual(conn.total_changes, before)
        self.assertEqual(store.get_robot_trade.call_count, 2)
        self.assertEqual(store.get_paper_command_by_order_link.call_count, 2)

    def test_second_missing_proof_blocks_without_mutations(self):
        conn, payload, store = fixture()
        before = conn.total_changes
        with self.assertRaisesRegex(FlatRecoveryBlocked, "orphan_immutable_close_proof_missing"):
            check(conn, payload, store, evidence=[object(), None])
        self.assertEqual(conn.total_changes, before)

    def test_live_report_blocks_on_ingress_and_unhealthy_coverage(self):
        conn, payload, store = fixture()
        payload["scanner"]["mode"] = "SCANNER_RUNNING"
        with self.assertRaisesRegex(FlatRecoveryBlocked, "scanner_not_stopped"):
            check(conn, payload, store)
        payload["scanner"]["mode"] = "SCANNER_STOPPED"
        payload["autopilot"]["mode"] = "PAPER_AUTO"
        with self.assertRaisesRegex(FlatRecoveryBlocked, "autopilot_not_off"):
            check(conn, payload, store)
        payload["autopilot"]["mode"] = "OFF"
        payload["protection"]["healthy"] = False
        with self.assertRaisesRegex(FlatRecoveryBlocked, "protection_unhealthy"):
            check(conn, payload, store)

    def test_approved_or_third_trade_never_inherits_two_owner_exception(self):
        conn, payload, store = fixture()
        conn.execute("INSERT INTO robot_candidates VALUES ('paper','approved','DOGEUSDT','APPROVED')")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_active_robot_candidate"):
            check(conn, payload, store)
        conn.execute("DELETE FROM robot_candidates WHERE candidate_id='approved'")
        conn.execute("INSERT INTO robot_trades VALUES ('paper','trade-x','cand-x','DOGEUSDT',NULL)")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_open_robot_owners"):
            check(conn, payload, store)

    def test_pending_command_and_limit_block(self):
        conn, payload, store = fixture()
        conn.execute("INSERT INTO trading_commands VALUES ('paper','submitting')")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unfinished_or_unknown_trading_command"):
            check(conn, payload, store)
        conn.execute("DELETE FROM trading_commands")
        conn.execute("INSERT INTO paper_limit_orders VALUES ('paper','new')")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "active_or_unknown_paper_limit"):
            check(conn, payload, store)
