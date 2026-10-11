"""SwordCounter S3: what the window shows for a given count, without Tk.

Numbers are shown only for a fresh OK result computed with the current settings.
Everything else replaces both numbers with a status word, never with stale values.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tools.SwordCounter.settings_store import AppSettings
from tools.SwordCounter.swords import STATUS_NO_CONNECTION, STATUS_OK, STATUS_UNAVAILABLE, SwordCount

GREEN = "#1E9E3E"
RED = "#D32F2F"
GREY = "#8A8A8A"
STALE_AFTER_S = 30.0          # three refresh intervals without a new result
WORKER_FAILED = object()      # unexpected refresh failure (not a Bybit error)


@dataclass(frozen=True)
class Display:
    header: str
    free_text: str
    used_text: str
    free_color: str
    used_color: str
    status_text: str
    numbers_shown: bool


def header_text(settings: AppSettings) -> str:
    return f"1 РО = {settings.ro_usdt} USDT"


def _word(settings: AppSettings, word: str, status: str) -> Display:
    return Display(header_text(settings), word, word, GREY, GREY, status, False)


def build_display(settings: AppSettings, result, age_s: float | None) -> Display:
    if result is None:
        return _word(settings, "…", "Загрузка…")
    if result is WORKER_FAILED:
        return _word(settings, "Ошибка", "Внутренняя ошибка обновления")
    if age_s is None or age_s > STALE_AFTER_S:
        return _word(settings, "Нет данных", "Данные устарели")
    if not isinstance(result, SwordCount):
        return _word(settings, "Ошибка", "Неизвестный результат")
    if result.total_swords != settings.total_swords or result.sword_size_usdt != Decimal(settings.ro_usdt):
        return _word(settings, "…", "Обновление после смены настроек…")
    if result.status == STATUS_NO_CONNECTION:
        return _word(settings, "Нет соединения", result.reason or "Нет соединения")
    if result.status == STATUS_UNAVAILABLE:
        return _word(settings, "Недоступно", result.reason or "Недоступно")
    if result.status != STATUS_OK or result.used_swords is None or result.free_swords is None:
        return _word(settings, "Ошибка", "Неизвестный статус")
    status = (f"Превышение лимита: задействовано {result.used_swords} из {result.total_swords}"
              if result.over_limit else "Обновлено")
    return Display(header_text(settings), str(result.free_swords), str(result.used_swords),
                   GREEN, RED, status, True)
