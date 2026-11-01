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
