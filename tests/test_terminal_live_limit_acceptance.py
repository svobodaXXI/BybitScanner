import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest import mock

from terminal.application.live_limit_acceptance import (
    LIVE_LIMIT_ACCEPTANCE_AGGREGATE_CEILING,
    LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
    LIVE_LIMIT_ACCEPTANCE_MAX_CREATE_COUNT,
    LIVE_LIMIT_ACCEPTANCE_PER_ORDER_CEILING,
    LIVE_LIMIT_ACCEPTANCE_SYMBOL,
    LiveLimitAcceptanceService,
    RuntimeProcessIdentity,
)
from terminal.application.trading_accounts import (
    TradingAccount,
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
)
from terminal.domain.models import (
    Category, CommandId, Controller, Notional, OrderId, OrderSide, Origin,
    Price, Quantity, Symbol, TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.persistence.schema import (
    SCHEMA_STATEMENTS, SCHEMA_V13_MIGRATION_STATEMENTS, SCHEMA_VERSION,
)
from terminal.persistence.sqlite_store import (
    CommandRecord, DuplicateIdentity, LiveLimitAcceptanceSessionRecord,
    LiveLimitAcceptanceState, LiveLimitRuntimeAttribution, PersistenceError,
    SQLiteStore,
)


ACCOUNT_ID = TradingAccountId("main-bybit")
SYMBOL = Symbol("ONGUSDT")
BUILD_SHA = "bd3f9c29f609842e30c3e932b391205e24f2166d"


class LiveLimitAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "terminal.sqlite3"
        self.store = SQLiteStore.open(self.database_path, busy_timeout_ms=5000)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def runtime(self, store=None, **changes):
        owner = store or self.store
        values = {
            "build_sha": BUILD_SHA,
            "process_instance_id": "process-instance-1",
            "process_started_at_ms": 900,
            "process_id": os.getpid(),
            "database_path": owner.normalized_path,
            "database_identity": owner.database_identity,
            "schema_version": SCHEMA_VERSION,
            "host_identity": "test-host/test-deployment",
        }
        values.update(changes)
        return LiveLimitRuntimeAttribution(**values)

    def arm(self, *, session_id="acceptance-1", max_count=1,
            aggregate="5.20", per_order="5.20", generation=7):
        return self.store.create_live_limit_acceptance_session(
            LiveLimitAcceptanceSessionRecord(
                acceptance_session_id=session_id,
                trading_account_id=ACCOUNT_ID,
                environment="MAINNET",
                symbol=SYMBOL,
                capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
                state=LiveLimitAcceptanceState.ARMED,
                max_create_count=max_count,
                aggregate_notional_ceiling=Decimal(aggregate),
                per_order_ceiling=Decimal(per_order),
                reserved_count=0,
                reserved_notional=Decimal("0"),
                opened_at_ms=1000,
                expires_at_ms=5000,
                authorized_build_sha=BUILD_SHA,
                database_identity=self.store.database_identity,
                operator_authorization_reference="CR-TRADING-WORKSPACE-001-r3.2/test",
                authorized_session_generation=generation,
                updated_at_ms=1000,
            )
        )

    def command(self, identity, *, notional="5.00", account=ACCOUNT_ID,
                symbol=SYMBOL, occurred_at_ms=1100):
        return CommandRecord(
            command_id=CommandId(f"cmd-{identity}"),
            order_link_id=f"tw-{identity}",
            trading_account_id=account,
            category=Category.LINEAR,
            symbol=symbol,
            position_idx=0,
            command_kind="create_limit",
            side=OrderSide.BUY,
            requested_notional=Notional(Decimal(notional)),
            normalized_price=Price(Decimal("0.10")),
            normalized_quantity=Quantity(Decimal(notional) / Decimal("0.10")),
            origin=Origin.TERMINAL_MANUAL,
            controller=Controller.MANUAL,
            current_state=CommandState.ADMITTED,
            version=1,
            exchange_order_id=None,
            created_at_ms=occurred_at_ms,
            updated_at_ms=occurred_at_ms,
        )

    def admit(self, identity, *, fingerprint=None, notional="5.00",
              session_id="acceptance-1", generation=7, runtime=None):
        return self.store.admit_live_limit_create(
            acceptance_session_id=session_id,
            environment="MAINNET",
            capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
            session_generation=generation,
            client_action_id=identity,
            request_fingerprint=fingerprint or f"fingerprint-{identity}",
            record=self.command(identity, notional=notional),
            reserved_notional=Decimal(notional),
            runtime=runtime or self.runtime(),
            occurred_at_ms=1100,
        )

    def test_acceptance_defaults_are_bounded_but_do_not_auto_arm(self):
        self.assertEqual(LIVE_LIMIT_ACCEPTANCE_SYMBOL, "ONGUSDT")
        self.assertEqual(LIVE_LIMIT_ACCEPTANCE_MAX_CREATE_COUNT, 1)
        self.assertEqual(LIVE_LIMIT_ACCEPTANCE_AGGREGATE_CEILING, Decimal("5.20"))
        self.assertEqual(LIVE_LIMIT_ACCEPTANCE_PER_ORDER_CEILING, Decimal("5.20"))
        with self.assertRaises(PersistenceError):
            self.admit("missing-session")

    def test_schema_v11_migrates_additively_to_current(self):
        self.store.close()
        connection = sqlite3.connect(self.database_path)
        connection.execute("DROP TABLE live_limit_actions")
        connection.execute("DROP TABLE live_limit_acceptance_sessions")
        connection.execute("PRAGMA user_version = 11")
        connection.commit()
        connection.close()
        self.store = SQLiteStore.open(self.database_path)
        self.assertEqual(self.store.settings().schema_version, SCHEMA_VERSION)
        tables = {
            row[0] for row in self.store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("live_limit_acceptance_sessions", tables)
        self.assertIn("live_limit_actions", tables)

    def test_schema_v12_migrates_additive_outcome_columns(self):
        path = Path(self.temp.name) / "v12.sqlite3"
        connection = sqlite3.connect(path)
        for statement in SCHEMA_STATEMENTS[:-len(SCHEMA_V13_MIGRATION_STATEMENTS)]:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 12")
        connection.commit()
        connection.close()
        with SQLiteStore.open(path) as migrated:
            self.assertEqual(migrated.settings().schema_version, SCHEMA_VERSION)
            columns = {
                row[1] for row in migrated._connection.execute(
                    "PRAGMA table_info(live_limit_actions)"
                )
            }
        self.assertTrue({
            "outcome_disposition", "outcome_reason", "outcome_at_ms", "outcome_code",
        }.issubset(columns))

    def test_concurrent_same_identity_has_one_owner_and_no_duplicate_admission(self):
        self.arm()
        self.store.close()

        def worker():
            with SQLiteStore.open(self.database_path, busy_timeout_ms=5000) as store:
                return store.admit_live_limit_create(
                    acceptance_session_id="acceptance-1", environment="MAINNET",
                    capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY, session_generation=7,
                    client_action_id="same", request_fingerprint="same-fingerprint",
                    record=self.command("same"), reserved_notional=Decimal("5.00"),
                    runtime=self.runtime(store), occurred_at_ms=1100,
                ).created

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.store = SQLiteStore.open(self.database_path, busy_timeout_ms=5000)
        self.assertEqual(sorted(results), [False, True])
        session = self.store.get_live_limit_acceptance_session(
            "acceptance-1", ACCOUNT_ID, "MAINNET", SYMBOL,
            LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
        )
        self.assertEqual(session.reserved_count, 1)
        self.assertEqual(session.reserved_notional, Decimal("5.00"))

    def test_same_identity_different_fingerprint_is_rejected(self):
        self.arm()
        self.admit("same", fingerprint="first")
        with self.assertRaises(DuplicateIdentity):
            self.admit("same", fingerprint="different")

    def test_second_distinct_identity_is_rejected_at_count_one(self):
        self.arm()
        self.admit("first")
        with self.assertRaises(PersistenceError):
            self.admit("second")
        self.assertIsNone(self.store.get_command(CommandId("cmd-second")))

    def test_aggregate_budget_rejects_second_individually_valid_request(self):
        self.arm(max_count=2, aggregate="5.20", per_order="5.20")
        first = self.admit("first", notional="3.00").action
        self.store.begin_live_limit_dispatch(first, runtime=first.runtime, occurred_at_ms=1200)
        self.store.mark_live_limit_reconciled(
            first, exchange_order_id=OrderId("exchange-first"), occurred_at_ms=1300,
        )
        with self.assertRaises(PersistenceError):
            self.admit("second", notional="3.00")
        self.assertIsNone(self.store.get_command(CommandId("cmd-second")))

    def test_transaction_failure_leaves_no_action_or_reservation_and_no_adapter_call(self):
        self.arm()
        adapter = mock.Mock()
        with mock.patch.object(
            self.store, "_insert_command", side_effect=sqlite3.OperationalError("disk unavailable")
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.admit("failed")
        adapter.create_limit_order.assert_not_called()
        self.assertIsNone(self.store.get_command(CommandId("cmd-failed")))
        session = self.store.get_live_limit_acceptance_session(
            "acceptance-1", ACCOUNT_ID, "MAINNET", SYMBOL,
            LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
        )
        self.assertEqual((session.reserved_count, session.reserved_notional), (0, Decimal("0")))

    def test_owned_dispatching_and_unknown_each_keep_session_locked(self):
        self.arm(max_count=4, aggregate="20.00")
        first = self.admit("first").action
        with self.assertRaises(PersistenceError):
            self.admit("owned-blocked")
        self.store.begin_live_limit_dispatch(first, runtime=first.runtime, occurred_at_ms=1200)
        with self.assertRaises(PersistenceError):
            self.admit("dispatching-blocked")
        self.store.mark_live_limit_unknown(first, occurred_at_ms=1300)
        with self.assertRaises(PersistenceError):
            self.admit("unknown-blocked")

    def test_release_is_allowed_only_before_dispatch_started(self):
        self.arm(max_count=2, aggregate="10.40")
        owned = self.admit("owned").action
        self.store.release_live_limit_pre_dispatch_failure(owned, occurred_at_ms=1200)
        session = self.store.get_live_limit_acceptance_session(
            "acceptance-1", ACCOUNT_ID, "MAINNET", SYMBOL,
            LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
        )
        self.assertEqual((session.reserved_count, session.reserved_notional), (0, Decimal("0")))
        dispatching = self.admit("dispatching").action
        self.store.begin_live_limit_dispatch(
            dispatching, runtime=dispatching.runtime, occurred_at_ms=1300,
        )
        with self.assertRaises(PersistenceError):
            self.store.release_live_limit_pre_dispatch_failure(
                dispatching, occurred_at_ms=1400,
            )

    def test_build_database_account_and_session_mismatches_fail_closed(self):
        self.arm()
        cases = (
            ("bad-build", {"runtime": self.runtime(build_sha="other")}),
            ("bad-db", {"runtime": self.runtime(database_identity="0" * 64)}),
            ("bad-session", {"generation": 8}),
        )
        for identity, arguments in cases:
            with self.subTest(identity=identity):
                with self.assertRaises(PersistenceError):
                    self.admit(identity, **arguments)
        with self.assertRaises(PersistenceError):
            self.store.admit_live_limit_create(
                acceptance_session_id="acceptance-1", environment="MAINNET",
                capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY, session_generation=7,
                client_action_id="bad-account", request_fingerprint="bad-account",
                record=self.command("bad-account", account=TradingAccountId("other")),
                reserved_notional=Decimal("5.00"), runtime=self.runtime(),
                occurred_at_ms=1100,
            )

    def test_service_reuses_active_account_session_and_readiness_fencing(self):
        self.arm()
        manager = TradingAccountManager((TradingAccount(
            ACCOUNT_ID, "Main Bybit", TradingAccountProvider.BYBIT,
            TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
        ),), active_account_id=ACCOUNT_ID, generation=7)
        service = LiveLimitAcceptanceService(
            manager, self.store, build_sha=BUILD_SHA,
            process_identity=RuntimeProcessIdentity(
                "process-instance-1", 900, os.getpid(), "test-host/test-deployment",
            ), writable_account_provider=lambda _: True,
        )
        result = service.admit_create(
            acceptance_session_id="acceptance-1", session_generation=7,
            client_action_id="service", request_fingerprint="service-fingerprint",
            record=self.command("service"), reserved_notional=Decimal("5.00"),
            occurred_at_ms=1100,
        )
        self.assertTrue(result.created)
        self.assertEqual(result.action.runtime.database_path, str(self.database_path.resolve()))
        self.assertEqual(result.action.runtime.schema_version, SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
