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

## 10. Системная ревизия паралича PAPER — 05.11.2026 (реальный результат прежде PR)

**Отправная точка:** owner READ-ONLY VPS 05.11 16:23 MSK: running
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
6. Root-owned forced-command `preflight|execute|diagnose` и установленная
   Gitless версия не дают внедрить новый collector/код restricted key.
   **Одно восстановление доверенного owner root доступа для установки
   фиксированного handler — реальная внешняя граница**, не исчезающая
   от очередного PR. Не расширять общий shell/sudo и не вводить второй
   независимый PAPER writer.

**Что заимствовать, а не переписывать:**
- Kubernetes controller-runtime: reconcile desired vs observed, per-key
  rate-limited retry, idempotent state convergence; coalesce повторные
  *requests* к сверке, но НЕ последовательные market crossings.
  https://github.com/kubernetes-sigs/controller-runtime/blob/main/FAQ.md
- Temporal/AWS Durable Execution: durable event/intent + idempotency key,
  at-most-once для неопределённого внешнего торгового side effect, bounded
  retry только после read-back и однозначного доказательства результата.
  https://docs.temporal.io/encyclopedia/retry-policies
  https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/
- systemd `sd_notify`/watchdog: отдельно мониторить готовность работы,
  не путать `active` с `Admission READY`. Supervisory restart возможен
  лишь для компонентов, чей restart не нарушает сохранение защиты.
  https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html

**Единый эксплуатационный критерий:** после одного owner-authorized
доступа/immutable upgrade — доказанная PAPER DB identity, Robot
READY/Admission READY, Scanner RUNNING, PAPER_AUTO, real protection event
under replayed overload, не потеряны STOP/TAKE, нет двойных исполнений;
проходит обычный PAPER order→fill→close; Telegram получает те же сведения.
Никаких XP/«готово» по CI или PR. Отсутствие данных либо реальная открытая
экспозиция означает узкое `BLOCKED`, но не останавливает независимые
read-only/Scanner работы. Никакого LIVE.


## 11. P0 — текущий монолит, зафиксированные наработки и маршрут завершения (06.11.2026)

**Назначение раздела:** единственный актуальный технический handoff к цели владельца: одна защищённая PAPER-операция `STOP → immutable upgrade → EDITOR_ONLY`, далее реальная приёмка Telegram → Редактор. Предыдущие разделы — история решений, не команда повторять операции. `BACKLOG.md` содержит приоритет, этот раздел — детали реализации. Разработку и runtime-операции не дробить на самостоятельные квесты. **GitHub CI/merge не являются доказательством перехода VPS.**

### 11.1. Подтверждённая фактическая граница (owner VPS, 06.11)

