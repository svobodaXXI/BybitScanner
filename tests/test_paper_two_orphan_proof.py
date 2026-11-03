"""Synthetic-only tests for dual Flat/OPEN owner evidence. No VPS or SQLite writes."""
import sqlite3
import json
import hashlib
import tempfile
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase, mock

from terminal.domain.models import PositionSide, Symbol, TradingAccountId
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked
from tools.paper_two_orphan_proof import (
    INCIDENT_BACKEND_SHA, JASMY_TRADE_ID, JASMY_CANDIDATE_ID,
    IDLE_APPROVALS, PROOF_LABEL, prove_two_flat_orphans, inspect_read_only,
)

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
          trading_account_id TEXT, candidate_id TEXT, symbol TEXT, status TEXT,
          approved_at_ms INTEGER
        );
        CREATE TABLE paper_limit_orders (
          trading_account_id TEXT, status TEXT, symbol TEXT, created_at_ms INTEGER
        );
        CREATE TABLE trading_commands (
          trading_account_id TEXT, current_state TEXT, symbol TEXT, created_at_ms INTEGER
        );
        CREATE TABLE executions (
          trading_account_id TEXT, symbol TEXT, exchange_timestamp_ms INTEGER
        );
        CREATE TABLE paper_protection_obligations (trading_account_id TEXT, status TEXT);
        CREATE TABLE reconciliation_checkpoints (trading_account_id TEXT, completed_at_ms INTEGER);
        INSERT INTO robot_runtime_state VALUES ('paper','ROBOT_RUNNING','PAUSED');
        INSERT INTO robot_autopilot_state VALUES ('paper','OFF');
        INSERT INTO position_projections VALUES ('paper','JASMYUSDT','Flat','0','synced');
        INSERT INTO position_projections VALUES ('paper','FLOWUSDT','Flat','0','synced');
        INSERT INTO robot_trades VALUES ('paper','robot-trade-2a023e646fd8add8b5b30cd8','2a023e646fd8add8b5b30cd8','JASMYUSDT',NULL);
        INSERT INTO robot_trades VALUES ('paper','trade-f','cand-f','FLOWUSDT',NULL);
        INSERT INTO robot_candidates VALUES ('paper','2a023e646fd8add8b5b30cd8','JASMYUSDT','OPEN',100);
        INSERT INTO robot_candidates VALUES ('paper','cand-f','FLOWUSDT','OPEN',100);
    """)
    payload = dict(
        expected_identity="synthetic-db",
        backend=dict(
            ok=True, component="paper_backend", mode="paper",
            paper_live_safe=True, database_identity="synthetic-db",
            build_sha=INCIDENT_BACKEND_SHA, process_instance_id="synthetic-instance",
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
    for sym, tid, cid in (("JASMYUSDT", JASMY_TRADE_ID, JASMY_CANDIDATE_ID), ("FLOWUSDT", "trade-f", "cand-f")):
        symbol = Symbol(sym)
        trades[tid] = SimpleNamespace(
            trade_id=tid, candidate_id=cid, symbol=symbol,
            trading_account_id=ACCOUNT, entry_path="LIMIT",
            direction="SHORT" if sym == "JASMYUSDT" else "LONG",
            pattern="Double Top" if sym == "JASMYUSDT" else "MIRROR",
            entry_quantity=Decimal("399" if sym == "JASMYUSDT" else "6550.8"),
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


def stale_incident_fixture():
    """Exactly the six incident approvals; never write to the real PAPER DB."""
    conn, payload, store = fixture()
    conn.executescript("""
        ALTER TABLE robot_candidates ADD COLUMN state_revision INTEGER;
        ALTER TABLE robot_candidates ADD COLUMN robot_state_json TEXT;
        ALTER TABLE paper_limit_orders ADD COLUMN order_id TEXT;
        ALTER TABLE paper_limit_orders ADD COLUMN filled_quantity TEXT DEFAULT '0';
        ALTER TABLE trading_commands ADD COLUMN exchange_order_id TEXT;
        ALTER TABLE trading_commands ADD COLUMN order_link_id TEXT;
        ALTER TABLE executions ADD COLUMN order_id TEXT;
        CREATE TABLE box_order_ownership (
            trading_account_id TEXT, candidate_id TEXT, order_id TEXT, role TEXT
        );
        CREATE TABLE robot_entry_orders (
            trading_account_id TEXT, order_id TEXT
        );
        CREATE TABLE box_attempt_ownership (
            trading_account_id TEXT, candidate_id TEXT
        );
    """)
    original_get = store.get_robot_candidate.side_effect
    approved_candidates = {}
    for symbol, (prefix, suffix) in IDLE_APPROVALS.items():
        candidate_id = prefix if not suffix else prefix + ("0" * 32) + suffix
        conn.execute(
            "INSERT INTO robot_candidates "
            "(trading_account_id,candidate_id,symbol,status,approved_at_ms,"
            "state_revision,robot_state_json) VALUES (?,?,?,?,?,0,NULL)",
            ("paper", candidate_id, symbol, "APPROVED", 200),
        )
        approved_candidates[candidate_id] = SimpleNamespace(
            candidate_id=candidate_id, trading_account_id=ACCOUNT,
            symbol=Symbol(symbol), status="APPROVED", approved_at_ms=200,
        )
    store.get_robot_candidate.side_effect = lambda cid: (
        approved_candidates[cid] if cid in approved_candidates else original_get(cid)
    )
    payload["protection"] = dict(
        healthy=False,
        unhealthy_symbols={
            "JASMYUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
            "FLOWUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
        },
        covered_symbols=["JASMYUSDT", "FLOWUSDT", "BBUSDT", "KITEUSDT"],
        armed_symbols=["BBUSDT", "KITEUSDT"],
        coverage_roles={
            "JASMYUSDT": "EXPOSURE", "FLOWUSDT": "EXPOSURE",
            "BBUSDT": "ENTRY_PENDING", "KITEUSDT": "ENTRY_PENDING",
        },
    )
    return conn, payload, store


def check(conn, payload, store, *, evidence=None):
    # The caller supplies a single pinned READ-ONLY transaction. The proof
    # must not silently accept an autocommit or writable SQLite connection.
    conn.commit()
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    try:
        with (
            mock.patch("tools.paper_two_orphan_proof.SQLiteStore", return_value=store),
            mock.patch("tools.paper_two_orphan_proof.robot_entry_order_ids", return_value=(
                SimpleNamespace(value="entry-1"),)),
            mock.patch("tools.paper_two_orphan_proof.PaperRuntime._robot_entry_fees", return_value=0),
            mock.patch("tools.paper_two_orphan_proof.prove_nonrobot_robot_close", side_effect=evidence),
        ):
            return prove_two_flat_orphans(conn, **payload)
    finally:
        conn.rollback()
        conn.execute("PRAGMA query_only=OFF")


class DualOrphanPreflightTests(TestCase):
    def test_proof_rejects_autocommit_and_write_capable_snapshot(self):
        conn, payload, store = fixture()
        with self.assertRaisesRegex(FlatRecoveryBlocked, "stable_snapshot_transaction_required"):
            prove_two_flat_orphans(conn, **payload)
        conn.execute("BEGIN")
        try:
            with self.assertRaisesRegex(FlatRecoveryBlocked, "read_only_snapshot_required"):
                prove_two_flat_orphans(conn, **payload)
        finally:
            conn.rollback()

    def test_both_lots_need_independent_verified_close_evidence_read_only(self):
        conn, payload, store = fixture()
        before = conn.total_changes
        self.assertEqual(
            check(conn, payload, store, evidence=[object(), object()]), PROOF_LABEL,
        )
        self.assertEqual(conn.total_changes, before)
        self.assertEqual(store.get_robot_trade.call_count, 2)
        self.assertEqual(
            {call.args[0] for call in store.get_robot_trade.call_args_list},
            {JASMY_TRADE_ID, "trade-f"},
        )
        self.assertEqual(
            {call.args[0] for call in store.load_executions_for_symbol.call_args_list},
            {ACCOUNT},
        )
        self.assertEqual(
            {call.args[1].value for call in store.load_executions_for_symbol.call_args_list},
            {"JASMYUSDT", "FLOWUSDT"},
        )
        self.assertEqual(store.get_paper_command_by_order_link.call_count, 2)

    def test_sqlite_row_factory_does_not_reject_valid_read_only_snapshot(self):
        conn, payload, store = fixture()
        conn.row_factory = sqlite3.Row
        self.assertEqual(
            check(conn, payload, store, evidence=[object(), object()]), PROOF_LABEL,
        )

    def test_inspector_opens_pinned_read_only_sqlite_without_writing(self):
        conn, payload, store = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.sqlite3"
            conn.commit()
            with sqlite3.connect(path) as destination:
                conn.backup(destination)
            conn.close()
            identity = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
            payload["expected_identity"] = identity
            payload["backend"]["database_identity"] = identity
            with (
                mock.patch("tools.paper_two_orphan_proof.SQLiteStore", return_value=store),
                mock.patch("tools.paper_two_orphan_proof.robot_entry_order_ids", return_value=(
                    SimpleNamespace(value="entry-1"),)),
                mock.patch("tools.paper_two_orphan_proof.PaperRuntime._robot_entry_fees", return_value=0),
                mock.patch("tools.paper_two_orphan_proof.prove_nonrobot_robot_close",
                           side_effect=[object(), object()]),
            ):
                self.assertEqual(inspect_read_only(
                    path, expected_identity=payload["expected_identity"],
                    snapshots={k: v for k, v in payload.items() if k != "expected_identity"},
                ), PROOF_LABEL)
            with self.assertRaisesRegex(FlatRecoveryBlocked, "paper_database_path_identity_mismatch"):
                inspect_read_only(
                    path, expected_identity="wrong-db-path-identity",
                    snapshots={k: v for k, v in payload.items() if k != "expected_identity"},
                )
            with sqlite3.connect(path) as unchanged:
                self.assertEqual(unchanged.execute(
                    "SELECT COUNT(*) FROM robot_trades WHERE exit_time_ms IS NULL"
                ).fetchone()[0], 2)

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
        conn.execute("INSERT INTO robot_candidates VALUES ('paper','approved','DOGEUSDT','APPROVED',100)")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_active_robot_candidate"):
            check(conn, payload, store)
        conn.execute("DELETE FROM robot_candidates WHERE candidate_id='approved'")
        conn.execute("INSERT INTO robot_trades VALUES ('paper','trade-x','cand-x','DOGEUSDT',NULL)")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_open_robot_owners"):
            check(conn, payload, store)

    def test_healthy_orphans_reject_unpinned_partial_approval(self):
        conn, payload, store = fixture()
        conn.execute(
            "INSERT INTO robot_candidates VALUES "
            "('paper','unrelated-approved','1000FLOKIUSDT','APPROVED',200)"
        )
        # Valid symbol and apparently healthy protection must not authorize
        # an unrelated candidate during exceptional protected handoff.
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_active_robot_candidate"):
            check(conn, payload, store, evidence=[object(), object()])

    def test_healthy_orphans_still_verify_all_six_exact_approvals(self):
        conn, payload, store = stale_incident_fixture()
        payload["protection"] = dict(
            healthy=True, unhealthy_symbols={},
            covered_symbols=["JASMYUSDT", "FLOWUSDT"], armed_symbols=[],
            coverage_roles={"JASMYUSDT": "EXPOSURE", "FLOWUSDT": "EXPOSURE"},
        )
        self.assertEqual(
            check(conn, payload, store, evidence=[object(), object()]), PROOF_LABEL,
        )
        conn.execute("INSERT INTO executions "
                     "(trading_account_id,symbol,exchange_timestamp_ms) "
                     "VALUES ('paper','1000FLOKIUSDT',200)")
        with self.assertRaisesRegex(
            FlatRecoveryBlocked, "approved_candidate_execution_or_ownership_unknown",
        ):
            check(conn, payload, store, evidence=[object(), object()])
        conn.execute("DELETE FROM executions")
        conn.execute(
            "INSERT INTO paper_limit_orders "
            "(trading_account_id,status,symbol,created_at_ms) "
            "VALUES ('paper','filled','1000FLOKIUSDT',201)"
        )
        with self.assertRaisesRegex(
            FlatRecoveryBlocked, "approved_candidate_execution_or_ownership_unknown",
        ):
            check(conn, payload, store, evidence=[object(), object()])
        conn.execute("DELETE FROM paper_limit_orders")
        conn.execute(
            "INSERT INTO trading_commands VALUES ('paper','filled','1000FLOKIUSDT',201)"
        )
        with self.assertRaisesRegex(
            FlatRecoveryBlocked, "approved_candidate_execution_or_ownership_unknown",
        ):
            check(conn, payload, store, evidence=[object(), object()])

    def test_stale_incident_requires_all_six_exact_idle_approvals(self):
        conn, payload, store = stale_incident_fixture()
        self.assertEqual(
            check(conn, payload, store, evidence=[object(), object()]), PROOF_LABEL,
        )
        conn.execute(
            "DELETE FROM robot_candidates WHERE symbol='BNCUSDT' AND status='APPROVED'"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_active_robot_candidate"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE robot_candidates SET candidate_id='spoofed' "
            "WHERE symbol='HEMIUSDT' AND status='APPROVED'"
        )
        # The missing BNC owner alone is enough to reject the legacy exception.
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_active_robot_candidate"):
            check(conn, payload, store)

    def test_six_exact_progressed_approvals_with_cancelled_zero_fill_are_inert(self):
        conn, payload, store = stale_incident_fixture()
        revisions = {
            "1000FLOKIUSDT": (6, "BOX_ENTRY_READY", 4),
            "BNCUSDT": (6, "RETEST_DETECTED", 1),
            "HEMIUSDT": (6, "BOX_ENTRY_READY", 4),
            "INUSDT": (6, "BOX_ENTRY_READY", 4),
            "PLAYSOUTUSDT": (4, "RETEST_DETECTED", 1),
            "RUNEUSDT": (3, "BOX_ENTRY_READY", 0),
        }
        for symbol, (revision, phase, count) in revisions.items():
            prefix, suffix = IDLE_APPROVALS[symbol]
            candidate_id = prefix if not suffix else prefix + ("0" * 32) + suffix
            state = {"phase": phase, "state_version": "1.0"}
            if phase == "BOX_ENTRY_READY":
                state["source_box_candidate_id"] = (
                    "box-plan-" + candidate_id.removeprefix("box-robot-")
                )
            conn.execute(
                "UPDATE robot_candidates SET state_revision=?, robot_state_json=? "
                "WHERE candidate_id=?",
                (revision, json.dumps(state), candidate_id),
            )
            for slot in range(count):
                order_id = f"cancelled-{symbol}-{slot}"
                conn.execute(
                    "INSERT INTO paper_limit_orders "
                    "(trading_account_id,status,symbol,created_at_ms,order_id,filled_quantity) "
                    "VALUES ('paper','cancelled',?,201,?,'0')",
                    (symbol, order_id),
                )
                conn.execute(
                    "INSERT INTO robot_entry_orders VALUES ('paper',?)", (order_id,),
                )
                if phase == "BOX_ENTRY_READY":
                    conn.execute(
                        "INSERT INTO box_order_ownership VALUES ('paper',?,?,'ENTRY')",
                        (state["source_box_candidate_id"], order_id),
                    )
        self.assertEqual(check(conn, payload, store, evidence=[object(), object()]),
                         PROOF_LABEL)

        # A nonzero cancelled partial fill is never inert even if the
        # order's terminal status says cancelled and no execution was linked.
        conn.execute(
            "UPDATE paper_limit_orders SET filled_quantity='0.1' "
            "WHERE symbol='BNCUSDT'"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "approved_candidate_has_admission_progress"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE paper_limit_orders SET filled_quantity='0' "
            "WHERE symbol='BNCUSDT'"
        )
        conn.execute(
            "UPDATE robot_candidates SET state_revision=7 WHERE symbol='BNCUSDT'"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "approved_candidate_has_admission_progress"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE robot_candidates SET state_revision=6 WHERE symbol='BNCUSDT'"
        )
        conn.execute(
            "UPDATE box_order_ownership SET role='EXIT' WHERE order_id='cancelled-HEMIUSDT-0'"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "approved_candidate_has_admission_progress"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE box_order_ownership SET role='ENTRY' WHERE order_id='cancelled-HEMIUSDT-0'"
        )
        conn.execute(
            "INSERT INTO executions (trading_account_id,symbol,exchange_timestamp_ms,order_id) "
            "VALUES ('paper','HEMIUSDT',201,'cancelled-HEMIUSDT-0')"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "approved_candidate_has_admission_progress"):
            check(conn, payload, store)

    def test_stale_approval_identity_progress_and_box_owner_fail_closed(self):
        conn, payload, store = stale_incident_fixture()
        bnc = IDLE_APPROVALS["BNCUSDT"][0]
        conn.execute(
            "UPDATE robot_candidates SET candidate_id='different' WHERE candidate_id=?",
            (bnc,),
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_approved_candidate_identity"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE robot_candidates SET candidate_id=? WHERE candidate_id='different'", (bnc,)
        )
        conn.execute(
            "UPDATE robot_candidates SET state_revision=1 WHERE candidate_id=?", (bnc,)
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "approved_candidate_has_admission_progress"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE robot_candidates SET state_revision=0, robot_state_json='{}' "
            "WHERE candidate_id=?", (bnc,)
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "approved_candidate_has_admission_progress"):
            check(conn, payload, store)
        conn.execute(
            "UPDATE robot_candidates SET robot_state_json=NULL WHERE candidate_id=?", (bnc,)
        )
        conn.execute(
            "INSERT INTO box_attempt_ownership VALUES ('paper',?)", (bnc,)
        )
        with self.assertRaisesRegex(
            FlatRecoveryBlocked, "approved_candidate_execution_or_ownership_unknown",
        ):
            check(conn, payload, store)

    def test_stale_approval_orphan_entry_order_metadata_blocks(self):
        conn, payload, store = stale_incident_fixture()
        conn.execute(
            "INSERT INTO robot_entry_orders VALUES ('paper','missing-order')"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "orphan_robot_entry_order_metadata"):
            check(conn, payload, store)

    def test_exact_flat_only_unhealthy_coverage_is_not_any_health_bypass(self):
        conn, payload, store = stale_incident_fixture()
        payload["protection"] = dict(
            healthy=False,
            unhealthy_symbols={
                "JASMYUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
                "FLOWUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
            },
            covered_symbols=["JASMYUSDT", "FLOWUSDT", "BBUSDT", "KITEUSDT"],
            armed_symbols=["BBUSDT", "KITEUSDT"],
            coverage_roles={
                "JASMYUSDT": "EXPOSURE", "FLOWUSDT": "EXPOSURE",
                "BBUSDT": "ENTRY_PENDING", "KITEUSDT": "ENTRY_PENDING",
            },
        )
        self.assertEqual(
            check(conn, payload, store, evidence=[object(), object()]), PROOF_LABEL,
        )
        # Do not reuse this incident-only exception for other protection failures.
        for wrong_reason in (
            "ingress_overflow", "continuity_lost", "websocket_disconnected",
        ):
            payload["protection"]["unhealthy_symbols"]["JASMYUSDT"] = wrong_reason
            with self.assertRaisesRegex(FlatRecoveryBlocked, "protection_unhealthy"):
                check(conn, payload, store)
        payload["protection"]["unhealthy_symbols"]["JASMYUSDT"] = (
            "websocket_disconnect:WebSocketConnectionClosedException"
        )
        payload["protection"]["unhealthy_symbols"]["DOGEUSDT"] = "ingress_overflow"
        with self.assertRaisesRegex(FlatRecoveryBlocked, "protection_unhealthy"):
            check(conn, payload, store)
        del payload["protection"]["unhealthy_symbols"]["DOGEUSDT"]
        payload["protection"]["coverage_roles"]["BBUSDT"] = "OBLIGATION"
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_protection_coverage"):
            check(conn, payload, store)
        payload["protection"]["coverage_roles"]["BBUSDT"] = "ENTRY_PENDING"
        conn.execute(
            "INSERT INTO paper_limit_orders "
            "(trading_account_id,status,symbol,created_at_ms) "
            "VALUES ('paper','open','BBUSDT',201)"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "active_or_unknown_paper_limit"):
            check(conn, payload, store)

    def test_wrong_backend_or_extra_coverage_cannot_authorize_incident(self):
        conn, payload, store = fixture()
        payload["backend"]["build_sha"] = "other-build"
        with self.assertRaisesRegex(FlatRecoveryBlocked, "paper_backend_identity_unproven"):
            check(conn, payload, store)
        payload["backend"]["build_sha"] = INCIDENT_BACKEND_SHA
        payload["protection"]["coverage_roles"]["OTHERUSDT"] = "EXPOSURE"
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_protection_coverage"):
            check(conn, payload, store)

    def test_other_jasmy_trade_or_wrong_flow_lot_is_not_the_incident(self):
        conn, payload, store = fixture()
        conn.execute(
            "UPDATE robot_trades SET trade_id='replacement' "
            "WHERE trade_id=?", (JASMY_TRADE_ID,)
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unexpected_incident_robot_lot"):
            check(conn, payload, store, evidence=[object(), object()])
        conn.execute(
            "UPDATE robot_trades SET trade_id=? WHERE trade_id='replacement'",
            (JASMY_TRADE_ID,),
        )
        flow = store.get_robot_trade("trade-f")
        flow.entry_quantity = Decimal("1")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "orphan_lot_identity_unproven"):
            check(conn, payload, store, evidence=[object(), object()])

    def test_duplicate_flat_projection_is_not_unique_owner_evidence(self):
        conn, payload, store = fixture()
        conn.execute(
            "INSERT INTO position_projections VALUES ('paper','FLOWUSDT','Flat','0','synced')"
        )
        with self.assertRaisesRegex(FlatRecoveryBlocked, "ambiguous_orphan_position_projection"):
            check(conn, payload, store)

    def test_pending_command_and_limit_block(self):
        conn, payload, store = fixture()
        conn.execute("INSERT INTO trading_commands VALUES ('paper','submitting','DOGEUSDT',100)")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "unfinished_or_unknown_trading_command"):
            check(conn, payload, store)
        conn.execute("DELETE FROM trading_commands")
        conn.execute("INSERT INTO paper_limit_orders VALUES ('paper','new','DOGEUSDT',100)")
        with self.assertRaisesRegex(FlatRecoveryBlocked, "active_or_unknown_paper_limit"):
            check(conn, payload, store)
