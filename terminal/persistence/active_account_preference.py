"""Atomic backend persistence for the preferred trading-account identity."""

from __future__ import annotations

import json
import os
from pathlib import Path

from terminal.domain.models import TradingAccountId


class ActiveAccountPreferenceError(RuntimeError):
    pass


class ActiveAccountPreferenceStore:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path.resolve()

    def load(self) -> TradingAccountId | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if set(payload) != {"version", "preferred_account_id"}:
                raise ValueError("invalid preference envelope")
            if payload["version"] != self.VERSION:
                raise ValueError("unsupported preference version")
            return TradingAccountId(payload["preferred_account_id"])
        except Exception as exc:
            raise ActiveAccountPreferenceError("active_account_preference_read_failed") from exc

    def save(self, account_id: TradingAccountId) -> None:
        if not isinstance(account_id, TradingAccountId):
            raise TypeError("preferred account id must be TradingAccountId")
        try:
            envelope = json.dumps({
                "version": self.VERSION,
                "preferred_account_id": account_id.value,
            }, separators=(",", ":"))
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(self._path.suffix + ".tmp")
            temporary.write_text(envelope, encoding="utf-8")
            os.replace(temporary, self._path)
        except Exception as exc:
            raise ActiveAccountPreferenceError("active_account_preference_write_failed") from exc
