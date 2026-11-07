"""Boundary tests for independent manual MAIN account inventory (#930)."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from terminal.application.manual_main_accounts import ManualMainAccounts, ManualMainAccountError
from terminal.persistence.credential_store import StoredBybitAccount


class FakeCredentials:
    def __init__(self, accounts=()):
        self.accounts = tuple(accounts)
        self.saves = []

    def load(self):
        return self.accounts

    def save(self, accounts):
        self.saves.append(accounts)
        self.accounts = tuple(accounts)


class FakeSnapshots:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeValidator:
    def __init__(self, environment="MAINNET", read_only=False):
        self.environment = environment
        self.read_only = read_only
        self.calls = 0

    def validate(self, credentials):
        self.calls += 1
        return SimpleNamespace(environment=self.environment, read_only=self.read_only)


class FakeReconciler:
    def __init__(self, manager, lookup, validator, store, **kwargs):
        self.manager = manager
        self.lookup = lookup
        self.calls = []

    def refresh(self, account_id):
        self.calls.append(account_id)
        # An authenticated Bybit read adapter is selected by the real
        # LiveAccountReconciler, not by this boundary unit test.
        return {"account_id": self.lookup(account_id).id, "positions": [], "orders": []}

    def summary(self, account_id):
        return {"account_id": self.lookup(account_id).id, "positions": []}


class ManualMainAccountsTests(unittest.TestCase):
    def setUp(self):
        self.c = FakeCredentials()
        self.snap = FakeSnapshots()
        self.v = FakeValidator()
        patcher = patch(
            "terminal.application.manual_main_accounts.LiveAccountReconciler",
            FakeReconciler,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def runtime(self):
        return ManualMainAccounts(self.c, self.snap, validator=self.v)

    def test_empty_start_has_no_paper_or_trading_authority(self):
        app = self.runtime()
        self.assertEqual(app.catalog(), {"accounts": []})
        self.assertFalse(hasattr(app, "place_order"))
        self.assertFalse(hasattr(app, "full_close"))
        self.assertFalse(hasattr(app, "start_robot"))
        self.assertEqual(self.c.saves, [])
        with self.assertRaises(LookupError):
            app.refresh("paper")
        app.close()
        self.assertTrue(self.snap.closed)

    def test_provision_is_validated_encrypted_store_only_then_refresh_uses_existing_reconciler(self):
        app = self.runtime()
        result = app.provision("Main subaccount", "some-key", "some-secret")
        self.assertTrue(result["created"])
        self.assertEqual(self.v.calls, 1)
        self.assertEqual(len(self.c.saves), 1)
        self.assertEqual(self.c.accounts[0].environment, "MAINNET")
        self.assertNotIn("some-secret", repr(result))
        self.assertNotIn("some-key", repr(app.catalog()))
        self.assertEqual(app.catalog()["accounts"][0]["status"], "DISCONNECTED")
        self.assertEqual(app.refresh(result["account_id"])["account_id"], result["account_id"])
        self.assertEqual(app.summary(result["account_id"])["account_id"], result["account_id"])
        self.assertEqual(app.provision("Main subaccount", "some-key", "some-secret")["created"], False)
        self.assertEqual(len(self.c.saves), 1)
        self.assertEqual(self.v.calls, 1)

    def test_reject_testnet_and_duplicate_secret_change_before_persistence(self):
        self.v.environment = "TESTNET"
        app = self.runtime()
        with self.assertRaisesRegex(ManualMainAccountError, "requires_mainnet"):
            app.provision("Main", "key", "secret")
        self.assertEqual(self.c.saves, [])
        self.v.environment = "MAINNET"
        app.provision("Main", "key", "secret")
        with self.assertRaisesRegex(ManualMainAccountError, "duplicate_api_key"):
            app.provision("Main", "key", "different")
        self.assertEqual(len(self.c.saves), 1)

    def test_existing_credentials_are_registered_without_network_or_paper(self):
        record = StoredBybitAccount(
            "bybit-preexisting", "Main", "MAINNET", "key", "secret", True,
        )
        self.c = FakeCredentials((record,))
        app = self.runtime()
        self.assertEqual(self.v.calls, 0)
        self.assertEqual(app.catalog()["accounts"][0]["id"], record.id)
        self.assertEqual(app.catalog()["accounts"][0]["status"], "DISCONNECTED")
        with self.assertRaises(LookupError):
            app.summary("paper")
        self.assertEqual(app.summary(record.id)["account_id"], record.id)
        self.assertEqual(self.c.saves, [])


if __name__ == "__main__":
    unittest.main()
