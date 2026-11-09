# Единый автономный PAPER-контур: план внутренней консолидации

Статус: **действующий минимальный контракт монолита, не акт приёмки**. Исходное решение 2026-10-27; актуализировано по VPS-доказательствам 2026-11-06.
Ветка реализации: `stable/adfb50b-forward`. Один адресный PR только при доказанной необходимости; merge и VPS-операции — по отдельным разрешениям.
Связанные задачи: #649 (существующая кнопка аварийного закрытия), #646 (переиспользование), #645/#648 (MIRROR, merge выполнен; VPS-приёмка не завершена), #592 (Wedge reentry после MIRROR).

## 1. Измеримый результат

Владелец управляет **одним PAPER-контуром** через существующие Telegram / Terminal / штатный запуск и остановку; сам не проверяет вручную systemd, процессы, порты, разные БД, статусы каждого модуля или расхождение загруженного кода. Проверка готовности, владения, защиты, восстановление и диагностика происходят внутри действующего контура.

**Инварианты:** LIVE запрещён; один PAPER account / одна авторитетная PAPER DB; никакого второго Robot / исполнения ордеров; Scanner, Autopilot, Admission, PaperRuntime и STOP/TAKE сохраняют существующие контракты. Работающий VPS, позиции и БД нельзя менять без отдельного разрешения владельца. Слова `READY`, `FLAT`, `CLOSED` требуют текущего доказательства, а не HTTP 200 / systemd active.

## 2. Выявленный разрыв и существующая архитектура

Текущая Telegram-кнопка `robot:cmd:close_all` существует в `robot_telegram_feed.py`: Telegram update принимает `telegram_monitoring.py`, делегирует `telegram_review._process_callback`, подтверждение `close_all_confirm` вызывает `terminal.application.robot_control.close_all_now()`; транспорт `telegram_review._post_robot_close_all_now` направляет запрос на `/api/robot/close-all-now`, далее `PaperRuntime.robot_close_all()`. Отдельный `/api/close-all` направляет в `PaperRuntime.close_all()`. Это два разных контракта владения: их нельзя механически смешивать.

Инцидент VPS 2026-10-27: три PAPER SHORT (FILUSDT, MELANIAUSDT, SPXUSDT); `PAPER_AUTO` включён; `POST /api/robot/close-all-now` ответил `not_found`; серверный Python-процесс стартовал до изменения файлов на диске. **Причина несовпадения запущенного обработчика не доказана**, результаты закрытия не подтверждены. Прямое изменение SQLite, слепой повтор POST, перезапуск при неизвестной экспозиции запрещены.

## 3. Целевая модель: переиспользование существующего монолита

**Результат, а не новая инфраструктура.** Одна разрешённая операция через существующий owner entrypoint должна довести PAPER до доказанного результата или сообщить **конкретный** `BLOCKED`. Не строить второй coordinator, отдельный recovery-сервис, шину, workflow engine, дополнительную БД, статусную машину, публичный API, UI или новые кнопки. Никакого «по одному инцидентному скрипту на каждый STOP».

**Существующие полномочия сохраняются:** `PaperRuntime` единолично владеет торговыми изменениями; Scanner — сигналами, Autopilot — решениями, Admission — разрешением новых входов, protection — STOP/TAKE, systemd — запуском и состоянием процессов, Telegram/Terminal — интерфейсами. Переиспользовать `tools/paper_maintenance.py`, `tools/stop_robot_runtime.py`, существующие Gitless installer/resume и уже защищённые receipts. Не копировать одни и те же trading/FLAT/identity predicates в новый параллельный контур; использовать единые авторитетные проверки там, где это реально возможно, и устранить **доказанные** расхождения между ними.

**Источником состояния служит фактический процесс, PAPER DB и защищённый журнал.** Не вводить speculative STARTING/TRADING/FLATTENING enum и дополнительные статусные таблицы. `healthy`, HTTP 200, `systemd active`, `SCANNER_STOPPED` или пустые покрытия по отдельности не доказывают safe-stop. `APPROVED` не равен автоматически активному ордеру, но считается инертным только при строгой независимой сверке исполнений и отсутствия владения.

## 4. Только необходимые свойства и критерии

| Необходимое свойство | Минимальная реализация в существующем коде | Доказательство |
| --- | --- | --- |
| Одна операция | Сверка фактической фазы → исполнение только оставшихся законных переходов | Не вызывает повторно уже завершённый Robot STOP или неопределённый POST/SIGINT |
| Безопасная остановка | Freeze ingress; сохранить Backend и STOP/TAKE при экспозиции; единый строгий proof FLAT, кандидатов, ордеров, команд и obligations | Изменение только после подтверждённой quiescence, неизвестность означает BLOCKED |
| Crash recovery | Переиспользовать корневые fsync receipts, точные SHA, PID/starttime/listener/cgroup и transaction journal | Нет повторного необратимого действия и нет release switch по одному лишь STOP intent |
| Развёртывание | Существующий Gitless installer проверяет остановленные сервисы и tracked files; запуск Backend/Telegram только в EDITOR_ONLY | Точный работающий SHA, identity и доступность редактора; Scanner/PAPER_AUTO не запускаются |
| Диагностика | Сохранять первопричину и последнюю доказанную фазу в ответе существующей операции | Один actionable BLOCKED вместо цепочки ручных SSH-команд |

