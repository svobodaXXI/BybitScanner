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

    def test_post_shutdown_proof_requires_separately_stopped_services(self):
        db, data = fixture()
        self.addCleanup(db.close)
        with self.assertRaisesRegex(
            recovery.PartialStopBlocked, "services_not_proven_stopped"
        ):
            recovery.prove_stopped_inert_approvals(
                db, expected_identity="x"*64, snapshots=None,
            )
        self.assertEqual(
            recovery.prove_stopped_inert_approvals(
                db, expected_identity="x"*64, snapshots=None,
                stopped_services_proven=True,
            ),
            "STOPPED_INERT_APPROVALS_PROVEN_ONLY",
        )
        db.execute("UPDATE position_projections SET side='Long',quantity='1'")
        with self.assertRaises(recovery.PartialStopBlocked):
            recovery.prove_stopped_inert_approvals(
                db, expected_identity="x"*64, snapshots=None,
                stopped_services_proven=True,
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
                "INSERT INTO paper_limit_orders(trading_account_id,status) VALUES ('paper',NULL)",
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

    def test_late_post_shutdown_ledger_change_prevents_install(self):
        root, stage, transactions, db = self.prepare()
        target = "a" * 40
        owner = mock.Mock()
        owner._probe_backend.return_value = recovery.PRESENT
        owner._probe_telegram.side_effect = [
            recovery.PRESENT, recovery.PRESENT,
            recovery.ABSENT, recovery.ABSENT,
        ]
        installs = []
        with (
            mock.patch.object(recovery.os, "geteuid", return_value=os.geteuid()),
            mock.patch("tools.paper_maintenance._proven_prior_exceptional_completion",
                       return_value=True),
            mock.patch("tools.paper_maintenance._complete_stop_intent"),
            mock.patch.object(recovery, "verify_release",
                              return_value=recovery.OLD_BACKEND),
            mock.patch.object(recovery, "_environment", return_value={}),
            mock.patch.object(recovery, "expected_database_identity",
                              return_value="x"*64),
            mock.patch.object(recovery, "_database_path", return_value=db),
            mock.patch.object(recovery, "RuntimeShutdown", return_value=owner),
            mock.patch.object(recovery, "_post_shutdown_durable_proof",
                              side_effect=recovery.PartialStopBlocked(
                                  "late_exposure_detected",
                              )),
        ):
            with self.assertRaisesRegex(
                recovery.PartialStopBlocked, "late_exposure_detected",
            ):
                recovery.recover_editor_only(
                    target=target, stage=stage, root=root,
                    transactions=transactions, uid=os.geteuid(),
                    inspect=lambda *a, **k: None,
                    proof=lambda *a: {},
                    handoff=lambda *a: "INTERRUPT_EXIT_OBSERVED",
                    telegram=lambda: None,
                    backend_stopped=lambda: True,
                    installer=lambda *a, **kw: installs.append("install"),
                )
        self.assertEqual(installs, [])
        self.assertTrue(recovery._receipt(
            transactions, "handoff-proven", os.geteuid(), target=target,
        ))

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




class OneFlatPartialStopResumeTest(unittest.TestCase):
    """The already-consumed canonical STOP must never run a second time."""

    def prepare(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        parent = Path(temp.name)
        root = parent / "installed"
        root.mkdir()
        stage = parent / "stage"
        stage.mkdir()
        transactions = parent / "journal"
        transactions.mkdir(mode=0o700)
        prior = "b" * 40
        target = "c" * 40
        old = "a" * 40
        (transactions / (".stop-invoked-" + prior)).write_bytes(
            b"STOP_INVOKED; not install authorization\\n"
        )
        (transactions / (".stop-invoked-" + prior)).chmod(0o600)
        db = parent / "PAPER.sqlite"
        db.write_bytes(b"test fixture; never read as SQL")
        return root, stage, transactions, db, prior, target, old

    def owner(self, *, telegram_active=True):
        owner = mock.Mock()
        owner._probe_backend.return_value = recovery.PRESENT
        owner._probe_telegram.side_effect = (
            [recovery.PRESENT, recovery.ABSENT, recovery.ABSENT, recovery.ABSENT]
            if telegram_active else [recovery.ABSENT] * 4
        )
        owner._robot_state.return_value = (
            "ROBOT_RUNNING", "RECONCILIATION_REQUIRED"
        )
        return owner

    def patches(self, root, db, old, owner, snapshots):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(recovery, "verify_release",
                                              return_value=old))
        stack.enter_context(mock.patch.object(recovery, "_environment",
                                              return_value={}))
        stack.enter_context(mock.patch.object(recovery, "_database_path",
                                              return_value=db))
        stack.enter_context(mock.patch(
            "tools.runtime_intent.expected_database_identity",
            return_value="x" * 64,
        ))
        stack.enter_context(mock.patch.object(recovery, "RuntimeShutdown",
                                              return_value=owner))
        stack.enter_context(mock.patch(
            "tools.flat_paper_recovery_transition.get_snapshots",
            return_value=snapshots,
        ))
        stack.enter_context(mock.patch(
            "tools.flat_paper_recovery_transition._service_pid",
            return_value=12345,
        ))
        stage_proof = stack.enter_context(mock.patch(
            "tools.flat_paper_recovery_transition.execute_flat_handoff",
            return_value="PRECHECK_ONLY: immutable close and freeze proven",
        ))
        complete = stack.enter_context(mock.patch(
            "tools.paper_maintenance._complete_stop_intent"
        ))
        return stage_proof, complete

    def snapshot(self, old):
        return {
            "backend": {
                "ok": True, "component": "paper_backend", "mode": "paper",
                "paper_live_safe": True, "database_identity": "x" * 64,
                "build_sha": old, "process_instance_id": "pinned-process",
            },
            "scanner": {"mode": "SCANNER_STOPPED", "worker_quiescent": True},
            "autopilot": {"mode": "OFF"},
            "protection": {
                "healthy": False,
                "covered_symbols": ["BASEDUSDT"],
                "armed_symbols": [],
                "coverage_roles": {"BASEDUSDT": "EXPOSURE"},
                "unhealthy_symbols": {
                    "BASEDUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
                },
                "ingress": {"current_pending": 0},
            },
        }

    def test_single_continuation_records_exit_and_editor_without_second_stop(self):
        root, stage, transactions, db, prior, target, old = self.prepare()
        owner = self.owner()
        stage_proof, complete = self.patches(root, db, old, owner,
                                             self.snapshot(old))
        signals = []
        installs = []

        def handoff():
            signals.append("exact-pid-sigint")
            return "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed"

        result = recovery.recover_one_flat_after_failed_stop(
            target=target, stage=stage, prior_stop=prior,
            expected_old_sha=old, root=root, transactions=transactions,
            uid=os.geteuid(), inspect=lambda *a, **k: None,
            backend_handoff=handoff,
            backend_stopped=lambda: True,
            postproof=lambda: None,
            installer=lambda *a, **k: installs.append(k) or "INSTALLED_STOPPED: test",
            resume=lambda *a, **k: "READY: EDITOR_ONLY",
        )
        self.assertEqual(result, "READY: EDITOR_ONLY")
        self.assertEqual(signals, ["exact-pid-sigint"])
        self.assertEqual(len(installs), 1)
        self.assertEqual(stage_proof.call_count, 1)
        complete.assert_called_once()
        for phase in ("handoff-attempt", "backend-exited", "handoff-proven"):
            self.assertTrue(recovery._one_flat_receipt(
                transactions, prior, phase, target, uid=os.geteuid(),
            ))
        self.assertFalse((transactions / (".stop-invoked-" + target)).exists())
        self.assertTrue((transactions / (".stop-invoked-" + prior)).exists())

    def test_unknown_backend_exit_blocks_any_signal_replay(self):
        root, stage, transactions, db, prior, target, old = self.prepare()
        recovery._one_flat_record(transactions, prior, "handoff-attempt",
                                  target, uid=os.geteuid())
        owner = self.owner(telegram_active=False)
        self.patches(root, db, old, owner, self.snapshot(old))
        signals = []
        with self.assertRaisesRegex(
            recovery.PartialStopBlocked, "backend_signal_outcome_unknown_no_retry",
        ):
            recovery.recover_one_flat_after_failed_stop(
                target=target, stage=stage, prior_stop=prior,
                expected_old_sha=old, root=root, transactions=transactions,
                uid=os.geteuid(), inspect=lambda *a, **k: None,
                backend_handoff=lambda: signals.append("unsafe-replay"),
            )
        self.assertEqual(signals, [])

    def test_exit_receipt_resumes_without_sending_backend_signal(self):
        root, stage, transactions, db, prior, target, old = self.prepare()
        recovery._one_flat_snapshot(
            transactions, prior, uid=os.geteuid(), value=self.snapshot(old),
        )
        for phase in ("handoff-attempt", "backend-exited"):
            recovery._one_flat_record(
                transactions, prior, phase, target, uid=os.geteuid(),
            )
        owner = self.owner(telegram_active=False)
        owner._probe_telegram.side_effect = [recovery.ABSENT] * 3
        proof, complete = self.patches(root, db, old, owner, self.snapshot(old))
        signals = []
        result = recovery.recover_one_flat_after_failed_stop(
            target=target, stage=stage, prior_stop=prior,
            expected_old_sha=old, root=root, transactions=transactions,
            uid=os.geteuid(), inspect=lambda *a, **k: None,
            backend_handoff=lambda: signals.append("unsafe-replay"),
            backend_stopped=lambda: True, postproof=lambda: None,
            installer=lambda *a, **k: "INSTALLED_STOPPED: resumed",
            resume=lambda *a, **k: "READY: EDITOR_ONLY",
        )
        self.assertEqual(result, "READY: EDITOR_ONLY")
        self.assertEqual(signals, [])
        proof.assert_not_called()
        self.assertTrue(recovery._one_flat_receipt(
            transactions, prior, "handoff-proven", target, uid=os.geteuid(),
        ))
        complete.assert_called_once()

    def test_wrong_old_backend_rejected_before_signal(self):
        root, stage, transactions, db, prior, target, old = self.prepare()
        owner = self.owner()
        proof, _ = self.patches(root, db, old, owner, self.snapshot(old))
        with self.assertRaisesRegex(
            recovery.PartialStopBlocked, "old_release_identity_not_pinned",
        ):
            recovery.recover_one_flat_after_failed_stop(
                target=target, stage=stage, prior_stop=prior,
                expected_old_sha="d" * 40, root=root, transactions=transactions,
                uid=os.geteuid(), inspect=lambda *a, **k: None,
            )
        proof.assert_not_called()
        self.assertFalse(recovery._one_flat_path(
            transactions, prior, "handoff-attempt",
        ).exists())

    def test_preflight_proof_failure_never_seals_new_attempt(self):
        root, stage, transactions, db, prior, target, old = self.prepare()
        owner = self.owner()
        proof, _ = self.patches(root, db, old, owner, self.snapshot(old))
        proof.side_effect = recovery.PartialStopBlocked("new_ledger_evidence_missing")
        with self.assertRaisesRegex(
            recovery.PartialStopBlocked, "new_ledger_evidence_missing",
        ):
            recovery.recover_one_flat_after_failed_stop(
                target=target, stage=stage, prior_stop=prior,
                expected_old_sha=old, root=root, transactions=transactions,
                uid=os.geteuid(), inspect=lambda *a, **k: None,
            )
        self.assertFalse(recovery._one_flat_path(
            transactions, prior, "handoff-attempt",
        ).exists())

    def test_missing_prior_stop_intent_is_never_implicit_authorization(self):
        root, stage, transactions, db, prior, target, old = self.prepare()
        (transactions / (".stop-invoked-" + prior)).unlink()
        signals = []
        with self.assertRaises(Exception):
            recovery.recover_one_flat_after_failed_stop(
                target=target, stage=stage, prior_stop=prior,
                expected_old_sha=old, root=root, transactions=transactions,
                uid=os.geteuid(), inspect=lambda *a, **k: None,
                backend_handoff=lambda: signals.append("unsafe"),
            )
        self.assertEqual(signals, [])



if __name__ == "__main__":
    unittest.main()
