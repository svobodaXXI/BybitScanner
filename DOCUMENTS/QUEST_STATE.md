## 🧾 OWNER FEEDBACK REGISTER — 2026-09-29

Owner feedback findings are consolidated in
`DOCUMENTS/OWNER_FEEDBACK_PROBLEM_REGISTER.md`.

New confirmed acceptance finding:
- B2USDT/BANKUSDT/BNBUSDT/BNCUSDT 5m Box cards were delivered without
  `🤖 Робот` and with the explicit candidate-creation failure warning;
- later BRETTUSDT showed a normal Robot button, so this is not a global Robot
  or Telegram outage;
- exact exception evidence was lost because the current implementation keeps
  the cause only in scrolling Scanner stdout;
- queue RH-FAIL-1 (candidate preparation failures) + RH-DIAG-1 (durable
  sanitized failure diagnostics) without interrupting the current same-process
  RVL-R6 run.

Already-known geometry, Telegram Menu, CELO manual PAPER, fixed TG-MON-1,
shutdown closure and correctly classified ARUSDT are included in the same
register to prevent duplicate rediscovery.

## 📐 GEOMETRY LAB — RVL-G1 COMPLETE — 2026-09-29

While RVL-R6 continued on the owner's live runtime, repository-only Geometry
inventory work completed without touching runtime state.

Completed:
- mapped exact frozen OHLC already present in repository;
- separated real archived evidence from synthetic detector controls;
- classified BSV/CORE and CARV/CPU/CROSS/CLO owner observations as RECOVERABLE;
- kept screenshot-only training references out of deterministic Gold;
- defined the compact case schema and first G2 seed.

Canonical document:
`DOCUMENTS/GEOMETRY_GOLD_INVENTORY.md`.

RVL-R6 remains the active Robot gate. Geometry next = RVL-G2 manifest/runner;
no geometry production fix has started.

## 🌙 NIGHT CHECKPOINT — 2026-09-29

Current owner acceptance evidence is preserved. Do not repeat completed checks.

### RVL-R6 evidence captured

Owner completed one full Scanner pass:
- scanned: **778/778** symbols;
- signals found: **186**;
- Telegram deliveries reported: **200**;
- Ikigai Box observations: **43**;
- elapsed: **104:55**.

After the pass, a fresh backend instance was observed with:
- `robot_admission_ready=true`;
- `paper_live_safe=true`;
- Robot protection `healthy=true`;
- no covered, armed, or unhealthy symbols;
- ingress `current_pending=0`, `high_watermark=0`;
- Scanner durable state `SCANNER_STOPPED`.

Important limitation: ingress metrics are process-local. Because this snapshot
came from a **new backend process instance**, zero high-watermark/overflow fields
prove the fresh runtime is clean, but do **not** retroactively prove that the
previous 104-minute process never overflowed.

Telegram `/robot` on the fresh runtime returned:
- Robot: **Запущен / Готов**;
- candidates under observation: **6**;
- Robot-owned open positions: **0**.

This is strong restart/recovery non-recurrence evidence. RVL-R6 is **not yet
declared PASS** until prior-run overflow evidence is resolved or a clean
sustained run captures the required same-process metrics.

### Telegram monitoring defect found and fixed

Owner reproduced:
- `/robot` saw 6 candidates;
- `/monitoring` update was consumed (offset advanced) but no reply appeared;
- Telegram Monitoring stayed `ready`;
- no loop exception was printed.

Root cause:
- Ikigai Box durable candidate IDs are long (`box-robot-<64hex>`);
- the old callback used the full ID in
  `monitor:candidate:<candidate_id>`, exceeding Telegram's 64-byte
  `callback_data` limit;
- Telegram returned an `ok:false` response that the monitoring list path did
  not validate, producing a silent failure.

PR #325 fixed this and merged to main as
`4ab838857519adbacfa8fb4d780b3461f2717851`:
- bounded deterministic callback token;
- token resolves only against current APPROVED candidates;
- collisions fail closed;
- legacy short callbacks remain compatible;
- Telegram delivery rejection is no longer silent;
- Robot PAPER acceptance GREEN.

Owner acceptance of the fixed `/monitoring` path is still pending after local
sync/restart on #325.

### Manual PAPER CELOUSDT

`/positions` shows `CELOUSDT Long 1.3`, average entry `0.075347`,
`sync_state=reconciliation_required`.

Its detailed card explicitly says:
**"Позиция не от робота — график недоступен"**.

Therefore:
- CELO is not Robot-owned;
- `/robot` correctly reports 0 Robot-owned open positions;
- CELO is separate manual/non-Robot PAPER reconciliation debt and must not be
  silently adopted or closed by Robot;
- future Manual Position Adoption design already covers this class.

### Owner feedback queued

Already documented and preserved:
- BSVUSDT 5m false-positive Box first impulse with internal corrective swing;
- CARV/CPU/CROSS/CLO 5m recurring post-breakdown secondary Box family;
- recurring Telegram Menu visibility symptom;
- Manual Chart → Autopilot handoff / explicit Position Adoption design.

Next session should begin from this checkpoint, not rediscover these items.