**Отдельная операция Close-All — не часть монолитного update.** Существующие Robot-only `/api/robot/close-all-now` и account-wide `/api/close-all` имеют разные полномочия. Запрос обновления/остановки **не** разрешает Market/Close-All или расширение торговой семантики; не объединять их ради единой кнопки.

**Не создавать заранее:** универсальный журнал событий, новые correlation-ID схемы, телеметрию/дашборды, watchdog, перезапуск `Restart=always`, обобщённую платформу orchestration или разветвлённые фазы PR. Использовать уже существующие журналы и метрики. Добавлять что-либо только при доказанной невозможности получить целевой результат существующим кодом.

## 5. Кратчайший маршрут реализации

Владелец ждёт **работающий Backend/Telegram в EDITOR_ONLY и реальную приёмку Telegram → Редактор**, а не очередные промежуточные задачи. По текущему инциденту: один согласованный кодовый фикс на **узкой доказанной границе** → адресные регрессии → PR/обязательный CI → отдельно разрешённый merge и защищённое продолжение текущей операции на VPS → наблюдаемая браузерная/Telegram приёмка. Если fix не нужен — не делать PR.

Не повторять законченные slices, не дробить одну остановку на квесты, не требовать у владельца ручной верификации каждого сервиса. Любой исход после неопределённого STOP/POST/SIGINT остаётся **запрещением повтора**, а не «идемпотентным retry». Сохранять старые защищённые receipts и разрешённые объёмы операций. LIVE запрещён; неизвестные PAPER obligations/exposure не обходить.

История уже объединённых узких рефакторингов и их границы остаётся в §7; P0 orchestration и реальные evidence — в §8–10.

## 6. Verification gate

Для одного доказанного изменения: минимальный scoped diff → адресные регрессии → обязательный CI → review → merge только по явному разрешению → deployment на VPS только по отдельному разрешению и доказанному безопасному runtime. Тесты в isolated temp DB не равны живой PAPER-приёмке. Исторические данные/открытые позиции не менять; XP/достижения за код, тесты или документы не начислять.

---

## 7. Реализация и сохранённые границы — 2026-10-28

Уже объединено в `stable/adfb50b-forward`: #650 (общий HTTP-транспорт
Telegram Robot), #651 (общий список разрешённых состояний Close-All),
#652 (сверка оставшейся Robot-экспозиции), #653 (стабильная идентичность
PAPER Market для повторного **того же** Close-All запроса).

Текущий ограниченный slice #649: **повторная доставка того же Telegram
`callback_query.id`** передаёт тот же существующий `client_action_id`
в `/api/robot/close-all-now` через необязательный внутренний аргумент.
Для остальных вызывающих сторон действует прежний clock-derived ID.
Новые подтверждающие нажатия имеют новые ID; пользовательский интерфейс,
имена REST-маршрутов, структура JSON, режимы Admission/Robot и правила
открытия/закрытия не меняются. Это намеренное узкое усиление
идемпотентности идентификатора, не перепроектирование торговой стратегии.
Один callback может быть переотправлен Telegram после сбоя; этот replay
не должен создавать новую идентичность ордера.

**Обязательная архитектурная оговорка:** действующий
`AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md` §4 прямо требует, чтобы
`close_all_now()` **не менял** READY/PAUSED и не затрагивал ручные позиции.
Поэтому включение PAUSE, отмены новых входов и account-wide flatten в
одну кнопку (предложено выше как целевое состояние) **не реализуется
внутренним рефакторингом**. Это отдельное изменение торгового поведения,
для которого нужны обновлённое решение владельца, контракт, тесты и
безопасная эксплуатационная приёмка. Требование запрета новых входов
пока выполняется через существующую независимую команду PAUSE.

Не реализовано и не заявляется: долговременный Close-All coordinator,
дедупликация **различных** подтверждений после тайм-аута,
возобновление незавершённой кампании, исправление ошибочного VPS route
`not_found`, автоматическое закрытие трёх ранее открытых PAPER-позиций,
автоматическое включение или изменение PAPER_AUTO, развёртывание на VPS.


## 8. P0 — orphan Robot-trade при Flat: обязательная граница монолитной остановки (01.11.2026)

