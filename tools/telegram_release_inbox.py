"""Unprivileged relay only. The inbox does NOT convey owner authority."""
import json
import os
from pathlib import Path
import re
import secrets
import stat

INBOX = Path("/var/lib/bybitscanner-owner-release-inbox")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
MAX_WIRE = 4096


def relay(update, *, inbox=INBOX):
    q = update.get("callback_query") or {}
    data = q.get("data")
    if not isinstance(data, str) or not data.startswith("owner-release:"):
        return None
    match = re.fullmatch(r"owner-release:(yes|no):([0-9a-f]{32})", data)
    receipt = update.get("owner_release_receipt")
    if not match or type(receipt) is not dict:
        return False
    try:
        wire = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
        if not 0 < len(wire) <= MAX_WIRE:
            return False
        fd = os.open(inbox, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                return False
            name = "receipt-" + match.group(2) + ".json"
            temp = ".incoming-" + secrets.token_hex(16)
            try:
                out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=fd)
                with os.fdopen(out, "wb") as stream:
                    stream.write(wire)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
                return True
            finally:
                try:
                    os.unlink(temp, dir_fd=fd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(fd)
    except (OSError, ValueError, TypeError, RecursionError):
        return False


def read_receipt(nonce, *, inbox=INBOX, relay_uid):
    """Root reads exactly one bounded untrusted file; no directory traversal."""
    if type(nonce) is not str or not NONCE.fullmatch(nonce):
        raise ValueError("invalid challenge nonce")
    parent = inbox.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise ValueError("inbox parent unprotected")
    directory = os.open(inbox, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(directory)
        if meta.st_uid != relay_uid or meta.st_mode & 0o077:
            raise ValueError("invalid relay inbox")
        try:
            fd = os.open("receipt-" + nonce + ".json",
                         os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != relay_uid
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise ValueError("invalid relay file")
            raw = stream.read(MAX_WIRE + 1)
        if not 0 < len(raw) <= MAX_WIRE:
            raise ValueError("invalid relay size")
        return raw
    finally:
        os.close(directory)
