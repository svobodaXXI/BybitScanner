"""Focused acceptance for the legacy protection recovery operator boundary.

Covers only what the application command itself owns: identity-only input,
delegation to the already-proven persistence attestation, idempotent replay,
fail-closed rejection, deterministic connection lifetime, and the absence of
any reconcile/Market side effect. Ownership-proof semantics stay covered by
tests/test_robot_legacy_protection_recovery.py and the reconciliation
lifecycle stays covered by tests/test_robot_legacy_protection_reconciliation.py.
"""

import ast
import inspect
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from terminal.application import robot_legacy_protection_recovery as command_module
from terminal.application.robot_legacy_protection_recovery import (
    attest_legacy_protection_recovery,
)
from terminal.persistence.legacy_protection_recovery import (
    LEGACY_ATTESTATION_SOURCE,
    LegacyProtectionRecoveryRejected,
)
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_legacy_protection_recovery import (
    ACTION_ID,
    ENTRY_ORDER_ID,
    POSITION_KEY,
    TRADE_ID,
    LegacyProtectionRecoveryFixture,
)


class LegacyProtectionRecoveryCommandTests(LegacyProtectionRecoveryFixture):
    def seed(self):
        """Build the eligible legacy scenario, then release the connection.

        The command owns its own short-lived connection, so the fixture's
        connection must be closed before the command runs.
        """
        with self.open_store() as store:
            _runtime, _trade, _candidate, obligation, position, executions = (
                self.seed_legacy_trade(store)
            )
            return obligation, position, executions

    def read_trade(self):
        with self.open_store() as store:
            return store.get_robot_trade(TRADE_ID)

    def read_audit(self):
        with self.open_store() as store:
            candidate = store.get_robot_candidate(
                store.get_robot_trade(TRADE_ID).candidate_id
            )
        execution_state = (candidate.robot_state or {}).get("execution") or {}
        return execution_state.get("legacy_entry_attestation")

    def ledger_snapshot(self):
        with self.open_store() as store:
            return (
                store.load_executions(),
                store.get_position_projection(POSITION_KEY),
                store.get_paper_protection_obligation_for_trade(TRADE_ID),
            )

    # -- delegation ------------------------------------------------------

    def test_successful_command_persists_canonical_attestation(self):
        obligation, position, _executions = self.seed()

        result = attest_legacy_protection_recovery(
            trade_id=TRADE_ID,
            obligation_id=obligation.obligation_id,
            client_action_id=ACTION_ID,
            database_path=self.database_path,
            clock_ms=lambda: 1500,
        )

        self.assertTrue(result.created)
        self.assertEqual(result.trade.entry_quantity, Decimal("2"))
        self.assertEqual(result.trade.entry_position_version, position.version)

        # Durable, not merely returned in memory.
        persisted = self.read_trade()
        self.assertEqual(persisted.entry_quantity, Decimal("2"))
        self.assertEqual(persisted.entry_position_version, position.version)

        audit = self.read_audit()
        self.assertEqual(audit["source"], LEGACY_ATTESTATION_SOURCE)
        self.assertEqual(audit["client_action_id"], ACTION_ID)
        self.assertEqual(audit["trade_id"], TRADE_ID)
        self.assertEqual(audit["obligation_id"], obligation.obligation_id)
        self.assertEqual(audit["entry_order_id"], ENTRY_ORDER_ID)
        self.assertEqual(audit["entry_quantity"], "2")
        self.assertEqual(audit["authorized_at_ms"], 1500)

    def test_same_client_action_id_replay_is_idempotent(self):
        obligation, _position, _executions = self.seed()

        first = attest_legacy_protection_recovery(
            trade_id=TRADE_ID,
            obligation_id=obligation.obligation_id,
            client_action_id=ACTION_ID,
            database_path=self.database_path,
            clock_ms=lambda: 1500,
        )
        first_audit = self.read_audit()

        repeated = attest_legacy_protection_recovery(
            trade_id=TRADE_ID,
            obligation_id=obligation.obligation_id,
            client_action_id=ACTION_ID,
            database_path=self.database_path,
            clock_ms=lambda: 1600,
        )

        self.assertTrue(first.created)
        self.assertFalse(repeated.created)
        self.assertEqual(repeated.trade.version, first.trade.version)
        self.assertEqual(repeated.candidate.state_revision, first.candidate.state_revision)
        # A later authorization instant must not rewrite proven evidence.
        self.assertEqual(self.read_audit(), first_audit)

    # -- fail closed -----------------------------------------------------

    def test_rejected_proof_persists_nothing(self):
        obligation, _position, _executions = self.seed()
        with self.open_store() as store:
            with store._transaction():
                store._connection.execute(
                    "UPDATE paper_protection_obligations SET observed_quantity='3' "
                    "WHERE obligation_id=?",
                    (obligation.obligation_id,),
                )
        before = self.ledger_snapshot()

        with self.assertRaises(LegacyProtectionRecoveryRejected):
            attest_legacy_protection_recovery(
                trade_id=TRADE_ID,
                obligation_id=obligation.obligation_id,
                client_action_id=ACTION_ID,
                database_path=self.database_path,
                clock_ms=lambda: 1500,
            )

        trade = self.read_trade()
        self.assertIsNone(trade.entry_quantity)
        self.assertIsNone(trade.entry_position_version)
        self.assertIsNone(self.read_audit())
        self.assertEqual(self.ledger_snapshot(), before)

    def test_invalid_identifiers_and_clock_fail_closed(self):
        obligation, _position, _executions = self.seed()
        valid = {
            "trade_id": TRADE_ID,
            "obligation_id": obligation.obligation_id,
            "client_action_id": ACTION_ID,
            "database_path": self.database_path,
        }
        invalid_cases = (
            {"trade_id": ""},
            {"trade_id": "   "},
            {"obligation_id": ""},
            {"client_action_id": ""},
            {"clock_ms": lambda: -1},
            {"clock_ms": lambda: True},
            {"clock_ms": lambda: 1500.0},
        )
        for override in invalid_cases:
            with self.subTest(override=sorted(override)):
                with self.assertRaises(ValueError):
                    attest_legacy_protection_recovery(**{**valid, **override})

        trade = self.read_trade()
        self.assertIsNone(trade.entry_quantity)
        self.assertIsNone(trade.entry_position_version)
        self.assertIsNone(self.read_audit())

    def test_invalid_database_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Exception) as caught:
                attest_legacy_protection_recovery(
                    trade_id=TRADE_ID,
                    obligation_id="any-obligation",
                    client_action_id=ACTION_ID,
                    database_path=directory,
                    clock_ms=lambda: 1500,
                )
            self.assertNotIsInstance(caught.exception, AssertionError)

    # -- no side effect / deterministic connection lifetime --------------

    def test_command_creates_no_market_execution_or_order_side_effect(self):
        obligation, _position, _executions = self.seed()
        with self.open_store() as store:
            limit_orders_before = store._connection.execute(
                "SELECT count(*) FROM paper_limit_orders"
            ).fetchone()[0]
        before = self.ledger_snapshot()

        attest_legacy_protection_recovery(
            trade_id=TRADE_ID,
            obligation_id=obligation.obligation_id,
            client_action_id=ACTION_ID,
            database_path=self.database_path,
            clock_ms=lambda: 1500,
        )

        with self.open_store() as store:
            limit_orders_after = store._connection.execute(
                "SELECT count(*) FROM paper_limit_orders"
            ).fetchone()[0]
        # Executions, position projection, obligation and orders are all
        # untouched: attestation repairs ownership evidence only.
        self.assertEqual(self.ledger_snapshot(), before)
        self.assertEqual(limit_orders_after, limit_orders_before)

    def test_store_is_closed_on_success_and_on_rejection(self):
        obligation, _position, _executions = self.seed()
        real_close = SQLiteStore.close
        closed = []

        def counting_close(store_self):
            closed.append(id(store_self))
            return real_close(store_self)

        with patch.object(SQLiteStore, "close", counting_close):
            attest_legacy_protection_recovery(
                trade_id=TRADE_ID,
                obligation_id=obligation.obligation_id,
                client_action_id=ACTION_ID,
                database_path=self.database_path,
                clock_ms=lambda: 1500,
            )
            self.assertEqual(len(closed), 1)

            # An exception raised after the connection is open must still
            # release it exactly once.
            with self.assertRaises(ValueError):
                attest_legacy_protection_recovery(
                    trade_id=TRADE_ID,
                    obligation_id=obligation.obligation_id,
                    client_action_id="another-action",
                    database_path=self.database_path,
                    clock_ms=lambda: -1,
                )
            self.assertEqual(len(closed), 2)

    # -- boundary shape --------------------------------------------------

    def test_boundary_accepts_identities_only(self):
        parameters = inspect.signature(attest_legacy_protection_recovery).parameters
        self.assertEqual(
            set(parameters),
            {"trade_id", "obligation_id", "client_action_id", "database_path", "clock_ms"},
        )
        # The operator can never supply ownership economics.
        for forbidden in ("quantity", "version", "price", "http_post", "backend_url"):
            self.assertTrue(
                all(forbidden not in name for name in parameters),
                msg=f"operator-supplied {forbidden} must not be accepted",
            )
        for name, parameter in parameters.items():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY, msg=name)

    def test_boundary_invokes_no_reconcile_and_no_execution_port(self):
        source = Path(command_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertTrue(
            {
                "terminal.application.robot_control",
                "terminal.runtime.paper_runtime",
                "terminal.runtime.paper_http_server",
                "terminal.paper.executor",
                "requests",
            }.isdisjoint(imported)
        )

        called = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if isinstance(target, ast.Name):
                called.add(target.id)
            elif isinstance(target, ast.Attribute):
                called.add(target.attr)
        forbidden_calls = {
            "reconcile_robot",
            "robot_reconcile",
            "request_maintenance_reconciliation",
            "robot_synchronize_pending_entries",
            "close_all_now",
            "execute",
            "market",
            "post",
        }
        self.assertTrue(forbidden_calls.isdisjoint(called))
        # Exactly one persistence entry point is delegated to.
        self.assertIn("attest_legacy_robot_entry", called)


if __name__ == "__main__":
    unittest.main()
