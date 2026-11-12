# Windows VPS Manager — установка, фактическая приёмка и связь с PAPER-монолитом (07.11.2026)

**Назначение:** одна воспроизводимая инструкция для ноутбука и второго Windows-ПК; журнал доказательств, а не декларация готовности VPS. Это только документация. VPS, PAPER DB, сервисы, позиции и торговое состояние не изменялись.

## 1. Проверенное на ноутбуке 07.11.2026

Из предоставленного владельцем вывода PowerShell:

- Через GitHub CLI скачан workflow artifact `BybitScanner-VPS-Manager-Windows` из GitHub Actions run `42374701807` репозитория `svobodaXXI/BybitScanner`.
- Локальная папка установки: `%LOCALAPPDATA%\BybitScanner\VPSManager\release-42374701807`; EXE: `BybitScanner-VPS-Manager.exe`.
- Создан ярлык на рабочем столе `BybitScanner VPS Manager - исправленный.lnk`. Он передаёт `--host 83.217.213.181 --user root --key "%USERPROFILE%\.ssh\bybitscanner_laptop"` (в команде PowerShell вычисляется полный путь).
- Выведено `UPDATE_INSTALLED_AND_LAUNCH_REQUESTED`: скачивание, наличие EXE, сохранение ярлыка и запрос запуска завершились без зарегистрированной ошибки.
- Скриншот владельца: окно **BybitScanner VPS Manager — PAPER** открылось, поля адреса `83.217.213.181`, пользователя `root` и ключа `C:\Users\SVOBODA21\.ssh\bybitscanner_laptop` уже заполнены. Есть кнопки «Состояние», «Диагностика PAPER», «Git / локальные изменения», «Предпроверка обновления», «Последние журналы». В первоначальном скриншоте строка состояния: **«Не подключено · PAPER only»**; журнал пуст. После этого владелец нажал «Состояние» и получил фактический результат ниже.
- Следовательно, **автозаполнение в текущем ярлыке подтверждено**, и SSH-аутентификация **подтверждена для команды «Состояние»**; остальные кнопки, полнота их вывода и возможность преодолеть монолитный блокер **не проверены**. Сообщение о запуске не является доказательством успешной SSH-сессии.

Ранее в этой же истории владелец показал `MACHINE_TIME_UPDATE_VERIFIED` и `LOCAL_REPLAY_PACKAGE_OK` для отдельной локальной «Машины времени». **Это не проверка VPS Manager**; не смешивать эти инструменты.

## 2. Как повторить установку на ноутбуке

Предусловия: установлен GitHub CLI `gh`, выполнен вход в GitHub с доступом к репозиторию и артефакту; OpenSSH Client; локальный разрешённый SSH-ключ; проверенная запись хоста в `known_hosts`. GitHub Actions artifacts имеют ограниченный срок хранения: run `42374701807` не является вечным URL; в будущем использовать актуальный прошедший CI workflow run и **точное имя артефакта**. Не подменять незаметно сборку.

PowerShell (локально; **не** на VPS):

