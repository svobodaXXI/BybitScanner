"""MAIN-only AEAD protector with a systemd-delivered, host-sealed key.

Never read the global systemd host secret from the service or create a
plaintext persistent key. Existing PAPER/DPAPI protectors are unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets

from terminal.persistence.credential_store import CredentialStoreError, DpapiCredentialStore

KEY_NAME = "bybitscanner-main-store-key"
MAGIC = b"BSMAIN-AEAD1"
NONCE_SIZE = 12
TAG_SIZE = 16


class MainServiceProtector:
    def __init__(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise CredentialStoreError("main_store_key_invalid")
        self._key = key

    @classmethod
    def from_systemd(cls) -> MainServiceProtector:
        try:
            directory = Path(os.environ["CREDENTIALS_DIRECTORY"])
            if not directory.is_absolute():
                raise ValueError("invalid credential directory")
            path = directory / KEY_NAME
            if path.is_symlink() or not path.is_file():
                raise ValueError("invalid credential file")
            with path.open("rb") as stream:
                return cls(stream.read(33))
        except (OSError, KeyError, ValueError) as exc:
            raise CredentialStoreError("main_store_key_unavailable") from exc

    def protect(self, value: bytes) -> bytes:
        from Crypto.Cipher import AES

        nonce = secrets.token_bytes(NONCE_SIZE)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_SIZE)
        cipher.update(MAGIC)
        encrypted, tag = cipher.encrypt_and_digest(value)
        return MAGIC + nonce + tag + encrypted

    def unprotect(self, value: bytes) -> bytes:
        from Crypto.Cipher import AES

        offset = len(MAGIC)
        if not value.startswith(MAGIC) or len(value) < offset + NONCE_SIZE + TAG_SIZE:
            # No guessing, fallback or rewriting the legacy envelope.
            raise CredentialStoreError("main_store_format_unsupported")
        nonce = value[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE
        tag = value[offset:offset + TAG_SIZE]
        try:
            cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_SIZE)
            cipher.update(MAGIC)
            return cipher.decrypt_and_verify(value[offset + TAG_SIZE:], tag)
        except ValueError as exc:
            raise CredentialStoreError("main_store_authentication_failed") from exc


def create_main_credential_store(path: Path) -> DpapiCredentialStore:
    protector = MainServiceProtector.from_systemd()
    # Verify the injected key and crypto dependency before publishing health.
    if protector.unprotect(protector.protect(b"main-store-self-check")) != b"main-store-self-check":
        raise CredentialStoreError("main_store_self_check_failed")
    return DpapiCredentialStore(path, protector)
