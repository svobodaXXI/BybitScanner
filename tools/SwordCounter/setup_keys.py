"""SwordCounter S5: local console wizard for the separate Read-Only Bybit key.

``python -m tools.SwordCounter.setup_keys`` (or ``setup_sword_counter_keys.bat``)

- The key and secret are typed by the owner into hidden prompts of an interactive console:
  never on a command line, in a file, in Git, a log or a report. No option accepts a secret.
- Before saving, the key is checked with Bybit through read-only requests only: it must
  report ``readOnly`` = 1 and be able to read positions. A key with trading rights is refused.
- It is saved only to the Windows Credential Manager (current user). It never touches the
  BybitScanner robot's keys.
- ``--status`` (no values), ``--test`` (re-check the saved key), ``--delete``.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from dataclasses import dataclass
from typing import Callable

from tools.SwordCounter.bybit_positions import (
    ApiKeyInfo, BybitCredentialsError, BybitPositionsError, Credentials, fetch_api_key_info,
    fetch_open_positions,
)
from tools.SwordCounter.credential_store import (
    DEFAULT_TARGET, CredentialStore, WindowsCredentialStore, resolve_credentials,
)

INTRO = """\
SwordCounter: настройка отдельного API-ключа Bybit (только чтение)

1. В Bybit создайте НОВЫЙ API-ключ специально для SwordCounter (не ключ робота).
2. Тип: системный (HMAC), права: только чтение (Read-Only). Торговля, вывод и перевод не нужны.
3. Рекомендуется привязать ключ к IP-адресу этого компьютера.
4. Значения вводятся скрыто (на экране не отображаются) и сохраняются только в Windows
   Credential Manager для вашей учётной записи. В файлы, Git и логи они не попадают.
"""


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


def verify_key(credentials: Credentials, *,
               info_fetch: Callable[[Credentials], ApiKeyInfo] = fetch_api_key_info,
               positions_fetch: Callable[[Credentials], tuple] = fetch_open_positions) -> CheckResult:
    """Read-only checks against Bybit. Fails closed; messages carry no key material."""
    try:
        info = info_fetch(credentials)
    except BybitPositionsError as error:
        return CheckResult(False, f"Bybit не подтвердил ключ: {type(error).__name__}: {error}")
    if not info.read_only:
        return CheckResult(False, "Ключ имеет права на запись или торговлю. Создайте ключ с правом Read-Only "
                                  "и повторите настройку. Этот ключ не сохранён.")
    try:
        count = len(positions_fetch(credentials))
    except BybitPositionsError as error:
        return CheckResult(False, f"Ключ Read-Only, но позиции не читаются: {type(error).__name__}: {error}")
    tip = "" if info.ip_restricted else " Совет: привяжите ключ к IP-адресу."
    return CheckResult(True, f"Bybit подтвердил: ключ Read-Only, позиции читаются (открытых: {count}).{tip}")


def _validate(key: str, secret: str) -> str | None:
    """Local check is only 'not empty': the real verdict on the format comes from Bybit (query-api)."""
    if not key:
        return "API-ключ пуст."
    if not secret:
        return "API-секрет пуст."
    return None


def run_wizard(*, ask_secret: Callable[[str], str], ask_yes_no: Callable[[str], bool],
               store: CredentialStore, verify: Callable[[Credentials], CheckResult],
               out: Callable[[str], object]) -> int:
    """0 saved, 1 refused or failed, 2 cancelled by the owner."""
    out(INTRO + "\n")
    if store.load() is not None:
        if not ask_yes_no("Ключ SwordCounter уже настроен. Заменить его?"):
            out("Отменено: прежний ключ оставлен.\n")
            return 2
    key = ask_secret("API-ключ Bybit (ввод скрыт): ").strip()
    secret = ask_secret("API-секрет Bybit (ввод скрыт): ").strip()
    problem = _validate(key, secret)
    if problem:
        out(problem + " Ничего не сохранено.\n")
        return 1
    credentials = Credentials(key, secret)
    out("Проверяю ключ через разрешённые read-only запросы Bybit…\n")
    result = verify(credentials)
    out(result.message + "\n")
    if not result.ok:
        out("Ничего не сохранено.\n")
        return 1
    store.save(credentials)
    out(f"Ключ сохранён в Windows Credential Manager ({DEFAULT_TARGET}). Значения нигде не показаны.\n")
    return 0


class _QuietParser(argparse.ArgumentParser):
    def error(self, message):  # never echo the offending arguments: they could be a secret
        sys.stderr.write("Недопустимые параметры. Ключи и секреты вводятся только в диалоге мастера.\n")
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _QuietParser(prog="setup_keys", allow_abbrev=False, add_help=True)
    parser.add_argument("--status", action="store_true", help="show whether a key is configured (no values)")
    parser.add_argument("--test", action="store_true", help="re-check the saved key with Bybit (read-only)")
    parser.add_argument("--delete", action="store_true", help="remove the saved SwordCounter key")
    return parser


def _ask_yes_no(question: str) -> bool:
    return input(f"{question} [y/N]: ").strip().lower() in ("y", "yes", "д", "да")


def main(argv: list[str] | None = None, *, store: CredentialStore | None = None,
         out: Callable[[str], object] | None = None, verify: Callable[[Credentials], CheckResult] | None = None,
         ask_yes_no: Callable[[str], bool] = _ask_yes_no,
         ask_secret: Callable[[str], str] = getpass.getpass) -> int:
    args = build_parser().parse_args(argv)
    out = out if out is not None else sys.stdout.write
    store = store if store is not None else WindowsCredentialStore()
    verify = verify if verify is not None else verify_key

    try:
        if args.status:
            configured = store.load() is not None
            out(f"Credential Manager ({DEFAULT_TARGET}): {'ключ настроен' if configured else 'ключ не настроен'}\n")
            return 0
        if args.delete:
            if store.load() is None:
                out("Ключ SwordCounter не настроен: удалять нечего.\n")
                return 0
            if not ask_yes_no("Удалить ключ SwordCounter из Credential Manager?"):
                out("Отменено.\n")
                return 2
            store.delete()
            out("Ключ SwordCounter удалён. Ключи робота и других программ не затронуты.\n")
            return 0
        if args.test:
            try:
                credentials, source = resolve_credentials(store)
            except BybitCredentialsError as error:
                out(f"{error}\n")
                return 1
            result = verify(credentials)
            out(f"Источник ключа: {source}. {result.message}\n")
            return 0 if result.ok else 1
        if not sys.stdin.isatty():
            out("Мастер запрашивает секреты только в интерактивной консоли. Запустите "
                "setup_sword_counter_keys.bat двойным щелчком; ввод из файла или конвейера не поддерживается.\n")
            return 1
        return run_wizard(ask_secret=ask_secret, ask_yes_no=ask_yes_no, store=store, verify=verify, out=out)
    except BybitCredentialsError as error:
        out(f"Хранилище ключей недоступно: {type(error).__name__}: {error}\n")
        return 1
    except Exception as error:  # class only: the message of an unexpected error may embed a secret
        out(f"Неожиданная ошибка мастера: {type(error).__name__}. Ничего не сохранено.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
