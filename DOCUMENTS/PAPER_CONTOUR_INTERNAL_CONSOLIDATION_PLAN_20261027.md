# Единый автономный PAPER-контур: план внутренней консолидации

Статус: **план, не акт приёмки**. Решение владельца: 2026-10-27.
Ветка реализации: `stable/adfb50b-forward`; отдельные PR, без автоматического merge.
Связанные задачи: #649 (существующая кнопка аварийного закрытия), #646 (переиспользование), #645/#648 (MIRROR, merge выполнен; VPS-приёмка не завершена), #592 (Wedge reentry после MIRROR).

## 1. Измеримый результат

Владелец управляет **одним PAPER-контуром** через существующие Telegram / Terminal / штатный запуск и остановку; сам не проверяет вручную systemd, процессы, порты, разные БД, статусы каждого модуля или расхождение загруженного кода. Проверка готовности, владения, защиты, восстановление и диагностика происходят внутри действующего контура.

**Инварианты:** LIVE запрещён; один PAPER account / одна авторитетная PAPER DB; никакого второго Robot / исполнения ордеров; Scanner, Autopilot, Admission, PaperRuntime и STOP/TAKE сохраняют существующие контракты. Работающий VPS, позиции и БД нельзя менять без отдельного разрешения владельца. Слова `READY`, `FLAT`, `CLOSED` требуют текущего доказательства, а не HTTP 200 / systemd active.

## 2. Выявленный разрыв и существующая архитектура

Текущая Telegram-кнопка `robot:cmd:close_all` существует в `robot_telegram_feed.py`: Telegram update принимает `telegram_monitoring.py`, делегирует `telegram_review._process_callback`, подтверждение `close_all_confirm` вызывает `terminal.application.robot_control.close_all_now()`; транспорт `telegram_review._post_robot_close_all_now` направляет запрос на `/api/robot/close-all-now`, далее `PaperRuntime.robot_close_all()`. Отдельный `/api/close-all` направляет в `PaperRuntime.close_all()`. Это два разных контракта владения: их нельзя механически смешивать.

Инцидент VPS 2026-10-27: три PAPER SHORT (FILUSDT, MELANIAUSDT, SPXUSDT); `PAPER_AUTO` включён; `POST /api/robot/close-all-now` ответил `not_found`; серверный Python-процесс стартовал до изменения файлов на диске. **Причина несовпадения запущенного обработчика не доказана**, результаты закрытия не подтверждены. Прямое изменение SQLite, слепой повтор POST, перезапуск при неизвестной экспозиции запрещены.

## 3. Целевая модель: модульный монолит, одна власть

- **Входные интерфейсы сохраняются:** те же Telegram callback_data, тексты и кнопки, те же Terminal endpoints, существующие `bybitscanner-paper-start.service` и штатная остановка. НЕ создавать новую кнопку, UI, публичный API или отдельный процесс-оркестратор.
- **Единая внутренняя точка координации** в существующем PAPER owner / application control: последовательно проверяет identity, разрешение на действие, risk/admission, торговые обязательства и нужную операцию; не копирует торговые правила.
- **Подсистемы имеют отдельные компетенции:** systemd обеспечивает процесс и запуск; Scanner производит кандидатов; Autopilot определяет автоматическое решение; Admission проверяет право на вход; Robot/PaperRuntime единолично управляет ордерами/исполнением; protection продолжает обслуживание позиции. Telegram — транспорт и read-only отображение, не торговый движок.
- **Агрегированное внутреннее состояние** вычисляется из уже авторитетных компонентных состояний (conceptually STARTING/TRADING/PROTECTION_ONLY/FLATTENING/BLOCKED/STOPPED); в первом PR не вводим новые публичные строки/enum, таблицы, режимы или переключатели. Ни один summary-status не отменяет обязательных per-component gates.

## 4. Улучшения и критерии приёмки

