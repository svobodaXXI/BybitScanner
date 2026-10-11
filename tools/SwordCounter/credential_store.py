"""SwordCounter S5: Bybit Read-Only key storage in the Windows Credential Manager.

- A generic credential of the *current Windows user*, persisted locally (LOCAL_MACHINE), kept
  by Windows encrypted with the user's logon secret (DPAPI). No file, registry value, dotenv
  file, batch file or JSON ever holds the key or the secret.
- The target name is SwordCounter's own. The BybitScanner robot's keys and variables are
  never read: only this entry and, as a fallback, the two ``SWORDCOUNTER_BYBIT_API_*``
  variables.
- Errors carry Windows error codes only, never stored content.
"""

from __future__ import annotations

import json
import sys
from typing import Mapping, Protocol

from tools.SwordCounter.bybit_positions import (
    API_KEY_ENV, API_SECRET_ENV, BybitCredentialsError, Credentials,
)

DEFAULT_TARGET = "SwordCounter/BybitReadOnly"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_BLOB_VERSION = 1
SETUP_HINT = "tools\\SwordCounter\\setup_sword_counter_keys.bat"
NOT_CONFIGURED = f"Ключ SwordCounter не настроен: запустите {SETUP_HINT}"


class CredentialStoreError(BybitCredentialsError):
    """The Windows Credential Manager could not be used (code only, no content)."""


class CredentialStore(Protocol):
    def save(self, credentials: Credentials) -> None: ...
    def load(self) -> Credentials | None: ...
    def delete(self) -> bool: ...


def _api():
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
            ("Attributes", wintypes.LPVOID), ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    lib = ctypes.WinDLL("advapi32", use_last_error=True)
    lib.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    lib.CredWriteW.restype = wintypes.BOOL
    lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    lib.CredReadW.restype = wintypes.BOOL
    lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    lib.CredDeleteW.restype = wintypes.BOOL
    lib.CredFree.argtypes = [wintypes.LPVOID]
    lib.CredFree.restype = None
    return ctypes, lib, CREDENTIALW


class WindowsCredentialStore:
    def __init__(self, target: str = DEFAULT_TARGET) -> None:
        if not isinstance(target, str) or not target.strip():
            raise ValueError("credential target must be a non-empty string")
        self.target = target

    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise CredentialStoreError("Windows Credential Manager is available only on Windows")

    def _write_blob(self, blob: bytes) -> None:
        self._require_windows()
        ctypes, lib, CREDENTIALW = _api()
        if not 0 < len(blob) <= 2560:
            raise CredentialStoreError("credential does not fit the Credential Manager blob limit")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self.target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "SwordCounter"
        if not lib.CredWriteW(ctypes.byref(credential), 0):
            raise CredentialStoreError(f"CredWrite failed (Windows error {ctypes.get_last_error()})")

    def save(self, credentials: Credentials) -> None:
        blob = json.dumps({"v": _BLOB_VERSION, "k": credentials.api_key, "s": credentials.api_secret},
                          separators=(",", ":")).encode("utf-8")
        self._write_blob(blob)

    def load(self) -> Credentials | None:
        self._require_windows()
        ctypes, lib, _CREDENTIALW = _api()
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not lib.CredReadW(self.target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            code = ctypes.get_last_error()
            if code == _ERROR_NOT_FOUND:
                return None
            raise CredentialStoreError(f"CredRead failed (Windows error {code})")
        try:
            record = pointer.contents
            blob = bytes(ctypes.string_at(record.CredentialBlob, record.CredentialBlobSize))
        finally:
            lib.CredFree(pointer)
        return self._parse(blob)

    @staticmethod
    def _parse(blob: bytes) -> Credentials:
        data = None
        try:
            data = json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            data = None
        if (not isinstance(data, dict) or data.get("v") != _BLOB_VERSION
                or not isinstance(data.get("k"), str) or not isinstance(data.get("s"), str)):
            raise CredentialStoreError("the stored SwordCounter credential is unreadable; run the setup again")
        return Credentials(data["k"], data["s"])

    def delete(self) -> bool:
        self._require_windows()
        ctypes, lib, _CREDENTIALW = _api()
        if lib.CredDeleteW(self.target, CRED_TYPE_GENERIC, 0):
            return True
        code = ctypes.get_last_error()
        if code == _ERROR_NOT_FOUND:
            return False
        raise CredentialStoreError(f"CredDelete failed (Windows error {code})")


def resolve_credentials(store: CredentialStore | None = None,
                        environ: Mapping[str, str] | None = None) -> tuple[Credentials, str]:
    """SwordCounter's credentials and where they came from; never the robot's, never guessed."""
    store = store if store is not None else WindowsCredentialStore()
    stored = store.load()
    if stored is not None:
        return stored, "credential_manager"
    if environ is None:
        import os

        environ = os.environ
    key, secret = environ.get(API_KEY_ENV, ""), environ.get(API_SECRET_ENV, "")
    if key.strip() and secret.strip():
        return Credentials(key, secret), "environment"
    raise BybitCredentialsError(NOT_CONFIGURED)
