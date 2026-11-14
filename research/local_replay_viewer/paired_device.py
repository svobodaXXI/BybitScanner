"""One-time owner-approved Windows pairing for read-only PAPER replay only.

Pairing originates from the owner-authenticated Telegram Terminal, but a
custom URI is untrusted until Windows presents the *exact HTTPS origin* and
the owner explicitly confirms it. Device credentials use per-user DPAPI,
not plaintext registry/env files. Never carries exchange or trading tokens.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from research.local_replay_viewer.device_relay_client import (
    DEVICE_ID, PairedEpisodeReceiver, valid_origin,
)

MAX_PAIR_URL = 1200
FILE_NAME = "paired-device.dpapi"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def parse_pairing_uri(uri: str) -> tuple[str, str, str]:
    if (not isinstance(uri, str) or len(uri) > MAX_PAIR_URL
            or not uri.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in uri)):
        raise ValueError("invalid_pairing_uri")
    try:
        parsed = urlsplit(uri)
        if (parsed.scheme != "bybitscanner-simulator" or parsed.netloc != "pair"
                or parsed.path or parsed.fragment):
            raise ValueError("invalid_pairing_route")
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        if len(pairs) != 3 or {key for key, _ in pairs} != {
            "device_id", "token", "origin"
        }:
            raise ValueError("invalid_pairing_fields")
        values = dict(pairs)
        device = values["device_id"]
        token = values["token"]
        origin = values["origin"]
        if not DEVICE_ID.fullmatch(device):
            raise ValueError("invalid_pairing_device")
        if not valid_origin(origin):
            raise ValueError("invalid_pairing_origin")
        # Reuse the receiver's exact scoped token and origin contract.
        PairedEpisodeReceiver(origin=origin, device_id=device, token=token,
                              local_archive=Path("."), open_episode=lambda _: False)
        return device, token, origin
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid_pairing_uri") from exc


def _storage() -> Path:
    if os.name != "nt":
        raise OSError("windows_pairing_only")
    root = os.environ.get("LOCALAPPDATA", "")
    if not root:
        raise OSError("windows_user_profile_unavailable")
    folder = Path(root) / "BybitScanner" / "MachineTime"
    if folder.is_symlink():
        raise OSError("pairing_directory_is_link")
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink():
        raise OSError("pairing_directory_is_link")
    return folder / FILE_NAME


def _crypt(raw: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise OSError("windows_dpapi_only")
    memory = ctypes.create_string_buffer(raw, len(raw))
    source = _Blob(len(raw), ctypes.cast(memory, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypto = ctypes.windll.crypt32
    # Explicit pointer-sized WinAPI signatures: never let ctypes infer a
    # 32-bit integer for an address on 64-bit Windows.
    crypto.CryptProtectData.argtypes = [
        ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    crypto.CryptProtectData.restype = wintypes.BOOL
    crypto.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    crypto.CryptUnprotectData.restype = wintypes.BOOL
    if decrypt:
        result = crypto.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target),
        )
    else:
        result = crypto.CryptProtectData(
            ctypes.byref(source), "BybitScanner PAPER read-only device",
            None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target),
        )
    if not result:
        raise OSError("windows_dpapi_unavailable")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(target.pbData, ctypes.c_void_p))


def _confirm(origin: str, device: str) -> bool:
    if os.name != "nt":
        return False
    # Neither the device-only token nor any URL containing it is displayed.
    message = (
        "Подключить «Машину времени» к терминалу BybitScanner?\n\n"
        f"Проверенный вами адрес терминала:\n{origin}\n\n"
        f"Устройство: {device}\n\n"
        "Будут приходить только записи PAPER для просмотра, без торговли.\n"
        "Разрешайте только если адрес действительно принадлежит вашему терминалу."
    )
    # MB_YESNO=0x04, MB_ICONQUESTION=0x20, IDYES=6
    return ctypes.windll.user32.MessageBoxW(
        None, message, "Подключение Симулятора", 0x04 | 0x20,
    ) == 6


def accept_pairing_url(uri: str, *, confirm=None) -> bool:
    device, token, origin = parse_pairing_uri(uri)
    if os.name != "nt":
        return False
    if not (confirm or _confirm)(origin, device):
        return False
    destination = _storage()
    if destination.is_symlink():
        raise OSError("pairing_file_is_link")
    raw = json.dumps({
        "schema": 1, "device_id": device, "token": token, "origin": origin,
    }, separators=(",", ":")).encode("utf-8")
    protected = _crypt(raw, decrypt=False)
    # Exact single per-user credential; replacing it requires another
    # explicit Windows confirmation. Do not touch other owner files.
    temporary = destination.with_name(destination.name + ".new")
    if temporary.exists() or temporary.is_symlink():
        raise OSError("pairing_write_already_pending")
    try:
        with temporary.open("xb") as stream:
            stream.write(protected)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def load_pairing() -> dict[str, str] | None:
    if os.name != "nt":
        return None
    location = _storage()
    if location.is_symlink():
        raise OSError("pairing_file_is_link")
    if not location.is_file():
        return None
    raw = location.read_bytes()
    if not 1 <= len(raw) <= 8192:
        raise OSError("invalid_pairing_store")
    try:
        parsed = json.loads(_crypt(raw, decrypt=True))
        if not isinstance(parsed, dict) or set(parsed) != {
            "schema", "device_id", "token", "origin"
        } or parsed["schema"] != 1:
            raise ValueError("invalid_pairing_record")
        PairedEpisodeReceiver(
            origin=parsed["origin"], device_id=parsed["device_id"],
            token=parsed["token"], local_archive=Path("."),
            open_episode=lambda _: False,
        )
        return parsed
    except (TypeError, ValueError, UnicodeError) as exc:
        raise OSError("invalid_pairing_store") from exc


def run_paired_receiver(stop, *, local_archive: Path, open_episode,
                        poll_interval: float = 3.0) -> None:
    """Hot-start the outbound receiver after Windows owner confirms pairing.

    The already-running viewer detects an added/rotated DPAPI credential
    without accepting any inbound network command or restarting trading.
    """
    active = None
    receiver = None
    while not stop.is_set():
        try:
            pairing = load_pairing()
            if pairing is None:
                active, receiver = None, None
            elif pairing != active:
                receiver = PairedEpisodeReceiver(
                    origin=pairing["origin"], device_id=pairing["device_id"],
                    token=pairing["token"], local_archive=local_archive,
                    open_episode=open_episode,
                )
                active = pairing
            if receiver is not None:
                receiver.poll_once()
        except (OSError, ValueError, TypeError, UnicodeError,
                json.JSONDecodeError):
            # Fail closed on this poll. Never log the device token.
            pass
        stop.wait(poll_interval)
