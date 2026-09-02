import tempfile
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch
from pathlib import Path

from terminal.persistence.credential_store import (
    CredentialStoreError, DpapiCredentialStore, StoredBybitAccount,
    SystemdCredsProtector, credential_store_path, create_credential_store,
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

    def test_windows_factory_preserves_dpapi_store_and_path(self):
        protector = ReversibleProtector()
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "paper.sqlite3"
            path = credential_store_path(database, platform_name="Windows")
            store = create_credential_store(
                path, platform_name="Windows",
                windows_protector_factory=lambda: protector,
            )
            self.assertIsInstance(store, DpapiCredentialStore)
            self.assertEqual(path.name, "paper.credentials.dpapi")

    def test_linux_systemd_store_round_trips_without_plaintext_or_secret_repr(self):
        protected = b"systemd-encrypted-credential"

        def run(command, **kwargs):
            if "encrypt" in command:
                self.assertIn("--with-key=host", command)
                return CompletedProcess(command, 0, stdout=protected, stderr=b"")
            self.assertEqual(kwargs["input"], protected)
            return CompletedProcess(command, 0, stdout=plaintext, stderr=b"")

        account = StoredBybitAccount(
            "bybit-1", "Main", "MAINNET", "sensitive-key", "sensitive-secret", False,
        )
        plaintext = b'[{"id":"bybit-1","display_name":"Main","environment":"MAINNET","api_key":"sensitive-key","api_secret":"sensitive-secret","read_only":false}]'
        self.assertNotIn("sensitive-key", repr(account))
        self.assertNotIn("sensitive-secret", repr(account))
        with tempfile.TemporaryDirectory() as temp, \
                patch("terminal.persistence.credential_store.platform.system", return_value="Linux"), \
                patch("terminal.persistence.credential_store.shutil.which", return_value="/usr/bin/systemd-creds"), \
                patch("terminal.persistence.credential_store.subprocess.run", side_effect=run):
            path = Path(temp) / "accounts.systemd"
            store = DpapiCredentialStore(path, SystemdCredsProtector())
            store.save((account,))
            persisted = path.read_text(encoding="ascii")
            self.assertNotIn(account.api_key, persisted)
            self.assertNotIn(account.api_secret, persisted)
            self.assertEqual(store.load(), (account,))

    def test_linux_corrupt_material_fails_closed_without_tool_error_details(self):
        secret = "must-not-escape"
        with tempfile.TemporaryDirectory() as temp, \
                patch("terminal.persistence.credential_store.platform.system", return_value="Linux"), \
                patch("terminal.persistence.credential_store.shutil.which", return_value="/usr/bin/systemd-creds"), \
                patch("terminal.persistence.credential_store.subprocess.run", return_value=CompletedProcess([], 1, stdout=b"", stderr=secret.encode())):
            path = Path(temp) / "accounts.systemd"
            path.write_text('{"version":2,"ciphertext":"Y29ycnVwdA=="}', encoding="ascii")
            store = DpapiCredentialStore(path, SystemdCredsProtector())
            with self.assertRaises(CredentialStoreError) as raised:
                store.load()
        self.assertEqual(str(raised.exception), "credential_store_read_failed")
        self.assertNotIn(secret, repr(raised.exception))

    def test_linux_unavailable_and_unsupported_platform_fail_closed(self):
        with patch("terminal.persistence.credential_store.platform.system", return_value="Linux"), \
                patch("terminal.persistence.credential_store.shutil.which", return_value=None):
            with self.assertRaisesRegex(CredentialStoreError, "systemd_creds_unavailable"):
                SystemdCredsProtector()
        with self.assertRaisesRegex(CredentialStoreError, "credential_protection_platform_unsupported"):
            create_credential_store(Path("accounts"), platform_name="Darwin")

    def test_linux_factory_selects_systemd_protector_and_path(self):
        protector = ReversibleProtector()
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "paper.sqlite3"
            path = credential_store_path(database, platform_name="Linux")
            store = create_credential_store(
                path, platform_name="Linux", linux_protector_factory=lambda: protector,
            )
            account = StoredBybitAccount("id", "name", "MAINNET", "key", "secret", True)
            store.save((account,))
            self.assertEqual(store.load(), (account,))
            self.assertEqual(path.name, "paper.credentials.systemd")
