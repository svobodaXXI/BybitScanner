# VPS PAPER — проверенный запуск, Telegram, ошибки и будущая одна кнопка

Статус: зафиксировано по фактической приёмке **27 октября 2026**, код `stable/adfb50b-forward` после PR #638 (HEAD `71213935`). Это **операционный runbook**, а не разрешение запускать/останавливать Runtime без владельца.

Связанные документы: [основной VPS runbook](VPS_DEPLOYMENT_RUNBOOK.md), [Telegram/SSH issue #631](https://github.com/svobodaXXI/BybitScanner/issues/631), [PR #637](https://github.com/svobodaXXI/BybitScanner/pull/637), [PR #638](https://github.com/svobodaXXI/BybitScanner/pull/638).

## 1. Проверенное 27.10.2026

- `git merge --ff-only` обновил **чистую** VPS-копию `/opt/BybitScanner` с `e74e821` до `71213935`. Установлен только изменённый `deploy/systemd/bybitscanner-paper-start.service`, затем `systemctl daemon-reload`; подтверждено `DEPLOY OK: 71213935`. PAPER SQLite не переносили/не изменяли.
- `systemctl start bybitscanner-paper-start.service` завершился штатно: `READY: intent=ALL changed=robot:start,scanner:start robot=READY protection=HEALTHY scanner=RUNNING` в 15:47:45 по локальному журналу VPS. Это **не означает**, что `PAPER_AUTO` или Telegram уже включены.
- С отдельным разрешением владельца через **существующий авторизованный API** `POST /api/robot/autopilot` включён `PAPER_AUTO`, подтверждён повторным GET: `mode=PAPER_AUTO`, версия 8. Не печатать токен, не обходить подтверждение или Admission. После нового перезапуска ожидается `OFF` (fail-closed).
- Telegram: VPS `curl --socks5-hostname 127.0.0.1:10809 https://api.telegram.org` вернул HTTP **302** (проверка сетевого маршрута); `systemctl start bybitscanner-telegram.service` дал **active**; `http://127.0.0.1:8766/health` вернул `status=ready` и ту же PAPER `database_identity`, что Backend; владелец **подтвердил получение реальных сигналов в Telegram-боте**. Команда `/status` **не подтверждена/не обязана существовать**, её молчание не означает сбой доставки.
- Дальнейшее исполнение новых PAPER-сделок и срабатывание STOP/TAKE **не доказаны одним только READY**: нужны реальные безопасные наблюдения и журнал. LIVE не разрешён.

## 2. Как именно был восстановлен Telegram (временный рабочий маршрут)

`Telegram API ↔ Xray SOCKS5 на Windows-ноутбуке 127.0.0.1:10808 ↔ SSH reverse forward ↔ VPS 127.0.0.1:10809 ↔ Telegram Monitoring`.

Предпосылки: на ноутбуке запущен и доступен Xray SOCKS5:10808, приватный SSH-ключ `bybitscanner_laptop` доступен только владельцу, публичный ключ заранее установлен в разрешённых `authorized_keys`. Подробности восстановления доступа — issue #631.

1. **Отдельное** окно PowerShell на ноутбуке (не SSH-консоль управления). Команда, доказанно сработавшая в приёмке:
   ```powershell
   ssh -i "$env:USERPROFILE\.ssh\bybitscanner_laptop" -o IdentitiesOnly=yes -o PasswordAuthentication=no -o ExitOnForwardFailure=yes -N -R 127.0.0.1:10809:127.0.0.1:10808 root@83.217.213.181
   ```
   Ввести **локальную passphrase ключа**, не пароль root; отсутствие нового приглашения `PS>` при `-N` нормально. Это отдельная длительная SSH-сессия; окно не закрывать. Не публиковать passphrase или ключ.
2. В другой, уже авторизованной SSH-консоли VPS **только** проверка маршрута (не передавать реальный bot token в аргументах):
   ```bash
   curl -sS --max-time 10 --socks5-hostname 127.0.0.1:10809 -o /dev/null -w 'TELEGRAM_HTTP=%{http_code}\n' https://api.telegram.org
   ```
   Приёмка показала **302**. Это проверка транспорта, **не** доставки ботом.
3. Если служба Telegram не работает, при наличии разрешения на управление Telegram: `systemctl reset-failed bybitscanner-telegram.service && systemctl start bybitscanner-telegram.service`. Затем `systemctl is-active bybitscanner-telegram.service` = `active`; `curl -sS --max-time 5 http://127.0.0.1:8766/health` = `status=ready`, identity совпадает с Backend.
4. **Приёмка сквозной доставки**: дождаться реального сообщения/сигнала BybitScanner в целевом Telegram-чате. Не сочинять `/status` как диагностическую команду. При ошибках не публиковать сырые логи, поскольку ошибки Telegram API могут включать URL с секретным bot token.

**Важное ограничение:** этот маршрут **не автономен**: закрытие ноутбука, Xray либо окна reverse SSH разрывает Telegram, даже если PAPER-ядро VPS работает. Заменить на постоянно доступный **серверный** egress к Telegram отдельным проверенным проектным изменением; до него не обещать 24/7 Telegram.

## 3. Единственная существующая точка запуска VPS (после #638)

```bash
systemctl start bybitscanner-paper-start.service
```

Это штатный unit systemd. `Requires=bybitscanner-paper-backend.service` — Backend обязателен; `Wants=bybitscanner-telegram.service` — Telegram best-effort, чтобы сбой Telegram API/туннеля не блокировал Robot/Scanner. `ExecStart=... python -m tools.runtime_intent --no-telegram ALL`; запуск идёт с `EnvironmentFile=/etc/bybitscanner/paper.env`, через ту же проверку канонической PAPER DB и один `POST /api/runtime/intent`. Никакого прямого запуска вторых процессов.

Единый `READY` подтверждает только `robot=READY`, `protection=HEALTHY`, `scanner=RUNNING`. Он **не включает** `PAPER_AUTO`, не подтверждает Telegram доставку или наличие сделок. Режим Autopilot надо отдельно проверить; включение — только после явного разрешения владельца, через отдельный API-токен из локального `/etc/bybitscanner/owner.env` с `confirm_paper_auto=true`. Не копировать эти секреты в GitHub. `LIVE` строго выключен; Admission, reconciliation, STOP/TAKE не обходить.

**Остановка** — только штатная `tools.stop_robot_runtime all --env-file /etc/bybitscanner/paper.env` от `bybitscanner` согласно [основному runbook](VPS_DEPLOYMENT_RUNBOOK.md). Не `kill -9`, не `systemctl restart` Backend, не повторять принудительные запуски после `BLOCKED`. Не менять SQLite руками.

## 4. Ошибки 26–27 октября и правила против повторения

| Ошибка / анти-паттерн | Почему случилось | Правильное действие |
|---|---|---|
| Парольный `ssh root@host` вместо ключа | Рабочий доступ был через отдельный ed25519 ключ; пароль root не проходил | Сразу использовать документированный `ssh -i … -o IdentitiesOnly=yes -o PasswordAuthentication=no`, локальную passphrase. Не перебирать пароли |
| Диагностика Telegram с нуля, хотя runbook уже был | Не подняли issue #631 и VPS-инструкцию | Сначала читать уже зафиксированный проверенный маршрут, только затем менять инфраструктуру |
| Telegram `SOCKS Connection refused` при работающем процессе | На VPS отсутствовал reverse tunnel 10809; служба `active` не равна успешному Telegram egress | Проверять путь `Xray:10808 ↔ SSH -R :10809` и фактическую доставку; не чинить вслепую код бота |
| Старый systemd `Requires=Telegram` и обязательный Telegram probe | Telegram TIME_WAIT/network мешали `runtime_intent ALL`, ядро не запускалось | PR #637 — singleton bind fix; PR #638 — Telegram optional (`Wants`), Backend required |
| Ручной `execute_runtime_intent("ALL", require_telegram=False)` без service environment | Идентичность локальной PAPER DB по умолчанию отличалась от VPS `/var/lib/bybitscanner/paper_runtime.sqlite3`; intent не отправлен | Не вызывать вручную Python entrypoints; использовать canonical systemd unit с `paper.env` |
| Попытка вызвать несуществующий `tools.stop_robot_runtime._parse_env_file` | Непроверенный импорт и непроверенная одноразовая команда | Не выдумывать интерфейсы; сверять исходники/тесты, проходить CI; работать через documented entrypoint |
| Много ручных команд на работающем VPS | Подмена задачи запуска бесконечной диагностикой; риск ненужного воздействия на runtime | «Результат прежде инфраструктуры»: исправлять в GitHub, делать review/CI, деплоить одной предсказуемой процедурой |
| `READY` интерпретировался как автоторговля и доставка | `runtime_intent ALL` не меняет `PAPER_AUTO`, Telegram отделён | Раздельная проверка Robot/Scanner, Autopilot mode, защиты, Telegram health и реальных сигналов |
| Предложена неподтверждённая команда бота `/status` | Её существование не проверено | Сверять реализованные команды с кодом; реальные пришедшие сигналы — достаточное свидетельство исходящей доставки |
| Автоматическая перезагрузка/удаление state для ускорения | Угроза защищаемым позициям/STOP/TAKE | Никакой принудительной остановки; fail closed, сохранить целостность PAPER DB и обязательств |

## 5. Следующая инженерная цель — действительно одна кнопка

**Желаемое UX:** владелец нажимает «Запуск робота» один раз; уже проверенная цепочка сама поднимает **один** Backend, Scanner, Robot, MIRROR, Telegram и разрешённый PAPER Autopilot; показывает **раздельный статус** торгового ядра и уведомлений. Повторное нажатие идемпотентно; никаких дополнительных ярлыков JOINT, ручных Python команд или SSH-окон как обязательного пользовательского сценария.

Для этого **ещё не реализовано**:
1. **Независимый VPS egress Telegram**, без ноутбука и временного SSH-туннеля; проверка доставки, singleton getUpdates и безопасный повторный запуск при отказе.
2. **Долговечная owner-authorized политика PAPER_AUTO** с отдельным решением о разрешённых автоматических повторах после перезапуска; текущий `OFF` после restart — необходимая fail-closed защита, не изменять без явного одобрения.
3. **Owner launcher / ярлык**: авторизованно вызывать штатный VPS systemd one-shot (не дублировать логику, не размещать ключи/пароли в ярлыке), показывать `core READY / autopilot mode / telegram delivery`; применять только разрешённые действия.
4. **Приёмка end-to-end**: остановка/запуск по отдельному согласию, PAPER DB identity, LIVE=false, admission, protection, реальные сигналы и последующий PAPER trade lifecycle. Без искусственного создания сделок и без LIVE-тестов.

Разработка: **GitHub → PR → CI → approval → squash merge → чистая VPS-копия fast-forward → обновление unit → один штатный запуск → проверка по факту**. Перед каждым деплоем проверять `git status`, HEAD, ветку, уникальные локальные изменения/секреты. Не считать `git pull` полной синхронизацией VPS и GitHub без аудита локального долга. Не делать runtime start/stop только потому, что смержен PR.


## 6. 05.11.2026 — ПОДТВЕРЖДЁННЫЙ прямой PowerShell SSH-доступ, без Codex/VNC

**Операционная политика владельца:** если Codex не может выполнить разрешённую VPS-задачу, использовать **прямой OpenSSH из Windows PowerShell** с уже доверенным ключом, прежде чем предлагать веб-VNC, замену ключей, новые forced-command мосты или многократные ручные действия. Это резервный *канал транспорта*, а не дополнительное разрешение на runtime/trading операции. VNC — только запасной вариант при реальном SSH-отказе. Не использовать Codex для разработки; GitHub остаётся авторитетом кода.

**Доказанный сеанс 05.11.2026 (владелец, реальная PowerShell/Ubuntu-консоль):**
- Исторический issue [#631](https://github.com/svobodaXXI/BybitScanner/issues/631) содержит тот же рабочий сценарий 27.10; ключ `bybitscanner_laptop` существует в `$env:USERPROFILE\.ssh`.
- Обычный `ssh root@83.217.213.181` и явный `bybitscanner_vdsina_2026` при `BatchMode=yes` возвращали `Permission denied (publickey,password)`. **Не делать вывод, что ключ не установлен или требуется VNC**: `BatchMode=yes` не разрешает интерактивный запрос passphrase незагруженного ключа.
- Следующая **точная** команда запросила *локальную passphrase* для `bybitscanner_laptop` и открыла Ubuntu 24.04.4 root shell (`root@v3286418:~#`):

```powershell
ssh -i "$env:USERPROFILE\.ssh\bybitscanner_laptop" -o IdentitiesOnly=yes -o PasswordAuthentication=no root@83.217.213.181
```

- Это проверенный интерактивный SSH-транспорт, **не** доказательство нового деплоя, Robot READY или безопасной остановки. Последующих root/runtime команд только по факту SSH-доступа не выполнять; для защищённых операций по-прежнему нужны отдельное разрешение, preflight, STOP/TAKE и PAPER DB invariants.
- SSH-сессия остаётся открытой, пока активен клиент; для нового подключения после закрытия используйте ту же команду. Не отключать парольную фразу ключа, не сохранять её в скриптах, репозитории, terminal history или CI.

### 06.11.2026 — повторный SSH-отказ из-за способа вставки passphrase в PowerShell (подтверждено владельцем)

**Симптом:** ранее рабочий `bybitscanner_laptop` внезапно дважды запрашивает passphrase, затем `Permission denied (publickey,password)`. Локальная `ssh-keygen -y -f ...` возвращает `incorrect passphrase supplied to decrypt private key`. Эти симптомы сами по себе **не доказывают** отзыв ключа на VPS, повреждение ключевого файла, отказ sshd или необходимость VNC.

**Выявленная причина этого инцидента:** владелец пытался вставить парольную фразу в интерактивное приглашение OpenSSH через **правую кнопку мыши** в PowerShell; в данном терминальном сеансе она вводилась не так, как ожидалось. При использовании **другого способа вставки** той же passphrase та же неизменная команда `ssh -i ...bybitscanner_laptop ...` снова открыла root shell Ubuntu **06.11.2026 02:21 MSK**. Публичные и приватные ключи, `authorized_keys`, SSH-сервер и VPS для этого успешного входа менять не требовалось. Точный альтернативный способ вставки не зафиксирован — не объявлять конкретное сочетание клавиш универсально работающим.

**Первое действие при повторении:** напомнить владельцу: **«Мы это уже проходили: при вводе passphrase не вставляй её правой кнопкой мыши — в прошлый раз именно из-за этого SSH не пускал. Используй тот другой способ вставки, который успешно сработал 06.11. Проверяем прежний `bybitscanner_laptop`, не меняем ключи и не переходим в VNC».** Ввод passphrase не отображается; не просить присылать сам секрет или логировать его. Если аккуратный повтор действительно не помогает — остановить попытки и диагностировать узко, без перебора ключей, правок `authorized_keys` и обходных путей наугад.

**Антипример:** последовательные попытки с `bybitscanner_vps_moba`, поиском GitHub public keys, VNC и длинными командами добавления `authorized_keys` потратили время владельца, хотя неизменный исходный ключ продолжал работать. Не повторять этот диагностический круг без новой доказанной причины. Этот факт касается только SSH-аутентификации и **не** подтверждает состояние PAPER/Robot/защиты или допустимость deployment.

### Повторный вход без ввода passphrase: штатный Windows OpenSSH ssh-agent (опционально)

Для удобства использовать стандартный **Windows OpenSSH Authentication Agent**, не незащищённый ключ. Настройка на **локальном ПК** (не VPS) по [Microsoft OpenSSH docs](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement):

1. Один раз в **PowerShell от имени администратора** (локально):
   ```powershell
   Get-Service ssh-agent | Set-Service -StartupType Automatic
   Start-Service ssh-agent
   ```
2. В **обычном PowerShell** пользователя:
   ```powershell
   ssh-add "$env:USERPROFILE\.ssh\bybitscanner_laptop"
   ssh-add -l
   ```
   При добавлении вводится *локальная* passphrase. После этого агент предоставляет ключ последующим сеансам без повторного ввода, пока агент и ключ доступны.
3. Подключение и ограниченная read-only проверка:
   ```powershell
   ssh -i "$env:USERPROFILE\.ssh\bybitscanner_laptop" -o IdentitiesOnly=yes -o PasswordAuthentication=no -o BatchMode=yes root@83.217.213.181 "id -u"
   ```
   Ожидаемый результат `0`. **Не считать это проверенным, пока владелец действительно не выполнит**.
4. Извлечь ключ из агента (при необходимости): `ssh-add -d "$env:USERPROFILE\.ssh\bybitscanner_laptop"`. Оставлять защищённый приватный файл у владельца; никаких копий в GitHub/сервере.

**Компромисс:** `ssh-agent` упрощает подключение, но делает загруженный административный ключ доступным приложениям в контексте текущей учётной записи Windows. Автозапуск и возможное сохранение записи ключа после перезагрузки расширяют время доступности: включать только на доверенном защищённом ПК. Для максимально строгой безопасности оставить ручной ввод passphrase. Никакие пароли/секреты не публиковать.

**Обязательный маршрут обслуживания (владелец подтвердил 05.11):** (1) ChatGPT самостоятельно использует GitHub для кода, PR, CI, проектной диагностики и доступных GitHub-мосту фактов; GitHub-доступ к репозиторию *не равен* произвольному доступу к живому VPS. (2) Для живого VPS при необходимости — одна цель и один ограниченный запрос существующему Codex/VPS-каналу с результатом и доказательством; рутинные чтения выполняет агент, а не владелец вручную. (3) **Только при конкретном подтверждённом блокере** этих маршрутов предложить владельцу прямой PowerShell SSH по уже проверенному `bybitscanner_laptop`, с минимальным числом команд. (4) VNC только если SSH недоступен. Не заставлять владельца повторять ключевые проверки, пересылать цепочки диагностик или заново восстанавливать уже рабочие ключи. Логин под root не отменяет project/owner authorization и fail-closed PAPER/LIVE ограничения.
