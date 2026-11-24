"""Prepare the MAIN-only sealed key before the reviewed gateway release.

Root-only, one-time, no services or trading actions. Never replace a key,
read real credential payloads or create a new key over an existing store.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat
import subprocess
import tempfile

KEY_NAME = "bybitscanner-main-store-key"
KEY_PATH = Path("/etc/bybitscanner/main-store-key.cred")
STORE_PATH = Path("/var/lib/bybitscanner-manual-main/main.credentials.systemd")


class MainStoreKeyBlocked(ValueError):
    pass


def _sealed_command(operation, value, *, run):
    argv = ["systemd-creds", "--name=" + KEY_NAME]
    if operation == "encrypt":
        argv.append("--with-key=host")
    argv.extend((operation, "-", "-"))
    try:
        result = run(argv, input=value, capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MainStoreKeyBlocked("main_store_key_tool_unavailable") from exc
    if result.returncode or not result.stdout or len(result.stdout) > 16384:
        raise MainStoreKeyBlocked("main_store_key_tool_failed")
    return result.stdout


def _trusted_directory(path, uid):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
        raise MainStoreKeyBlocked("main_store_key_directory_untrusted")


def _read_sealed(path, uid):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_mode & 0o077 or info.st_nlink != 1
                or not 0 < info.st_size <= 16384):
            raise MainStoreKeyBlocked("main_store_key_file_untrusted")
        return stream.read(16385)


def verify_main_store_key(*, path=KEY_PATH, run=subprocess.run, uid=0):
    if os.geteuid() != uid:
        raise MainStoreKeyBlocked("main_store_key_root_required")
    _trusted_directory(path.parent, uid)
    sealed = _read_sealed(path, uid)
    if len(_sealed_command("decrypt", sealed, run=run)) != 32:
        raise MainStoreKeyBlocked("main_store_key_invalid")
    return "VERIFIED"


def prepare_main_store_key(*, path=KEY_PATH, store=STORE_PATH, run=subprocess.run, uid=0):
    if os.geteuid() != uid:
        raise MainStoreKeyBlocked("main_store_key_root_required")
    _trusted_directory(path.parent, uid)
    if os.path.lexists(path):
        verify_main_store_key(path=path, run=run, uid=uid)
        return "EXISTS_VERIFIED"
    # An existing (even corrupt or symlinked) store may require its old key.
    # Never manufacture a replacement or automatically migrate it.
    if (os.path.lexists(store) or os.path.lexists(store.with_suffix(store.suffix + ".tmp"))
            or store.parent.is_symlink()):
        raise MainStoreKeyBlocked("main_store_existing_data_requires_review")
    key = secrets.token_bytes(32)
    sealed = _sealed_command("encrypt", key, run=run)
    if not secrets.compare_digest(_sealed_command("decrypt", sealed, run=run), key):
        raise MainStoreKeyBlocked("main_store_key_roundtrip_failed")
    # Atomic create-only publication. The temporary file contains ciphertext only.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".main-key-") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(sealed)
        stream.flush()
        os.fsync(stream.fileno())
        os.link(stream.name, path, follow_symlinks=False)
    directory = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    verify_main_store_key(path=path, run=run, uid=uid)
    return "CREATED_VERIFIED"


def main():
    try:
        print("MAIN_STORE_KEY=" + prepare_main_store_key())
        return 0
    except (MainStoreKeyBlocked, OSError, ValueError) as exc:
        # Never expose stderr, key contents or user-controlled paths.
        print("MAIN_STORE_KEY=BLOCKED:" + type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