**Runtime evidence (owner-supplied, 23:27 MSK, installed f100ef369a1105443332b5729b558464c27be48f):** JASMYUSDT authoritative PAPER position is Flat after Sell/Buy executions, but a durable Robot trade remains OPEN with STOP/TAKE. Four *other* symbols still have protected exposure (CELO/DJT/ICP/SENT); eight LIMIT orders, fourteen APPROVED candidates, Scanner RUNNING and PAPER_AUTO enabled. Protection healthy does not imply quiescent. Exact JASMY fill/owner/exit-reason attribution has NOT yet been proven. Do not declare the orphan resolved.

**Unified-stop owner contract:** Existing canonical shutdown and account-wide Close-All are distinct from Robot-only close_all_now; preserve their authority and all existing URLs/buttons. Before any action that could drop local STOP/TAKE protection, an internally coordinated preflight must correlate **authoritative positions, every OPEN Robot trade, OPEN candidates, active entry/exit LIMIT, unresolved commands/obligations and pending admissions** by account/symbol and immutable candidate/trade/execution IDs. Flat+OPEN-trade is a real **ledger discrepancy**, never a successful FLAT/quiescent attestation. Do not infer a completed trade, fill economics or exit reason from net Flat alone. A symbol may be net Flat while multiple offsetting fills and candidates remain unresolved.

**Safe resolution gate:** Reuse the existing evidence-based completion paths in PaperRuntime.robot_reconcile (BOX ownership, durable manual Close-All intent or the strict `robot_flat_closure.prove_flat_closure` emergency attribution) **only if all respective predicates are satisfied**. For JASMY, first obtain a bounded READ-ONLY forensic record of full symbol executions, entry order ownership, trade/candidate state, linked protection, projection versions and exit intent. If no existing predicate applies, develop one narrowly justified proof in GitHub with idempotent atomic state transition and per-fill fee/PnL provenance; do not generalize emergency evidence to ordinary STOP/TAKE or manual closes. Uncertainty => BLOCKED with exact orphan trade_id and missing evidence. Never manually mutate SQLite, fabricate an exit, repeat Market, force-close, or run reconcile merely to make a deploy possible.

**Stop orchestration / acceptance (not implemented by this document):**
1. Before flattening, separate the **explicitly authorized** stop/close command from any operational preflight; freeze new admission/Autopilot entry dispatch only through a legally permitted owner command, never as an undocumented side effect or an inferred permission. Existing protected exposure must retain active protection while unsafe to switch.
2. Resolve or block every Flat+OPEN-trade orphan and every contradictory candidate/trade ledger entry before reporting completion. Failures may be isolated per symbol for diagnostics, but **do not** report global stop success while any orphan, exposure, entry/exit LIMIT, obligation, in-flight command or capacity for new entries remains. A pending candidate alone may be invalidated only by its canonical legal transition.
3. Prove quiescence from a fresh consistent post-action state (same PAPER DB/process identity, authoritative FLAT for all symbols, **zero OPEN Robot trades и active кандидатов с правом входа** (инертные APPROVED — только по строгому proof), zero active LIMIT, commands and unresolved obligations, no new admissions); verify backend/Telegram/process ownership. If any asynchronous state changes during the proof, restart a read-only preflight rather than treating a stale snapshot as terminal evidence.
4. Only after separate owner deploy authorization and canonical safe-stop may immutable release staging and switch proceed. No hot-swap while protection continuity is unproven; no LIVE.
5. Required regression matrix: JASMY-like Flat+OPEN orphan; matching Box/manual/emergency completed fill with strict provenance; missing exit marker; duplicate/tied timestamps; overlapping entry orders/partial fills; new PAPER_AUTO admission racing with stop; active exit LIMIT; unresolved STOP obligation; idempotent retry after partial stop; preservation of healthy protection under BLOCKED. All assertions use isolated fixtures, not production DB.

**Observed status:** mechanism still incomplete; JASMY forensic proof and end-to-end unified-stop acceptance PENDING. Keep this in the same P0 shutdown/deploy queue; not a separate trading feature. XP cannot be awarded for a document or green CI.

### 05.11.2026: защита от повторного `protection ingress_overflow` внутри START

READ-ONLY VPS evidence: Robot `ROBOT_RUNNING / RECONCILIATION_REQUIRED`, `PAPER_AUTO`
настроен, но Admission NOT READY; Protection HEALTHY. Причина
`ROBOT_PROTECTION_COVERAGE_LOST symbol=MSTUUSDT reason=ingress_overflow`;
event `MSTUUSDT:190402711884:3824963`, очередь `64/64`, max latency `2356ms`,
самый медленный owner callback Autopilot `1436ms`.
Кандидат MSTUUSDT `d6223996117e1f7b4aab5ffa` — APPROVED/RETEST_DETECTED,
без привязанного trade/fill/entry order или активного LIMIT.
Открытые позиции/trades, unfinished commands, LIMIT и obligations — 0;
FOLKSUSDT/LITEUSDT покрыты как ENTRY_PENDING. Это **новый эпизод класса
ingress_overflow**, не повтор JASMY/FLOW.

