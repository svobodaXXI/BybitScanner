from __future__ import annotations

import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from http.server import ThreadingHTTPServer

from terminal.application.live_limit_acceptance import (
    LIVE_LIMIT_ACCEPTANCE_CAPABILITY, LiveLimitAcceptanceAdmin,
    RuntimeProcessIdentity,
)
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import (
    Category, CommandId, Controller, Notional, OrderId, OrderSide, Origin, Price,
    Quantity, Symbol, TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import (
    CommandRecord, LiveLimitRuntimeAttribution, PersistenceError, SQLiteStore,
)
from terminal.runtime.paper_http_server import PaperHttpHandler
from tools.dev.live_limit_acceptance import _parser, _request


ACCOUNT = TradingAccountId("bybit-main")
SYMBOL = Symbol("ONGUSDT")


class LiveLimitAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp.name) / "trading.sqlite3")
        self.manager = TradingAccountManager((TradingAccount(
            ACCOUNT, "Main", TradingAccountProvider.BYBIT,
            TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
        ),), active_account_id=ACCOUNT)
        self.now = 1000
        self.admin = self._admin()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _admin(self, *, build="build-1", writable=True):
        return LiveLimitAcceptanceAdmin(
            self.manager, self.store, build_sha=build,
            process_identity=RuntimeProcessIdentity(
                "process-1", 900, os.getpid(), "host/deployment",
            ), writable_account_provider=lambda _: writable,
            gates_provider=lambda: {
                "live_mainnet_authorized": False,
                "live_limit_mutations_enabled": False,
                "live_market_mutations_enabled": False,
                "live_parity_mutations_enabled": False,
            }, clock_ms=lambda: self.now,
        )

    def _arm(self, session_id="session-1", **changes):
        values = {
            "acceptance_session_id": session_id,
            "account_id": ACCOUNT.value,
            "environment": "MAINNET",
            "symbol": SYMBOL.value,
            "capability": LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
            "max_create_count": 1,
            "aggregate_notional_ceiling": Decimal("5.20"),
            "per_order_ceiling": Decimal("5.20"),
            "expires_at_ms": 2000,
            "operator_authorization_reference": "CR-r3.2/operator-test",
            "authorized_build_sha": "build-1",
            "authorized_database_identity": self.store.database_identity,
            "authorized_session_generation": 1,
        }
        values.update(changes)
        return self.admin.arm(**values)

    def _command(self):
        return CommandRecord(
            CommandId("cmd-1"), "link-1", ACCOUNT, Category.LINEAR, SYMBOL, 0,
            "create_limit", OrderSide.BUY, Notional(Decimal("5")),
            Price(Decimal("0.1")), Quantity(Decimal("50")), Origin.TERMINAL_MANUAL,
            Controller.MANUAL, CommandState.ADMITTED, 1, None, 1100, 1100,
        )

    def _runtime(self):
        return LiveLimitRuntimeAttribution(
            "build-1", "process-1", 900, os.getpid(), self.store.normalized_path,
            self.store.database_identity, SCHEMA_VERSION, "host/deployment",
        )

    def test_no_session_by_default_and_diagnostics_are_non_secret(self):
        diagnostics = self.admin.diagnostics()
        self.assertIsNone(diagnostics["current_acceptance_session"])
        self.assertEqual(diagnostics["acceptance_sessions"], ())
        self.assertEqual(diagnostics["build_sha"], "build-1")
        self.assertEqual(diagnostics["application_version"], "0.1.0")
        self.assertEqual(diagnostics["active_account_id"], ACCOUNT.value)
        self.assertEqual(diagnostics["account_session_generation"], 1)
        self.assertEqual(diagnostics["database_path"], self.store.normalized_path)
        self.assertEqual(diagnostics["schema_version"], SCHEMA_VERSION)
        self.assertFalse(any("secret" in key.lower() or "credential" in key.lower()
                             for key in diagnostics))

    def test_explicit_valid_session_arms_and_conflict_rejects(self):
        session = self._arm()
        self.assertEqual(session.state.value, "ARMED")
        with self.assertRaises(PersistenceError):
            self._arm("session-2")

    def test_authority_mismatches_and_invalid_limits_reject(self):
        cases = (
            {"authorized_build_sha": "wrong"},
            {"authorized_database_identity": "wrong"},
            {"authorized_session_generation": 2},
            {"account_id": "other"},
            {"max_create_count": 0},
            {"aggregate_notional_ceiling": Decimal("0")},
            {"per_order_ceiling": Decimal("6")},
            {"expires_at_ms": 1000},
        )
        for index, changes in enumerate(cases):
            with self.subTest(changes=changes), self.assertRaises((PersistenceError, ValueError)):
                self._arm(f"invalid-{index}", **changes)
        with self.assertRaises(PersistenceError):
            self._admin(writable=False).arm(**{
                "acceptance_session_id": "not-writable", "account_id": ACCOUNT.value,
                "environment": "MAINNET", "symbol": SYMBOL.value,
                "capability": LIVE_LIMIT_ACCEPTANCE_CAPABILITY, "max_create_count": 1,
                "aggregate_notional_ceiling": Decimal("5.20"),
                "per_order_ceiling": Decimal("5.20"), "expires_at_ms": 2000,
                "operator_authorization_reference": "CR-r3.2/test",
                "authorized_build_sha": "build-1",
                "authorized_database_identity": self.store.database_identity,
                "authorized_session_generation": 1,
            })

    def test_unresolved_action_blocks_new_session(self):
        self._arm()
        self.store.admit_live_limit_create(
            acceptance_session_id="session-1", environment="MAINNET",
            capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY, session_generation=1,
            client_action_id="action-1", request_fingerprint="fingerprint-1",
            record=self._command(), reserved_notional=Decimal("5"),
            runtime=self._runtime(), occurred_at_ms=1100,
        )
        with self.assertRaises(PersistenceError):
            self._arm("session-2")

    def test_unresolved_operation_blocks_new_session(self):
        self._arm()
        admission = self.store.admit_live_limit_create(
            acceptance_session_id="session-1", environment="MAINNET",
            capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY, session_generation=1,
            client_action_id="action-1", request_fingerprint="fingerprint-1",
            record=self._command(), reserved_notional=Decimal("5"),
            runtime=self._runtime(), occurred_at_ms=1100,
        )
        self.store.begin_live_limit_dispatch(
            admission.action, runtime=self._runtime(), occurred_at_ms=1101,
        )
        dispatching = self.store.get_live_limit_action(
            "session-1", ACCOUNT, 1, "action-1",
        )
        action = self.store.record_live_limit_outcome(
            dispatching, disposition="acknowledged",
            exchange_order_id=OrderId("exchange-1"), reason="ack", occurred_at_ms=1102,
        )
        parent = self.store.complete_live_limit_reconciliation(
            action, exchange_order_id=OrderId("exchange-1"), occurred_at_ms=1103,
        )
        amend = CommandRecord(
            CommandId("cmd-amend"), "operation-link", ACCOUNT, Category.LINEAR,
            SYMBOL, 0, "amend", OrderSide.BUY, Notional(Decimal("0")),
            Price(Decimal("0.09")), None, Origin.TERMINAL_MANUAL,
            Controller.MANUAL, CommandState.ADMITTED, 1, None, 1104, 1104,
        )
        self.store.admit_live_limit_operation(
            parent=parent, record=amend, operation="AMEND",
            client_action_id="amend-1", request_fingerprint="amend-fingerprint",
            requested_price=Decimal("0.09"), requested_quantity=None,
            conservative_notional=Decimal("4.5"), runtime=self._runtime(),
            occurred_at_ms=1104,
        )
        with self.assertRaises(PersistenceError):
            self._arm("session-2")

    def test_revoke_preserves_capacity_and_blocks_admission_or_rearm(self):
        self._arm()
        revoked = self.admin.revoke(
            acceptance_session_id="session-1", account_id=ACCOUNT.value,
            environment="MAINNET", symbol=SYMBOL.value,
            capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
        )
        self.assertEqual(revoked.state.value, "REVOKED")
        self.assertEqual((revoked.reserved_count, revoked.reserved_notional), (0, Decimal("0")))
        with self.assertRaises(PersistenceError):
            self.store.admit_live_limit_create(
                acceptance_session_id="session-1", environment="MAINNET",
                capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY, session_generation=1,
                client_action_id="action-1", request_fingerprint="fingerprint-1",
                record=self._command(), reserved_notional=Decimal("5"),
                runtime=self._runtime(), occurred_at_ms=1100,
            )
        with self.assertRaises(Exception):
            self._arm("session-1")

    def test_expiry_is_durable_and_stale_startup_authority_is_diagnostic(self):
        self._arm()
        self.now = 2000
        expired = self.admin.diagnostics()["current_acceptance_session"]
        self.assertEqual(expired["state"], "EXPIRED")
        with self.assertRaises(PersistenceError):
            self.store.select_live_limit_acceptance_session(
                account_id=ACCOUNT, environment="MAINNET", symbol=SYMBOL,
                capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY, session_generation=1,
                client_action_id="new", occurred_at_ms=2000,
            )
        with self.assertRaises(Exception):
            self._arm("session-1", expires_at_ms=3000)

        self.now = 1000
        fresh = self._arm("session-2", expires_at_ms=3000)
        self.assertEqual(fresh.state.value, "ARMED")
        stale = self._admin(build="other-build").diagnostics()["current_acceptance_session"]
        self.assertFalse(stale["authority_matches_runtime"])
        other = TradingAccountId("bybit-other")
        self.manager.register_inactive(TradingAccount(
            other, "Other", TradingAccountProvider.BYBIT,
            TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
        ))
        self.manager.activate(other)
        switched = self.admin.diagnostics()
        self.assertEqual(switched["active_account_id"], other.value)
        self.assertEqual(switched["current_acceptance_session"]["acceptance_session_id"],
                         "session-2")
        self.assertFalse(switched["current_acceptance_session"]["authority_matches_runtime"])

    def test_cli_arm_has_no_implicit_safety_values(self):
        with self.assertRaises(SystemExit):
            _parser().parse_args(["arm", "--acceptance-session-id", "only-one-value"])

    def test_operator_http_requires_token_and_returns_non_secret_diagnostics(self):
        diagnostics = self.admin.diagnostics()

        class Runtime:
            def call(self, operation):
                class Target:
                    def live_limit_acceptance_diagnostics(self):
                        return diagnostics
                return operation(Target())

        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = Runtime()
        operator_token = "test-operator-token-with-32-characters"
        server.operator_token = operator_token
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        backend = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(backend + "/api/operator/live-limit-acceptance")
            self.assertEqual(rejected.exception.code, 403)
            result = _request(
                backend, "/api/operator/live-limit-acceptance", operator_token,
            )
            self.assertTrue(result["ok"])
            self.assertNotIn("credentials", result)
            self.assertNotIn("api_secret", result)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
