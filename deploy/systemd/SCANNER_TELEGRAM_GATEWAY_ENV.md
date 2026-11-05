# Scanner → Telegram Gateway: единое окружение PAPER

**Подтверждено 2026-10-30:** запущенный backend/Scanner не содержит `BYBITSCANNER_TELEGRAM_GATEWAY_URL` и `BYBITSCANNER_TELEGRAM_GATEWAY_SECRET`; Telegram-служба обе переменные содержит. Поэтому отправка сигнала Scanner шла напрямую через недоступный SOCKS, несмотря на работающий Gateway.

**Каноническая точка конфигурации уже существует:** обе systemd-службы используют `EnvironmentFile=/etc/bybitscanner/paper.env`. Нельзя менять список EnvironmentFile в unit-файлах: его охраняют `tools.vps_check` и регрессионные тесты. Специальный новый unit или перезапуск торгового backend не нужен.

## Действие при следующем отдельно разрешённом безопасном запуске

1. VPS-оператор переносит из **уже защищённой и работающей конфигурации Telegram-службы** три согласованных значения: `BYBITSCANNER_TELEGRAM_GATEWAY_URL`, `BYBITSCANNER_TELEGRAM_GATEWAY_SECRET`, `TELEGRAM_CHAT_ID` — в существующий `/etc/bybitscanner/paper.env`. Секреты не выводить, не включать в shell-командную строку и не сохранять в GitHub. Перед изменением сделать защищённую точечную резервную копию и не трогать остальные переменные.
2. Проверить только синтаксис env-файла и отсутствие конфликтующих drop-in overrides. Не вызывать сервисный restart или kill. Изменение env-файла **не меняет окружение уже работающего процесса**.
3. При отдельно разрешённом **каноническом safe stop/start** PAPER-контура подтвердить admission/protection/positions и только тогда разрешить новый backend-процесс со штатным общим `paper.env`. Запрещён `systemctl restart bybitscanner-paper-backend`.
4. Подтвердить, что **новый** backend/Scanner имеет обе Gateway-переменные (не раскрывая секреты), и дождаться одного настоящего Scanner-сигнала в Telegram без генерации ложных торговых сигналов.

**Текущее состояние:** исправление сигнального пути пока **не активировано**; рабочий Scanner остаётся без Gateway-настроек. Нельзя заявлять восстановление доставки по одному только merge или правке env-файла.

PAPER-only; никакого LIVE. Robot, Scanner, PAPER_AUTO, STOP/TAKE, Admission и PAPER DB не менять без отдельного разрешения владельца.