## ✅ SHUTDOWN INCIDENT CLOSED — 2026-09-28

Canonical owner stop is now proven on a clean cycle from main
`d3504c695c5793dde6c41cf952276535d56a324a` (#322):

- fresh desktop start reached Robot READY and Scanner RUNNING;
- one desktop `Остановить робота` action completed;
- backend/Telegram/stop windows closed without extra input;
- post-stop read-only proof: no listeners on 8765/8766, no PAPER backend,
  Telegram worker or new stop-shell process;
- five historical idle stop-shells from the old #316 `pause` behavior were
  separately removed after exact PID/command-line verification and did not
  recur on the clean #322 cycle.

The investigation path and recurrence fast path are recorded in
`DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md`. Do not repeat the #310-#322
shutdown investigation without contradictory new evidence.

This closes the shutdown sub-incident only. **RVL-R6 remains ACTIVE** until a
real sustained owner PAPER acceptance proves protection healthy, no
`ingress_overflow`, queue drain under multi-symbol traffic, and normal
reconcile/restart without recurrence.

## 📱 TELEGRAM MENU VISIBILITY — OWNER FEEDBACK 2026-09-28

During the current real run the desktop Telegram client again shows no visible
Menu button.

Prior server-side evidence already proved `menu_button.type=commands` and all
eight commands. Queue **TG-MENU-1** after RVL-R6: one bounded server-state
re-check, then, if still correct, investigate owner-visible client/UX access
rather than repeating already-proven Bot API wiring.

Do not restart/duplicate Telegram monitoring for this presentation symptom.
Current RVL-R6 continues unless command handling itself is proven broken.

## 🧭 OWNER SIGNAL FEEDBACK QUEUED — 2026-09-28

Two Geometry Quality tasks were captured from the current real Scanner run
without interrupting RVL-R6:

- **BSVUSDT 5m** — Ikigai Box false positive: first impulse contains a real
  internal corrective swing/zigzag, not just harmless opposite-colour pause
  candles. Queue as a negative Geometry Gold case and fix the general
  structural first-impulse rule.
- **CARVUSDT 5m** — possible missed Ikigai Box after an independently detected
  Compression Triangle. Queue as a source-time evidence recovery + positive
  missed-detection investigation; an earlier Triangle must not by itself
  suppress a later independent Box.

Detailed tasks and acceptance conditions are in `DOCUMENTS/BACKLOG.md`;
Geometry Gold inventory is updated in
`DOCUMENTS/DEVELOPMENT_VALIDATION_LOOP_PLAN.md`.

Additional owner feedback from the same run broadened CARV into a recurring
candidate family: `CARVUSDT / CPUSDT / CROSSUSDT / CLOUSDT 5m` show the
visual sequence `compression -> downside sloping-boundary break -> later compact
Box-like consolidation`. Queue this as one general Geometry Quality class, not
ticker-specific tuning.

Future terminal/Autopilot UX is also frozen as a queued design in
`DOCUMENTS/MANUAL_CHART_AUTOPILOT_HANDOFF_DECISION.md`: one context-aware
Autopilot action, explicit Да/Нет adoption prompt for an open manual position,
one shared Robot workspace, immediate Robot-owned-symbol awareness on every
terminal symbol transition, and machine-readable Manual Pattern Drafts for
manual chart/Fibonacci handoff. Manual positions remain manual unless explicit
fail-closed adoption succeeds.

Active gate remains **RVL-R6**. Do not interrupt the current owner PAPER
acceptance for these geometry findings unless the owner explicitly
reprioritizes.

## 🤖 ROBOT STABILITY CHECKPOINT — 2026-09-28

PR #305 merged as `76a89efa1d48f7821b16fb5fcddf8f6de6fda60b`.

Completed:
- RVL-R2 deterministic manager-path ENTRY_PENDING overload replay;
- RVL-R3 ingress and lifecycle coverage boundary;
- RVL-R4 production fix: pre-LIMIT high-rate coverage removed, temporary coverage arm established before resting LIMIT/grid creation, gap-free handoff to durable ENTRY_PENDING, Box covered too;
- RVL-R5 regression gate GREEN: Robot PAPER acceptance workflow run `36400222441` SUCCESS with 385 passed; focused local checks green apart from two verified pre-existing unrelated failures.

Active gate:
- RVL-R6 only — one canonical owner PAPER acceptance on merged main. Required evidence: Robot legal READY, protection healthy, no ingress_overflow, queue drains under real multi-symbol traffic, normal reconcile/restart does not recreate the incident.

Known non-blocking debt remains separate: W1 orphan LIMIT crash window, fence metric overwrite on empty-symbol fence overflow, and exact source of the post-#293 64/64 incident not proven to reconcile alone.

## 🌙 CHECKPOINT НА НОЧЬ — 2026-09-28

Сегодняшний Box/Runtime acceptance сохранён, повторять пройденное не нужно.

Закрыто:
- no-WATCH owner contract;
- PR #300 tick-normalized Box grid/TAKE;
- frozen `2ZUSDT 1m` regression PASS;
- focused Box planner 11/11 PASS;
- one-action desktop start proof;
- реальный `AKEUSDT 5m -> 🤖 Робот -> Сигнал принят`;
- server-side Telegram Menu/8 commands подтверждены Bot API.

ARUSDT 1m классифицирован: это не Box-баг. Frozen stop-math дал
`NO_VALID_STOP_EXISTS`: RR>=2 требует STOP >= 4.780, а STOP строго за P4
требует <= 4.777. Пересечения нет, поэтому отсутствие `🤖 Робот` корректно.

Следующее действие разработки — основной P0 gate RVL-R6:
одна полная owner PAPER acceptance на текущем merged main. RVL-R2..R5 уже
закрыты и не повторяются.

## 🎯 АКТИВНЫЙ РЕЙД — «Две лаборатории»

**Приоритет:** P0  
**Канон:** `DOCUMENTS/DEVELOPMENT_VALIDATION_LOOP_PLAN.md` §§10–13  
**Активный квест:** **RVL-R6 — canonical owner PAPER acceptance**

Цель рейда: закрыть два главных блокирующих босса v0.1 без повторных длинных
циклов ручной проверки.

### 👹 Босс 1 — «Переполненный шлюз» / Robot Stability

Очередь:
1. ✅ RVL-R1 — replay contract/runner: PR #296, Robot PAPER acceptance #226 PASS;
2. ✅ RVL-R2 — реальный класс continuous `ENTRY_PENDING` overflow воспроизведён;
3. ✅ RVL-R3 — точная граница ENTRY_PENDING coverage;
4. ✅ RVL-R4 — минимальный production fix;
5. ✅ RVL-R5 — replay pack + focused PAPER CI;
6. ▶ RVL-R6 — один реальный owner PAPER acceptance.

Босс не считается поверженным до RVL-R6 PASS.

### 📐 Босс 2 — Geometry Quality

После Robot Stability:
RVL-G1 inventory/schema → G2 first gold set → G3 baseline report → G4
defect-class fixes → G5 invariants → G6 один полный owner Scanner acceptance.

### 🧰 После боссов

RVL-V1 compact validation report; RVL-V2 bounded capture только при доказанной
необходимости; RVL-V3 tier-aware CI.

Autopilot и остальной feature expansion сохранены в документации, но находятся
в Таверне ожидания до прохождения двух quality gates либо явного нового решения
владельца.

**Следующий технический outcome:** завершить RVL-R6: sustained real
multi-symbol PAPER traffic, protection healthy без `ingress_overflow`, queue
drain и normal reconcile/restart без повторения инцидента. Shutdown-path уже
отдельно доказан и не требует повторного расследования.

XP за сам план/очередь не начисляется.

## 🎯 Активный процессный квест — «Каждый баг оставляет карту»

**Статус:** OWNER-APPROVED / DOCUMENTED 2026-09-27  
**Канон:** `DOCUMENTS/DEVELOPMENT_VALIDATION_LOOP_PLAN.md`

После повторного реального `ingress_overflow` меняется не safety, а путь разработки:
каждый воспроизводимый реальный дефект сначала превращается в детерминированный fixture/replay, затем исправляется локально и только после GREEN нижних ворот снова тратит время владельца на реальную acceptance.

Два главных босса проекта до отдельного owner reprioritization:
- 🛡️ **Robot Stability** — «Переполненный шлюз» остаётся RED: #293 сократил reconcile примерно с 9.1 с до 1.4 с, но очередь снова достигла 64/64 и 2ZUSDT получил `ingress_overflow` при `ENTRY_PENDING` coverage;
- 📐 **Geometry Quality** — клинья/треугольники/анкеры переводятся на compact geometry golden set из реальных candles + expected anchors/negative cases.

Новые ворота разработки: **FAST → REPLAY → PAPER CI → OWNER ACCEPTANCE**.
Replay — developer regression, а не замена полного owner Scanner pass. Полный Scanner acceptance по-прежнему только один complete eligible-universe run с обычным Telegram и всеми integrated patterns.

Следующий технический slice для текущего P0: создать первый continuous multi-symbol `ENTRY_PENDING` runtime replay без искусственных drain barriers и доказать текущий overflow как RED до следующего production fix.

# BybitScanner — состояние кампании

Статус: ACTIVE  
GAME_MODE: ACTIVE  
Обновлено: 2026-09-27  
Назначение: компактная игровая проекция текущего GTD/backlog состояния для автоматического восстановления в новом чате.

> Этот файл не задаёт технический приоритет сам по себе. При конфликте текущая
> команда владельца и `DOCUMENTS/BACKLOG.md` имеют более высокий приоритет.

## 🖥️ Канонический ручной запуск владельца

Постоянная пользовательская точка входа: ярлыки на рабочем столе
`start_scanner`, `Запуск робота` и связанный ярлык остановки.

Новые результаты разработки Scanner/Robot/runtime должны автоматически
подключаться под этот существующий desktop-путь. Владелец не должен каждый
раз объяснять, чем он запускает систему, или переходить на новый терминальный
workflow. Ассистент обязан апгрейдить target/scripts за ярлыками и проверять
их соответствие текущему canonical runtime перед acceptance. Сам запуск
остаётся ручным действием владельца.

Runtime checkpoint 2026-09-27: desktop Robot start/stop path migrated and
owner-verified end-to-end. PR #280 fixed canonical safe-stop module invocation;
final stop persisted `ROBOT_STOPPED / ROBOT_STOPPED` with backend/Telegram
left alive by design. Future recurring runtime incidents must use
`DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md` before exploratory diagnosis.

## P0 interruption — Robot protection ingress, 2026-09-27

Активный квест: устранить повторный `ingress_overflow` без ослабления защиты.
Autopilot и PR #291 заморожены по текущей команде владельца.
Один bounded snapshot: 2ZUSDT/ARBUSDT/ARKUSDT = ENTRY_PENDING,
APPROVED/RETEST_DETECTED без ордеров/позиций/обязательств; durable version 91,
RECONCILIATION_REQUIRED. Slowest owner: canonical reconcile, 9065.29 ms.
Подтверждён обход candle cache в default recovery geometry provider.
Минимальный fix реализован в `codex/robot-recovery-ingress` от dedf1fd:
recovery geometry читает прогретый cache, missing/stale evidence fail-closed.
Focused evidence: 36 existing unittest checks PASS; после исправления test fixture
11 pytest checks + 2 subtests PASS (production provider, burst, FIFO, crossing,
duplicate fill, real overflow). Runtime не обновлялся; PR/merge не создавались.
Приём кандидатов и live acceptance пока не восстановлены; XP без изменений.

## Кампания

**«PAPER Robot: Гильдия паттернов»**

## Текущий уровень

- XP: **285**
- Уровень: **3 — Следопыт клиньев**
- Серия: **Комбо переиспользования ×1**

Канонический XP/ачивки/loot теперь восстанавливаются из
`DOCUMENTS/QUEST_REWARD_LEDGER.md`; этот файл — только текущая проекция.
Baseline ledger был зафиксирован на **140 XP**; затем reward reconciliation
2026-09-27 добавил только доказанные post-baseline outcomes. Текущий
канонический итог: **285 XP**. Планирование, документация, количество коммитов
и тестов сами по себе XP не добавляют.

## 🏆 Reward reconciliation — 2026-09-27

После baseline 140 XP были пропущены шесть доказанных post-baseline outcomes:
Telegram Menu (+25), shared Pattern → Robot handoff (+25), truthful Box Robot
affordance (+25), ingress-overflow evidence (+10), dual-timeframe contract
proof (+10) и завершённый owner-verified desktop runtime composition (+50).

Итого: **285 XP, уровень 3 — «Следопыт клиньев»**.

AIGENSYN не начислен повторно, потому что его production fix/merge предшествует
migration baseline. Draft PR #267 по карточке позиции также не начислен:
реальная Telegram acceptance/merge boundary ещё не закрыта.

## ✅ Побеждённый босс — Ikigai Box «Кривой первый импульс»

AIGENSYNUSDT 5m geometry defect закрыт.

- required first production slice выполнен на **Opus 5.5**;
- implementation commit:
  `1ce2aaa12920d1e6a407fe2268173299ce69fdb6`;
- first impulse теперь заканчивается на первом подтверждённом terminal structural
  pivot по существующей mirrored 3/3 pivot semantics;
- later second-leg progress больше не переносит исторический B с 19:05 на 20:00;
- harmless 1–2 opposite-colour pause candles не обрывают импульс без confirmed
  counter-swing;
- AIGENSYN regression находится в current `main`;
- `Ikigai Box detector` workflow #82: **SUCCESS**.

RED/diagnosis/Opus implementation этого дефекта повторять нельзя без нового
противоречащего evidence.

## Последний reconciliation checkpoint — 2026-09-26

Обязательный долг синхронизации/reconciliation закрыт.

- `C:\BybitScanner-sync-20260926` fast-forward синхронизирован с текущим `main`;
- `C:\BybitScanner-box-robot-run` синхронизирован с текущим `main` и сохраняет
  локальные launcher-файлы;
- уникальные локальные дельты `C:\BybitScanner` для
  `geometry/ikigai_box_chart.py` и `start_scanner.bat` сохранены побайтово
  в `C:\BybitScanner-reconciliation-backup-20260926\main-local`; сам dirty
  checkout не очищался и не перезаписывался;
- PAPER backend поднят на актуальном коде без Scanner и без LIVE;
- protection coverage восстановлено в healthy state;
- explicit operator reconciliation успешно перевёл Robot из
  `ROBOT_RUNNING / RECONCILIATION_REQUIRED` в
  `ROBOT_RUNNING / PAUSED`;
- открытая RDWUSDT PAPER-позиция не закрывалась; вход, durable trade,
  protection и ownership были согласованы; unresolved protection obligations = 0;
- admission остаётся закрытым, Scanner не запускался.

Backup и dirty локальный checkout пока сохраняются; не удалять их только ради
cleanup. Следующий активный этап — один полный owner-run PAPER acceptance.

## 🎯 Активный квест

### Рейд «Автопилот — охотник без рук»

**Приоритет:** P0  
**Статус:** IMPLEMENTATION PLAN FROZEN; NEXT = STAGE A SHADOW FOUNDATION  
**Канонический план:** `DOCUMENTS/ROBOT_AUTOPILOT_IMPLEMENTATION_PLAN.md`

**Цель:** Robot сам находит поддерживаемые кандидаты, проверяет их через
единые admission/risk gates и в PAPER_AUTO передаёт разрешённые сделки в уже
существующий Robot execution/protection/recovery lifecycle без нажатия
владельцем `🤖 Робот`.

Архитектурный контракт:
- discovery/selection — новый слой;
- immutable candidate/plan — существующие pattern adapters;
- admission — только существующий canonical boundary;
- execution/protection/reconcile — только существующий Robot;
- сначала `OFF → SHADOW`, затем `PAPER_AUTO`;
- SHADOW ничего не торгует и должен объяснять WOULD_ADMIT / WAIT / REJECT;
- WATCH не торгуется;
- LIVE запрещён;
- portfolio/risk значения для unattended PAPER не изобретаются кодом и должны
  быть явно заморожены до Stage D.

Последняя подготовленная добыча: PR #288 merged as
`6e865536cd1cd1a5cf7a7211576e1fe5d8b57be8`; Box manual admission boundary
теперь отделён от Scanner, поэтому поверх него можно строить Autopilot без
скрытого auto-admission.

**Следующий кодовый slice:** Stage A — durable Autopilot
`OFF/SHADOW/PAPER_AUTO` state + pure read-only SHADOW policy + минимальный
audit решений. Никаких order/admission mutations в этом slice.

## 🕓 Предыдущий активный квест — acceptance остаётся в очереди

### Рейд «Один запуск — весь прототип»

**Приоритет:** P0  
**Статус:** ONE-ACTION INTENT COMPLETE; FINAL FULL OWNER ACCEPTANCE RUNNING / NOT YET COMPLETE  
**Цель:** сделать один канонический owner-start путь, после которого PAPER
backend, Robot protection/admission, Telegram callbacks/menu и Scanner имеют
по одному владельцу, одну runtime authority и проверенную readiness-цепочку.

Причина переключения: 2026-09-26 длинный acceptance-run был начат после
неполного preflight. Backend и Robot были READY, но Telegram callback worker
не работал; дополнительно обнаружен split-brain Scanner ownership:
standalone `main.py` и backend `ScannerControlRuntime` являются разными
владельцами и могут породить дубли.

**Этапы рейда:**

- [x] PR #249 merged (`2032188`): one-pass authoritative Scanner runtime с pause/resume/stop;
- [x] PR #251 merged (`b02e330`): canonical launcher больше не запускает standalone `main.py`; Scanner стартует через backend `/api/scanner/start`;
- [x] PR #252 merged (`1e07dec`): Telegram getUpdates worker теперь singleton + observable readiness;
- [x] PR #254 merged (`fe56450`): backend bind/reserve 127.0.0.1 listener происходит ДО REST/WebSocket/SQLite/runtime/recovery side effects;
- [x] PR #253 merged (`18fc8c2`): Scanner restart-safe + launcher lifecycle-aware;
- [x] PR #255 merged (`0f209e7`): backend `/api/health` теперь подтверждает canonical PAPER backend, live owner и database identity;
- [x] PR #256 merged (`f7815fe`): canonical launcher переиспользует уже живой canonical PAPER backend с совпадающей database identity;
- [x] startup-path закрыт fail-closed: backend PR #257, Robot admission PR #258, Robot/protection barrier PR #259, Telegram DB identity health PR #260, launcher Telegram/backend identity match PR #261, backend PAPER/config safety health PR #262, launcher safety enforcement PR #263;
- [x] PR #265 merged (`15ad7aa`): failure Robot candidate persistence теперь даёт одно owner-only Telegram warning после обычной доставки сигнала, без декоративной Robot-кнопки и без утечки exception/DB/path деталей;
- [x] PR #264 merged (`5852a09`): explicit 1m Wedge больше не observational-only; Robot handoff строится только после успешного evidence projection/cursor и остаётся fail-closed при ошибке;
- [x] PR #266 merged (`90b8559`): stale FLOCK synthetic fixture приведён к owner rule 2026-09-23 — A теперь actual local reversal origin; detector не менялся, red-core и 55%/12% box-boundary coverage сохранены; Ikigai Box detector CI SUCCESS;
- [x] 2026-09-27 owner desktop launch доказал backend READY, PAPER/LIVE safety, Robot RUNNING/READY, admission/protection READY, Telegram Monitoring на той же DB и реальный Scanner traversal;
- [x] Scanner Pause/Continue state semantics подтверждены owner-run: пауза реально остановила новые сигналы, повторный вход показал ту же `/scanner` как `▶ Продолжить сканер`;
- [x] PR #271 merged (`e0afeee`): общий Telegram Menu reassert после owner messages/callbacks;
- [x] PR #274 merged (`878d18d`): общий Pattern → Robot pre-admission handoff для Wedge/L-shape;
- [x] PR #275 merged (`03d19cb`): у non-executable Ikigai Box убран ложный `🤖 Робот` status-affordance; Box execution остаётся fail-closed до authoritative executable contract;
- [x] PR #276 merged (`0f72355`): canonical tracked safe-stop path без process-title kills/forced close;
- [x] owner-PC: current `main` загружен, desktop Robot start/stop path перенаправлен на canonical tracked launchers и safe-stop owner-run подтверждён;
- [x] P0.5: PR #285 (`543168420afaab3b0dde9be083969ff867b69263`) реализовал общий Runtime Intent Reconciler; owner-run desktop `Запуск робота` доказал one-action ALL до Robot READY + Scanner RUNNING;
- [ ] завершить чистый полный owner-run PAPER acceptance после текущих P0 stability gates. Частичный checkpoint уже доказал реальный CONFIRMED AKEUSDT 5m -> `🤖 Робот` -> `Сигнал принят`; server-side Telegram Menu подтверждён Bot API. ARUSDT 1m больше не считается blocker: frozen stop-math доказал корректный fail-closed non-executable setup under P4 + net RR >= 2.

**Награда:** без XP за документацию/рефакторинг; награда только за доказанный
полный запуск без ручного кризисного восстановления.

Предыдущий рейд «Г-образные врата» не отменён: PR #248 merged, но его
реальная PAPER acceptance временно ждёт завершения этого P0 operational gate.

## 🧭 Новый P0-квест — «Одно намерение — один запуск»

Owner evidence 2026-09-27 показал новый orchestration gap: после штатного
safe-stop нормальный desktop `Запуск робота` остановился на
`robot_admission_ready=false`, потому что Robot был корректно
`ROBOT_STOPPED / ROBOT_STOPPED`. Для продолжения требовался отдельный
Telegram START и повторный запуск ярлыка.

Это больше не считается допустимым normal UX.

Канонический план:
`DOCUMENTS/RUNTIME_INTENT_RECONCILER_PLAN.md`.

Цель квеста: владелец одним действием задаёт `SCANNER`, `ROBOT` или `ALL`;
система сама проверяет authoritative state, запускает/reuse'ит зависимости,
делает допустимые START/RESUME/reconcile переходы, перепроверяет postconditions
и либо достигает desired state, либо один раз возвращает точный
неисправимый blocker. Ручные промежуточные проверки/переключения в normal
flow запрещены.

Full owner acceptance остаётся обязательным, но теперь идёт **после** этого
P0 gate и должен доказать именно one-action запуск из безопасного
неподготовленного состояния.

## 🚧 Временные ворота активного рейда

### «Портал не должен исчезать»

Owner-run 2026-09-27 подтвердил Scanner Pause/Continue semantics, но выявил
общий UI-дефект: после управляющего действия Telegram Menu button может исчезнуть
из уже открытого чата и появиться только после повторного входа. Dynamic
`/scanner` label при этом корректно меняется на `▶ Продолжить сканер`.

PR #271 merged as `e0afeee`; common menu-button lifecycle исправлен в
repository state. До загрузки current `main` на owner PC прежний runtime всё
ещё остаётся pre-fix evidence, а не acceptance исправления.

### «Один портал для всех зверей»

Ikigai Box сигнал показал `🤖 Робот`, но callback открыл только Robot status,
поскольку текущий Robot state-machine поддерживает Wedge, а не Box candidate
admission. Это признано архитектурным boundary defect: общий Telegram/Robot
lifecycle не должен заново проектироваться для каждого паттерна.

Канонический стандарт:
`DOCUMENTS/PATTERN_ROBOT_INTEGRATION_STANDARD.md`.

PR #274 merged as `878d18d`: общий pre-admission handoff вынесен в
`pattern_robot_integration.py`; Wedge и L-shape используют один boundary.
L-shape дальше уже идёт через общий admission/monitor/execution/protection/
reconcile lifecycle. PR #275 merged as `03d19cb`: Box больше не показывает
ложный Robot status-action. Box execution остаётся намеренно закрытым до
authoritative executable contract.

### «Переполненный шлюз»

Robot protection ingress ранее дал `ingress_overflow`, после чего штатный
fail-closed recovery аварийно закрыл owned позиции и оставил Robot в
`ROBOT_RUNNING / RECONCILIATION_REQUIRED`. Аварийное закрытие не считать
дефектом защиты; отдельный незакрытый босс — причина переполнения ingress.
Перед новыми PAPER admission требуется штатная evidence-based сверка.


### «Сломанный телепорт Codex»

Read-only разбор торговли Robot за 25.09.2026 ещё не выполнен. Codex Desktop
повторно отвечает `401 Incorrect API key`, хотя локальная диагностика
подтверждает ChatGPT auth, отсутствие сохранённого API key и доступность
ChatGPT endpoint. Desktop остаётся на 26.917.9434.0 при доступной
26.924.1866.0; встроенное обновление пока не меняет установленную версию.
Сначала восстановить рабочий Codex Desktop, затем сделать только read-only
аудит сделок/PnL. Отдельный `helper_sandbox_lock_failed` не считать дефектом
BybitScanner без доказанной связи.

## 🗓️ План на сегодня — 2026-09-27

Binding owner order:

1. 🧭 **P0 — Постоянный Telegram Menu**
   - довести PR #271;
   - Menu не исчезает после Scanner/Robot owner actions;
   - та же `/scanner` мгновенно отражает Pause/Continue/Start state.

2. 🧩 **P0 — «Один портал для всех зверей»**
   - реализовать общий Pattern → Robot integration contract;
   - общий candidate/admission, execution ownership, protection, position cards,
     lifecycle notifications, monitoring/reconcile;
   - pattern-specific оставить только evidence + trading strategy adapter.

3. 🐉 **P0 — Миграция паттернов на общий lifecycle**
   - Wedge сохранить как reference adapter;
   - Box: убрать misleading status action и подключать реальный candidate только
     через общий admission;
   - L-shape: тот же shared lifecycle со своими trading rules;
   - не изобретать недостающие strategy parameters.

4. 🖥️ **P0 — Закрыть desktop runtime debt**
   - GitHub-side safe stop закрыт PR #276 (`0f72355`);
   - remaining owner-PC step: загрузить current `main`, перенаправить постоянные Robot start/stop shortcuts на canonical tracked launchers;
   - затем runtime-check safe stop; GitHub-side safe-stop work не повторять.

5. 👹 **P1 — Ikigai Box «Кривой первый импульс»**
   - продолжить уже доказанный AIGENSYN RED на Opus 5.5;
   - diagnosis не повторять.

6. 🏁 **P1 — Один чистый полный owner-run acceptance**
   - только после загрузки P0 fixes;
   - полный universe, обычный Telegram, все integrated patterns;
   - Menu persistence + Pause/Continue + real Robot candidate admission where supported.

7. 🏢 **P2 — Full dual-timeframe 5m→1m**
   - per-symbol 5m then 1m;
   - independent symbol × timeframe × pattern × formation state.

Текущий pre-fix Scanner run полезен как exploratory evidence, но не может
принять исправления, которых в его runtime ещё нет.

## 📜 Исторический план — 2026-09-26

Работаем строго в таком порядке:

1. 🧹 **Разобрать старые открытые PR недели**
   - закрыть superseded/obsolete;
   - оставить только реально нужные;
   - ничего не merge'ить механически.

2. 🎨 **Карточка открытой позиции Robot**
   - увеличить пространство справа от последних свечей;
   - убрать слово «Вход», оставить уровень/цену;
   - «Стоп» / «Тейк» заменить на `SL` / `TP`;
   - уменьшить execution triangles;
   - цвет контура по направлению позиции;
   - `Размер` = quantity + USDT notional;
   - добавить под карточкой кнопку **«Открыть в Trading View»** для текущего symbol;
   - под всеми Scanner-сигналами переименовать существующую TradingView-кнопку в **«Открыть в Trading View»**.

3. 👹 **Ikigai Box — «Кривой первый импульс»**
   - AIGENSYNUSDT 5m;
   - исправлять общий first-impulse construction rule;
   - FLOCK regression не переоткрывать без нового доказательства.

4. 🏢 **Полный dual-timeframe Scanner 5m→1m**
   - для каждого symbol сначала 5m, затем сразу 1m;
   - независимые symbol × timeframe × pattern × formation identity/dedup/evidence.

Этот порядок действовал 2026-09-26 и теперь сохранён только как исторический checkpoint.

## 📜 Historical owner order — 2026-09-26 (superseded 2026-09-27)

Исторический порядок работ владельца:

1. 🧹 **Разобрать старые открытые PR недели** — triage открытых PR: закрыть superseded/obsolete, оставить только реально нужные; ничего не merge'ить механически.
2. 🎨 **Карточка открытой позиции Robot** — Telegram position card refinement без изменения торговой логики; добавить под карточкой кнопку **«Открыть в Trading View»** для её symbol и унифицировать подпись соответствующей TradingView-кнопки под **всеми Scanner-сигналами** на **«Открыть в Trading View»** (сейчас signal-кнопка подписана `📈 Open TradingView`).
3. 👹 **Ikigai Box — «Кривой первый импульс»** — AIGENSYNUSDT 5m и общий first-impulse construction rule; FLOCK regression уже закрыт и не должен переоткрываться без нового доказательства.
4. 🏢 **Полный dual-timeframe Scanner 5m→1m** — per-symbol 5m then 1m, независимые symbol × timeframe × pattern identities/dedup/evidence.

Этот owner order **временно supersede'ит** прежнее утверждение, что следующий шаг — немедленный полный PAPER acceptance. Acceptance остаётся обязательным финальным gate для соответствующих Scanner/runtime изменений, но не должен вытеснять перечисленные четыре задачи раньше времени.

## Очередь после активного квеста

### 2. 👹 Босс «Кривой первый импульс»

Ikigai Box first-impulse geometry. Конкретный дефект: AIGENSYNUSDT 5m.

Правило владельца:

- отчётливая встречная коррекционная волна завершает первый импульс;
- допускаются только 1–2 небольшие встречные свечи как пауза;
- если они формируют отдельный локальный counter-swing, это уже конец импульса.

Связанный FLOCK baseline рассматривается в том же geometry-slice только если
причина действительно общая.

### 3. 🧰 Побочный квест «Приодеть карточку позиции»

Telegram open-position card:

- больше места справа от последних свечей;
- убрать слово «Вход», оставить уровень/цену;
- «Стоп» / «Тейк» -> `SL` / `TP`;
- уменьшить execution triangles;
- цвет контура по направлению;
- `Размер` = quantity + USDT notional;
- добавить под карточкой позиции кнопку **«Открыть в Trading View»** для текущего symbol;
- под всеми Scanner-сигналами переименовать существующую TradingView-кнопку в **«Открыть в Trading View»**; сейчас общий signal keyboard использует `📈 Open TradingView`.

Торговую логику не менять.

## Таверна ожидания / отложено

- **Рейд «Много зверей — один тикер»** — multi-pattern Scanner:
  все паттерны 5m -> все паттерны 1m -> следующий тикер.
- **Квест «Ночной дозор»** — FocusedPatternMonitor для новых структур после
  ухода Full Scanner.
- синхронизация/ручной restart PC runtime с сегодняшним новым main — только
  когда владелец решит перезапускать runtime; не прерывать текущую сессию
  автоматически.
- полный real Scanner acceptance — только по существующему owner-run правилу.

## Открытые ачивки

- ✅ **«Повелитель барьера»** — #237: reconnect barrier больше не уничтожает
  валидные pre-disconnect события из-за задержки owner FIFO.
- ✅ **«Феникс»** — reconcile восстановил корректный Robot lifecycle без ручных
  правок БД; затем владелец штатно вернул Robot в READY через Telegram.
- ✅ **«Новый монстр, старый движок»** — #274: L-shape/Wedge идут через общий Pattern → Robot handoff без второго execution engine.
- ⬜ **«Один тикер — много зверей»** — будущий multi-pattern Scanner.
- ⬜ **«Оба этажа зачищены»** — будущий полный 5m+1m per-symbol traversal.
- ⬜ **«Ночной дозор»** — будущий FocusedPatternMonitor.
- ✅ **«Контекст не потерян»** — 2026-09-27 новый чат без ручного handoff
  восстановил из репозитория актуальный проектный state и видимый игровой
  режим; зафиксировано в `QUEST_REWARD_LEDGER.md` без дополнительного XP.


## Последняя доказанная добыча

- ordered disconnect/reconnect continuity barrier;
- regression/acceptance proof для protection continuity;
- единый owner desktop runtime start/stop path с доказанными PAPER/LIVE safety,
  Robot admission/protection, Telegram same-DB readiness и canonical safe-stop;
- `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md` — короткие повторно используемые
  пути диагностики/recovery, чтобы не расследовать известные runtime-сбои с нуля;
- Opus 5.5 structural terminal-pivot fix для AIGENSYN first impulse, подтверждённый Ikigai Box detector CI #82;
- `DOCUMENTS/PATTERN_ROBOT_INTEGRATION_STANDARD.md` — общий Signal → Robot
  integration/UX контракт для всех паттернов;
- `DOCUMENTS/QUEST_REWARD_LEDGER.md` — append-only authority для XP,
  ачивок и reusable loot;
- два утверждённых архитектурных плана:
  multi-pattern Scanner и FocusedPatternMonitor;
- русская GTD Quest System;
- стабильный Custom Instructions bootstrap для автоматического нового-чата и
  быстрого освежения контекста;
- 2026-09-27 новый чат подтвердил полный repository-driven bootstrap вместе с
  видимым игровым response-mode; ачивка «Контекст не потерян» открыта.

## Response-mode contract

Пока `GAME_MODE: ACTIVE`, новый или продолжающийся BybitScanner-чат должен не
только загрузить этот save-game, но и **видимо продолжать работу в русском
игровом/GTD режиме**. На рабочих переходах кратко использовать актуальную
игровую сущность (рейд, квест, босс, ворота, добыча, достижение), не раздувая
технические ответы. Если после bootstrap ответ стал обычным техническим и
игровой слой пропал, это считается потерей режима и должно быть исправлено
автоматически до отправки следующего ответа.

`GAME_MODE: ACTIVE` не меняет техническую authority, scope, safety,
acceptance, runtime ownership или PAPER/LIVE permissions.

## Правило автоматического восстановления

При первом BybitScanner-сообщении нового ChatGPT-чата:

1. загрузить `AGENTS.md`;
2. восстановить минимальный task-scoped контекст;
3. прочитать этот файл;
4. сверить его с верхним текущим priority index в `DOCUMENTS/BACKLOG.md`;
5. если пользователь в новом чате сразу даёт новый приоритет — он побеждает;
6. продолжить уже в русском игровом режиме;
7. не просить пользователя вручную переносить этот контекст.

Если этот файл устарел относительно BACKLOG, исправить его при ближайшем
документационном checkpoint, а не следовать устаревшему квесту.

В существующем чате короткая команда владельца «освежи контекст» означает
быстро сверить этот save-game с актуальными BACKLOG/owning spec и сообщить
только важное изменение. Команда `э` продолжает активный квест; если state
сомнительно свежий, перед продолжением выполняется такое быстрое освежение.