| Область | Реализация за существующими интерфейсами | Доказательство |
| --- | --- | --- |
| Единое управление | Общие приватные валидаторы/маршруты для start, stop, close, reconcile без параллельного Robot | Один owner path; сохранение разрешённых переходов и отказов |
| Кнопка закрытия #649 | Сохранить двухшаговый Telegram callback. Внутренняя последовательность: запрет новых admissions, cancel неисполненных ордеров, закрытие Robot-owned и остальных PAPER-обязательств через существующие примитивы, сверка | По каждому символу подтверждённые fills/fees/net PnL или явный отказ; zero open + zero obligations только по проверке |
| Идемпотентность | Один устойчивый command ID + payload fingerprint + журнал статусов; после timeout читать итог/сверять, не повторять ордера вслепую | crash/duplicate/retry/partial fill не создают двойной close |
| Восстановление | Единая сверка позиций/ордеров/владения/STOP/TAKE при старте и переходах; не считать отсутствие записи подтверждением FLAT | Сбой/рестарт с позицией не нарушает protection; unknown блокирует новые entries |
| Running-build identity | Фиксировать SHA/конфигурацию в запускаемом процессе и сравнивать с ожидаемой установленной ревизией внутри readiness, без доверия только файловой системе | Расхождение процесса и checkout обнаружено до мутации; диагноз доступен существующей службе |
| Lifecycle автоматика | Один согласованный startup/shutdown route, health/ownership/port/protection checks внутри существующего runtime, без SSH-проверок владельца | Штатные launch/stop определяют итог автоматически, без ложного успеха от systemd active |
| Диагностика | Структурированные внутренние причины отказов, correlation ID события/команды и метрики (queue lag, processing, recovery) без дублирующих решений | Любая неудача локализована в одном журнале; пользователь видит прежнюю безопасную поверхность |
| Развёртывание | Проверка открытой экспозиции, backend identity, DB identity, STOP/TAKE до остановки/обновления; ни один gate не смягчать | Несовместимость или неполное закрытие блокирует unsafe deploy |

Принципы зрелых систем, используемые **как модели, а не заимствование чужого движка**:
NautilusTrader — сверка исполнения/позиций; Freqtrade — разделение запрета новых входов и закрытия; Kubernetes — desired-vs-actual reconciliation; AWS — идемпотентные команды; SRE — actionable diagnostic, а не ручной перебор checks. Kubernetes/microservices, другая БД, новая шина сообщений и новый Robot **не нужны**.

## 5. Порядок реализации и boundaries

**Slice 0 (этот PR):** документирование + один узкий рефакторинг *внутреннего* Telegram→Robot HTTP transport: свести дублирующиеся проверки ответов к одной приватной функции, сохранить точные URL, JSON, коды/исключения, timeout, тексты и callback flow. Добавить regression tests для успешного/ошибочного ответов. Никаких изменений поведения, БД, UI или торговой стратегии.