Узкий путь внутри **одной явно разрешённой штатной команды START**:
проверить точный running SHA, DB и LIVE isolation; штатными OFF/Scanner STOPPED
заморозить ingress, не останавливая Backend/MIRROR/защиту; доказать FLAT,
отсутствие незавершённых владельцев и **два спокойных замера текущей + 60-секундной
очереди**. Исторические high-watermark не считать текущей загрузкой. Затем
один canonical `/api/robot/reconcile` с долговременным no-replay receipt;
только из подтверждённого PAUSED — штатный runtime intent ROBOT → READY,
после чего при сохранённой безопасности вернуть Scanner и авторизованный
PAPER_AUTO. Любая ошибка/неизвестный результат: `BLOCKED`, Admission закрыт,
Backend и STOP/TAKE сохранены. Не подменять причину простым restart и не
превращать эту процедуру в отдельную ручную операцию. Реальная VPS-приёмка
не следует из CI/PR и требует отдельного разрешения владельца.

## 9. P0 — монолитная остановка/обновление без повторов (владелец: 02.11; уточнено 06.11)

**Один owner end-to-end outcome:** безопасно довести PAPER до EDITOR_ONLY для приёмки редактора. Freeze/drain/proof/STOP/deploy — *внутренние зависимые действия*, не ручные подзадачи и не отдельные квесты. При невозможности — один точный BLOCKED с безопасно сохранённым Backend и журналом. Ни этот текст, ни merge PR не дают runtime/market/LIVE полномочий.

**Минимальная последовательность при наличии отдельного разрешения:**

1. Сверить работающий SHA/process instance, DB identity, действующие полномочия, ledger (позиции, trades, candidates, LIMIT, команды, obligations/checkpoints), Scanner, Autopilot, protection и прежние receipts. Не основывать решение на устаревшем снимке.
2. В уже начатой операции **наблюдать фактическую фазу**, а не безусловно запускать всю цепочку. Если Robot `ROBOT_STOPPED`, Scanner `SCANNER_STOPPED` и Autopilot `OFF`, эти мутации повторно не выполнять. Не повторять неопределённые reconcile/STOP/POST/SIGINT.
3. Если есть реальная экспозиция — оставить Backend/STOP/TAKE и ждать законного естественного drain, иначе BLOCKED. Market/Close-All и отмены торговых обязательств не следуют из разрешения update.
4. Доказать quiescence согласованно: FLAT + synchronized projections, отсутствие OPEN trades, post-approval fills, рабочего/неизвестного LIMIT, незавершённых commands/obligations/checkpoints, покрытий и новых admissions. Не считать все исторические `APPROVED` опасными только из-за статуса; допускать **только индивидуально доказанно инертные** записи при отсутствии owner/fill. **Работающий старый Backend может иметь более строгую проверку:** такое расхождение не обходить новым preflight и не выполнять hot-swap.
5. Для доказанной частично завершённой операции — пользоваться существующей защищённой моделью handoff/receipt/immutable installer, но **не превращать незавершённый STOP intent в успешный STOP**. Только отдельное разрешение на конкретный guarded handoff, точная identity процесса, неизменный proof под SQLite writer reservation (никакого HTTP под lock), один сигнал без повтора, подтверждённый выход Backend и Telegram. Не копировать историческое исключение JASMY/FLOW на другой инцидент без нового доказательства.
6. Проверить остановленные сервисы и отсутствие listeners, активировать Gitless release и Backend/Telegram **только EDITOR_ONLY**. Scanner, Robot admission и PAPER_AUTO не возобновлять; возвращение торговли — отдельная явно авторизованная операция после иной приёмки.

**Новый инцидент монолитного запуска/восстановления — 09.11.2026: SSH + Telegram Gateway.**
Это **один тип восстановления внутри того же owner-ledger workflow**, не второй монолит
и не отдельная очередь ручных диагностических задач. Разработанная граница
`tools.paper_maintenance.resume_installed_release` должна сохранять уже
подтверждённую фазу EDITOR_ONLY, а не повторно останавливать/устанавливать код.

- **Вход на VPS:** 08–09.11 новый платный IPv4 `212.193.14.116/24` иногда
  отсутствовал на `ens3`, несмотря на успешный `netplan generate`; это
  подтверждено VNC-наблюдением до ручного `ip addr add`. После добавления
  адреса SSH через Windows OpenSSH иногда возвращал `SSH_OK`, иногда зависал
  до banner; локальный `sshd` отвечал, TCP на сервер доходил. Одна
  успешная сессия не доказывает устойчивого удалённого управления и
  сохранения адреса после reboot. Считать `banner exchange timeout`
  **транспортным BLOCKED до исполнения монолита**, а не поводом менять
  ключ, повторять STOP, перезапускать сервисы или переустанавливать релиз.
  Использовать документированный рабочий Windows SSH config/ключ и
  доступный owner VNC как резерв; никакого автоматического `netplan apply`,
  нового default route или reboot под предлогом восстановления.
