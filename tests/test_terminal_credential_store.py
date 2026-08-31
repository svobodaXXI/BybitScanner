import tempfile
import unittest
from pathlib import Path

from terminal.persistence.credential_store import (
    CredentialStoreError, DpapiCredentialStore, StoredBybitAccount,
)


class ReversibleProtector:
    def protect(self, value: bytes) -> bytes:
        return bytes(item ^ 0xA5 for item in value)

    def unprotect(self, value: bytes) -> bytes:
        return self.protect(value)


class CredentialStoreTests(unittest.TestCase):
    def test_encrypted_store_round_trips_without_plaintext_material(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "accounts.dpapi"
            store = DpapiCredentialStore(path, ReversibleProtector())
            account = StoredBybitAccount("bybit-1", "Main", "MAINNET", "sensitive-key", "sensitive-secret", False)
            store.save((account,))
            raw = path.read_text(encoding="ascii")
            self.assertNotIn("sensitive-key", raw)
            self.assertNotIn("sensitive-secret", raw)
            self.assertEqual(store.load(), (account,))

    def test_store_fails_closed_on_corrupt_ciphertext(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "accounts.dpapi"
            path.write_text('{"version":1,"ciphertext":"broken!"}', encoding="ascii")
            with self.assertRaisesRegex(CredentialStoreError, "credential_store_read_failed"):
                DpapiCredentialStore(path, ReversibleProtector()).load()

    def test_store_rejects_previous_envelope_version_without_migration_guessing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "accounts.dpapi"
            path.write_text('{"version":1,"ciphertext":""}', encoding="ascii")
            with self.assertRaisesRegex(CredentialStoreError, "credential_store_read_failed"):
                DpapiCredentialStore(path, ReversibleProtector()).load()
