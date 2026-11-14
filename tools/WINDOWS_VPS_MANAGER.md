# BybitScanner VPS Manager — общий вход в серверный монолит

Три интерфейса одного владельческого механизма: Windows GUI, Windows PowerShell CLI и
консоль VPS (Termius/VDSina). Все изменяющие действия передаются серверному
`tools.vps_owner_control`; он запускает **существующий** `tools.paper_maintenance`
в отдельном transient systemd oneshot unit. Второго координатора торговых действий нет.

## Windows

`tools/Запустить VPS Manager.cmd` открывает Tkinter GUI; для CLI применяется
тот же `tools/windows_vps_manager.py`. Доступны пять прежних read-only диагностик,
а также отдельные подтверждаемые кнопки **Обновить EDITOR_ONLY**, **Запустить
PAPER-ядро**, **Остановить PAPER-ядро**, **Обновить и запустить PAPER** и запрос статуса.

```powershell
py -3 tools\windows_vps_manager.py --operation update --sha <approved-40-char-SHA>
py -3 tools\windows_vps_manager.py --operation start
py -3 tools\windows_vps_manager.py --operation status --request-id <request-id>
py -3 tools\windows_vps_manager.py --operation list
```

Для UPDATE нужен **точный разрешённый SHA**, для START/STOP SHA текущего
установленного релиза вычисляется на VPS посредством `verify_release`.
Если в `%USERPROFILE%\.ssh\config` существует `Host bybitscanner-vps`,
программа автоматически использует этот alias и его host/key/user/port,
без ручной подстановки IP. Иначе используется только заранее настроенная
`BYBITSCANNER_VPS_SSH_TARGET=user@host` или явный `--host/--user/--key`.
Имя Windows-устройства отображается в окне и записывается в описание операции.
Не угадывать PC/LAPTOP по неизвестному оборудованию: локальные имена различаются.

Применяется `BatchMode=yes`, `StrictHostKeyChecking=yes`: программа **не хранит**
секреты и не расшифровывает закрытые ключи. Для работы без повторной passphrase
на каждом новом SSH соединении заранее настроенный OS ssh-agent должен иметь
уже разблокированный ключ. При недоступном агенте авторизация не обходится.
Никакого автоматического изменения VPN/host key/SSH-конфига.

## VPS / смартфон

После установки совместимого серверного релиза из Termius или консоли VDSina:

```sh
cd /opt/BybitScanner && /opt/BybitScanner/venv/bin/python -m tools.vps_owner_control submit update <approved-40-char-SHA>
cd /opt/BybitScanner && /opt/BybitScanner/venv/bin/python -m tools.vps_owner_control list
cd /opt/BybitScanner && /opt/BybitScanner/venv/bin/python -m tools.vps_owner_control status <request-id>
```

SUBMISSION=ACCEPTED означает **только передачу**. Монолит продолжает работу
на VPS даже после обрыва SSH; результат определяется `STATUS=FINISHED_OK`
с кодом завершения или `STATUS=FAILED`. Идентификатор запроса связывает
системный unit, origin и журнал. Повторное обращение с тем же ID не запускает
операцию заново; после неизвестного ответа проверять только статус. Успешный
релиз дополнительно требует установленной runtime/HTTPS/UI приёмки.

Операции от имени root разрешены **только при явном выборе владельца** и
применяют штатные STOP/START/UPDATE монолита с его preflight, STOP receipts,
защитой PAPER DB, admission и STOP/TAKE. Менеджер не включает PAPER_AUTO, LIVE,
не пишет в SQLite и не делает альтернативных прямых systemctl restart/STOP.
Без одобренного конкретного релиза, работающего доверенного SSH маршрута или
подтверждённой quiescence — ожидаемый исход BLOCKED без обхода.

## Граница готовности

GitHub CI покрывает сборку Windows EXE и изолированные контракты запроса.
Реальный проход из GUI, PowerShell и Termius до VPS не считается доказанным
без отдельной приёмки на установленной версии. До разрешённого merge/deploy
этот интерфейс нельзя использовать для рабочего VPS.
