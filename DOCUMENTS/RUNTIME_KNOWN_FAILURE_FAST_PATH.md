# BybitScanner — Runtime Known-Failure Fast Path

Status: ACTIVE  
Date: 2026-09-27  
Purpose: compact evidence-first runbook for recurring Scanner / PAPER Robot / Telegram / desktop-launch failures.  
Primary objective: minimize owner time. Known failure classes are diagnosed from repository authority and one bounded host snapshot before any exploratory sequence.

## PAPER P0 — Gitless EDITOR_ONLY после #855: неудачный immutable staging (05.11.2026)

**Инцидент и безопасная граница.** Установленный VPS release `4090641514b8f558a0054fd577b2750b944fd8d6`; Robot `ROBOT_RUNNING / RECONCILIATION_REQUIRED`, Scanner STOPPED, Autopilot OFF. По последнему отчёту Codex JASMYUSDT/FLOWUSDT подтверждены FLAT встречными executions, `nonrobot_close_proof` и ownership PASS; unfinished LIMIT/commands/protection obligations = 0, protection healthy, PAPER DB integrity OK. Это **предыдущий снимок, не текущая runtime-аттестация**. Reconcile POST и `runtime_intent ROBOT` ещё не выполнялись; READY не доказан.

**Два воспроизведённых отказа, один класс:** immutable staging `c3219ab73bfb0054af8d2c0257b1919ec6d76a9d` отказал, потому что HEAD stable уже был `dec84f01a7d4e84d0878296edcebf0489914606e`; повторная попытка staging `dec84f01…` отказала после движения HEAD на `1121f5ac2f8e923c20133a14d9146e902c662032`. Оба `command_failed_exit_128` были **до staging**: STOP, deploy, restart, receipt, reconcile и runtime_intent не выполнены, DB и установленный release не изменились. Позднее HEAD продвигался дальше. Привязка staging к HEAD является **доказанным источником отказа**, а не признаком повреждения PAPER или новой ошибки Robot.

**Уже реализовано:** PR #855 (merged, `c3219ab…`) исправил финализацию защищённого `editor-ready` для exceptional prior-target Gitless handoff с повторным использованием оригинальных receipts и сверкой установленного release; код `tools/paper_maintenance.py` имел одинаковый Git blob на `c3219ab…` и `1121f5ac…`. Это **исправление кода**, не receipt, не выполненный reconcile и не runtime acceptance.

**Кратчайший путь при повторении:**
1. Если staging вернул exit 128 **до начала VPS-операций**, не повторять STOP/deploy и не трактовать это как неизвестный исход торгового действия. Проверить только фазу операции и актуальную допустимую ревизию через существующий GitHub-мост.
2. Если текущий мост требует HEAD=target, брать актуальный HEAD *непосредственно в разрешённой операции* и проверять наличие #855 и нужных неизменных инструментов. Не пересылать владельцу цепочку устаревающих SHA. Это **временный способ обхода гонки**, не гарантированное решение при новом изменении HEAD.
3. **Постоянный инженерный фикс — ещё НЕ реализован:** в существующем мосте однократно аттестовать разрешённый immutable commit/content и затем продолжать staging на этой идентичности, без повторной зависимости от изменяющегося HEAD. Найти и исправить именно владеющий этим сравнением компонент; не ослаблять проверку источника, целостности и разрешений, не строить второй мост.
4. Только после реально успешного staging: по уже разрешённому bounded recovery проверить защищённые exceptional receipts/EDITOR_ONLY, завершить `editor-ready` без повторного STOP/deploy, подтвердить JASMY/FLOW ownership/FLAT и отсутствие obligations, максимум один canonical reconcile (только после всех gates), затем существующий `runtime_intent ROBOT` и проверка READY/Admission/protection/DB. Scanner — только владелец, PAPER_AUTO не включать без соответствующих полномочий. Не выполнять команду с неизвестным результатом повторно.

**Правило принятия решения:** `exit_128 before staging` = проблема GitHub-моста, не причина нового торгового recovery. `editor-ready` = подтверждение перехода установленного редакторского контура, **не** право на торговлю. `READY` объявлять только по свежему VPS-доказательству. LIVE, raw Market, ручная правка SQLite и обход STOP/TAKE запрещены.

