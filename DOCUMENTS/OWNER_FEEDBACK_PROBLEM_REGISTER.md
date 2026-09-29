## 2026-09-29 owner-prioritized remediation queue

Implementation order is now canonical in:
`DOCUMENTS/OWNER_FEEDBACK_REMEDIATION_QUEUE.md`.

The following owner-observed findings are queued **before Geometry resumes**:
- RH-DIAG-1 / RH-FAIL-1 candidate handoff diagnostics + root cause;
- CASHCATUSDT emergency-close root cause / protection observability;
- stale/completed Box suppression using frozen TAKE;
- BOX-LATE-1 crossed-grid catch-up;
- position-card chart/labels/volume cleanup;
- TradingView navigation from position cards.

This priority does not reopen TG-MON-1, RVL-G1, ARUSDT or the closed shutdown
incident.

# Owner Feedback Problem Register

Status: ACTIVE  
Date: 2026-09-29  
Purpose: one canonical register of product/runtime/geometry problems found directly from owner feedback during real BybitScanner use and acceptance. This prevents repeated rediscovery and keeps resolved findings distinguishable from open debt.

This register is descriptive only. It does not weaken any Scanner, Robot, PAPER/LIVE, Geometry, or owner-acceptance contract.

## Status vocabulary

- **OPEN** — confirmed problem with remaining engineering/acceptance work.
- **RECOVERABLE EVIDENCE** — real owner-observed problem, but exact source-time OHLC/log/error evidence still must be frozen before implementation.
- **FIXED / OWNER ACCEPTED** — production fix merged and owner reproduced the intended result.
- **CLOSED / CLASSIFIED CORRECT** — reported symptom was investigated and shown to be correct fail-closed behavior, not a defect.
- **DESIGN DEBT** — owner feedback established required future behavior, but implementation is intentionally deferred.

## Strategy / execution gaps discovered from owner feedback

### BOX-LATE-1 — crossed-grid late admission requires slot-preserving market catch-up
**Status: OPEN strategy implementation gap**

Owner feedback 2026-09-29:
- the existing Box strategy did not define what Robot should do if, by the time
  of admission/submission, price has already entered or passed part of the
  original four-part limit grid;
- one aggregate 1-RO late market entry is **not** the desired behavior.

Required owner contract now frozen:
- original `P1..P4` levels remain frozen;
- each already-crossed entry slot is acquired by MARKET for that slot's equal
  part;
- untouched slots remain resting entry LIMITs at their original levels;
- caught-up parts retain per-slot ownership/identity;
- every caught-up market part must receive a corresponding opposite/closing
  LIMIT order;
- existing shared Robot lifecycle/protection/recovery is reused;
- the familiar Box STOP/protection is still required and catch-up must never
  create an unprotected interval.

Still unresolved:
- exact price mapping for each paired closing LIMIT;
- if actual market catch-up fills conflict with the existing frozen
  planned-average/RR STOP arithmetic, the precise STOP calculation rule must be
  explicitly frozen before implementation.

Owning strategy authority:
`DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`, section
"Owner correction — late admission / crossed Box grid catch-up (2026-09-29)".

## Telegram / control surface

### TG-MENU-1 — Menu button intermittently absent in Telegram Desktop
**Status: OPEN UX debt**

Owner-observed behavior:
- Telegram Bot API previously proved the owner chat menu button was configured as `commands`;
- all expected bot commands existed;
- nevertheless the visible **Menu** button sometimes disappeared from the already-open Telegram Desktop chat;
- sending an owner command such as `/robot` caused the Menu button to appear again after the common menu-surface refresh.

Constraints:
- do not create/restart a duplicate Telegram polling worker merely to restore presentation;
- do not repeat already-proven Bot API command/menu wiring without contradictory evidence;
- acceptance is owner-visible reliable access to the control surface after ordinary startup/restart.

Likely work class: client-visible menu lifecycle/fallback UX, not server command publication.

### TG-MON-1 — `/monitoring` silently returned no candidate list
**Status: FIXED / OWNER ACCEPTED**

Owner evidence:
- `/robot` showed approved candidates;
- `/monitoring` update was consumed (offset advanced);
- Telegram Monitoring health remained `ready`;
- no candidate-list reply appeared and no loop exception was printed.

Root cause:
- Box durable IDs such as `box-robot-<64hex>` were embedded directly in
  `monitor:candidate:<candidate_id>`;
- resulting Telegram `callback_data` exceeded the 64-byte limit;
- Telegram returned `ok:false`;
- the old candidate-list path did not validate that result, producing a silent failure.

Fix:
- PR #325 merged as `4ab838857519adbacfa8fb4d780b3461f2717851`;
- bounded deterministic callback tokens;
- collision/ambiguity fail-closed;
- legacy short callback compatibility;
- Telegram send failure no longer silent.

Owner acceptance 2026-09-29:
- fresh `/monitoring` returned an active-candidate list with working inline buttons.

Do not reopen unless the symptom reproduces on #325 or later.