- **Внешний Telegram:** прежняя схема Cloudflare → Vercel получает HTTP
  `402` от Vercel после исчерпания квоты. GitHub PR #964 подготовил
  Cloudflare → Telegram напрямую, но merge **не** устанавливает Worker и
  не подтверждает секреты. Три private bindings нового Worker:
  `GATEWAY_SHARED_SECRET` (точное совпадение с VPS
  `BYBITSCANNER_TELEGRAM_GATEWAY_SECRET`), `TELEGRAM_BOT_TOKEN`
  (прежний бот), `TELEGRAM_CHAT_ID` (проверенный owner private chat).
  Сравнивать конфигурацию *установленной* Telegram-службы из
  `/opt/BybitScanner`, а не отдельного `/root/BybitScanner`. Не
  искать эти значения через цепочки ручных SSH-команд и не помещать
  значения в GitHub, журналы, stdout или тестовые fixtures.
- **Фаза восстановления:** при подтверждённом Backend точного SHA и
  замороженном Scanner/Autopilot, но активной Telegram-службе с
  `/health=503`, существующий монолит возвращает один
  `BLOCKED: Telegram_running_not_ready:<redacted_reason>` и **не**
  повторяет STOP, restart, Gitless install, смену PAPER DB или торговые
  операции. **Уточнение аудита 09.11:** прежняя диагностика #968
  ошибочно выводила причину из предполагаемого `<install-root>/config.py`.
  Это не подтверждает фактически импортированный модуль `config`
  и не является предусловием Cloudflare staging; такая эвристика удалена.
  Для активного Telegram с неподтверждённым health монолит сообщает
  только подтверждаемое `worker_active_health_unproven`.
  `getUpdates` не запускается вторым процессом; наличие кода и публичный
  `/health=200` не доказывают реальную доставку Telegram.
- **Единое продолжение, не отдельные квесты:** после единственного
  необходимого owner-допуска на секреты/Cloudflare production monolith
  переиспользует разрешённую настройку существующего Worker, не создаёт
  нового бота/poller; проверяет реальное `getUpdates` только через
  действующего VPS Telegram consumer, затем `status=ready`, ту же PAPER
  DB identity, реальную доставку и кнопки. Все внешние Cloudflare
  staging/deploy остаются **отдельно авторизуемыми** контролируемыми
  эффектами; монолит их не совершает самовольно. Не скрывать
  `BLOCKED`, не объявлять `READY` по одним тестам, HTTP health
  или готовому коду. Сохранить защиту Backend и LIVE=OFF.

**Системный аудит предпосылок (09.11.2026, репозиторий):**

| Независимая операция | Что действительно необходимо | Что не должно блокировать её |
| --- | --- | --- |
| Cloudflare staging (неопубликованная версия) | Проверенный исходник Worker из GitHub, Cloudflare auth и секреты существующего Worker | Наличие GitHub SHA на VPS, запущенные Backend/Telegram, `config.py`, SQLite, systemd или STOP |
| Cloudflare production (только по отдельному разрешению) | Подтверждённая новая версия Worker и контролируемое переключение Cloudflare deployment | Gitless install PAPER, Scanner/Robot stop или изменение VPS IP |
| EDITOR_ONLY запускаемого релиза | Защищённый exact-SHA установленного VPS, DB identity, frozen Scanner/Autopilot, Backend и реально готовый Telegram | Отсутствие последнего SHA GitHub на **другом** хосте/Cloudflare |
| Неактивная служба Telegram | Доказанное отсутствие systemd worker/listener, затем один разрешённый start | Слепой повтор START после неизвестного результата |
| Активная служба Telegram с `503` | Сохранить установленный SHA/Backend и выдать конкретный runtime BLOCKED | Повтор STOP, installer и анализ предполагаемого `config.py` |
| PAPER STOP/Trade | Свежие ledger/identity/protection/STOP-TAKE proofs, владелец операции, guarded receipts и разрешение | Упрощения безопасности ради независимого Gateway staging |

**Ещё одна доказанная ложная связка и исправление:** до этого аудита
`tools.vps_systemd_unit_prepare.UNITS` одновременно использовался для
строгой stopped-only **замены файлов релиза** и обычного **PAPER START**.
В списке находился независимый `bybitscanner-manual-main-read.service`,
поэтому работающий MAIN/занятый порт 8771 блокировал обычное продолжение
Backend/Telegram. В исправлении `PAPER_UNITS` используется для
`prepare_units`, `check_resume` и проверки портов 8765/8766.
При этом `UNITS` всех четырёх служб, полная сверка их unit-файлов,
строгие порты 8765/8766/8771 и `_stopped` остаются обязательными
для `activate_staged_release`: замена кода под работающим MAIN
по-прежнему запрещена. Доказательство: адресные регрессии для
active/absent MAIN, точных unit bytes и занятого MAIN-порта.

