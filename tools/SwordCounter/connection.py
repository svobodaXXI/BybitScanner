"""SwordCounter S5: «Подключение Bybit» section of the settings window, without Tk.

- The check runs the existing read-only ``verify_key`` (GET /v5/user/query-api, then
  GET /v5/position/list) on a background thread; the GUI thread only polls ``poll()``.
- Saving is allowed only for exactly the values that passed the check: any edit of a field
  drops the confirmation, and a check that finishes after an edit is discarded.
- Values go only to the credential store (Windows Credential Manager). Messages never carry
  them; an unexpected error is reported by its class name only.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable

from tools.SwordCounter.bybit_positions import BybitPositionsError, Credentials
from tools.SwordCounter.credential_store import DEFAULT_TARGET, CredentialStore
from tools.SwordCounter.setup_keys import CheckResult, verify_key

CHECKING = "Проверяю подключение к Bybit (только чтение)…"
NEED_CHECK = "Сначала нажмите «Проверить подключение» для текущих значений."


def _in_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="swordcounter-key-check", daemon=True).start()


class ConnectionController:
    def __init__(self, store: CredentialStore, *,
                 verify: Callable[[Credentials], CheckResult] = verify_key,
                 run_async: Callable[[Callable[[], None]], None] = _in_thread) -> None:
        self._store = store
        self._verify = verify
        self._run_async = run_async
        self._results: queue.Queue = queue.Queue()
        self._generation = 0
        self._confirmed: Credentials | None = None
        self.checking = False

    @property
    def confirmed(self) -> bool:
        return self._confirmed is not None

    def fields_changed(self) -> None:
        self._generation += 1
        self._confirmed = None

    @staticmethod
    def _credentials(key: str, secret: str) -> Credentials | str:
        key, secret = key.strip(), secret.strip()
        if not key:
            return "Введите API Key."
        if not secret:
            return "Введите API Secret."
        return Credentials(key, secret)

    def start_check(self, key: str, secret: str) -> str:
        """Start the background check; returns the text to show right away."""
        credentials = self._credentials(key, secret)
        if isinstance(credentials, str):
            return credentials
        self._confirmed = None
        self.checking = True
        generation = self._generation

        def work() -> None:
            try:
                result = self._verify(credentials)
            except Exception as error:  # class only: a message could embed request details
                result = CheckResult(False, f"Проверка не выполнена: {type(error).__name__}")
            self._results.put((generation, credentials, result))

        self._run_async(work)
        return CHECKING

    def poll(self) -> CheckResult | None:
        """GUI thread: the finished check, if any. A check for edited values is dropped."""
        try:
            generation, credentials, result = self._results.get_nowait()
        except queue.Empty:
            return None
        self.checking = False
        if generation != self._generation:
            return CheckResult(False, "Значения изменены во время проверки. Проверьте ещё раз.")
        if result.ok:
            self._confirmed = credentials
        return result

    def save(self, key: str, secret: str) -> CheckResult:
        current = self._credentials(key, secret)
        if self._confirmed is None or isinstance(current, str) or current != self._confirmed:
            return CheckResult(False, NEED_CHECK)
        try:
            self._store.save(self._confirmed)
        except BybitPositionsError as error:
            return CheckResult(False, f"Не удалось сохранить ключ: {type(error).__name__}: {error}")
        except Exception as error:
            return CheckResult(False, f"Не удалось сохранить ключ: {type(error).__name__}")
        return CheckResult(True, f"Ключ сохранён в Windows Credential Manager ({DEFAULT_TARGET}).")