**Slice 1 (#649, отдельный PR):** после анализа существующего owner/runtime пути — проверяемая идемпотентность и согласованная безопасная операция закрытия; новая торговая семантика только при явной спецификации и тестах, не как «рефакторинг». Не касаться live VPS без отдельного разрешения.

**Slice 2 (#646):** консолидация повторных admission/reconciliation проверок, устранение подтверждённого дублирования и конфликтов, без изменения решений. Фокус на одной доказанной границе за PR.

**Slice 3:** единая read-only внутренняя диагностика identity, readiness и безопасного развертывания; не расширять публичные интерфейсы без отдельного решения.

**После выпуска и разрешённой проверки:** MIRROR real PAPER E2E на VPS, затем Wedge #592 и Box retry по отдельной очереди.

**Жёсткая совместимость текущего задания:** не менять торговую функциональность, callback_data, сообщения Telegram, кнопки, REST routes / body / status, таблицы или схему PAPER DB, env keys, режимы, risk gates, тайминги/идентификаторы торговых команд, lifecycle Robot или поведение STOP/TAKE. Любая новая safety-функция из плана требует отдельного ограниченного PR и доказательства.

## 6. Verification gate

На каждом slice: минимальный scoped diff → регрессии совпадения публичного поведения и ошибок → релевантный CI → review → merge только по явному разрешению → deployment на VPS только по отдельному разрешению и доказанному безопасному runtime. Тесты в isolated temp DB не равны живой PAPER-приёмке. Исторические данные/открытые позиции не менять; XP/достижения за код, тесты или документы не начислять.

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
3. Prove quiescence from a fresh consistent post-action state (same PAPER DB/process identity, authoritative FLAT for all symbols, **zero OPEN Robot trades and active candidates**, zero active LIMIT, commands and unresolved obligations, no new admissions); verify backend/Telegram/process ownership. If any asynchronous state changes during the proof, restart a read-only preflight rather than treating a stale snapshot as terminal evidence.
4. Only after separate owner deploy authorization and canonical safe-stop may immutable release staging and switch proceed. No hot-swap while protection continuity is unproven; no LIVE.
5. Required regression matrix: JASMY-like Flat+OPEN orphan; matching Box/manual/emergency completed fill with strict provenance; missing exit marker; duplicate/tied timestamps; overlapping entry orders/partial fills; new PAPER_AUTO admission racing with stop; active exit LIMIT; unresolved STOP obligation; idempotent retry after partial stop; preservation of healthy protection under BLOCKED. All assertions use isolated fixtures, not production DB.

**Observed status:** mechanism still incomplete; JASMY forensic proof and end-to-end unified-stop acceptance PENDING. Keep this in the same P0 shutdown/deploy queue; not a separate trading feature. XP cannot be awarded for a document or green CI.

## 9. P0 — освобождение PAPER-контура как внутренняя фаза монолитной остановки/обновления (решение владельца 02.11.2026)

**Нормативное решение владельца.** Подготовка безопасного освобождения PAPER-контура от новых входов и ожидание доказанного FLAT — **не отдельный этап/квест, не отдельная команда пользователя и не новая ручная процедура**. Это обязательная внутренняя часть **одного end-to-end workflow**: монолитная остановка → безопасный immutable switch → восстановление Robot/JASMY → эксплуатационная проверка. Система сама выполняет законные внутренние переходы и проверяет доказательства; владелец получает один результат либо конкретный BLOCKED. Данный документ не является разрешением на торговые действия, остановку VPS или deployment.

**Обязательная последовательность внутри единой операции (целевой контракт, НЕ реализованный полностью):**

1. **Identity/authority preflight.** Проверить running SHA/process-instance, PAPER DB identity, актуальные позиции и STOP/TAKE, Scanner, Robot, Autopilot/Admission, все entry/exit LIMIT, кандидаты/trades, незавершённые команды, obligations и checkpoints. Авторитетен существующий PAPER owner; не создавать второй writer/Robot.
2. **Внутренний ingress freeze.** В рамках одной явно разрешённой операции согласованно отключить новые Scanner/Autopilot/Robot admissions и дождаться/синхронизировать уже in-flight entry dispatch. Использовать только законные transition и проверку pending-entry LIMIT. Autopilot OFF, Scanner STOPPED, Robot PAUSED либо RECONCILIATION_REQUIRED по действующим контрактам — зависимые проверки **внутри** coordinator, а не последовательные ручные задания владельцу. Нельзя переводить Robot в STOPPED при защищаемой позиции или orphan-trade.
3. **Защищённый drain.** Сохранять Backend и STOP/TAKE, включая связанные EXIT LIMIT, пока открыта экспозиция. Чётко различать естественное завершение STOP/TAKE и принудительный account-wide Close-All: торговые/отменяющие мутации только при отдельно явно разрешённой торговой семантике. Согласие «обновить» или этот план не разрешает активное закрытие. Если законного пути FLAT пока нет, оставить protection-only/BLOCKED без горячей замены Backend.
4. **Единый quiescence proof.** Перед сменой Backend доказать FLAT/0 для каждой PAPER-позиции, ноль active/unknown entry/exit LIMIT, незавершённых команд, obligations/checkpoints и новых admissions, Scanner STOPPED и Autopilot OFF. Flat + OPEN Robot-trade (JASMY) блокирует обычный safe-stop. Исключительная ветвь допускает только один точный JASMY orphan при подтверждённой immutable command/order/execution attribution и полном отсутствии других открытых владельцев. Reference: tools/jasmy_flat_handoff_proof.py и tools/flat_paper_recovery_transition.py из #762. Это не общий обход Robot lifecycle.
5. **Однократный защищённый handoff/upgrade/reconcile.** При отдельном owner-runtime authorization: exact running SHA, systemd/PID/starttime/listener/cgroup и DB identity; повторный immutable proof внутри SQLite writer barrier без HTTP внутри; один pidfd SIGINT без retry/SIGKILL. Затем verified immutable Gitless release switch и unit preparation, разрешённый start, canonical Robot/JASMY reconciliation уже новой версией, сверка protection/Admission/Telegram и конечной функции. Не считать успехом только CI, HTTP 200 или systemd active.

**Единая очередь P0:** реализовать внутренний coordinator freeze → drain → proof → protected handoff → release/reconcile, включая гонку PAPER_AUTO против stop, partial entry/exit LIMIT, STOP obligations, orphan JASMY, idempotent retries и доказанные причины BLOCKED. Не порождать самостоятельный «квест освобождения контура» и не требовать от владельца нескольких технических ручных шагов. Торговое разрешение и разрешение на VPS runtime mutation по-прежнему отдельные полномочия, которые не выводятся из этой записи.

**Актуальная исходная граница (owner-supplied read-only VPS, 02.11.2026 00:08 MSK):** running f100ef369a1105443332b5729b558464c27be48f; пять защищённых позиций CFX/DJT/GRASS/ICP/SENT; девять active LIMIT; Scanner RUNNING; PAPER_AUTO; Robot READY; JASMY Flat + OPEN. Stable после #762: c4e4ce01b2f011ce2eb8814795a45bb24e2eeca6, не deployed. **Ни drain, ни safe-stop, ни upgrade, ни recovery JASMY не подтверждены.** XP не начислять.

## 10. P0 — одна кнопка запуска, остановки и обслуживания VPS — конечный продуктовый результат (03.11.2026)

**Решение владельца.** Все повторяемые ручные действия подготовки к PAPER, запуска, остановки, защищённого закрытия по отдельной воле владельца, проверки готовности, обновления и восстановления VPS должны стать **внутренними зависимыми фазами единого owner-owned механизма**. Внешне: одна команда/кнопка на каждый из трёх пользовательских сценариев — `START`, `STOP`, `UPDATE/SERVICE`; без вызова Codex, ручного SSH, цепочки диагностик или переутверждения промежуточных штатных шагов. Это развитие текущего §9, а не второй coordinator, отдельные API/Robot/Writer или набор микро-квестов. До доказанной приёмки — целевой контракт, а не выполненная функция.

**Граница режимов и полномочий.** `START` выбирает PAPER-режим: обычный RUNNING/PAPER_AUTO только если владелец выбрал торговлю и доказаны READY + Admission + HEALTHY. `STOP` прекращает допуск новых входов и защищённо дожидается реальной quiescence; не подразумевает Market. `STOP + CLOSE ALL PAPER` — явно выбранное, отдельно авторизованное торговое действие через существующий канонический account-wide Close-All; не заменять Robot-only close-all или raw Market. `UPDATE/SERVICE` охватывает тот же STOP, доказанное безопасное переключение релиза и запуск в запрошенный режим (например, Backend+Telegram+Terminal для приёмки редактора, без Scanner/PAPER_AUTO). LIVE запрещён в каждом режиме. Не выводить разрешение на SIGINT/Market/deploy из самого документа или ранее выданного разрешения на merge.

**Автоматизация внутри одного решения:**
1. **Preflight и freeze:** минимальный текущий снимок одного PAPER owner (running build+PID/starttime/process identity, DB identity/integrity, позиция/STOP/TAKE, order/candidate/trade/obligation/checkpoint, protection, Scanner/Autopilot/Telegram), затем legal OFF → Scanner STOPPED → Robot PAUSED/REQUIRED; безопасная синхронизация in-flight entry и частичных LIMIT.
2. **Доказательный drain/cleanup:** каноническое завершение никогда не исполнявшихся APPROVED только по immutable evidence; stale временные coverage arms только при нулевых доказанных durable entry owners; Flat+OPEN Robot ledger JASMY/FLOW — только по атрибутированным exit executions и строгому исключительному контракту для данного инцидента. Не требовать здорового живого feed **как заместителя** доказательства отсутствия защищаемой экспозиции, но и не считать отсутствие позиции основанием молча сбросить durable loss/coverage. При настоящей экспозиции непрерывно поддерживать Backend и STOP/TAKE.
3. **Quiescence и guarded handoff:** одна свежая согласованная DB snapshot; ноль позиций/неизвестных исполнений/лишних OPEN owners/активных entry+exit LIMIT/unfinished commands/obligations/admissions; точная привязка к backend/systemd/listener. Все HTTP до SQLite writer barrier; под барьером только immutable proof и разрешённый одноразовый pidfd SIGINT (если штатный shutdown невозможен). Не повторять необратимые действия при неизвестном исходе.
4. **Immutable deploy/resume/start:** сохранить единственную PAPER DB/WAL/backup, secrets, чужие правки, системные drop-in и runtime-конфигурацию; проверить точный target SHA/content и зависимости; unit install → daemon-reload → verify loaded → optional reset-failed → start. Разрешённый canonical reconcile и protection postconditions **до** допуска новых PAPER входов. Не возобновлять PAPER_AUTO при обслуживании одного редактора.
5. **Одна итоговая приёмка:** проверка реальных событий запуска/остановки/release switch, Telegram callback/Editor (где применимо), точного runtime SHA, DB identity, live-safe, защиты/ордера, отсутствия duplicate owner и доставки Gateway. При безопасном частичном результате coordinator возобновляет работу по observed state без replay; при действительно недоказанной безопасности возвращает **один конкретный BLOCKED**, оставляет защищающий Backend и не просит владельца исполнять внутреннюю цепочку вручную.

**Приоритет/приёмочный критерий:** текущий инцидент с двумя Flat+OPEN Robot trades, шестью APPROVED и stale ENTRY_PENDING — обязательный регрессионный пример; затем один полноценный операционный START → STOP → UPDATE/SERVICE → START на VPS. Успехом считается реальное пользовательское действие «одна кнопка», не наличие кнопки, документа, CI, PR или staging. Исключительные инцидентные предикаты не становятся универсальным разрешением. Новые самостоятельные очереди, сервисы, таблицы, перезапуски по таймеру и автоматические торговые полномочия не добавлять без отдельного подтверждённого основания.


## 11. Инвентаризация инцидентов START/STOP/UPDATE (03.11.2026)

**Основание:** BACKLOG.md, QUEST_STATE.md, RUNTIME_KNOWN_FAILURE_FAST_PATH.md, PAPER_VPS_BLOCKERS_LOSS_REVIEW_20261101.md, PAPER_VPS_RECOVERY_POSTMORTEM_20261101.md, PROJECT_STATE.md, PR #249–#322, #354, #625–#650, #674, #692, #704–#705, #731–#744, #755, #762–#802. Перечислены все установленные **классы отказов**, найденные в рассмотренных источниках, а не все когда-либо случившиеся ошибки в нечитанных VPS-логах. Исторический успешно исправленный дефект не означает, что последний установленный релиз исправлен.

| Случай/источник | Почему «одна кнопка» не сработала | Переиспользуемый компонент / обязательная защита |
| --- | --- | --- |
| 08–09.2026: старые backend и Vite, WebSocket HTTP 426; PROJECT_STATE §M9, §VPS | Split-brain процессов, Nginx не проксировал Upgrade, HTTP 200 не доказал работу интерфейса | systemd singleton, listener/process identity, WS 101 и реальный UI |
| 26–27.09: Scanner сам запускал следующий проход, PAUSE не означала STOP; #249/#251 | Неоднозначная lifecycle semantics | ScannerControlRuntime и канонический Scanner stop |
| 27.09: одновременно standalone Scanner и backend child, Telegram callback owner отсутствовал; #251–#263 | Два владельца, неполная готовность | RuntimeIntentBootstrap, backend-owned Scanner, Telegram singleton |
| 27–29.09: штатный Robot STOPPED требовал Telegram START + повторный desktop START; BLEND/CASHCAT REQUIRED; #280/#285/#354 | Проверялась уже достигнутая READY вместо достижимости desired state; не снимался owned continuity fence | runtime_intent ALL, canonical reconcile и owned-fence recovery |
| 27–29.09: ingress_overflow, saturated owner FIFO, ENTRY_PENDING stale, emergency exits; #291/#310–#320 | Сигнал управления стоял за рыночным backlog; временные arms принимались за владение | serialized owner, protection manager, bounded stale-arm proof |
| 27–28.09: ModuleNotFoundError в stop, некорректные ярлыки, остающиеся cmd.exe; #280/#313–#316/#322 | Неканонический launcher и ложная диагностика по окнам | python -m tools.stop_robot_runtime, единые owner shortcuts |
| 28.09: backend HTTP недоступен, но listener PID=700 жив; #317/#322 | Timeout ошибочно классифицировали как ABSENT | exact listener/cgroup/process identity; unknown != absent |
| 10.2026: Telegram 8766 TIME_WAIT, недоступный SOCKS/Gateway мешал core старту; #637/#638/#690/#692 | Неверная зависимость readiness и environment | systemd start unit, SO_REUSEADDR, Telegram best-effort с отдельным статусом |
| 10–11.2026: Gitless release/dirty worktree/systemd drop-ins; #625/#743/#755 | Нельзя делать git merge поверх работающей установки или стирать чужие конфиги | vps_release_identity, vps_check, reviewed drop-ins, immutable staging |
| 01.11: BUSDT STOP DISPATCHING при Flat, Close-All HTTP 503, VIRTUAL всё ещё OPEN; #731/#735 | Расхождение атрибуции STOP/TAKE и Robot trade; неготовность canonical Close-All | durable executions, protection obligations, canonical reconcile, one action id |
| 01.11: отсутствует running build SHA; #738/#743 | Маркер на диске не доказывает идентичность исполняемого кода | root-protected manifest, vps_release_identity exec-backend |
| 01.11: HTTP внутри BEGIN IMMEDIATE, после SIGINT active→failed ошибочно объявлен отказом; #739/#741 | Self-deadlock SQLite writer и ошибочная классификация irreversible outcome | pre-lock HTTP snapshot, pidfd one-shot, EXIT_OBSERVED / UNKNOWN |
| 01.11: Unit not loaded, неверный порядок reset-failed; #742/#744/#755 | Отсутствие ordered unit prepare и возобновления после частичного switch | vps_systemd_unit_prepare, vps_release_resume |
| 01–03.11: JASMY/FLOW Flat+OPEN Robot trades, шесть APPROVED, BB/KITE ENTRY_PENDING, unhealthy WS; #762/#801/#802 | Нет законного автоматического terminalization инертных кандидатов и доказательства orphan, protection proof ожидает healthy у старого процесса | two_orphan_proof, immutable entry/exit proofs, strict owner lifecycle |
| 02–03.11: при каждом BLOCKED заново запускались preflight/stop/reconcile, staged release не установлен; #764–#803 | Нет одного возобновляемого UPDATE с сохранением observed side-effect outcome | RuntimeShutdown + paper_maintenance + release_resume |
| Telegram Editor: callback открывал Windows-only процесс на Linux; контекст signal_id терялся после login; #746/#794 | Runtime и интерфейс не проходили сквозную пользовательскую приёмку | workspace_telegram_handoff, authenticated /login, geometry feedback API |

**Статусы:** отдельные исторические дефекты закрыты (#322, #354, #637, #739, #741–#744, #755 и др.), но **текущий VPS остаётся BLOCKED** на installed f100ef36, target stable после #802 — только staged. PR #793 со строгой typed coverage shutdown-evidence на момент исследования **открыт, не merged**: оценить и переиспользовать, не дублировать код. Не повторять уже закрытые расследования как новые квесты.

### 11.1 Проверенные внешние решения: что заимствовать, а что не устанавливать

- **Freqtrade**: /pause /stopentry прекращает новые входы, пока защита и exits продолжаются. Применить точную границу ENTRY_QUIESCE != BACKEND_STOP. В нашем PAPER STOP/TAKE реализован в Backend, поэтому нельзя предполагать независимую биржевую защиту. https://docs.freqtrade.io/en/2026.1/telegram-usage/
- **Kubernetes**: desired state и observed state, level-triggered reconciliation; повторный запрос должен сходиться к цели без replay необратимых действий. Взять подход, а не внедрять Kubernetes. https://kubernetes.io/docs/concepts/architecture/controller/
- **Argo CD**: зависимости проходят дальше по реальным health checks, а не по коду 0 hooks; hooks могут повторно запускаться. Использовать настоящие postconditions. https://github.com/argoproj/argo-cd/blob/master/docs/user-guide/sync-waves.md
- **Temporal**: durable history и возобновление после crash. Взять минимальную запись intent/action/outcome, **без** отдельного Temporal сервера или обещания exactly-once внешних вызовов. https://docs.temporal.io/encyclopedia/event-history
- **systemd**: обычный TimeoutStopSec может завершиться SIGTERM/SIGKILL, что недопустимо для локально защищаемого PAPER Backend. Сохранить действующие no-force-stop units, наблюдать фактический MainPID/process exit. https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- **Ansible**: идемпотентное ensure, restart только на изменениях. Заимствовать принцип в release/unit orchestration, **не** добавлять Ansible или новый daemon. https://docs.ansible.com/projects/ansible-core/devel/playbook_guide/playbooks_intro.html

## 12. GitHub-first рабочий blueprint — один интегрированный продуктовый патч

**Основа уже в stable:**
- tools/runtime_intent.py и deploy/systemd/bybitscanner-paper-start.service: one-command desired START, включая разрешённый PAPER_AUTO.
- tools/stop_robot_runtime.py: canonical freeze/stop + natural drain + guarded dual-orphan handoff.
- tools/paper_maintenance.py (merged #674): единственный уже существующий entry point UPDATE; реализация устарела — повторяет stop и использует git fetch/merge в рабочем VPS-каталоге вместо Gitless immutable release.
- tools/flat_paper_recovery_transition.py, tools/paper_two_orphan_proof.py, tools/jasmy_flat_handoff_proof.py: проверка orphan + точный writer barrier/pidfd signal.
- tools/vps_check.py, tools/vps_release_identity.py, tools/vps_release_resume.py, tools/vps_systemd_unit_prepare.py: проверки, manifest, pre-start resume и правильный unit-order.
- terminal/runtime/paper_runtime.py, terminal/runtime/paper_http_server.py и terminal/persistence/sqlite_store.py: **единственный** serialized owner и canonical durable lifecycle.
- Telegram Gateway, workspace_telegram_handoff.py и защищённый Terminal HTTPS — готовая коммуникация с владельцем; не создавать новый Gateway/Terminal.

**Три видимые owner-операции:** START(TRADE|EDITOR_ONLY), STOP(protected_wait|explicit_PAPER_CLOSE_ALL), UPDATE(target_sha, resume_mode). Выбор STOP с Close-All требует явно выбранной торговой семантики; обычный STOP или UPDATE никогда сам не посылает Market. START(EDITOR_ONLY) не включает Scanner/PAPER_AUTO. Успех старта торговли = доказанные READY/Admission/HEALTHY, а не просто systemd active. Все кнопки/ярлыки переиспользуют этот маршрут, не создавая параллельного Robot/SQLite writer.

### 12.1 Точный coding plan — выполнить внутри одного GitHub code PR, не отдельными квестами

1. **Сначала patch tools/paper_maintenance.py, не второй coordinator.** Заменить его небезопасный для Gitless release git merge и mutating stop polling на: observe actual state → выбрать одну canonical safe delta → execute once with stable action id → read-only postcondition → следующая delta. Target manifest/staging/permissions/config проверить **до** freeze. Для недоступного API не принимать ABSENT без socket+PID proof. Reuse текущих tools, не добавлять вторую БД.
2. **Freeze и reconciliation по owner authority.** В tools/stop_robot_runtime.py и только необходимой части terminal/runtime/paper_runtime.py/terminal/runtime/paper_http_server.py: один durable ingress admission fence, Autopilot OFF, Scanner STOPPED, in-flight entry sync и legal Robot PAUSE/REQUIRED. Уже принятую, частично исполненную ENTRY/EXIT заявку не терять. STOP/TAKE действует непрерывно до proved zero exposure. Unknown mutation response → read-only observe, не слепой POST retry.
3. **Исправить узкую реальную причину BLOCKED.** До exceptional handoff в canonical owner допустимо terminalize шесть APPROVED по **индивидуальному** доказательству отсутствия любого entry ownership/fill/active order/unfinished command и соответствующей phase/revision; box slot evidence отдельно. BB/KITE retired только при доказанном отсутствии durable entry/partial fill и только через действующую coverage owner transition. JASMY/FLOW: две независимые immutable entry/close атрибуции, exact trade/candidate/projection identity. При любом unknown/partial/двойном owner — BLOCKED. Если feed unhealthy при нуле всех exposure, обсуждать **ограниченный** incident-specific proof path отдельно от здоровья реальных STOP/TAKE, не устанавливать правило «Flat значит безопасно».
4. **Safestop→Gitless switch→resume.** HTTP и живые снимки ДО SQLite writer reservation; внутри только pinned immutable DB/process proof и максимум один разрешённый pidfd SIGINT. Не повторять при неизвестном исходе. Внешний минимальный служебный operation journal (вне PAPER DB) фиксирует intent id, phase, irreversible action id, NOT_SENT/CONFIRMED/UNKNOWN и observed provenance; запись атомарно и защищённо, а фактические process/DB наблюдения всегда авторитетнее журнала. switch только exact verified tracked release; не трогать user-owned config/drop-ins/DB/WAL/venv. Для units использовать vps_systemd_unit_prepare; для restart после interrupted switch — vps_release_resume. Откат только при доказанной schema compatibility.
5. **Единый START и целевая приёмка Telegram Editor.** Переиспользовать runtime_intent и oneshot. EDITOR_ONLY поднимает Backend+Telegram/Terminal, Scanner STOPPED, Autopilot OFF, без входов. Проверить owner-кнопку, HTTPS login, сохранённый signal_id, замороженные исходные лучи, независимые редактируемые лучи и сохранение feedback в API. Для TRADE — автономное согласованное восстановление Robot, Scanner, MIRROR, PAPER_AUTO только с прежними разрешениями.

**Никакого нового сервиса, event bus, Kubernetes/Temporal, public trading API, параллельной торговой БД, таймеров auto-merge/deploy или ручного SQLite repair.** Допустим один небольшой защищённый журнал этапов обслуживания, потому что наблюдение и replay необратимого действия должны различаться. Обновлять старый process путём подмены .py на диске запрещено: текущий f100ef36 исполняет старые handlers, нужен доказанный миграционный handoff.

### 12.2 Матрица проверок ДО одного реального деплоя

Один интегрированный offline acceptance suite поверх существующих tests/test_paper_maintenance.py, tests/test_stop_robot_runtime.py, tests/test_paper_two_orphan_proof.py, tests/test_flat_paper_recovery_transition.py, Robot PAPER acceptance и release/unit tests. Использовать реальный coordinator и реальные SQLiteStore schema/row_factory с injected shell/HTTP/systemd adapters, не только замоканные success results.

Сценарии: чистый START/STOP/UPDATE и их idempotent повтор; STOPPED→START, PAUSED→STOP, natural protected drain; реальная открытая позиция и STOP/TAKE; частично заполненный ENTRY/EXIT LIMIT; stale ENTRY_PENDING; шесть never-executed candidates против одного proven-filled/UNKNOWN; обе Flat+OPEN lots и неверная exit attribution; concurrent Autopilot, второй operator/double click; Queue overflow; NULL/unknown status; HTTP timeout с живым listener; crash до/после каждого необратимого действия; SIGINT sent unknown, active→failed/MainPID=0; неверные SHA/manifest/drop-in/DB; systemd unit not loaded; interrupted release switch + безопасный resume/rollback; Telegram недоступен и позже восстановился; protected web auth + signal_id + geometry-feedback; LIVE prohibited. Никакого silent PASS при отсутствии доказательства.

**Граница приёмки:** один code PR через ChatGPT GitHub connector → targeted mandatory CI на его HEAD → отдельное разрешение merge → **один отдельно разрешённый** VPS end-to-end до установки точного stable SHA и Telegram Editor acceptance, сохранив Scanner OFF/PAPER_AUTO OFF → затем нормальный проверенный START/STOP с protected exposure и единственным PAPER owner. Codex — только исполнитель одной VPS-операции, не автор кода. Не выдавать PR/тесты/staging за реальный продуктовый результат.

**Реалистичное инженерное обещание:** после внедрения нормальные и заранее известные безопасные состояния не требуют промежуточных owner-команд. Неопределённая настоящая экспозиция или неподтверждённая exit-attribution всё равно может остановить работу BLOCKED с одним точным доказательным blocker, а защищающий Backend продолжает работать. Безусловное «никогда не будет блокеров» несовместимо с безопасной торговлей.