| Проверка / этап | Точное подтверждение | Чего НЕ доказывает |
| --- | --- | --- |
| Старый незавершённый STOP `094d74f6699528b47578cb740e8e06a45d8c7840` | После PR [#888](https://github.com/svobodaXXI/BybitScanner/pull/888) на VPS `PRIOR_STOP_RECOVERY_PROVEN: True`: старый intent сопоставлен с root-owned exceptional JASMY/FLOW handoff и установленным `4090641514b8f558a0054fd577b2750b944fd8d6` | Это **не** подтверждение нового STOP и не разрешение на повтор |
| Установленная старая версия | `verify_release("/opt/BybitScanner")` подтвердил `4090641514b8f558a0054fd577b2750b944fd8d6` | Не установлена новая версия |
| Staging / preflight | Immutable staging был fast-forward до `1e9129f51e5b620f71503bb1814f14a431498fc5`; вызов `inspect_staged_release(..., root="/opt/BybitScanner")` вернул `RELEASE_PREFLIGHT: PASS` | Не разрешает STOP/deploy; первоначальный ложный `installed_release_unproven` возник из-за **ошибочного диагностического вызова без `root`**, не из-за повреждения установки |
| Новая **одна разрешённая** операция | `paper_maintenance 1e9129f... --staged-gitless-editor-only` вернул `BLOCKED: canonical_safe_stop_unproven; no retry, no deployment` | Причина конкретного внутреннего отказа не выведена наружу; повтор STOP запрещён |
| Долговременный результат на VPS после отказа | `ROBOT_STOPPED/ROBOT_STOPPED`; `SCANNER_STOPPED`; Autopilot `OFF`; admission false; Backend HTTP 200 на `40906415...`; protection `healthy=True` и **covered=[], armed=[], coverage_roles={}, unhealthy_symbols={}** | `healthy` в одиночку не доказал бы quiescence; свежий полный durable shutdown proof и отсутствие непройденных кандидатов отдельно ещё не установлены |
| Незавершённая release transaction | `.stop-invoked-1e9129f...` существует; каталога установки `/var/lib/bybitscanner-release-transactions/1e9129f...` **нет** | Нет `CANONICAL_ALL_STOP_CONFIRMED`; маркер нельзя удалить, переписать или считать успешным STOP |
| Scanner worker | Поле `worker_quiescent` отсутствует (в выводе `UNKNOWN`); для установленного legacy Backend старый код допускает отсутствие необязательного поля | Не является доказательством живого worker и не отменяет независимую проверку exit/quiescence |
| GitHub после исправления | PR [#889](https://github.com/svobodaXXI/BybitScanner/pull/889) **squash merged** в `stable/adfb50b-forward`, merge SHA `d08f61cb93a33449aad9fd304fba4651b749ae0e`; 3/3 PR CI success | Этот SHA **не установлен** на VPS и **не** является прежним pinned target `1e9129f...` |

**Следствие:** это **частично исполненная**, а не успешная или полностью неизвестная операция. Robot/Scanner/Autopilot уже остановлены, защита пуста, Backend **ещё жив**, Telegram/новый релиз не приняты. Работоспособность EDITOR_ONLY/редактора на новой версии не доказана. Не заявлять «Монолит готов», «можно повторить STOP» или «VPS безопасно обновлён».

### 11.2. Что уже построено и что повторно использовать

- **Существующие владельцы:** `RuntimeShutdown` (`tools/stop_robot_runtime.py`) управляет freeze, Robot reconcile/STOP, protection и graceful Backend/Telegram exit; `PaperRuntime`/`SQLiteStore.paper_shutdown_blocker` владеют долговременным торговым состоянием; `RobotProtectionCoverageManager` — активной защитой; systemd — процессами. **Не создавать** новый торговый writer, новый RabbitMQ/Temporal/Kubernetes, параллельный orchestrator или другой service.
- **Единое обновление:** `tools/paper_maintenance.py:deploy_staged_editor_only` делает строгий preflight → one-shot STOP → Gitless switch → `resume_installed_release`; `tools/vps_release_identity.py` удостоверяет tracked bytes и manifest; `tools/vps_gitless_release_activate.py` и `tools/vps_release_resume.py` защищают транзакцию установки, unit/listener attestation, postcondition. Уже имеются `.stop-invoked-*` и `.stop-confirmed-*` (разные значения, разные полномочия).
- **Пример безопасного восстановления:** PR [#844](https://github.com/svobodaXXI/BybitScanner/pull/844) — подтверждённый результат STOP до install journal; PR [#845](https://github.com/svobodaXXI/BybitScanner/pull/845) и [#855](https://github.com/svobodaXXI/BybitScanner/pull/855) — **исключительный**, независимо подтверждённый JASMY/FLOW handoff, не универсальный пропуск; PR [#888](https://github.com/svobodaXXI/BybitScanner/pull/888) признаёт старый STOP исторически superseded только по полному набору root-owned квитанций. Для **нового** `1e9129f...` такого доказательства пока нет.
- **Критерий инертного APPROVED:** `_active_required_flat_proof` допускает только проверенный APPROVED при отсутствии связанного Robot trade и post-approval executions. Старый `SQLiteStore.paper_shutdown_blocker` запрещал **любой** APPROVED; PR [#889](https://github.com/svobodaXXI/BybitScanner/pull/889) устранил несогласованность в **новом GitHub-коде**, сохранив запрет на незавершённые команды, LIMIT, obligations/checkpoints, не-FLAT, неизвестные данные и новые исполнения. Старый **работающий** Backend не изменился; это **возможная**, но **не доказанная VPS** причина `canonical_safe_stop_unproven`. Не обходить старый gate по предположению.
- **Существующие защитные примитивы:** `tools/flat_paper_recovery_transition.py` содержит привязанный к точному systemd MainPID/starttime/listener/cgroup, `pidfd` и SQLite barrier one-shot handoff без HTTP под writer lock. `tools/paper_interrupted_stop_recovery.py` показывает fsync фаз и запрет replay. Переносить можно **паттерн proof + intent + observed result**, но НЕ инцидентные JASMY/FLOW константы на текущий `40906415...`.
- **Другие узкие исправления/уроки:** #318/#516/#865 — каноническая обработка кандидатов до входа; #872 — защищённое восстановление ingress-overflow внутри разрешённого START; #878/#879 — снижения перегрузки owner-потока/осиротевшей ENTRY_PENDING-защиты (сверять реальный merge/CI перед использованием). Не считать их установленными. `Restart=no` для Backend оставлять, пока незакрытая позиция могла бы потерять software STOP/TAKE.
- **Заимствованные архитектурные принципы, без сторонней платформы:** Kubernetes reconcile desired/observed; durable workflow checkpoints/at-most-once для внешнего side effect (Temporal/AWS); systemd подтверждает **факт завершения** unit/PID, а не факт отправки команды. Контракт — наблюдаемое состояние определяет следующий **допустимый** переход; unknown не «лечится» retry.

### 11.3. Целевой конечный автомат одной owner-authorized операции

`AUTHORIZED(target, scope, DB/process identity) → FREEZE_INGRESS → DRAIN_OR_BLOCK → PROVE_QUIESCENCE → STOP_BACKEND → STOP_TELEGRAM → VERIFIED_STOPPED → INSTALL_PINNED_RELEASE → EDITOR_ONLY_READY → ACCEPT_EDITOR`.

**Состояния являются внутренним планом; не добавлять публичный API/новые таблицы ради диаграммы.** Каждый переход должен переиспользовать существующий owner/systemd/Gitless contract. Состояние не принимается по намерению: требуется проверенный postcondition и долговременная запись там, где действие необратимо. При сбое возвращается `BLOCKED(phase, reason, receipts)`, сохраняются действующие protection, DB и evidence. Повторный вызов читает подтверждённые фазы, а не переисполняет их.

1. **Authority/identity:** отдельное разрешение на новый runtime side effect, exact целевой SHA и staged tracked bytes, доказанный installed SHA, protected PAPER DB identity, процесс/unit/listener. Изменившийся SHA/owner/DB = BLOCKED.
2. **Freeze/drain:** Autopilot OFF, Scanner STOPPED, Robot canonical STOPPED/законная PAUSED только по реальным правилам; защищённая экспозиция сохраняет Backend+STOP/TAKE до естественного выхода. Market/Close-All/отмена protection — исключительно отдельное торговое согласие, никогда из «обновить».
3. **Один непротиворечивый FLAT proof:** account-scoped positions Flat/0 synced, ноль OPEN trades, working/unknown LIMIT, unfinished trading_commands, unresolved obligations/checkpoints, реальных entry owners; кандидаты APPROVED только с строгой approval/fill/trade provenance; no in-process coverage; Scanner/Autopilot frozen; identity/process неизменны. Отличать `healthy` от `quiescent`. Никакого обобщённого разрешения «APPROVED всегда безопасен».
4. **Переход Backend/Telegram:** privileged graceful/exceptional one-shot только при полном proof и отдельном owner authorization. Фазовый protected intent fsync **до** любого необратимого вызова; точный process instance/PID/start token/listener/cgroup; отсутствие signal/POST replay после unknown; подтверждать реальный exit unit+порт, лишь затем Telegram. `STOP_INTENT` без `STOP_CONFIRMED` **не** даёт installer entitlement.
5. **Install+start Editor:** только после точного `VERIFIED_STOPPED` — зафиксированные файлы, systemd unit check, защищённый install journal/rollback и `EDITOR_ONLY` Backend+Telegram с той же DB identity; Scanner и PAPER_AUTO остаются OFF. Не делать hot swap текущего Backend.
6. **UI/E2E acceptance:** реальная Telegram-кнопка «Редактор» → загрузка исходной геометрии Scanner (read-only) и отдельной редактируемой пары линий → изменение → сохранение feedback → повторное открытие того же кандидата → сохранённые координаты совпадают; проверить независимость от торгового запуска. Затем **отдельная** owner-authorized проверка монолитного PAPER start/stop с защитой и отчётом, но не включать PAPER_AUTO при приёмке EDITOR_ONLY.

### 11.4. Конкретная recovery-ветка ПОСЛЕ прерванного STOP `1e9129f...`

**Критическая тонкость:** в текущем journal только `.stop-invoked-1e9129f...`, не `.stop-confirmed-*` и не installation journal. Прежняя операция выдала `ok=False` при живом Backend; нельзя задним числом записать успешный STOP или вызвать `paper_maintenance` повторно. Даже если Robot теперь STOPPED, его прежний reconcile/STOP/retire-entry-arms **не повторять**.

**Минимальный порядок разработки и применения:**

A. **Один агрегированный READ-ONLY root-cause proof** существующего Backend: подсчитать именно те active/APPROVED кандидаты, executions/trades и остальные предикаты, которые проверяет установленный `paper_shutdown_blocker`; зафиксировать снимок Robot/Scanner/Autopilot/coverage, process/DB identity, systemd PID+unit и журнальные фазы. Вызовы, способные создавать команды, запрещены. Если found APPROVED — считать несовпадение gate доказанной причиной **только когда факт отказа привязан к этому gate**; иначе отметить причину «не установлена» и не выдумывать. Для отсутствующего `worker_quiescent` на старом Backend нельзя придумывать `True`; использовать независимое process evidence.
B. **Одна узкая реализация resume** в существующем `paper_maintenance` или связанном приватном helper, не в новом контроллере: принять **только** неизменный protected marker `1e9129f...`, точный installed SHA `40906415...` и утверждённую целевую release identity. Доказать frozen STOPPED + истинный FLAT/no-exposure/no-obligation и ownership Backend/Telegram; fence drift. Установить **новый самостоятельный защищённый recovery intent**, явно отличающийся от прошлого STOP, исключительно под отдельно разрешённый **новый** lifecycle handoff. Прежде чем отправлять какое-либо новое shutdown действие, доказать, что оно не является слепым повтором неизвестного исхода старого POST; если невозможность повторного действия не доказана — BLOCKED. Один bounded guarded handoff по реально применимому контракту (не скопированным JASMY условиям), затем отдельный `backend-exited` / `telegram-exited` receipt **после наблюдаемого** выхода. Отсутствие квитанции после неопределённого действия = BLOCKED/no replay. Never synthesize `stop-confirmed`.
C. **Installer entitlement** только из доверенного доказательства completion конкретного нового handoff, exact stopped units/listeners и pinned target; переиспользовать `activate_staged_release` + `resume_installed_release`. Сначала восстановить **тот же** pinned target `1e9129f...` либо спроектировать **явную** owner-approved SHA migration с новыми proof/receipts: после #889 stable уже `d08f61c...`, но **нельзя** молча переписать stage/intent на latest. Ветка миграции не должна интерпретировать старый STOP как подтверждённый.
D. **Не вводить ручной сервисный ритуал:** один фиксированный protected execution route (существующий Codex/VPS канал при доступе) собирает доказательства и выполняет разрешённую остаточную фазу. Владелец только разрешает действительно новую runtime-мутацию/merge и участвует в реальной UI приёмке; не носит по одному HTTP/SQLite/PID отчёту между чатами.

**Приоритетный кодовый delta после #889:** gated `resume-interrupted-stop` с отдельным no-replay recovery intent и краткой точной причиной блокировки в journal/выводе. Достаточно переиспользовать текущий coordinator и exit checks — **не** менять целиком STOP/Robot/DB и не добавлять инфраструктуру. Пока этот delta не прошёл тесты, PR, отдельный merge и owner runtime approval, переход VPS запрещён.

### 11.5. Минимальная проверочная матрица и приёмка

| Сценарий | Ожидаемый результат |
| --- | --- |
| `APPROVED` исторический, нет post-approval executions/Robot trade | Новый shutdown proof принимает **только** при полной валидной provenance (PR #889, 3/3 CI) |
| `APPROVED` без id/symbol/approved_at, с unknown timestamp execution или linked Robot trade; OPEN/null/unknown candidate | BLOCKED, не потерять защиту |
| Flat с OPEN Robot-trade, не-FLAT, защищённая позиция, LIMIT, obligation, checkpoint, новые admission/coverage | BLOCKED до backend exit/deploy |
| Старый `.stop-invoked` без `stop-confirmed`; no install journal; Backend жив | Старый STOP **не повторяется**, install **не допускается** только по маркеру |
| Новая protected recovery attempt, неопределённый shutdown POST/SIGINT либо изменение PID/identity | BLOCKED; нет повторного POST, SIGINT, Robot STOP/Market, нет установки |
| Доказанный existing `backend-exited`, Telegram ещё жив | Resume **только** разрешённой Telegram-фазы с отдельной записью, без Backend shutdown |
| Installed/Editor ready receipt уже подтверждён | Не перезапускать STOP/install; повторно доказать конечное состояние |
| При любом сбое до Backend exit обнаружена реальная экспозиция | Backend/protection сохраняется, Admission остаётся закрыт |
| Один разрешённый end-to-end recovery в тестовом аналоге + реальная VPS приёмка | Точный SHA, целая PAPER DB, остановленные units/ports перед switch, EDITOR_ONLY Backend+Telegram, Scanner/Autopilot OFF, действующая UI запись геометрии |
| Последующее отдельно разрешённое PAPER start/stop | Robot READY, Admission READY, Scanner RUNNING, PAPER_AUTO по отдельному opt-in, protected order→fill→STOP/TAKE, Telegram; безопасный stop с нулём незавершённых owner и без повторных side effects |

**Статус на 06.11:** code #889 merged, host runtime остаётся `BLOCKED / partial STOP`, CODE↔VPS drift есть, `EDITOR_ONLY` на новом SHA не проверен. **Следующий шаг — одна адресная GitHub реализация recovery-resume**, целевые тесты и PR; никакого повторного STOP/deploy по старому разрешению. Документ и CI не зарабатывают XP.

