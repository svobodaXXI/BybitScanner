# PAPER VPS — восстановление 2026-11-01: итог, блокеры и быстрый путь

Status: **RECOVERED по отчёту оператора Codex**, не независимый аудит VPS и не доказательство закрытого PnL-цикла.
Scope: только PAPER, исторический эпизод BUSDT; LIVE запрещён. Это runbook и postmortem, **не** инструкция повторять одноразовый SIGINT. Текущий runtime всегда сверять заново.

## 1. Доказанный результат (отчёт Codex после восстановления)

- Installed exact release `86fda079cebb1139c2dd3b1e48990d5c8212f79a` (PR #739 входит).
- PAPER DB identity `e0cbafb1c172b65f2db3a2c7cef2636b4164a4b1a229bd183bd907e7984ff0ad`, integrity `OK`, идентичность сохранилась. Проверены 1745 tracked blobs target перед переключением, mismatch = 0; DB, конфигурация, venv, runtime-файлы и бэкапы сохранены.
- BUSDT STOP obligation: **RESOLVED** штатным reconciliation; 6 executions, прежний fingerprint, второго STOP нет. Незавершённых obligations, LIMIT и Market-команд: 0.
- Backend active PID 604104; Telegram active/ready PID 604975, DB identity совпадает; Robot `ROBOT_RUNNING / READY`; Scanner `SCANNER_RUNNING`; Autopilot `PAPER_AUTO`; Admission READY; protection HEALTHY.
- После восстановления Scanner создал PAPER LONG AIOUSDT qty 8100: позиция синхронизирована, coverage `EXPOSURE`, protection HEALTHY. **Это новая открытая позиция, не завершённый торговый цикл**; никакого вывода о чистом PnL. LIVE не затронут.
- Важно: `RECOVERED` — результат переданного пользователем отчёта Codex; по этой записи не утверждать, что состояние сохраняется на момент нового запуска.

## 2. Цепочка блокеров — симптомы, причина, безопасная развязка

| Этап / наблюдение | Причина или точная граница доказательства | Вывод на будущее |
| --- | --- | --- |
| Robot `RECONCILIATION_REQUIRED`, BUSDT STOP `DISPATCHING`, при FLAT/0 | Durable obligation не может быть стёрта по признаку отсутствия позиции; потребовалось исправление ownership/reconcile (#731) на новом release | Не редактировать SQLite, не повторять STOP; сохранять executions/fingerprint и выполнять canonical reconcile после обновления |
| Действующий старый backend без `/api/health.build_sha`, `BYBITSCANNER_BUILD_SHA` UNSET | Marker SHA в папке не доказывает SHA загруженного Python-процесса; отсутствует обычная аттестация исполняемого release | Деплой обязан давать проверяемую provenance; для *этого* legacy PID был создан узкий одноразовый контракт #738, не универсальный обход |
| Первый transition: `tools.runtime_intent.Unreachable: timed out` | Повторный HTTP API snapshot выполнялся под `BEGIN IMMEDIATE` SQLite writer reservation и мог ждать собственный writer slot backend; сигнал ещё не был отправлен | #739 перенёс все HTTP reads **до** writer barrier; внутри только durable proof, PID/starttime и один разрешённый сигнал. Не делать HTTP/API внутри writer lock |
| Второй transition: `BLOCKED: backend_unit_not_active` **после SIGINT** | Post-signal polling вызывал `_service_pid()`, которая требует `ActiveState=active`. Уже завершившийся процесс ошибочно классифицировался как blocker | **Остающийся дефект кода**: post-action outcome должен независимо классифицировать `EXIT_OBSERVED` по PID/starttime и отсутствию listener; состояние `inactive/failed` после разрешённого сигнала не равно «сигнал не отправлен» |
| После SIGINT старый PID 500879 отсутствует, MainPID 0, порт 8765 свободен | Несмотря на ответ BLOCKED, подтверждённое состояние изменилось; STOP был однократным | Никаких повторов SIGINT/transition. Продолжать с **доказанно остановленным** backend, а не с исходной точки |
| Во время установки target все 1745 tracked blobs совпали; но `reset-failed` для Telegram и PAPER-start → `Unit ... not loaded` | Сбой порядка service-unit load / reset-state; `daemon-reload` затем показал units загруженными | **Остающийся дефект orchestration**: порядок `install unit → daemon-reload → load verification → reset-failed (если нужен) → start`; `reset-failed` — служебное действие, его ошибку нельзя выдавать за нарушение защиты без проверки фактических units |
| Backend и Telegram после переключения inactive, но DB intact | Предыдущее строгое «при любой ошибке — BLOCKED» прервало продолжение на вспомогательной systemd-команде | Fail-closed для неизведанной safety-ошибки; для доказанного неопасного ordering-сбоя — одна локальная проверка фактического состояния, затем продолжение того же разрешённого пути |
| Recovery после исправления порядка systemd | Запуск только PAPER backend → один canonical BUSDT reconcile → только затем Robot READY, Scanner, PAPER_AUTO, Telegram, Admission/protection | На этом эпизод завершён успешно; допустимость новых входов определяется текущими protective gates, не фактом успешного старта |

Нельзя смешивать *причины, установленные кодом*, с гипотезами: deadlock соответствует найденному вызову `get_snapshots()` внутри writer barrier и исчез из #739, но внешний runtime-таймаут сам по себе не является трассировкой SQLite locks; ошибочный post-signal `_service_pid()` доказуем по текущему исходнику. Причина `Unit not loaded` установлена на уровне последовательности состояний systemd, не подтверждён root cause происхождения выгрузки units.

## 3. Канонический recovery-путь — ветвление по текущему состоянию

**Сначала один снимок фактов:** approved exact stable SHA; установленный release/content; systemd MainPID + cgroup/команда + process starttime + локальный LISTEN fd; DB identity и SQLite integrity с WAL; резервная копия через SQLite backup API; positions/exposure, active LIMIT/Market, durable candidates, STOP/TAKE obligations + execution fingerprint; protection roles, Robot/Scanner/Autopilot/Admission; Telegram identity. Переиспользовать неизменившиеся PASS. Сигнал, deploy или новые входы не предлагать до соответствующего gate.

1. **Backend active + protected exposure / unresolved unknown:** обычный owner-safe-stop/reconcile по действующим контрактам; не применять принудительный stop. `FLAT` должен включать отсутствие скрытых pending orders и обоснование stale coverage. Для ambiguous result — STOP и точная новая улика.
2. **Backend active + официальный FLAT gate PASS + canonical stop реально заблокирован:** допускается только отдельный, актуальный, явно разрешённый и строго ограниченный exceptional contract. Не переиспользовать `--legacy-unversioned-20261031` для нового PID, процесса или incident. Проверки по immutable PID/starttime, process_instance_id, systemd/cgroup/listener и DB identity должны оставаться точными; только один разрешённый pidfd сигнал. Вся HTTP-аттестация ДО SQLite writer reservation. Backend может завершиться в `failed/inactive`: outcome измерять по состоянию процесса, не считать `ActiveState != active` доказательством отказа до сигнала.
3. **Backend уже отсутствует, порт свободен:** не выполнять transition и не сигналить снова. Подтвердить DB и отсутствие конкурентного runtime, затем по существующему штатному release-switch пути установить exact approved SHA с сохранением конфигурации, venv, DB/WAL и бэкапов. Для release без `.git` не применять `git merge --ff-only` внутри installed tree; использовать проверенный immutable-artifact/staging механизм, с content SHA verification до переключения.
4. **Перед запуском:** проверка unit files, `daemon-reload`, явная проверка загрузки нужных units, затем узкий `reset-failed` только если нужен, затем start. Если служебная команда завершилась неудачно, подтвердить **реальное** состояние units перед решением о повторе, не запускать blind retries.
5. **Backend PAPER поднят, admission ещё закрыт:** выполнить canonical reconciliation ровно в предусмотренных условиях; подтвердить BUSDT `RESOLVED`, executions/fingerprint неизменны, 0 unfinished obligations и active Market/LIMIT. Не открывать Scanner/Autopilot при неразрешённом STOP или отсутствии protection evidence.
6. **Только при READY + HEALTHY:** запустить/подтвердить Robot, Scanner, Autopilot PAPER_AUTO и Telegram, единый DB identity, backend build identity, Admission; проверить protection каждой открытой позиции и STOP/TAKE. Уже возникшее новое exposure нельзя трактовать как FLAT или безопасно остановить без нового штатного safety gate.
7. **Финал:** результат в одном кратком отчёте: exact SHA, DB identity + integrity, obligations/executions fingerprint, positions/STOP/TAKE, runtime readiness, Telegram, LIVE-safe, а также факты нового PAPER fill/exit. `RECOVERED` только после фактических evidence; отдельно подтверждать закрытый цикл и net PnL.

## 4. Правила предотвращения повторения

**Нельзя ослаблять:** PAPER-only; STOP/TAKE coverage; admission/reconciliation; никакого direct SQLite mutation; никаких повторных STOP/Market; никакого сигнала по одному PID без starttime/process/systemd provenance; никаких `kill -9`, обхода gates или повторного исполнения ambiguous action.

**Engineering defects, требующие отдельного узкого исправления, не препятствующие нынешнему RECOVERED при подтверждённой защите новой AIOUSDT позиции:**
- [ ] Исправить post-SIGINT result classification: `_service_pid()` не должен требовать active unit, когда он уже наблюдает успешное завершение. Обеспечить различение `EXIT_OBSERVED`, `NO_SIGNAL_SENT`, `SIGNAL_SENT_OUTCOME_UNKNOWN`; не скрывать `SIGINT sent` за общим `BLOCKED`. Синтетические тесты на смену `active → failed/0`, pid gone/listener gone, PID reuse и timeout. **Не менять безопасную pre-signal аттестацию.**
- [ ] В штатном release orchestration сделать проверяемый порядок загрузки systemd units после staging/activation; `reset-failed` только после `daemon-reload` и проверки unit load. Независимо классифицировать ошибку служебной команды и фактический safety gate; тест на `not loaded → daemon-reload → loaded`. Не добавлять произвольный retry loop.
- [ ] В обычном деплое обеспечить runtime `build_sha` и аттестацию exact immutable content без reliance на marker файловой системы; предотвратить повторение unversioned legacy exception.
- [ ] Поддерживать canonical atomic/recoverable release-switch для deployment tree без `.git` и с сохранением user-owned runtime + DB/WAL; предусмотреть resume checkpoint после фактически выполненного шага, чтобы одна вспомогательная ошибка не заставляла повторять сигнал или всю процедуру.
- [ ] Для change с lifecycle signal + writer barrier проверять **post-action** контракт и отсутствие network/API call под held SQLite write lock до runtime handoff.
- [ ] Один разрешённый end-to-end операторский запрос, минимальный обязательный proof, без повторных owner approvals на неизменённые границы. Каждое следующее действие зависит от **observed host state**, а не только от return code предыдущей команды.

Эти пункты — **долг кода/оркестрации**, не реализованные изменения. Не выдавать их за исправленные лишь потому, что текущий хост RECOVERED. Приоритет новых исправлений определяется фактическим риском и владельцем; не прерывать защищённый PAPER runtime ради профилактики.

## 5. Результат и источники

Incident run: PR #731 (BUSDT owner/reconcile), #738 (точечная unversioned identity), #739 (HTTP outside SQLite barrier); stable `86fda079cebb1139c2dd3b1e48990d5c8212f79a`. Фактические стадии BLOCKED и итог RECOVERED — последовательные отчёты VPS-оператора, предоставленные владельцем 2026-11-01. Подтверждение итогового RECOVERED не означает, что любой другой VPS/release безопасен для аналогичного exceptional handoff.
