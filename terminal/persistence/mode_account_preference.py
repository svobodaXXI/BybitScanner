"""Independent, durable display preferences for manual Terminal and Autopilot.

This store does not activate trading accounts or grant trading authority.
Eligibility and successful account selection must be checked by the caller
before save(); unknown/unavailable accounts must never be silently replaced.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from terminal.domain.models import TradingAccountId


AccountMode = Literal["TERMINAL", "AUTOPILOT"]
_MODES = frozenset(("TERMINAL", "AUTOPILOT"))


class ModeAccountPreferenceError(RuntimeError):
    pass


class ModeAccountPreferenceStore:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path.resolve()

    @staticmethod
    def _check_mode(mode: AccountMode) -> str:
        if mode not in _MODES:
            raise ValueError("unsupported account preference mode")
        return mode

    def _load_unlocked(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"version", "accounts"}:
                raise ValueError("invalid preference envelope")
            if type(payload["version"]) is not int or payload["version"] != self.VERSION:
                raise ValueError("unsupported preference version")
            accounts = payload["accounts"]
            if not isinstance(accounts, dict) or not set(accounts).issubset(_MODES):
                raise ValueError("invalid account preference modes")
            return {
                mode: TradingAccountId(value).value
                for mode, value in accounts.items()
            }
        except Exception as exc:
            raise ModeAccountPreferenceError("mode_account_preference_read_failed") from exc

    def load(self, mode: AccountMode) -> TradingAccountId | None:
        mode = self._check_mode(mode)
        with self._lock:
            account_id = self._load_unlocked().get(mode)
            return TradingAccountId(account_id) if account_id is not None else None

    def save(self, mode: AccountMode, account_id: TradingAccountId) -> None:
        """Persist an already-authorized selection, leaving the other mode untouched."""
        mode = self._check_mode(mode)
        if not isinstance(account_id, TradingAccountId):
            raise TypeError("account id must be TradingAccountId")
        with self._lock:
            accounts = self._load_unlocked()
            accounts[mode] = account_id.value
            try:
                envelope = json.dumps(
                    {"version": self.VERSION, "accounts": accounts},
                    separators=(",", ":"), sort_keys=True,
                )
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._path.with_suffix(self._path.suffix + ".tmp")
                temporary.write_text(envelope, encoding="utf-8")
                os.replace(temporary, self._path)
            except Exception as exc:
                raise ModeAccountPreferenceError("mode_account_preference_write_failed") from exc
