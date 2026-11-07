"""SwordCounter S4: one window per Windows user session (named mutex, no admin rights).

``Local\\`` keeps the mutex per user session. The mutex lives only as long as the process
that holds it, so a crash never leaves a stale lock.
"""

from __future__ import annotations

import sys

MUTEX_NAME = "Local\\SwordCounter.SingleInstance"
_ERROR_ALREADY_EXISTS = 183
_SYNCHRONIZE = 0x00100000


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenMutexW.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return k


class SingleInstance:
    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._handle = None

    def acquire(self) -> bool:
        """True when this process now owns the instance; False when another one already does."""
        if self._handle is not None:
            return True
        if sys.platform != "win32":
            return True  # the guard is a Windows feature; elsewhere do not block
        import ctypes

        k = _kernel32()
        handle = k.CreateMutexW(None, False, self.name)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            k.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            _kernel32().CloseHandle(self._handle)
            self._handle = None


def is_running(name: str = MUTEX_NAME) -> bool:
    """True when some process currently holds the instance mutex (read-only probe)."""
    if sys.platform != "win32":
        return False
    k = _kernel32()
    handle = k.OpenMutexW(_SYNCHRONIZE, False, name)
    if not handle:
        return False
    k.CloseHandle(handle)
    return True
