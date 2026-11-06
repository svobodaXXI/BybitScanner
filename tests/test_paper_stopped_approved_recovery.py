"""Fail-closed evidence for the 2026-11-06 interrupted PAPER STOP."""
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from tools import paper_stopped_approved_recovery as recovery


def fixture():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    CREATE TABLE robot_runtime_state (
        trading_account_id TEXT, mode TEXT, recovery_status TEXT
    );
    INSERT INTO robot_runtime_state VALUES ('paper','ROBOT_STOPPED','ROBOT_STOPPED');
    CREATE TABLE scanner_runtime_state (
        trading_account_id TEXT, mode TEXT
    );
    INSERT INTO scanner_runtime_state VALUES ('paper','SCANNER_STOPPED');
    CREATE TABLE robot_autopilot_state (
        trading_account_id TEXT, mode TEXT
    );
    INSERT INTO robot_autopilot_state VALUES ('paper','OFF');
    CREATE TABLE position_projections (
        trading_account_id TEXT, symbol TEXT, side TEXT,
        quantity TEXT, sync_state TEXT
    );
    INSERT INTO position_projections VALUES ('paper','ABCUSDT','Flat','0','synced');
    CREATE TABLE robot_trades (
        trading_account_id TEXT, candidate_id TEXT, exit_time_ms INTEGER
    );
    CREATE TABLE paper_limit_orders (trading_account_id TEXT, status TEXT, symbol TEXT, created_at_ms INTEGER);
    CREATE TABLE trading_commands (trading_account_id TEXT, current_state TEXT, symbol TEXT, created_at_ms INTEGER);
    CREATE TABLE paper_protection_obligations (trading_account_id TEXT, status TEXT);
    CREATE TABLE reconciliation_checkpoints (
        trading_account_id TEXT, completed_at_ms INTEGER
    );
    CREATE TABLE robot_candidates (
        trading_account_id TEXT, candidate_id TEXT, symbol TEXT,
        status TEXT, approved_at_ms INTEGER
    );
    INSERT INTO robot_candidates VALUES
        ('paper','abc-1','ABCUSDT','APPROVED',1000);
    CREATE TABLE executions (
        trading_account_id TEXT, symbol TEXT, exchange_timestamp_ms INTEGER
    );
    """)
    data = {
        "backend": {
            "ok": True, "component": "paper_backend", "mode": "paper",
            "build_sha": recovery.OLD_BACKEND,
            "paper_live_safe": True,
            "database_identity": "x"*64,
            "process_instance_id": "current-process",
        },
        "scanner": {"ok": True, "mode": "SCANNER_STOPPED"},
        "autopilot": {"ok": True, "mode": "OFF"},
        "protection": {
            "ok": True, "healthy": True, "covered_symbols": [],
            "armed_symbols": [], "coverage_roles": {},
            "unhealthy_symbols": {},
        },
    }
    return db, data


class EvidenceTest(unittest.TestCase):
    def test_inert_approved_allowed_without_discarding_candidate(self):
        db, data = fixture()
        self.addCleanup(db.close)
        self.assertEqual(
            recovery.prove_stopped_inert_approvals(
                db, expected_identity="x"*64, snapshots=data),
            "STOPPED_INERT_APPROVALS_PROVEN_ONLY",
        )
        self.assertEqual(
            db.execute("SELECT status FROM robot_candidates").fetchone(),
            ("APPROVED",),
        )

    def test_no_active_approval_is_valid_flat_evidence(self):
        db, data = fixture()
        self.addCleanup(db.close)
        db.execute("DELETE FROM robot_candidates")
        self.assertEqual(
            recovery.prove_stopped_inert_approvals(
                db, expected_identity="x"*64, snapshots=data,
            ),
            "STOPPED_INERT_APPROVALS_PROVEN_ONLY",
        )

    def test_historical_fill_before_approval_is_not_entry_work(self):
        db, data = fixture()
        self.addCleanup(db.close)
        db.execute("INSERT INTO executions VALUES ('paper','ABCUSDT',999)")
        self.assertEqual(
            recovery.prove_stopped_inert_approvals(
                db, expected_identity="x"*64, snapshots=data,
            ),
            "STOPPED_INERT_APPROVALS_PROVEN_ONLY",
        )

    def test_denies_actual_or_ambiguous_paper_work(self):
        changes = {
            "live_position":
                "UPDATE position_projections SET side='Long',quantity='1'",
            "position_unsynced":
                "UPDATE position_projections SET sync_state='unknown'",
            "OPEN_candidate":
                "UPDATE robot_candidates SET status='OPEN'",
            "invalid_candidate":
                "UPDATE robot_candidates SET approved_at_ms=NULL",
            "candidate_trade":
                "INSERT INTO robot_trades VALUES ('paper','abc-1',123)",
            "historical_trade":
                "INSERT INTO robot_trades VALUES ('paper','abc-1',NULL)",
            "post_approval_fill":
                "INSERT INTO executions VALUES ('paper','ABCUSDT',1000)",
            "unknown_fill_time":
                "INSERT INTO executions VALUES ('paper','ABCUSDT',NULL)",
            "unknown_terminal_limit":
                "INSERT INTO paper_limit_orders VALUES ('paper','filled','ABCUSDT',NULL)",
            "new_terminal_command":
                "INSERT INTO trading_commands VALUES ('paper','filled','ABCUSDT',1000)",
            "unknown_terminal_command":
                "INSERT INTO trading_commands VALUES ('paper','filled','ABCUSDT',NULL)",
            "active_LIMIT":
                "INSERT INTO paper_limit_orders(trading_account_id,status) VALUES ('paper','open')",
            "unknown_LIMIT":
                "INSERT INTO paper_limit_orders VALUES ('paper',NULL)",
            "working_command":
                "INSERT INTO trading_commands(trading_account_id,current_state) VALUES ('paper','submitting')",
            "obligation":
                "INSERT INTO paper_protection_obligations VALUES ('paper','LATCHED')",
            "checkpoint":
                "INSERT INTO reconciliation_checkpoints VALUES ('paper',NULL)",
            "autopilot":
                "UPDATE robot_autopilot_state SET mode='PAPER_AUTO'",
            "robot_running":
                "UPDATE robot_runtime_state SET mode='ROBOT_RUNNING'",
            "scanner_running":
                "UPDATE scanner_runtime_state SET mode='SCANNER_RUNNING'",
        }
        for label, change in changes.items():
            with self.subTest(label=label):
                db, data = fixture()
                try:
                    db.execute(change)
                    with self.assertRaises(recovery.PartialStopBlocked):
                        recovery.prove_stopped_inert_approvals(
                            db, expected_identity="x"*64, snapshots=data)
                finally:
                    db.close()

    def test_denies_unknown_coverage_or_backend_identity(self):
        for label, operation in (
            ("covered", lambda s: s["protection"]["covered_symbols"].append("ABCUSDT")),
            ("roles", lambda s: s["protection"]["coverage_roles"].update(ABCUSDT="EXPOSURE")),
            ("unhealthy", lambda s: s["protection"].update(healthy=False)),
            ("SHA", lambda s: s["backend"].update(build_sha="z"*40)),
            ("DB", lambda s: s["backend"].update(database_identity="y"*64)),
            ("LIVE", lambda s: s["backend"].update(paper_live_safe=False)),
        ):
            with self.subTest(label=label):
                db, data = fixture()
                try:
                    operation(data)
                    with self.assertRaises(recovery.PartialStopBlocked):
                        recovery.prove_stopped_inert_approvals(
                            db, expected_identity="x"*64, snapshots=data)
                finally:
                    db.close()


class JournalTest(unittest.TestCase):
    def prepare(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        top = Path(temporary.name) / "trusted"
        top.mkdir(mode=0o700)
        transactions = top / "transactions"
        transactions.mkdir(mode=0o700)
        root = Path(temporary.name) / "installed"
        root.mkdir()
        stage = Path(temporary.name) / "stage"
        stage.mkdir()
        db = root / "paper.sqlite3"
        db.touch()
        (transactions / (".stop-invoked-" + recovery.PRIOR_TARGET)).write_bytes(
            b"STOP_INVOKED; not install authorization\\n"
        )
        for f in transactions.iterdir():
            f.chmod(0o600)
        return root, stage, transactions, db

    def test_once_and_never_repeat_uncertain_signal(self):
        root, stage, transactions, db = self.prepare()
        target = "a"*40
        fake_owner = mock.Mock()
        fake_owner._probe_backend.return_value = recovery.PRESENT
        fake_owner._probe_telegram.side_effect = [
            recovery.PRESENT, recovery.PRESENT, recovery.ABSENT,
        ]
        calls = {"signal": 0}

        def handoff(*args):
            calls["signal"] += 1
            return "OUTCOME_UNKNOWN"

        with (
            mock.patch.object(recovery.os, "geteuid", return_value=os.geteuid()),
            mock.patch("tools.paper_maintenance._proven_prior_exceptional_completion",
                       return_value=True),
            mock.patch.object(recovery, "verify_release",
                              return_value=recovery.OLD_BACKEND),
            mock.patch.object(recovery, "_environment", return_value={}),
            mock.patch.object(recovery, "expected_database_identity",
                              return_value="x"*64),
            mock.patch.object(recovery, "_database_path", return_value=db),
            mock.patch.object(recovery, "RuntimeShutdown", return_value=fake_owner),
        ):
            def attempt():
                return recovery.recover_editor_only(
                    target=target, stage=stage, root=root,
                    transactions=transactions, uid=os.geteuid(),
                    inspect=lambda *a, **k: None,
                    proof=lambda *a: {},
                    handoff=handoff,
                    backend_stopped=lambda: True,
                    installer=lambda *a, **k: "INSTALLED_STOPPED:",
                    resume=lambda *a, **k: "READY:",
                )
            with self.assertRaisesRegex(
                recovery.PartialStopBlocked, "backend_signal_outcome_unknown_no_retry"
            ):
                attempt()
            self.assertTrue(recovery._receipt(
                transactions, "handoff-attempt", os.geteuid(), target=target
            ))
            with self.assertRaisesRegex(
                recovery.PartialStopBlocked, "prior_backend_signal_unknown_no_retry"
            ):
                attempt()
            self.assertEqual(calls["signal"], 1)

    def test_foreign_receipt_is_not_authority(self):
        root, stage, transactions, db = self.prepare()
        path = transactions / (
            recovery.MARKER_PREFIX + "handoff-attempt-" + recovery.PRIOR_TARGET
        )
        path.write_text("foreign-target\n")
        with self.assertRaisesRegex(
            recovery.PartialStopBlocked, "recovery_receipt_invalid"
        ):
            recovery._receipt(transactions, "handoff-attempt",
                              os.geteuid(), target="a"*40)


if __name__ == "__main__":
    unittest.main()