**Отдельная гипотеза об IP:** `vps_release_resume.REVIEWED_DROPINS`
содержит исторически разрешённый HTTPS-адрес терминала
`83.217.213.181` в `terminal-ingress.conf`. Это **не**
`HostName` Windows SSH alias и не Cloudflare route. Новому IP
`212.193.14.116` не следует автоматически подменять этот защищённый
terminal URL без proof фактического ingress и отдельного
разрешения на конфигурацию. Данный hardcode объясняет потенциальный
`unexpected_systemd_dropin` после ручной смены terminal URL,
но не доказывает причину `STABLE_SHA_UNAVAILABLE_ON_VPS`.

**Причина `STABLE_SHA_UNAVAILABLE_ON_VPS`:** такого именованного
блокера в текущем проверенном коде нет; формулировка получена от внешнего
исполнителя. Вероятно, он ошибочно сделал сравнение VPS SHA условием
Cloudflare staging. **Это не доказательство неисправности самого VPS.**
Исходный SHA Cloudflare берётся из проверенного GitHub stable, а installed
SHA VPS контролирует только VPS Gitless release/Editor/Trading.
Гипотеза о сетевой природе не исключена: Windows SSH alias на новом
`212.193.14.116` хотя бы дважды проходил, но попытки Codex могли
использовать иной SSH config/route, а баннер мог пропадать до выполнения
команды. Различать `SSH_TRANSPORT_UNVERIFIED` и `VPS_RELEASE_SHA_MISMATCH`
по доказанному результату **одной** ограниченной проверки только когда
потребуется реальная VPS-операция; не запускать эту диагностику для
Cloudflare staging. Никакой автоматической смены IP, netplan,
reboot или повторного STOP.

**Подход зрелых систем:** Flux разделяет получение проверяемого
артефакта из Git от применения желаемого состояния и последующего
health-check; Kubernetes reconciliation сравнивает состояние **своего**
ресурса с желаемым, не требует неизменности чужих компонентов.
Cloudflare Workers раздельно хранит *uploaded version* и *active
deployment*. Применить эти границы **в действующем monolith**, не
устанавливая Kubernetes/Flux, нового orchestrator или БД.

**Acceptance этого инцидента:** один согласованный запуск/продолжение до
доказанной доставки и EDITOR_ONLY либо один точный безопасный BLOCKED,
без цепочки owner-run SSH/secret поисков. Реальный VPS/Cloudflare результат
не доказан этим изменением репозитория; текущий Cloudflare production не
изменён.

**Актуальное доказательство VPS, 06.11.2026 (после одной разрешённой попытки):** stage `1e9129f51e5b620f71503bb1814f14a431498fc5`, `RELEASE_PREFLIGHT: PASS`; установлен `4090641514b8f558a0054fd577b2750b944fd8d6`. Исторический `094d74f…` признан superseded строго по защищённым handoff receipts (`PRIOR_STOP_RECOVERY_PROVEN: True`). Новый вызов вернул `BLOCKED: canonical_safe_stop_unproven; no retry, no deployment`; его `.stop-invoked-1e9129f…` сохранён, install journal целевого SHA отсутствует. После этого Robot `ROBOT_STOPPED/ROBOT_STOPPED`, Scanner `SCANNER_STOPPED`, Autopilot `OFF`, Backend старой версии отвечает HTTP 200, protection healthy и `covered_symbols=[]`, `armed_symbols=[]`, `coverage_roles={}`, `unhealthy_symbols={}`. Поле `worker_quiescent` в этой старой версии отсутствует (UNKNOWN), и само по себе не является отказом. **Точная причина отказа backend shutdown не установлена.** Возможное расхождение: текущий `paper_shutdown_blocker()` старого Backend отвергает всякий `APPROVED`, тогда как новый `_active_required_flat_proof()` допускает строго доказанные инертные кандидаты; наличие таких кандидатов **на текущем VPS ещё не доказано**. Нельзя объявлять END/READY и повторять STOP.

**Единственная требуемая development-граница:** зафиксировать именно источник отказа последнего safe-stop и обеспечить одноразовое доказанное продолжение оставшихся фаз *через имеющиеся примитивы*. Не строить вторую модель управления или отдельный recovery-tool для каждого символа/инцидента. Требуемые регрессии: инертный `APPROVED` и конкурирующий fill, active LIMIT, non-FLAT/OPEN, неизвестный outcome, crash после сигнала, точный service/DB/release identity, отсутствие повторного сигнала. Цель приёмки — живой EDITOR_ONLY редактор, не число PR/тестов.

## 10. Системная ревизия паралича PAPER — 05.11.2026 (реальный результат прежде PR)

**Исторический снимок (НЕ текущее состояние):** owner READ-ONLY VPS 05.11 16:23 MSK: running
`4090641514b8f558a0054fd577b2750b944fd8d6`, Admission false,
PAPER_AUTO ON, Scanner API RUNNING, Protection HEALTHY, последняя перегрузка
MONUSDT/EXPOSURE, ingress 64/64, max owner callback ~4885 ms. Полная
quiescence/Robot durable reason неизвестны из-за отсутствующего owner root SSH
и слишком узкого forced-command. GitHub stable содержит более новые fixes;
ни их deployment, ни восстановление PAPER не доказаны.

