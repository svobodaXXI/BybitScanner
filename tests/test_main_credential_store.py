"""Offline tests for the isolated MAIN storage key, no exchange or runtime."""
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from terminal.persistence.credential_store import CredentialStoreError, StoredBybitAccount
from terminal.persistence.main_credential_store import (
    KEY_NAME, MAGIC, MainServiceProtector, create_main_credential_store,
)
from tools.vps_main_store_key import (
    MainStoreKeyBlocked, prepare_main_store_key,
)


class MainStoreTests(unittest.TestCase):
    def test_encrypted_store_survives_reconstruction_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / KEY_NAME).write_bytes(b"k" * 32)
            account = StoredBybitAccount("id", "MAIN", "MAINNET", "private-key", "private-secret", True)
            path = root / "accounts"
            with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(root)}):
                store = create_main_credential_store(path)
                store.save((account,))
                original = path.read_bytes()
                self.assertNotIn(b"private-key", original)
                self.assertNotIn(b"private-secret", original)
                self.assertEqual(create_main_credential_store(path).load(), (account,))
                store.save((account,))
                self.assertNotEqual(original, path.read_bytes())
                (root / KEY_NAME).write_bytes(b"x" * 32)
                with self.assertRaises(CredentialStoreError):
                    create_main_credential_store(path).load()
        protector = MainServiceProtector(b"k" * 32)
        blob = protector.protect(b"private")
        self.assertTrue(blob.startswith(MAGIC))
        with self.assertRaises(CredentialStoreError):
            protector.unprotect(blob[:-1] + bytes([blob[-1] ^ 1]))
        with self.assertRaises(CredentialStoreError):
            protector.unprotect(b"legacy-systemd-ciphertext")

    def test_missing_invalid_or_symlinked_injected_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(root)}):
                with self.assertRaises(CredentialStoreError):
                    create_main_credential_store(root / "accounts")
                key = root / KEY_NAME
                key.write_bytes(b"short")
                with self.assertRaises(CredentialStoreError):
                    create_main_credential_store(root / "accounts")
                key.unlink()
                (root / "other").write_bytes(b"k" * 32)
                key.symlink_to(root / "other")
                with self.assertRaises(CredentialStoreError):
                    create_main_credential_store(root / "accounts")

    def test_root_seal_create_only_and_reverify(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            value = kwargs["input"]
            if "encrypt" in argv:
                self.assertIn("--with-key=host", argv)
                return CompletedProcess(argv, 0, stdout=b"sealed:" + value, stderr=b"")
            if not value.startswith(b"sealed:"):
                return CompletedProcess(argv, 1, stdout=b"", stderr=b"never print")
            return CompletedProcess(argv, 0, stdout=value[7:], stderr=b"")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = root / "key.cred"
            store = root / "accounts"
            params = dict(path=key, store=store, run=run, uid=os.geteuid())
            self.assertEqual(prepare_main_store_key(**params), "CREATED_VERIFIED")
            original = key.read_bytes()
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(prepare_main_store_key(**params), "EXISTS_VERIFIED")
            self.assertEqual(key.read_bytes(), original)
            self.assertEqual(sum("encrypt" in call for call in calls), 1)
            key.write_bytes(b"corrupt")
            with self.assertRaises(MainStoreKeyBlocked):
                prepare_main_store_key(**params)
            self.assertEqual(key.read_bytes(), b"corrupt")
            key.unlink()
            store.write_bytes(b"existing encrypted data")
            with self.assertRaises(MainStoreKeyBlocked):
                prepare_main_store_key(**params)
            self.assertFalse(key.exists())
            self.assertEqual(store.read_bytes(), b"existing encrypted data")


if __name__ == "__main__":
    unittest.main()