## Scanner -> Robot candidate handoff

### RH-FAIL-1 — valid Box signal delivered, Robot candidate not created
**Status: OPEN / diagnostic evidence gap**

Owner-observed 5m examples from the 2026-09-29 real Scanner run:
- `B2USDT`;
- `BANKUSDT`;
- `BNBUSDT`;
- `BNCUSDT`.

Observed owner UI:
- ordinary Ikigai Box chart/card was delivered;
- `🤖 Робот` button was absent;
- owner received:
  **"⚠️ Робот: кандидат <symbol> 5м не создан. Сигнал доставлен без Robot-кнопки."**
- later `BRETTUSDT 5m` showed a normal Robot button, so this was not a global Telegram/Robot outage.

What this proves from current code:
- the Box signal reached the executable Robot-plan preparation path;
- `_prepare_owner_robot_handle(...)` failed closed because the Box plan preparer raised or returned an invalid source/handle;
- ordinary Scanner delivery intentionally continued without a false Robot button.

Missing evidence:
- the precise exception text was printed only to the scrolling Scanner console as
  `[ROBOT CANDIDATE ERROR] symbol=... pattern=IKIGAI_BOX error=...`;
- by the time the problem was reviewed, the console had advanced and exact root cause was no longer practically recoverable.

Required work:
1. preserve every Robot candidate preparation failure in a bounded durable diagnostic surface;
2. record at least timestamp, symbol, timeframe, pattern, failure stage and sanitized error class/message;
3. never persist secrets, credentials, full DB paths, or unsafe payloads;
4. keep failure fail-closed: no Robot button unless durable candidate/plan creation actually succeeds;
5. once durable diagnostics exist, reproduce/classify B2/BANK/BNB/BNC or the next same-class failure before changing planner logic.

Do not guess that these four symbols share one planner/math defect until exact error evidence proves it.

### RH-DIAG-1 — candidate-preparation failure evidence is console-only
**Status: OPEN observability debt**

This is the enabling defect exposed by RH-FAIL-1.

Current behavior:
- exact failure cause is printed to transient Scanner stdout;
- Telegram owner warning intentionally hides exception details;
- no durable diagnostic record remains for later investigation.

Required result:
- one small persistent/runtime diagnostic sink sufficient to investigate the next failure without asking the owner to scroll a busy Scanner window;
- bounded retention;
- sanitized error data;
- no effect on Scanner delivery status or Robot admission semantics.

### RCV-SELF-1 — Robot remains in "Нужна сверка" after emergency close
**Status: OPEN runtime recovery blocker**

Owner evidence:
- CASHCATUSDT SHORT was emergency-closed;
- later Robot admission was rejected;
- owner status displayed `Запущен / Нужна сверка`;
- Robot did not visibly return to READY on its own.

This is distinct from the emergency-close root cause itself. The emergency close
may have been correct fail-closed behavior; the unresolved problem is that the
runtime appears to remain non-admitting after the position is already closed.

Do not attribute this to network loss without evidence. Investigate the exact
durable reconciliation/protection state and the expected automatic transition
back to READY.

Owning queue: `OFR-3A` in
`DOCUMENTS/OWNER_FEEDBACK_REMEDIATION_QUEUE.md`.

## Geometry / pattern quality

### G-BOX-1 — malformed Ikigai Box first impulse
**Status: RECOVERABLE EVIDENCE**

Owner-observed examples:
- `BSVUSDT 5m`;
- `COREUSDT 5m` as the same structural class.

Problem:
- the admitted A→B first impulse contains a real internal corrective swing/zigzag;
- this should not count as one continuous first impulse;
- this is different from harmless one/two opposite-color pause candles with no confirmed counter-swing.

Required work:
- recover exact source-time candles and cutoff;
- freeze negative Geometry Gold case(s);
- implement a general structural rule, never a symbol-specific exclusion;
- preserve valid controls such as AIGENSYN/FLOCK-style non-structural pauses.

### G-BOX-2 — missed later Box after an earlier Triangle
**Status: RECOVERABLE EVIDENCE**

Primary owner-observed example:
- `CARVUSDT 5m`.

Problem:
- Scanner emitted a Compression Triangle;
- a later, structurally separate right-side consolidation looked like a valid Ikigai Box to the owner;
- no Box signal was emitted.

Required work:
- recover exact OHLC/cutoff before changing detector behavior;
- determine whether the later structure already satisfies the existing Box contract;
- inspect enumeration/windowing/ranking/dedup and cross-pattern coexistence;
- an earlier Triangle must not by itself suppress a later independent Box.

### G-BOX-3 — recurring post-breakdown secondary Box family
**Status: RECOVERABLE EVIDENCE / strategy classification needed**

Owner examples:
- `CARVUSDT 5m`;
- `CPUSDT 5m`;
- `CROSSUSDT 5m`;
- `CLOUSDT 5m`.

Recurring visual sequence:
`compression/wedge/triangle -> downside break of sloping boundary -> later compact consolidation/Box`.