**Подтверждённые дефекты кода и границы исправлений:**
1. `SerializedPaperRuntime` сериализует критическую защиту и обычные owner
   callbacks. Если дорогая операция держит owner, отдельная строгая FIFO
   очередь защиты заполняется, и `RobotProtectionCoverageManager` ставит
   durable `RECONCILIATION_REQUIRED`. Удалять STOP/TAKE события, увеличивать
   capacity бесконечно или подменять `REQUIRED` на `READY` нельзя.
2. `collect_portfolio_facts` на каждом PAPER_AUTO решении строил вложенный
   обход **каждый historical SHADOW ALLOW × каждый Robot candidate** для
   handoff проверки. По мере роста истории это O(A×C) внутри owner write
   transaction, включая время, когда ingress продолжает получать книги.
   Исправление в #879 — один индекс handoff ссылок O(A+C) с сохранением
   `>1` ambiguous-owner rejection и прежних фактов. Реальный вклад в
   4885 ms без host profiling ещё не измерен.
3. Временные `ENTRY_PENDING` subscriptions могут переживать провал
   создания resting LIMIT. Они продолжают заполнять очередь без нужного
   entry ownership. #879 убирает только доказанно осиротевшие arms после
   grace period и monitor idle guard; все position/command/obligation/LIMIT
   owners сохраняют listener. Первый replay поймал premature retire;
   исправление допускается только после повторного зелёного replay.
4. #878 устранил ненужную preflight-подготовку PAPER_AUTO уже во время
   подтверждённого ingress overload. **Это не защита от длинной owner
   транзакции, начатой до перегрузки**; количественный предел работы
   Autopilot и его чтений остаётся отдельным доказуемым runtime acceptance.
5. `RuntimeIntentReconciler`, `RuntimeShutdown`, `paper_maintenance` и
   systemd oneshot имеют разные точки входа/phase transitions; это не
   основание заводить новых контроллеров. Для VPS нужен один существующий
   owner-ledger-driven workflow: converge/freeze/prove/handoff/start/verify.
   `deploy/systemd/bybitscanner-paper-backend.service` сознательно имеет
   `Restart=no`, так как простая перезагрузка теряет software protection.
   Менять на безусловный Restart=always нельзя.
6. Root-owned forced-command `preflight|execute|diagnose` ограничивает
   защищённый bridge; не расширять общий shell/sudo и не создавать второго
   PAPER writer. **Обновление 06.11:** владелец уже выполнял read-only
   проверки и одну разрешённую операцию через существующий root SSH,
   поэтому новый SSH-контур, collector или отдельный доступ ради монолита
   не нужны. Это не разрешает повторный STOP, deploy или торговлю.

**Применимые идеи зрелых систем — без новых зависимостей:** фактическая фаза вместо перезапуска всей последовательности (controller reconciliation), fsync-журнал результата (durable execution), строго не повторять неоднозначный необратимый side effect (at-most-once), systemd использовать лишь как supervisor/process evidence. Не внедрять Kubernetes, Temporal, AWS Step Functions, watchdog, `sd_notify`, сервис очередей или новый persistence layer ради текущего P0. Безусловный `Restart=always` опасен для protection и не разрешён.

**Два разных приёмочных результата:** (1) **текущий P0 — EDITOR_ONLY**: доказанный Gitless SHA/DB identity, Backend+Telegram под контролем, Scanner STOPPED, Autopilot OFF, реальная Telegram → Редактор → сохранение и повторное открытие геометрии; (2) отдельная позднейшая явно разрешённая **PAPER trading** приёмка: Robot/Admission READY, Scanner RUNNING, PAPER_AUTO и полный защищённый order→fill→close, без двойных исполнений. Ни CI, ни PR не равны реальному результату; за них нет XP. Никакого LIVE.


## 11. 07.11.2026 — подтверждённое продолжение прерванного STOP, установка EDITOR_ONLY и остаток до однокликовой приёмки

**Факт из owner-provided postcheck 07.11, не повторная проверка хоста:** после объединения #924 (точная проверка защиты при orphan) и #925 (resume прерванного STOP без повторного сигнала) защищённый переход с immutable close proof `ONE_FLAT_ORPHAN_IMMUTABLE_CLOSE_EVIDENCE_ONLY` для BASEDUSDT завершился установкой `f9123737fdacc658548160109c6c4e1685710899`. Наблюдались защищённые receipts `backend-exited`, `telegram-attempt`, `handoff-proven`; новый STOP/SIGINT не посылался. После установки: работающий Backend PID 1954668, Telegram PID 1954699/ready, `/api/health.build_sha` равен установленному SHA, `mode=paper`, `paper_live_safe=true`, PAPER DB identity `e0cbafb1c172b65f2db3a2c7cef2636b4164a4b1a229bd183bd907e7984ff0ad`, Scanner `SCANNER_STOPPED`, Autopilot `OFF`. Первичный `EDITOR_ONLY_postconditions_unproven` был **позже опровергнут ограниченным runtime postcheck** по названным компонентам; это не доказывает завершённость всех release receipts, frontend-build, браузерную приёмку или торговую готовность.

