"""Current-user DPAPI-backed persistence for Bybit credentials."""

from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


class CredentialStoreError(RuntimeError):
    pass


class Protector(Protocol):
    def protect(self, value: bytes) -> bytes: ...
    def unprotect(self, value: bytes) -> bytes: ...


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(wintypes.BYTE))]


class WindowsDpapiProtector:
    def __init__(self) -> None:
        if os.name != "nt":
            raise CredentialStoreError("windows_dpapi_unavailable")
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        blob_pointer = ctypes.POINTER(_Blob)
        self._crypt32.CryptProtectData.argtypes = [
            blob_pointer, wintypes.LPCWSTR, blob_pointer, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, blob_pointer,
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            blob_pointer, ctypes.POINTER(wintypes.LPWSTR), blob_pointer,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_pointer,
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    @staticmethod
    def _blob(value: bytes) -> tuple[_Blob, object]:
        buffer = ctypes.create_string_buffer(value)
        return _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE))), buffer

    def _transform(self, value: bytes, function_name: str) -> bytes:
        source, source_buffer = self._blob(value)
        output = _Blob()
        function = getattr(self._crypt32, function_name)
        if function_name == "CryptProtectData":
            ok = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
        else:
            ok = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
        _ = source_buffer
        if not ok:
            error_code = ctypes.get_last_error()
            raise CredentialStoreError(f"windows_dpapi_failure_{error_code}")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            self._kernel32.LocalFree(output.pbData)

    def protect(self, value: bytes) -> bytes:
        return self._transform(value, "CryptProtectData")

    def unprotect(self, value: bytes) -> bytes:
        return self._transform(value, "CryptUnprotectData")


@dataclass(frozen=True, slots=True, repr=False)
class StoredBybitAccount:
    id: str
    display_name: str
    environment: str
    api_key: str
    api_secret: str
    read_only: bool

    def __post_init__(self) -> None:
        if not isinstance(self.read_only, bool):
            raise TypeError("stored read_only permission must be boolean")


class DpapiCredentialStore:
    def __init__(self, path: Path, protector: Protector | None = None) -> None:
        self._path = path
        self._protector = protector or WindowsDpapiProtector()

    def load(self) -> tuple[StoredBybitAccount, ...]:
        if not self._path.exists():
            return ()
        try:
            envelope = json.loads(self._path.read_text(encoding="ascii"))
            if set(envelope) != {"version", "ciphertext"} or envelope["version"] != 2:
                raise ValueError("unsupported credential envelope")
            plaintext = self._protector.unprotect(base64.b64decode(envelope["ciphertext"], validate=True))
            payload = json.loads(plaintext.decode("utf-8"))
            if not isinstance(payload, list):
                raise ValueError("credential payload must be a list")
            return tuple(StoredBybitAccount(**item) for item in payload)
        except Exception as exc:
            raise CredentialStoreError("credential_store_read_failed") from exc

    def save(self, accounts: tuple[StoredBybitAccount, ...]) -> None:
        try:
            plaintext = json.dumps([asdict(account) for account in accounts], separators=(",", ":")).encode("utf-8")
            encrypted = self._protector.protect(plaintext)
            envelope = json.dumps({
                "version": 2,
                "ciphertext": base64.b64encode(encrypted).decode("ascii"),
            }, separators=(",", ":"))
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(self._path.suffix + ".tmp")
            temporary.write_text(envelope, encoding="ascii")
            os.replace(temporary, self._path)
        except Exception as exc:
            raise CredentialStoreError("credential_store_write_failed") from exc