## PAPER P0 — цепочка блокировок доказательства APPROVED после незавершённого STOP (2026-11-04)

**Назначение:** готовый путь повторного применения, не новый квест. Цель владельца прежняя: безопасно завершить монолитное обслуживание PAPER, установить готовый релиз и принять редактор через Telegram. **Нельзя** «лечить» инцидент последовательным разрешением всё новых ревизий, повторением STOP или обнулением одноразовых маркеров.

### Подтверждённые факты и причины (отделять от гипотез)

1. **INUSDT — подтверждённая причина первоначальной ложной блокировки.** Инцидентная проверка ранее требовала, чтобы *все исторические* LIMIT-ордера по символу имели `cancelled` и нулевое исполнение, не ограничиваясь текущим APPROVED-кандидатом. READ-ONLY staging [run 41738096705](https://github.com/svobodaXXI/BybitScanner/actions/runs/41738096705) доказал: **ровно 2** предшествующих APPROVED ордера `cancelled` с **положительными частичными исполнениями**, оба с executions и robot_entry_orders, без box_order_ownership. Это **не** «невыполненные» ордера. **Готовое решение:** PR #829 дал агрегированную диагностику без ослабления gate; PR #830 разрешил *исключительно два старых INUSDT-ордера* лишь при точной сверке объёмов executions, нулевом подписанном итоге всего журнала, отсутствии новых fills, открытых Robot trades и при синхронизированной FLAT-проекции. [READ-ONLY preflight 41744174822](https://github.com/svobodaXXI/BybitScanner/actions/runs/41744174822) после #830 показал PREFLIGHT_PASS. Запрещено общее правило «cancelled значит не исполнен».
2. **Незавершённый STOP — доказанный прерыватель перехода, причина изменения ревизий ещё не атрибутирована.** Один разрешённый `/paper-vps execute 094d74f...` прошёл preflight, записал `EXECUTE_INTENT_FSYNCED`, затем завершился `BLOCKED: canonical_safe_stop_unproven; no retry, no deployment` — [run 41744751691](https://github.com/svobodaXXI/BybitScanner/actions/runs/41744751691). После этого оставлены `chatops_marker=true`, `stop_marker=true`, `install_journal=false`. На [READ-ONLY диагностике 41747040889](https://github.com/svobodaXXI/BybitScanner/actions/runs/41747040889) backend всё ещё работал на `f100ef369a1105443332b5729b558464c27be48f`; Scanner STOPPED, Autopilot OFF, Robot RUNNING/RECONCILIATION_REQUIRED, две OPEN Robot-trades, ноль активных LIMIT, защита unhealthy (2). **Из этого нельзя вывести**, какое именно внутреннее действие STOP/Robot изменило candidate metadata. Повторный execute/STOP и сброс маркеров не разрешены.
3. **BNCUSDT — доказанный drift ожидаемой ревизии, не доказанная причина drift.** До execute строгий proof принимал `APPROVED / revision=6 / RETEST_DETECTED`. После попытки STOP READ-ONLY показал `APPROVED / revision=7 / RETEST_DETECTED` (тип JSON object), а preflight [41744921288](https://github.com/svobodaXXI/BybitScanner/actions/runs/41744921288) блокировал `revision_or_state_type_mismatch`. Причина *отказа proof* — жёсткое ожидание `6`; причина *изменения ревизии* не установлена. **Готовое решение:** PR #833 допускает только BNC ревизию 7 при неизменной фазе и всей проверке отсутствия executions, незакрытых ордеров, commands/trades и конкурирующего владельца. Регрессионные тесты отвергают revision=8, другую фазу и fill. Это изменение доказательства, **не** завершение STOP и не разрешение на продолжение.
4. **PLAYSOUTUSDT — новый обнаруженный BLOCKED, первопричина НЕ УСТАНОВЛЕНА.** После #833 [READ-ONLY preflight 41750752442](https://github.com/svobodaXXI/BybitScanner/actions/runs/41750752442) прошёл staging точного `2fb98b8d2a5143b9c723f7c9e6973628f57a80d0`, но остановился на `PLAYSOUTUSDT:revision_or_state_type_mismatch`. Код ожидает `revision=4, RETEST_DETECTED`. **Фактическая ревизия и тип на VPS не считаны в этом запуске**; ошибка допускает и несовпадение ревизии, и неверный тип JSON. Не утверждать, что revision вырос, что кандидат был исполнен или что STOP это вызвал.

### Готовый алгоритм для следующего аналогичного случая (один проход по всем владельцам)

1. **Один READ-ONLY снимок всех APPROVED-кандидатов**, а не по одному символу/PR: точные candidate ID, status, revision, phase, timestamp APPROVED, исходный Box/Mirror owner, история переходов; отдельно все LIMIT (status, filled_quantity, created_at), executions, trading_commands, robot_entry_orders, box_order_ownership, box_attempt_ownership, Robot trades, position projections и текущие HTTP snapshots/protection. Доступ к фактическим данным только через разрешённый защищённый канал; в публичные Actions-логи — лишь ограниченные категории, без идентификаторов и секретов. Если фиксированный `diagnose` ещё не возвращает нужные поля, расширять только фиксированный READ-ONLY отчёт, а не исполнять произвольный SQL или повторять мутации.
2. **Сопоставить с до-STOP доказательством и журналом операции.** Отдельно доказать порядок/источник каждого перехода состояния (где возможно по имеющимся audit records), не приписывать причины только по корреляции во времени. Проверить все шесть кандидатов сразу, чтобы не проходить цепочку INUSDT → BNCUSDT → PLAYSOUTUSDT отдельными попытками.
3. **Разрешать только подтверждённый инертный исторический прогресс.** Строгие identity, phase, order/fill provenance, отсутствие post-approval executions, pending/unknown orders, commands, конкурентных owner и OPEN trades; независимо FLAT/quiescent и неизменный PAPER DB identity. Отсутствующая или неоднозначная запись = **BLOCKED**. Никогда не корректировать данные SQLite вручную, не подменять текущий status, не превращать revision range в универсальный allowlist.
4. **После узкой кодовой поправки** — адресные synthetic/regression tests, merge только с отдельным разрешением, **один** exact-SHA READ-ONLY preflight. При PASS это доказывает лишь готовность к следующему *разрешённому* шагу, не безопасность повторного STOP. Уже записанные one-shot markers требуют отдельного, доказательно безопасного recovery/resume контракта; любой неизвестный исход = **STOP**.
5. **Вернуться к цели владельца:** только после защищённого перехода установить релиз и реально проверить Telegram → редактор → исходную и редактируемую геометрию → сохранение → повторное открытие. PR, тесты и preflight сами по себе не являются готовностью UI на VPS.

**Операционный урок:** различать *исторические исполнения*, *неидемпотентную остановку* и *изменение метаданных кандидата*. Не порождать отдельные исправления «на каждый следующий символ», пока не снят один согласованный срез по всем шести. При любом неизвестном STOP сохранять runtime и маркеры; не проводить hot upgrade и LIVE.

## VPS normal one-action stop: blocker register (2026-11-01)

Current stage: protected PAPER exposure was flattened by a separately approved one-shot Close All, but normal full stop and release installation have not yet been verified. Target stable is 12cc0822; installed marker was 86fda079; running process SHA was not attested.

- Running Scanner, PAPER_AUTO, active positions and entry LIMIT initially blocked shutdown. Autopilot was switched to durable OFF; Scanner stopped through its canonical API, while Backend/Robot continued maintaining STOP/TAKE.
- A direct control process failed before any mutation: shell quoting supplied database_path with spaces around the absolute database pathname. SQLite interpreted it as a nonexistent relative path. The authoritative PAPER DB remained intact. Never infer DB corruption from this failure or recreate the DB.
- The Telegram worker has no HTTP pause endpoint. Its canonical Robot Pause is triggered by an authenticated owner Telegram callback. The owner pressed Pause; durable Robot became RUNNING/PAUSED, and synchronisation cancelled all 15 remaining entry LIMIT without fills or unresolved pending protection.
- The exceptional flat_paper_recovery_gate is specifically for RECONCILIATION_REQUIRED and the historical BUSDT STOP incident, **not** ordinary RUNNING/PAUSED FLAT shutdown. Its unexpected_robot_state response on a healthy PAUSED robot is expected. Never force the Robot into an error state to make this gate pass.
- The owner-authorized PAPER Close All closed the final BLUAIUSDT Long 8240 for Net -0.3019660520 USDT. Following that close: positions 0, active LIMIT 0, unfinished commands 0, unresolved obligations 0, protection healthy and quiescent, Scanner STOPPED, Autopilot OFF, Robot RUNNING/PAUSED.
- The canonical full stop belongs to tools.stop_robot_runtime, which transitions the stoppable Robot to STOPPED then shuts down Telegram and Backend, with Backend last. Each current ownership and quiescence condition must be re-proven; do not rerun ambiguous mutations, bypass protections or manually change DB state.
- After demonstrated full stop, install needs exact code/build provenance and unchanged PAPER DB identity, then protected start acceptance. A release marker or GitHub merge alone does not prove a running target version.

- **New post-install resume blocker:** the canonical full stop and exact tracked release installation of `12cc082267cfd3631642a5923b54be80bcb2e85e` were reported successful, with all PAPER units stopped and protected manifest verified. Read-only `tools.vps_release_resume` then returned `unexpected_systemd_dropin`, because its `_systemd_state` rejects **every** nonempty `DropInPaths`. Existing backend `telegram-proxy.conf` and Telegram `proxy.conf` / `terminal-ingress.conf` must not be erased: these are user-owned network/Terminal configurations. Filenames alone do **not** prove safety; inspect complete installed bytes, ownership, paths, and effective `systemctl cat/show` directives before a narrowly-scoped acceptance change. Keep reject-on-unknown and protections for `ExecStart`, `ExecStop`, `User`, DB identity, `Restart`, `KillSignal`, `SendSIGKILL`, environment and privilege boundaries. Do not bypass the resume gate or mutate already verified tracked release files in-place. No start authority is inferred from installed SHA or passed stop.

This is an incident record and next-step boundary, not evidence of completed monolithic shutdown/restart. The owner authorized the guarded full stop and subsequent update; neither has yet been observed.

## Stuck PAPER recovery / release switch — 2026-11-01

For `RECONCILIATION_REQUIRED` with BUSDT-like `DISPATCHING` STOP, stale incident coverage, unversioned backend, or partially completed release transition, **do not rediscover this case**: read [PAPER VPS recovery postmortem and state-based runbook](PAPER_VPS_RECOVERY_POSTMORTEM_20261101.md) and apply only the branch proven by the **current** host state. Especially: no HTTP inside SQLite writer barrier; an inactive systemd unit *after* authorized SIGINT may prove exit rather than failed preflight; when backend is already absent, do not repeat transition; release without `.git` needs exact tracked-content verification; load units after `daemon-reload` before `reset-failed`; canonical BUSDT reconcile comes **before** opening admission/PAPER_AUTO. Incident-specific legacy PID and flags must not be reused. The 2026-11-01 outcome was RECOVERED as reported by Codex, but post-SIGINT classification, systemd ordering and automatic build attestation still have open engineering debt. Preserve any new protected PAPER exposure on the running host.

## Universal principle

**Known path before investigation.**

When a runtime symptom belongs to a previously documented class, the assistant must:

1. load the known path and current committed entrypoint first;
2. identify the smallest authoritative state that can decide the class;
3. obtain missing host-only evidence in one bounded read-only snapshot where possible;
4. apply the existing recovery/repair path if the signature matches;
5. broaden the investigation only when the evidence contradicts the known signature.

Do not rediscover launchers, routes, state machines, recovery transitions, process ownership rules, database authority or acceptance rules that are already documented and unchanged.

A repeated incident should normally cost the owner **at most one diagnostic round-trip before the known repair/recovery action**. If more is genuinely required, name the exact new unknown that prevents use of the fast path.

## Runtime decision order

For Scanner / Robot / Telegram / backend incidents, classify in this order:

1. **Entrypoint / launcher failure**
   - Read the current tracked launcher and helper first.
   - If Python reports repository-package import failure from a helper under a subdirectory, check script-vs-module invocation before inspecting Robot state.
   - Canonical Windows rule: repository helpers that import project packages run from repository root as modules when appropriate (`python -m ...`), not as direct subdirectory scripts that change `sys.path[0]`.

2. **Durable Robot recovery state**
   - Read `get_robot_runtime_status()` from the configured PAPER DB.
   - Never infer Robot authority from a process window.
   - `RECONCILIATION_REQUIRED` is a fail-closed latch, not permission to edit SQLite.
   - If current evidence may already be settled, inspect candidate/trade/executions/position projection read-only, then use the canonical reconciliation route.

3. **Canonical reconciliation**
   - Legal state: `ROBOT_RUNNING / RECONCILIATION_REQUIRED`.
   - Operator route: `POST /api/robot/reconcile`.
   - Success lands in `ROBOT_RUNNING / PAUSED` with unresolved candidate/trade/obligation sets empty and `reason=None`.
   - Do not hand-clear `recovery_status`.

4. **Canonical safe stop**
   - Legal Robot states: `ROBOT_RUNNING / READY` or `ROBOT_RUNNING / PAUSED`; reconciliation remains fail-closed when required.
   - Owner surface: desktop shortcut `Остановить робота` -> tracked `C:\BybitScanner\stop_robot_runtime.bat` directly.
   - Full-stop success means Scanner STOPPED, Robot `ROBOT_STOPPED / ROBOT_STOPPED`, Telegram monitoring gone, and PAPER backend gone.
   - Never put an untracked/local wrapper between the desktop shortcut and the tracked stop launcher.

5. **Process shape on Windows venv**
   - A venv `python.exe` parent with a base Python child can be one logical interpreter launch, not two independent workers.
   - Do not label it duplication from process count alone.
   - Prove duplication from independent parentage/ownership/listeners, not executable path difference.

6. **Protection ingress / owner-thread pressure**
   - Reuse current ingress diagnostics before adding instrumentation: pending, high-watermark, queue latency, processing latency, slowest owner task, symbol/role, candle-cache metrics.
   - A short burst immediately after crash/power-loss recovery is not by itself proof of a persistent runtime bottleneck.
   - Compare against a clean subsequent run before reopening architecture, unless overflow or sustained pressure repeats.

7. **Scanner lifecycle**
   - Durable mode is authoritative for start/pause/resume/stop routing.
   - One manual start -> at most one full pass.
   - Do not diagnose Scanner control from window presence alone.
   - Final Scanner visual acceptance remains one complete owner-manual universe pass with ordinary Telegram delivery.

## Historical PAPER exposure → recovery → acceptance — 2026-10-20

**Trigger only:** owner wants to resume a PAPER acceptance run and earlier
Robot positions remain open after runtime downtime. Do not automatically
perform this entire procedure for a clean start. Case study:
LSKUSDT LONG and SAMSUNGUSDT SHORT, entered 2026-10-19; runtime stopped
after ~20:40 UTC. A historical minute-kline STOP touch on LSK and TAKE
touch on SAMSUNG on 2026-10-20 did **not** mean PAPER orders had executed.
The two trade exits were absent in the working SQLite/WAL. The initial LSK
loss estimate had a factor-of-ten error; use quantity × actual price delta
and separately account for entry/exit fees rather than copying old figures.

**One bounded end-to-end recovery brief, not serial investigations:**

1. **One host snapshot:** prove canonical PAPER DB identity (including WAL),
   runtime/process and listener ownership, durable Robot admission status,
   open trade/position/protection/obligation/limit/candidate records, and a
   verified SQLite Backup API snapshot. Reuse fresh evidence; do not change
   unrelated user files or LIVE.
2. **Separate facts:** last healthy live-protection observation, true durable
   executions and current open exposure. Historical public *last* and *mark*
   candles may establish probable STOP/TAKE contact and order, but not bid/ask
   fills during downtime. Label any trigger-price PnL hypothetical; do not
   invent executions or merge scenario outcomes with realized PnL.
3. **Pick recovery route once:** existing Robot restart + protection-crossing
   evaluated on a **fresh real book** gives a current-market PAPER close when
   gates allow. Historical backfill is a different, explicitly authorized
   durable-data modification requiring its own proof and provenance; it is not
   the default. PR #545 ONGUSDT owner attestation applies to LIVE *commands*,
   not PAPER trades or positions; do not repeat that search for this class.
4. **No new-entry window:** before any backend start, prove *every relevant*
   admission and order-entry path is fenced; `READY` with APPROVED retest
   candidates can open fresh exposure. In the 2026-10-20 case,
   `pause_robot_fallback.py` while backend was down moved durable state to
   `RECONCILIATION_REQUIRED`; the normal `RobotBreakoutMonitor` admission
   gate rejected entry in that state, while protection processing was coded
   independently. This was proven by source inspection and state probe,
   **not** yet by a running-paper result. Do not generalize to uninspected
   alternative entry routes, and do not mark safe from source inspection
   alone. No direct SQLite edit to force READY/STOPPED.
5. **Owner runtime boundary:** Scanner starts remain exclusively owner-manual;
   owner-only launch/approval constraints from ASSISTANT_PROTOCOL apply to
   backend/Robot as well where prescribed. The agent prepares the single
   verified launch surface and separately observes the outcome; never claim
   a prompt itself authorized a prohibited launch. Do not start Scanner or
   open PAPER_AUTO during position recovery.
6. **Observe closure and continue:** require actual exit executions and
   `robot_trades` exit reason/time, FLAT position projection, coherent
   protection/candidate/ledger/obligations, no unexpected new fills, and
   actual fees/net PnL. If not flat, name the one evidenced blocker and stop
   unsafe progression. If flat, use canonical reconciliation (may land PAUSED),
   then advance to the **already-requested** single owner-controlled Scanner
   + PAPER Robot + integrated feature acceptance run; no extra generic
   regression campaign.

**Evidence checkpoint (2026-10-20):** backup created at
`C:\BybitScanner_pc_backup_20261020_preclose\paper_runtime.sqlite3`
and integrity checked, durable admission moved to
`ROBOT_RUNNING/RECONCILIATION_REQUIRED`, zero outstanding entry limits
reported. **Backend launch and both position closures were not observed
at this checkpoint.** Do not report recovery PASS or E2E READY.

**Time-saving stop rule:** after one bounded confirmation of the known
signature, take the canonical authorized transition. Further research is
justified only by a proven mandatory safety unknown or contradictory
evidence; return to the same original trading acceptance goal immediately
after that blocker is resolved.

## 2026-09-27 incident — closed path

Observed sequence after abrupt power loss and local migration to canonical desktop wrappers:

- canonical start successfully brought up PAPER backend and Telegram Monitoring;
- startup recovery showed protection queue pressure and closed prior exposure;
- Robot durable state was `ROBOT_RUNNING / RECONCILIATION_REQUIRED` with `ROBOT_ENTRY_OWNERSHIP_MISMATCH` for BLENDUSDT candidate `d31c60b4abeda16305c062bf`;
- read-only durable evidence later showed the candidate CLOSED, no open Robot trade, FLAT/synced position, and two exactly offsetting executions (SELL 581, BUY 581);
- canonical `POST /api/robot/reconcile` cleared the stale recovery latch and landed `ROBOT_RUNNING / PAUSED`;
- desktop safe-stop then exposed a separate launcher defect: `ModuleNotFoundError: No module named 'terminal'`;
- root cause: `stop_robot_runtime.bat` executed `tools\stop_robot_runtime.py` as a script, making `tools` the import root;
- PR #280 changed the launcher to `python -m tools.stop_robot_runtime` and added focused regression coverage; Robot PAPER acceptance #218 passed; merged as `adcd44e1580a1f7648abb79c20a84c6980859660`;
- owner reran the canonical stop path: exit 0, expected success text, final durable state `ROBOT_STOPPED / ROBOT_STOPPED` version 80; backend/Telegram intentionally remained running.

### Fast path if this class repeats

- Import error from canonical stop: inspect current `stop_robot_runtime.bat` first; verify module invocation. Do not investigate Robot ownership first.
- `RECONCILIATION_REQUIRED` with a now-flat/settled symbol: read durable evidence once, then call canonical reconciliation. Do not edit DB.
- Stop shortcut appears ineffective: first prove the shortcut's `TargetPath`. It must point directly to tracked `C:\BybitScanner\stop_robot_runtime.bat`; do not assume an untracked wrapper delegates correctly.
- If the direct tracked launcher runs but shutdown is blocked, use its exact stdout/stderr and current health/durable evidence; do not infer failure from window presence alone.
- venv/base-Python parent-child chain: treat as one logical launch unless independent ownership evidence proves otherwise.

## 2026-09-28 legacy full-stop incident — CLOSED

### Final owner evidence

The canonical desktop stop path is now owner-verified on a clean cycle from
main `d3504c695c5793dde6c41cf952276535d56a324a` (PR #322):

- fresh canonical owner start reached Robot `ROBOT_RUNNING / READY` and Scanner
  RUNNING;
- one click on desktop `Остановить робота` closed the stop window, PAPER
  backend window and Telegram monitoring window without further owner input;
- a read-only post-stop host snapshot proved no listeners on
  `127.0.0.1:8765` or `127.0.0.1:8766`;
- no `terminal.runtime.paper_http_server`, `telegram_monitoring.py` or new
  `stop_robot_runtime.bat` process remained;
- five historical stop-shells left by the old failure-visible `pause`
  behavior were separately identity-checked and terminated once; the clean
  #322 cycle did not recreate them.

This closes the **canonical shutdown incident**, not RVL-R6 as a whole. The
Robot Stability owner gate still requires sustained real multi-symbol traffic,
healthy protection with no `ingress_overflow`, queue drain, and a normal
reconcile/restart that does not recreate the original incident.

### Investigation path that must not be repeated

The incident took multiple distinct blockers in sequence. Preserve this order
for provenance, but use the compact fast path below for any recurrence.

1. **#310 — orphan ENTRY_PENDING retirement safety**
   - added the migration-only stale-arm retirement bridge;
   - required durable no-work proof, exact process ownership and a SQLite writer
     barrier before exact-PID termination.

2. **#311 — canonical Windows `cmd.exe /c` ancestry**
   - recognized the real canonical backend/Telegram launcher shape instead of
     treating it as unprovable ownership.

3. **#312 — stale-arm `ingress_overflow`**
   - allowed only the exact stale temporary `ENTRY_PENDING` shape with
     `ingress_overflow`; all other unhealthy reasons remained fail-closed.

4. **#313 / #314 — desktop shortcut authority**
   - removed untracked local wrappers from the critical owner path;
   - made shortcut repair compatible with Windows PowerShell 5.1.

5. **#315 — saturated owner-queue shutdown path**
   - avoided enqueuing Scanner control behind a provably saturated legacy owner
     queue;
   - preserved Robot STOPPED, durable quiescence, writer barrier and exact PID
     ownership gates.

6. **#316 — persistent stop diagnostics**
   - introduced `%TEMP%\BybitScanner-stop-last.log`;
   - this was decisive for later blockers;
   - the original version deliberately kept failures visible with `pause`,
     which left old idle cmd shells after repeated failed attempts.

7. **#317 — transient legacy health re-proof**
   - retried only read-only health proof for transport timeout or exact
     `paper_runtime_unavailable`; mutations remained single-attempt.

8. **#318 / #319 — correct Robot-scoped PAPER quiescence**
   - inert APPROVED candidates are not by themselves active Robot ownership;
   - full stop no longer requires the entire PAPER account to be flat;
   - unrelated/manual PAPER exposure may persist, while Robot-owned or
     ambiguous pending exposure still blocks fail-closed.

9. **#320 — overflow is an entry trigger, not a final invariant**
   - once the proven legacy-starvation path is selected, queue recovery is not
     a reason to abort shutdown;
   - the stable invariant is exact temporary ENTRY_PENDING coverage shape plus
     durable/process ownership proof.

10. **#322 — live listener can never equal ABSENT**
    - decisive false-success evidence: the persisted log said
      `PAPER backend: absent` and `Runtime STOPPED`, while a read-only host
      snapshot still showed listener PID 700 on 8765 and exact backend chain
      `15028 -> 13476 -> 700`;
    - root cause: an unreachable `/api/health` request was incorrectly treated
      as proof that the process did not exist;
    - #322 added exact localhost listener presence proof and fail-closed
      ownership handling, and removed the launcher `pause` so future failures
      do not leak idle stop shells.

Final successful stop log from the pre-fix backend showed:

```text
[STOP] PAPER backend: present
[STOP] Telegram monitoring: absent
[STOP] Scanner STOPPED confirmed
[STOP] retiring stale entry protection coverage
[STOP] legacy backend identity re-proof delayed (transport unavailable); retrying read-only probe attempt 2
[STOP] legacy backend identity re-proof delayed (transport unavailable); retrying read-only probe attempt 3
[STOP] legacy backend identity re-proof delayed (transport unavailable); retrying read-only probe attempt 4
Runtime STOPPED.
steps=scanner:stop,protection:legacy-entry-proof,backend:legacy-terminate
[STOP BAT] EXIT_CODE=0
```

### Fast path if stop ever appears broken again

Use this exact order; do not restart the two-day investigation tree.

1. Read `%TEMP%\BybitScanner-stop-last.log` once.
2. Read-only check listeners 8765/8766 and exact runtime process ownership.
3. Never infer success or failure from console-window presence alone.
4. If log says backend `absent` but 8765 has a listener, treat that as a
   contradiction and a stop defect; listener evidence wins over HTTP timeout.
5. If backend is present, preserve exact DB/process ownership and durable
   Robot-scoped quiescence; never use account-wide flattening or broad
   kill-by-name.
6. Historical idle `stop_robot_runtime.bat` cmd shells with no Python child are
   launcher residue, not proof that the runtime is still alive.
7. A clean pass requires: one owner stop action, exit 0, 8765/8766 gone, backend
   and Telegram processes gone, and no newly leaked stop shell.

Do not reopen #310-#322 individually unless new evidence contradicts one of
these recorded invariants.

## Telegram monitoring silent candidate list — 2026-09-29

Known signature:
- `/robot` reports APPROVED candidates;
- owner sends `/monitoring`;
- Telegram update offset advances;
- monitoring health remains `ready`;
- no candidate-list reply appears;
- no loop exception is printed.

Root cause proven in the 2026-09-28 owner run:
- Ikigai Box handoff candidate IDs use `box-robot-<64hex>`;
- old monitoring buttons embedded the full durable ID in
  `monitor:candidate:<candidate_id>`;
- this exceeded Telegram's 64-byte `callback_data` limit;
- Telegram returned `ok:false`, and the old list path did not validate the
  response, so failure was silent.

Canonical repair:
- PR #325, merged as `4ab838857519adbacfa8fb4d780b3461f2717851`;
- new buttons use a bounded deterministic callback token;
- token resolution is restricted to current APPROVED candidates and fails
  closed on ambiguity;
- legacy short callbacks remain accepted;
- monitoring send failures are surfaced instead of silently ignored.

Fast path if this symptom reappears:
1. confirm current checkout includes #325 or later;
2. confirm Telegram Monitoring health is `ready`;
3. send `/monitoring` once;
4. if it still fails, inspect the now-surfaced runtime error instead of
   re-investigating update ownership/offset or candidate persistence first.

## Maintenance rule

Whenever a new runtime failure is resolved and is reasonably repeatable:

- add only the stable symptom -> decisive evidence -> canonical recovery/repair path here;
- remove superseded diagnostic branches;
- link the code/PR checkpoint when useful;
- do not turn this document into an incident diary.

The goal is fewer owner round-trips, not more documentation.

## Repeated ingress overflow during canonical reconcile — 2026-09-27

A successful reconcile to PAUSED followed by renewed coverage loss is not a
stale-latch-only incident. Do not repeat reconcile/resume as the repair.
Observed: ENTRY_PENDING on 2ZUSDT/ARBUSDT/ARKUSDT, no orders/exposure;
capacity/high-watermark 64/64, max queue latency 9620.0137 ms,
max protection processing 666.6149 ms, slowest owner call
`BackendRuntimeIntentPorts.reconcile_robot.<locals>.<lambda>` 9065.2912 ms.
Trace: robot_reconcile -> RobotRecoveryCoordinator._latest_geometry_indices
-> default ScannerGeometryCursorProvider -> latest_scanner_closed_candle_time_ms
-> candle REST. This bypassed the warmed candle cache (owner cache misses = 0).
Recovery geometry must use the same pre-warmed closed-candle evidence; a
missing/stale cache entry fails recovery closed instead of performing owner REST.
Bootstrap recovery before subscriptions retains its original evidence path.
Do not enlarge ingress capacity, weaken continuity checks or infer a need to
remove pre-entry coverage solely because its LIMIT has not yet been created.
Patch/runtime acceptance remains separate: no runtime restart or recovery retry
is authorized by a successful developer test.