Owner feedback:
- these are setups the owner would manually consider trading.

Required work:
- freeze representative positive and negative source-time windows;
- decide whether this is already valid Ikigai Box geometry after an independent prior pattern, or a separately specified secondary-Box subtype;
- distinguish genuine secondary consolidation from noisy continuation;
- do not make "trendline broke down" sufficient by itself for admission.

### G-COEXIST-1 — one pattern must not suppress another valid pattern
**Status: OPEN invariant / tied to G-BOX-2/G-BOX-3**

Owner feedback established that:
- valid L-shape and Box signals should be independently deliverable on the same symbol when both exist;
- an earlier Wedge/Triangle/Box must not automatically suppress a later independent formation.

Implementation should preserve independent pattern identity, source-time cutoff and dedup namespace.

## PAPER position / Robot ownership UX

### PAPER-CELO-1 — manual CELOUSDT exposure remains `reconciliation_required`
**Status: OPEN manual PAPER reconciliation debt**

Owner evidence:
- `/positions` showed `CELOUSDT · Long`;
- quantity `1.3`;
- average entry `0.075347`;
- engaged roughly `0.10 USDT`;
- state `reconciliation_required`;
- detailed card explicitly said:
  **"Позиция не от робота — график недоступен"**;
- `/robot` correctly reported zero Robot-owned open positions.

Interpretation:
- this is manual/non-Robot PAPER exposure, not Robot ownership;
- do not silently close, adopt, or mutate it through Robot recovery;
- resolve via explicit manual PAPER reconciliation, or later through the separately designed Position Adoption flow.

### POS-ADOPT-1 — manual open position -> explicit Robot adoption
**Status: DESIGN DEBT**

Owner-required future behavior is frozen in
`DOCUMENTS/MANUAL_CHART_AUTOPILOT_HANDOFF_DECISION.md`.

Key requirements:
- one context-aware **Autopilot** action;
- when current symbol has a manual open position: ask
  **"Хотите передать эту сделку роботу?" — Да / Нет**;
- `Нет` leaves manual position untouched;
- `Да` runs an explicit fail-closed adoption gate;
- Robot ownership is shown only after durable ownership attestation succeeds;
- conflicting/ambiguous existing Robot ownership blocks adoption.

### POS-CONTEXT-1 — Robot-owned symbol awareness on every terminal navigation
**Status: DESIGN DEBT**

When navigating to a symbol already traded by Robot, the terminal must immediately
show authoritative Robot ownership/context regardless of navigation path
(watchlist, search, Scanner signal, direct symbol entry, position list, workspace,
back/forward/deep link).

## Robot stability / acceptance findings

### R6-EVIDENCE-1 — same-process no-overflow evidence was previously missing
**Status: ACTIVE ACCEPTANCE GATE**

A prior full Scanner pass completed:
- 778/778 symbols;
- 186 signals found;
- 200 Telegram deliveries;
- 43 Box observations;
- 104:55 elapsed.

But its post-run protection metrics were read from a **new backend process**, so
`high_watermark=0` could not prove that the previous process never overflowed.

Current 2026-09-29 run now has a fixed same-process baseline:
- backend instance
  `be72ef65-5167-44ef-a645-5c6ce447e49d`;
- Robot admission ready;
- PAPER live-safe;
- Scanner acceptance ready;
- protection healthy;
- ingress pending 0 / high-watermark 0 at baseline;
- Scanner RUNNING.

Exit evidence still required after the current pass:
- same `process_instance_id`;
- protection remains healthy;
- `current_pending=0` after drain;
- no `last_overflow_symbol/role`;
- high-watermark below saturation;
- no incident recreated through normal restart/reconcile.

### SHUTDOWN-1 — canonical stop chain failures
**Status: FIXED / OWNER ACCEPTED**

Historical #310–#322 shutdown incident is closed and has its own authoritative
runbook:
`DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md`.

Do not reopen or re-document the two-day investigation unless new evidence
contradicts one of its recorded invariants.

## Correctly classified non-defects

### ARUSDT 1m — no Robot button
**Status: CLOSED / CLASSIFIED CORRECT**

Frozen stop math proved `NO_VALID_STOP_EXISTS` under the approved constraints:
the required RR-valid STOP tick and the mandatory beyond-P4 STOP region do not
overlap. The missing Robot affordance was correct fail-closed behavior, not a bug.

## Canonical follow-up order

While the current RVL-R6 owner run continues:
1. do not restart/stop it merely to investigate feedback findings;
2. preserve same-process R6 metrics at completion;
3. RH-FAIL-1/RH-DIAG-1 is the highest-value new operational defect because real
   executable Box signals lost the Robot handoff and exact cause was ephemeral;
4. Geometry cases enter the Geometry Gold flow only after exact evidence is
   frozen;
5. TG-MENU-1 remains separate UX debt;
6. CELO/manual position debt remains non-Robot and must not contaminate Robot
   ownership/recovery logic.