```powershell
$ErrorActionPreference = 'Stop'
$run = '42374701807' # заменить на проверенный доступный run при повторной установке
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) { $gh = "$env:ProgramFiles\GitHub CLI\gh.exe" }
if (-not (Test-Path $gh)) { throw 'GitHub CLI не найден' }
$dir = "$env:LOCALAPPDATA\BybitScanner\VPSManager\release-$run"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
& $gh run download $run --repo svobodaXXI/BybitScanner --name BybitScanner-VPS-Manager-Windows --dir $dir
if ($LASTEXITCODE -ne 0) { throw 'Ошибка загрузки сборки' }
$exe = Join-Path $dir 'BybitScanner-VPS-Manager.exe'
if (-not (Test-Path $exe)) { throw 'EXE не найден' }
$key = "$env:USERPROFILE\.ssh\bybitscanner_laptop"
if (-not (Test-Path $key)) { throw 'Локальный SSH-ключ отсутствует' }
$arguments = "--host 83.217.213.181 --user root --key `"$key`""
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'BybitScanner VPS Manager - исправленный.lnk'))
$link.TargetPath = $exe
$link.Arguments = $arguments
$link.WorkingDirectory = $dir
$link.Save()
Start-Process -FilePath $exe -ArgumentList $arguments
Write-Host 'UPDATE_INSTALLED_AND_LAUNCH_REQUESTED'
```

Команда повторяет фактический путь установки **для данного ноутбука**, не подтверждает подключение и не делает операций на VPS. Отдельный `root`-ключ может быть защищён passphrase; приложение использует пакетный SSH и не гарантирует интерактивный запрос passphrase — для такой конфигурации возможен отказ, даже при корректном ключе.

## 3. Откуда берётся автозаполнение; перенос на второй ПК

Текущее автозаполнение достигнуто **параметрами локального ярлыка** `--host`, `--user`, `--key`; самостоятельное автоматическое обнаружение сервера/учётной записи/SSH-identity кодом **не доказано**. Поэтому требование «не вводить три поля вручную» для ноутбука выполнено; создание безопасного ярлыка на другом ПК остаётся шагом установки, не новой функцией VPS.

Для второго ПК:

1. Получить тот же или более новый **проверенный** GitHub Actions артефакт по процедуре выше, подставив текущий run и свою папку профиля.
2. Создать отдельную SSH identity для **непривилегированного** `vpsmanager` на втором ПК; не копировать приватный ключ ноутбука и не коммитить ключи или пароль. Публичный ключ добавить к разрешённому аккаунту только через отдельно разрешённый административный маршрут, не перезаписывая остальные ключи.
3. На втором ПК создать локальный ярлык с тем же адресом хоста, `--user vpsmanager`, `--key` указывающим на **существующий на том ПК** приватный ключ; не предполагать, что `C:\Users\SVOBODA21\...` существует на другом устройстве.
4. Проверить known_hosts / fingerprint хоста из доверенного канала, затем реально выполнить `Состояние` и проверить SSH exit 0 плюс ожидаемую идентичность сервера. До этих проверок второй ПК не принят.

Исторические доказательства: [PR #663](https://github.com/svobodaXXI/BybitScanner/pull/663) добавлял аргументы ярлыка и явный SSH identity, [PR #664](https://github.com/svobodaXXI/BybitScanner/pull/664) описывал отдельные ноутбучные ключи и ограниченного `vpsmanager`. При прошлой приёмке 28.10 под `vpsmanager` кнопка «Состояние» возвращала exit 0 (backend и Telegram active, one-shot paper-start inactive/dead). **Это исторический снимок, не доказательство нынешнего состояния VPS.** Административный `root` не должен становиться режимом по умолчанию для будущего ПК.

## 4. Кнопки и доказательства

| Действие | Назначение по исходному проекту PR #662/#663 | Фактическая приёмка |
| --- | --- | --- |
| Состояние | Сведения о systemd-сервисах | **Проверено 07.11 под `root`: exit 0, backend PID 1954668 active/running, второй unit active/running, третий inactive/dead**; раньше было проверено 28.10 под `vpsmanager` |
| Диагностика PAPER | systemd backend и локальный `/api/health` | **Не проверено** в новой сборке |
| Git / локальные изменения | Информация об установленном исходнике или явное `UNKNOWN` при gitless | **Не проверено** в новой сборке |
| Предпроверка обновления | Информационная проверка, **не разрешение на deploy** | **Не проверено** в новой сборке |
| Последние журналы | Чтение последних записей systemd journal | **Не проверено** в новой сборке; права на чтение могут ограничивать результат |

Нужно получить полный фактический вывод кнопок (без секретов) и exit codes; записать дату, run, target, признак gitless, точное состояние/ошибку. При ошибках **не** выдавать sudo/journal права автоматически и не запускать цикл повторных попыток.

## 5. Что VPS Manager может дать квесту «Монолит / Автопилот / обновление VPS»

Потенциальная польза — один ручной Windows-интерфейс для **read-only evidence collection**: активность сервисов, PID, локальное здоровье Backend, журналы и признак gitless установленного релиза. Эту информацию можно сопоставить с текущим источником истины `DOCUMENTS/BACKLOG.md` (P0 монолитный safe-stop/recovery) и соответствующим ChangeRequest, а также с данными официального preflight.

**Не считать VPS Manager официальным safe-stop/deploy gate:** исходный MVP намеренно не выполняет STOP/START, reconcile, DB repair, switch release, POST торговых команд, не доказывает отсутствие ордеров/позиций или корректность protection obligations. Даже «systemctl active» и HTTP health по отдельности не доказывают Robot READY, Admission, protection HEALTHY и безопасную возможность обновления. Результат `DEPLOY_PREFLIGHT=NOT_PROVEN` при gitless — наблюдение, а не инструкция обходить блокер.

Для недавнего блокера `canonical_safe_stop_unproven / dual orphan / one_orphan_unrelated_protection_failure` утилита может помочь **локализовать** ошибку, если покажет коррелирующие PID/health/journal, но устранение должно оставаться в каноническом жизненном цикле PAPER с доказательствами покрытия/обязательств, а не через ручной systemctl или сырой SSH. Нельзя утверждать, что конкретный блокер устранён: фактических результатов кнопок 07.11 пока нет.

## 6. Границы полномочий

Только PAPER и чтение до отдельного разрешения. Не изменять VPS, БД, сервисы, позиции, ордера, Admission, STOP/TAKE и RELEASE; LIVE запрещён. GitHub PR документации не разрешает merge или runtime действия. Не публиковать приватные ключи, пароли, секреты и полный SSH-agent inventory.

## 7. Новая фактическая приёмка 07.11 — кнопка «Состояние»

На следующем скриншоте владельца в установленном EXE из run `42374701807` с заполненными `--host 83.217.213.181 --user root --key ...bybitscanner_laptop` статус стал **«Успешно · Exit code: 0»**. Журнал:

```text
> Состояние
MainPID=1954668
ActiveState=active
SubState=running
ActiveState=active
SubState=running
ActiveState=inactive
SubState=dead
Exit code: 0
```

По проверенному исходному контракту действия «Состояние» это последовательность systemd-запросов к PAPER backend, Telegram и одноразовому paper-start. Следовательно, backend `active/running` c PID `1954668`, Telegram `active/running`, paper-start `inactive/dead`. Статус one-shot `inactive/dead` сам по себе не доказывает остановку PAPER. Отсутствие подписей unit в текущем журнале — **диагностическая UX-неоднозначность**; для дальнейшей работы лучше добавить метки к каждой группе, но не делать это условием монолитного recovery.

**Доказано:** SSH соединение, исполнение allowlisted read-only команды, exit 0 и отображение её вывода. **Не доказано:** режимы Scanner/Robot/PAPER_AUTO, Admission/protection, целостность DB, отсутствие exposure, результат официального safe-stop или корректность обновления. «Диагностика PAPER», «Git / локальные изменения», «Предпроверка обновления», «Последние журналы» на этом скриншоте не нажимались; их статус остаётся непроверенным. VPS/торговое состояние не менялись.