**Доказанное решение класса блокеров:** не переисполнять уже совершённый необратимый STOP при потерянном ответе; сверить защищённую идентичность прежней операции, конкретный immutable orphan-close proof, факт выхода старого процесса и fsync receipts; продолжить только отсутствующие разрешённые фазы Gitless установки/EDITOR_ONLY postcheck. Ни `STOP intent`, ни HTTP 200, ни установленный backend SHA по отдельности не эквивалентны полной приёмке. Не превращать исключение конкретного orphan в универсальное разрешение игнорировать Ledger или protection. См. реализацию #924/#925; не создавать альтернативный recovery script или второй coordinator.

**Уточнение по актуальному исходному ingress:** `deploy/terminal_ingress/nginx-authenticated.conf` имеет `root /var/www/bybitscanner` и отдаёт статические assets из этого каталога, тогда как Gitless installer (`tools/vps_gitless_release_activate.py`) управляет release tree `/opt/BybitScanner`. Это **доказанное разделение путей в коде**, но не доказательство конкретных байтов на VPS. Требуется один READ-ONLY compare защищённого HTTPS `index.html`/JS/CSS, `/var/www/bybitscanner` и целевого PR #906; при подтверждённом stale UI — интегрировать защищённую сборку/атомарную активацию/проверку frontend assets в уже существующий release path, без второго деплой-менеджера и без переключения Backend под экспозицией. Не рассчитывать, что обновление Python backend автоматически меняет Nginx root.

**Новая жалоба владельца (07.11):** после открытия HTTPS-Терминала вкладка «Автопилот» выглядит по-старому, хотя PR #906 объединён и новый Backend SHA доказан. Это **не доказанный frontend deployment**. Источники `terminal/frontend/src/components/ModePanel.tsx` и `AutopilotFirstScreen.tsx` содержат новый компактный экран; Backend health не сообщает версию реально отданного браузеру JS/CSS. Следующая задача — *одна* read-only сверка активного защищённого Terminal static origin, реально выданных HTML/assets и их build identity с артефактом PR #906, включая кеш браузера/прокси; затем минимальное устранение именно установленного рассогласования в существующем release/terminal launch path. Не считать принудительную перезагрузку страницы или повторное обновление Backend доказанным исправлением. Приёмка — визуально новый экран в авторизованной сессии и корректные PnL/кнопки, без старых блоков; никаких торговых POST.

**Итоговый owner-facing монолит без новой платформы:**
- **Запуск PAPER:** один уже существующий owner entrypoint; сначала сверяет installed release/DB/actual phase и защиту, затем доводит только законные незавершённые переходы до доказанного состояния. Режим торговли/Scanner/PAPER_AUTO включается лишь с отдельным действующим разрешением, не в ходе EDITOR_ONLY update.
- **Остановка:** единый существующий coordinator freeze/drain/FLAT+ledger/quiescence/guarded process exit с сохранением STOP/TAKE при экспозиции; не повторяет неизвестный STOP/POST/SIGINT. Остановка не подразумевает Close-All/Market.
- **Обновление:** продолжает защищённые receipts и immutable Gitless switch только после доказанной остановки; отдельно подтверждает backend+Telegram и **фактический frontend asset** для UI-релиза. Не выдаёт `READY` по одному SHA backend.
- **Перезапуск:** режимно-осведомлённый stop/start только при доказанном safe state; не `systemctl restart`/ `Restart=always` поверх неизвестной экспозиции.
- **Один результат:** ровно один итог `READY` с проверенным целевым режимом либо конкретный `BLOCKED` с сохранённой защитой, фазой, однократными receipts и безопасным следующим действием. Переиспользовать `tools/paper_maintenance.py`, `tools/vps_gitless_release_activate.py`, `tools/vps_release_resume.py`, `tools/vps_paper_auto_start.py`, systemd и существующий Windows VPS Manager **только как read-only наблюдатель**, без параллельного writer/механизма деплоя.

**Граница оставшейся реализации:** сначала удостоверить/исправить отдачу frontend #906, затем один точечный end-to-end тест текущего owner entrypoint для mode-specific START/STOP/UPDATE/RESTART с отказами и crash resume; если доказано, что существующие механизмы уже покрывают поведение, не писать дублирующий код. Реальные VPS мутации, merge, торговый старт и Close-All требуют своих разрешений. До новой браузерной и host-приёмки статус монолита — **не принят**, XP не начислять.
