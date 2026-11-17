# BybitScanner — ЕДИНЫЙ РЕЕСТР ПОДКЛЮЧЕНИЙ К VPS

**Актуализация владельца: 17.11.2026. ЕДИНСТВЕННАЯ операционная точка истины о маршрутах SSH и состоянии подключения.** Ссылки из AGENTS.md, VPS Manager и иных runbook ведут сюда. Маршруты ниже приведены в порядке приоритета **по последней фактической приёмке**, а не по дате создания IP или прежнему названию alias.

## 0. АКТУАЛЬНОЕ ПОДКЛЮЧЕНИЕ С HAPP/VPN ВКЛЮЧЁН (проверено владельцем 17.11.2026)

**Подтверждённый успешный сценарий на основном ПК:** Happ → сервер **«Основной 1»** (Нидерланды, **VLESS / TCP / REALITY / JSON**), режим TUN включён; обычный Windows PowerShell пользователя `C:\Users\svobo`; существующий ключ **ПК** `bybitscanner_vdsina_gateway_20261030` (не ноутбучный); SSH напрямую на `root@212.193.14.116`, обходя старую конфигурацию alias с помощью `-F none`.

```powershell
ssh -F none -i "$env:USERPROFILE\.ssh\bybitscanner_vdsina_gateway_20261030" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 root@212.193.14.116 'echo SSH_OK; hostname'; "SSH_EXIT_CODE=$LASTEXITCODE"
```

**Фактическая приёмка владельца с Happ включённым:** `SSH_OK`, `v3286418.hosted-by-vdsina.ru`, `SSH_EXIT_CODE=0`. Это доказательство одного успешного SSH-сеанса, **не** доказательство постоянной стабильности или работы VPS Manager с его текущим автоматически выбранным адресом. При сохранении того же активного VPN-профиля это **первый документированный маршрут для основного ПК с включённым Happ**. Не подменять его прежним PC alias, другим профилем Happ, ноутбучным ключом или автоматически выбранным адресом `83.217.213.181`.

**Наблюдения, объясняющие смену маршрута:** до переключения VPN-узла оба IP шли через `happ-default-tun`, но SSH banner не доходил; на «Основной 2» (VLESS / WS / TLS) для `212.193.14.116` отдельный TCP-пробник однажды получил `SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.18`, а полноценный SSH затем дал timeout/255. После переключения на **«Основной 1»** полноценный SSH на `212.193.14.116` прошёл с кодом 0. Приветствие на `83.217.213.181` через предыдущий VPN-узел не пришло. **Корневая причина нестабильного SSH на других VPN-узлах не доказана**. Не повторять всю сеть диагностических тестов ради этого маршрута.

**Границы:** не менять Happ/маршрутизацию/SSH config/host keys/ключи/sshd автоматически; секреты не публиковать. Рабочий SSH не разрешает VPS update, STOP/START, PAPER, Robot/Scanner, admission или LIVE. Сопряжение `owner-pc` остаётся `UNPROVEN`; одноразовый `provision-owner-pc` не повторять без отдельного доказанного protected preflight. При отключённом Happ использовать отдельно подтверждённый маршрут §1, без смешения условий приёмки.

## 1. ГЛАВНЫЙ, АКТУАЛЬНЫЙ, РАБОЧИЙ — основной ПК Windows (17.11.2026)

**Состояние: VERIFIED SSH_OK (17.11.2026) при Happ/VPN OFF; при Happ/VPN ON см. более новую приёмку §0.** Устройство: основной ПК, пользователь Windows \`C:\Users\svobo\`, обычный PowerShell. **Happ/VPN выключен для этой подтверждённой сессии** (условие подтверждённой приёмки, не утверждение о невозможности других режимов). Цель: \`root@83.217.213.181\`. Существующий ключ **именно основного ПК**, а не ноутбука: \`$env:USERPROFILE\.ssh\bybitscanner_vdsina_gateway_20261030\`.

\`\`\`powershell
ssh -i "$env:USERPROFILE\.ssh\bybitscanner_vdsina_gateway_20261030" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 root@83.217.213.181 'echo SSH_OK; hostname'
"SSH_EXIT_CODE=$LASTEXITCODE"
\`\`\`

**Полученный владельцем вывод 17.11.2026:**

\`\`\`text
SSH_OK
v3286418.hosted-by-vdsina.ru
SSH_EXIT_CODE=0
\`\`\`

**Правило исполнителю:** при **Happ/VPN OFF** для подключения с основного ПК начать отсюда; при **Happ/VPN ON** использовать проверенную комбинацию из §0. Не предлагать сначала \`bybitscanner-vps\`, \`212.193.14.116\`, прямой ключ Codex Desktop на этот адрес, новые IP, агент, ключи, VNC или обходы. Не переключать Happ автоматически, не править маршрутизацию/ACL/sshd. Если рабочая сессия уже есть, использовать её для одной ограниченной авторизованной задачи, без повторных SSH-проб. При включённом Happ есть отдельно подтверждённый SSH-маршрут §0 — не требовать выключить VPN по умолчанию. Успех SSH — **только доступ**, не разрешение на STOP/START/обновление/торговлю.

**Текущее ограничение:** успешна ровно одна подтверждённая сессия 17.11; долговременная стабильность не доказана. Последующее сопряжение \`owner-pc\` и relay Backend **не проверены** одним лишь SSH_OK. Проверять bridge read-only, не повторять неоднозначный \`provision-owner-pc\` без protected preflight.

## 2. ИСТОРИЧЕСКИЕ АЛЬТЕРНАТИВЫ И НЕУДАЧНЫЕ ПРОБЫ — основной ПК (до приёмки §0)

### 2.1. НЕ ИСПОЛЬЗОВАТЬ КАК ОСНОВНОЙ: alias \`bybitscanner-vps\`

Ранее был проверен 14.11.2026 на ПК с Happ/VPN ON: \`SSH_OK\`, правильный hostname, код \`0\`. Направляет на \`212.193.14.116\` с ключом \`bybitscanner_vdsina_gateway_20261030\`.

**Результат ранних проверок 17.11 (до нового успешного VPN-профиля §0): TIMEOUT** — \`Connection timed out during banner exchange\`, \`SSH_EXIT_CODE=255\`. Это исторически успешный, но **сейчас второстепенный/заблокированный** маршрут. Не выдавать как «главный» на основании старого доказательства.

Историческая команда (для идентификации, **не выполнять первой**):

\`\`\`powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 bybitscanner-vps 'echo SSH_OK; hostname'
"SSH_EXIT_CODE=$LASTEXITCODE"
\`\`\`

### 2.2. НЕ ИСПОЛЬЗОВАТЬ КАК ОСНОВНОЙ: явный \`212.193.14.116\` из Codex Desktop

Ранее успешно проверен 15.11.2026 в **Codex Desktop** на основном ПК с Windows OpenSSH \`C:\Windows\System32\OpenSSH\ssh.exe\`, \`-F none\`, ключом \`C:\Users\svobo\.ssh\bybitscanner_vdsina_gateway_20261030\` и адресом \`root@212.193.14.116\`: \`SSH_OK\`, код \`0\`. Это был отдельный execution context, не native PowerShell alias.

**Повторная проверка 17.11 с тем же адресом и ключом: НЕ РАБОТАЕТ** — \`banner exchange timeout\`, \`255\`. Перепроверять ключи и alias вместо выбора маршрута §1 запрещено. Для Codex Desktop **не считать** успешный native-PowerShell доступ автоматическим доказательством доступа из его sandbox: использовать утверждённый маршрут §1 в доступной Windows host execution boundary и отдельно подтвердить успешное выполнение, без перемены host key policy.

Архивная команда для сопоставления прежнего поведения (не первый выбор):

\`\`\`powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' -F none -i 'C:\Users\svobo\.ssh\bybitscanner_vdsina_gateway_20261030' -o IdentitiesOnly=yes -o BatchMode=yes -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 root@212.193.14.116 'echo SSH_OK; whoami; hostname'
"SSH_EXIT_CODE=$LASTEXITCODE"
\`\`\`

### 2.3. Диагностика 17.11, не повторять как новый поиск

- \`Test-NetConnection 212.193.14.116 -Port 22\`: \`TcpTestSucceeded=True\`, \`InterfaceAlias=happ-default-tun\`, \`SourceAddress=10.6.7.1\`.
- Отдельный \`TcpClient\` read получил \`SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.18\`. Это **не** успешный SSH login.
- \`ssh -vv\` на \`212.193.14.116\`: \`Connection established\`; отправлено \`Local version string SSH-2.0-OpenSSH_for_Windows_9.5\`; удалённое SSH-приветствие в той сессии не получено до timeout.
- Дополнительный HTTPS probe другого исполнителя закончился TLS handshake timeout, без HTTP-ответа. **Первопричина этих отдельных сбоев не доказана** (нельзя называть VPS сломанным или VPN первопричиной).
- \`provision-owner-pc\` UUID \`481e7aa30fcb4be0aa5554d2da0003e3\`: \`STATUS_UNPROVEN\`. Отсутствие UUID в текущем списке transient systemd units не доказывает, что операция не запускалась. Повторное provision вслепую запрещено.
- **STOP RULE:** уже выполненные проверки TCP, banner, \`-vv\`, alias, прямого адреса и ключа **не повторять**. Зафиксировать последнее реальное свидетельство, работать через §1. Без новых доказательств не переходить к VNC и не менять sshd/Netplan/VPN/ключи.

## 3. ДРУГОЕ УСТРОЙСТВО: ноутбук Windows (\`C:\Users\SVOBODA21\`)

**Не путать с основным ПК.** Исторически и независимо 15–16.11.2026 подтверждался \`root@83.217.213.181\` с ключом ноутбука \`C:\Users\SVOBODA21\.ssh\bybitscanner_laptop\`. Это маршрут **для ноутбука**, а не основание подставить ноутбучный ключ на ПК.

\`\`\`powershell
& 'C:\Windows\System32\OpenSSH\ssh.exe' -i 'C:\Users\SVOBODA21\.ssh\bybitscanner_laptop' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 root@83.217.213.181 'echo SSH_OK; hostname'
"SSH_EXIT_CODE=$LASTEXITCODE"
\`\`\`

Наблюдался \`Permission denied (publickey,password)\` при остановленном \`ssh-agent\` (\`Stopped/Manual\`); после однократного разрешённого \`Start-Service ssh-agent\` уже загруженная identity стала доступна, а SSH вернул \`SSH_OK\`, код 0. Это относится **только к ноутбуку**. Не менять StartType, ACL, не сохранять passphrase. Если ноутбучный agent отсутствует/ключ не загружен, остановиться без перебора ключей.

### Исторический ноутбучный Telegram reverse tunnel (27.10; не управление ПК)

Для старой схемы Xray SOCKS5 на ноутбуке \`127.0.0.1:10808\` → VPS \`127.0.0.1:10809\` применялся отдельный долгоживущий канал:

\`\`\`powershell
ssh -i "$env:USERPROFILE\.ssh\bybitscanner_laptop" -o IdentitiesOnly=yes -o PasswordAuthentication=no -o ExitOnForwardFailure=yes -N -R 127.0.0.1:10809:127.0.0.1:10808 root@83.217.213.181
\`\`\`

Он **не заменяет** обычный SSH и не является действующим обязательным способом доставки Telegram. Исторические факты приёмки хранятся в соответствующем Telegram runbook.

## 4. Android / Termius / VDSina

Termius на телефоне использовался владельцем для просмотра VPS; это **не** проверенный сегодня способ с основного ПК и не лицензия на изменение runtime. Ключи/публичные fingerprints из иных заметок не подменяют SSH identity основного ПК. Провайдерская VDSina console/VNC — только с отдельным решением владельца при настоящем блокере всех доступных подтверждённых путей, а не типовой шаг при timeout на §2.

## 5. История сетевого инцидента и технические детали (для сохранения контекста, НЕ инструкции на сегодня)

- VPS VDSina Ubuntu 24.04; hostname \`v3286418.hosted-by-vdsina.ru\`; исторический адрес \`83.217.213.181\`, позднее дополнительно выделен IPv4 \`212.193.14.116\`. Добавочный адрес платный и **не является необходимым** для подтверждённого подключения 17.11.
- 08–11.11: в сети с Happ/TUN прямой TCP к новому адресу мог быть доступен, но SSH banner задерживался. VDSina показывал \`Your IP address is blacklisted!\` при другом выходном IP; причина сетевых ограничений осталась гипотезой.
- Дополнительный IPv4 был добавлен к \`ens3\` без restart, затем закреплён в Netplan с сохранением исходного default gateway. Этим объяснялся старый успех подключения, **не** сегодняшняя приоритетность адреса.
- 11.11 основной ПК, **VPN OFF**, старый адрес \`83.217.213.181\` и ключ \`bybitscanner_vdsina_gateway_20261030\` уже давали \`SSH_OK\`, код 0. После включения VPN следующая read-only команда снова дала banner timeout. 17.11 подтверждён **тот же рабочий маршрут**.
- Если позднее при SSH выполнении удалённой команды появится \`PAPER_unit_not_stopped\`, необходима отдельная защищённая проверка четырёх units, release identity и receipts; это другая проблема, которую нельзя исправлять переключением SSH/IP или повтором STOP. Ранее наблюдавшиеся \`STOP\` receipts и SHA в старых инцидентах не являются текущей приёмкой.
- Корректный код возврата SSH должен быть \`0\` и ожидаемый \`SSH_OK\`. Нет прав на PAPER/DB/LIVE от одного успешного соединения. Запрещены SQL, обход Admission/STOP/TAKE, правки env вручную, слепой \`provision-owner-pc\`, изменение SSH fingerprints и публикация private key.

**При любых противоречиях с другими документами об SSH:** текущая команда/статус **§1** имеют приоритет. Исторические разделы в иных файлах — архив причин/ошибок, **не альтернативные способы входа**.
