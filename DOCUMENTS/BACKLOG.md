## IMPLEMENTATION PLAN — DELIVERY-FIRST RESET — 2026-10-04

Owner decision: optimize for the shortest verified path to a reliable PAPER Robot,
not for completing research work before product validation.

### 1. Critical path

The critical path is now product-facing:

`real defect -> smallest fix -> focused regression -> merge -> PAPER acceptance -> next defect`.

A task belongs on the critical path only when it:
- removes a real Scanner/Robot/PAPER blocker;
- reduces trading/protection/recovery risk;
- opens the next acceptance gate;
- or fixes geometry that has a concrete observed bad signal behind it.

Research that does not meet one of those conditions must not block PAPER progress.

### 2. Geometry / calibration routing

GEO-U1 remains valuable but is no longer allowed to monopolize the critical path.

Current H28 state:
- v4 runner/gate is merged;
- no accepted `calibration_result_v4.json` exists;
- the 16-process run exhausted the laptop;
- the 1-process exhaustive run is operationally too slow for the normal workflow.

Therefore exhaustive v4 is **PARKED / background research**, not a prerequisite for
continuing PAPER Robot work. It may resume later on a stronger machine or after a
runner optimization that preserves exact methodology and supports checkpoint/resume.

Geometry work returns to the main queue only when:
1. a real signal exposes a concrete geometry defect; or
2. a bounded Geometry slice directly opens a product acceptance gate.

When that happens: pin the bad case -> add it to Gold -> fix that defect class ->
focused regression -> merge. Avoid broad semantic expansion unless the evidence
requires it.

### 3. Product-critical execution order

Resume the owner feedback / Robot reliability queue ahead of more exhaustive Geometry:

1. **Robot readiness and recovery**
   - eliminate persistent `reconciliation_required` / not-ready states when the
     authoritative PAPER state is already safe and flat;
   - keep fail-closed behavior when state is genuinely uncertain;
   - make the durable blocker explicit when automatic recovery is impossible.

2. **Execution and protection correctness**
   - close any unresolved emergency-close / protection-path cause that can affect
     capital safety;
   - verify partial-fill protection, STOP behavior, restart/recovery and no
     duplicate obligations.

3. **Box execution correctness**
   - crossed-grid catch-up, actual-average STOP translation, paired closing
     orders and completion/stale suppression;
   - prove behavior with focused PAPER regressions before expanding strategy.

4. **Natural PAPER acceptance and statistics**
   - prefer real full Scanner passes and naturally occurring Robot candidates over
     synthetic runtime churn;
   - accumulate PAPER trades and use them to rank the next defects by real impact.

5. **Feature expansion only after reliability**
   - dual-grid / re-entry / multi-TF / master-junior Robot features remain queued,
     but must not outrank unresolved safety/recovery defects.

### 4. Slice size / anti-stall rules

To keep throughput high without sacrificing safety:

- one slice = one defect or one gate;
- reuse existing evidence before collecting new evidence;
- one focused regression set, not broad test inflation;
- merge completed slices quickly instead of stacking long research chains;
- after at most **2-3 consecutive research slices**, require a product checkpoint:
  `what became safer or closer to PAPER acceptance?`
- if the answer is “nothing yet”, park the research line and return to the product queue;
- no archaeology after evidence is proven unrecoverable;
- no heavy exhaustive job may block normal development.

### 5. Heavy computation policy

Long-running calibration/optimization jobs are infrastructure work, not owner-interactive
critical-path work.

Required direction before another expensive exhaustive run:
- checkpoint/resume;
- deterministic chunking;
- reuse/caching where semantics remain identical;
- optional execution on a stronger PC/server;
- failure must preserve completed work instead of restarting from zero.

No approximation may silently replace the accepted exhaustive methodology. A faster
screen may be used only as a prefilter if the final accepted result is still validated
by the exact method.

### 6. Agent prompt / workflow format

Default delegated prompt should be short:
- authoritative base;
- one goal;
- 3-5 hard boundaries;
- acceptance result;
- STOP.

Do not restate the full project history in every prompt. Repository authority and the
owning spec carry context. Expand a prompt only when a concrete dependency requires it.

### 7. Definition of progress

Progress is measured primarily by:
- fewer unresolved real PAPER blockers;
- safer and more self-recovering Robot behavior;
- more successful natural PAPER candidates/trades;
- fewer owner interventions;
- shorter time from observed defect to merged verified fix.

Number of research slices, documents, tests, or calibration stages is not itself a
progress metric.

### 8. Immediate routing decision

Do **not** make H28/H28C the next critical-path task.

Next planning action:
- refresh the current owner-feedback / Robot reliability queue from repository truth;
- choose exactly one highest-risk unresolved product blocker;
- run the normal vertical slice:
  `evidence -> fix -> focused regression -> merge -> PAPER acceptance`.

Geometry v4 remains preserved for later continuation; no accepted work is discarded.

## NOW — 2026-10-07 — OWNER FEEDBACK QUEUE

The following owner-observed defects and UX requirements are now in the active
product queue. They are distinct slices; do not bundle trading-safety changes
with geometry or presentation changes unless the implementation dependency is
strictly necessary.

1. **P0 — BOX-PRISTINE-FLAT-1 — pristine FLAT Box admission**
   - AVNTUSDT 5m LONG was admitted as linked `APPROVED / BOX_ENTRY_READY` but
     remained unexecuted after repeated attempts with
     `Box ownership requires reconciled FLAT position and journal`;
   - NEARUSDT 5m LONG independently reproduced the same defect on 2026-10-07:
     `APPROVED / BOX_ENTRY_READY`, attempt_count=2, same last_execution_error,
     with no NEAR position projection, no executions and no Box order ownership;
   - read-only evidence for both AVNTUSDT and NEARUSDT is consistent with a
     pristine symbol: no position projection, no executions and no Box ownership;
   - treat `no position row + no executions + no ownership/exposure evidence`
     as a provable pristine-FLAT baseline for PAPER Box ownership;
   - keep fail-closed behavior when any execution/history/ownership/exposure
     evidence exists without a reconciled projection;
   - acceptance: pristine symbol reaches catch-up classification and normal
     MARKET/LIMIT execution path; ambiguous symbol remains blocked.

2. **P0 — MON-CAND-EXEC-1 — candidate execution observability**
   - candidate monitoring currently hides durable execution state behind the
     generic text `Сделка: не открыта`;
   - show phase, attempt count, last execution error/block reason and, for Box,
     MARKET-vs-LIMIT catch-up slot state / ownership readiness when available;
   - the owner must be able to distinguish waiting, blocked, planned and actually
     submitted states without reading SQLite manually.

3. **P1 — MON-CAND-CHART-1 — chart in candidate monitoring**
   - every monitored durable candidate must have an updated chart on its signal
     timeframe using current closed candles;
   - preserve frozen candidate identity, anchors/geometry and trading levels;
     monitoring must not silently re-detect/re-anchor from later candles;
   - retain TradingView navigation and degrade to the text card if rendering fails;
     chart failure must never block Robot execution/protection.

4. **P0 — GEO-ADJ-ANCHOR-1 — anchors only on adjacent opposite extrema**
   - CAPUSDT 5m is the owner visual reference for a malformed triangle caused by
     anchor selection across non-adjacent opposite pivots;
   - an anchor pair is valid only when the opposite extremum is the immediate
     neighboring opposite pivot in chronological pivot order;
   - skipping an intermediate opposite extremum is a hard geometry reject, not a
     score penalty;
   - acceptance: no Wedge/Triangle candidate may be built from a pair that jumps
     over another opposite pivot.

5. **P0 — GEO-CORRECTIVE-WEDGE-START-1 — corrective wedge first anchor**
   - CASHCATUSDT 5m is the owner visual reference: after a strong decline, the
     rising corrective wedge should begin at the lowest reversal extremum that
     terminates the impulse, not at a later local point inside the correction;
   - mirror the rule after a strong rise for falling corrective wedges;
   - anchor selection must preserve impulse/reversal chronology and must not crop
     away the true start merely because a later local fit scores well.

6. **P1 — GEO-WEDGE-IMPULSE-CONTEXT-1 — impulse context in wedge selection**
   - wedge geometry/ranking must distinguish a corrective wedge after a strong
     impulse from an isolated local shape;
   - reuse structural pivot evidence; do not add a coin-specific threshold or
     presentation-only patch;
   - this slice is subordinate to the hard adjacent-anchor and corrective-start
     rules above.

7. **P0 — WEDGE-TP-BASE-1 — TP/potential must equal wedge-base measurement**
   - CTUSDT 1m Falling Wedge is the owner visual reference: displayed TP is much
     farther than the visible wedge base implies;
   - trace whether target calculation, frozen geometry or chart rendering is using
     a different span;
   - one authoritative wedge-base measurement must drive both displayed potential
     percentage and TP level;
   - if the base cannot be established validly, reject/flag the candidate rather
     than publish an inflated target.

8. **P0 — WEDGE-STOP-1 — structural stop for wedge entries**
   - LONGXIAUSDT 5m Falling Wedge is the owner visual reference: the current STOP
     is too close to entry and can be hit by ordinary noise while the wedge thesis
     remains structurally valid;
   - trace the current wedge STOP source and replace any over-tight local/minor-low
     behavior with a structural rule tied to the relevant wedge boundary/extremum,
     with an appropriate safety buffer;
   - preserve risk gating and fail closed if a valid structural STOP cannot produce
     acceptable risk/reward; do not widen STOP merely to force an entry;
   - acceptance: STOP is structurally defensible on the frozen wedge geometry and
     is consistent with the scale of the formation.

9. **P0 — WEDGE-REENTRY-2 — bounded re-entry attempts per signal**
   - owner requirement: after a failed wedge entry, the same still-valid signal may
     be entered again up to two times;
   - maximum is three failed entries total for one signal: initial attempt + two
     re-entry attempts; after the third failed entry, invalidate/cancel the signal
     and forbid further entry;
   - re-entry is allowed only while the original frozen signal remains structurally
     valid and a fresh admissible entry trigger exists; do not blindly re-enter
     immediately after STOP;
   - define the failed-attempt accounting durably and expose the current attempt
     number in monitoring/lifecycle UI;
   - preserve the original signal identity and avoid creating parallel owners for
     the same symbol/signal.

10. **P1 — POSITION-CARD-STATUS-CLEANUP-1 — remove redundant open-status row**
   - remove the user-visible line `Статус: открыта` from the position card;
   - do not replace it with equivalent noise; preserve useful PnL/SL/TP/volume and
     navigation controls.

11. **P0 — PAPER-UNCERTAINTY-1 — unresolved PAPER state / stale reconciliation debt**
   - `/positions` currently reports `PAPER · Состояние не подтверждено` while no
     open position projection is shown;
   - many historical FLAT projections remain `sync_state=reconciliation_required`;
   - separately identify the unfinished command and/or unfinished reconciliation
     checkpoint that actually triggers the warning, then repair self-recovery or
     stale terminalization through canonical persistence APIs only;
   - no manual SQL cleanup; preserve fail-closed behavior when exposure is genuinely
     uncertain.

Routing order for these new items: fix PAPER/Robot execution blockers first
(`BOX-PRISTINE-FLAT-1`, `PAPER-UNCERTAINTY-1`), then execution correctness
(`WEDGE-STOP-1`, `WEDGE-REENTRY-2`), then candidate observability, then geometry
hard gates/target correctness, then presentation cleanup. A real owner-observed
safety blocker may preempt this order.


## NOW — 2026-09-30 — G6 FULL PASS COMPLETED / GEOMETRY GATE REOPENED

Owner screenshot at 14:48 confirms natural Scanner completion:
- scanned tickers: **782**;
- signals found: **112**;
- sent to Telegram: **128**;
- Ikigai Box observations: **28**;
- elapsed: **73:39**.

The complete traversal and normal Telegram-delivery requirement is satisfied.
However G6 is **not a Geometry Quality PASS**, because the same run produced
owner-confirmed systematic geometry issues (anchor consensus/selection and
Broadening/«Рупор» misclassification). Those are preserved under GEO-U1/GEO-U2.
The next operational dependency is no longer "wait for G6": harvest durable
APRUSDT Robot-candidate incident evidence for OFR-3, then continue the
owner-prioritized remediation queue.

## OWNER PROPOSALS CHECKPOINT — 2026-09-30

All owner proposals raised during the current Scanner/Geometry/Box review are
preserved below. This is a routing checkpoint, not a parallel source of strategy
truth: the owning specs/register entries remain authoritative.

1. **GEO-U1 — universal pivot-consensus geometry**
   - build geometry from structural pivots first, not from a preselected pattern label;
   - choose structurally correct opposite anchors, then fit each boundary to the
     largest coherent set/consensus of same-side pivots;
   - allow isolated wick/pivot pierces when the surrounding pivot cluster still
     confirms the same boundary, but reject systematic boundary violations;
   - require meaningful oscillation/touches between both boundaries rather than
     accepting shapes where price only rides one side;
   - only after the envelope is built classify it as Wedge, Triangle,
     Compression/Поджатие, or another family;
   - one universal geometry engine should serve these converging families.

2. **GEO-U2 — Broadening Formation / «Рупор»**
   - widening boundaries are the geometric opposite of a converging wedge;
   - detect/classify them explicitly so they cannot be mislabelled as Wedges;
   - include them in Scanner/Telegram discovery;
   - Robot execution strategy is deferred until separately specified.

3. **SCAN-MULTI-TF — real multi-signal traversal**
   - for each ticker, process 5m and then 1m before moving to the next ticker;
   - all enabled pattern families are evaluated independently on each timeframe;
   - signal/dedup identity is at least
     `symbol × timeframe × pattern × formation/source identity`;
   - one valid 5m signal must not suppress another valid 1m signal or a different
     pattern on the same symbol;
   - Scanner multi-signal delivery is distinct from Robot's current one-owner
     execution constraints and from BOX-MTF-REENTRY-1.

4. **G-COEXIST — independent pattern coexistence**
   - an earlier Triangle/Wedge/Box/L-shape must not automatically suppress a
     later structurally independent pattern on the same symbol;
   - STORJ/CARV-style sequences are evidence that discovery must keep looking
     after the first detected formation.

5. **BOX-DUAL-GRID-1 — simultaneous 1.618 + 2.618 grids**
   - arm both Box grids in advance from the same frozen parent geometry;
   - the first grid may STOP while the already-resting second grid begins filling;
   - both grids use the same frozen parent TAKE;
   - combined risk/ownership/event ordering must be frozen before implementation.

6. **BOX-STALE-2 / OFR-4 — completed Box lifecycle**
   - once frozen TAKE was already achievable, the old Box is completed/stale for
     new actionable delivery/admission;
   - a later independent setup, including another timeframe on the same symbol,
     remains eligible;
   - SOMIUSDT 5m -> later 1m structure is retained as regression evidence.

7. **BOX-MTF-REENTRY-1 — parent 5m Box -> confirmed 1m child execution**
   - after bounded stopped attempts, a still-valid 5m parent thesis may admit a
     new 1m confirmation-based tactical execution;
   - STORJUSDT is the owner visual reference; first proposed SHORT trigger is a
     confirmed bearish engulfing/absorption-style reversal, with LONG mirrored;
   - this is neither a blind third grid nor ordinary Scanner multi-signality;
   - persist durable parent/child ownership and reuse the shared Robot engine;
   - position cards/history must visibly identify the relation, approximately
     `Дочернее исполнение: 1m ← родитель 5m`;
   - retry count, risk budget, exact trigger, STOP/TAKE and parent invalidation
     remain specification gates before PAPER implementation.

Current work priority is unchanged: active OFR/G6 work is not interrupted by
these future-design records. LIVE execution remains prohibited.

## FUTURE — BOX-MTF-REENTRY-1 — parent 5m setup -> confirmed 1m child execution

Owner-frozen design concept from STORJUSDT, 2026-09-30:
- keep the confirmed 5m Ikigai Box as the parent thesis;
- after bounded failed parent attempts, allow a later 1m confirmation-based
  re-entry (first concrete example: bearish engulfing for SHORT);
- this is separate from the passive 1.618/2.618 dual-grid mechanism and separate
  from ordinary multi-signal Scanner traversal;
- persist explicit parent/child ownership;
- reuse shared Robot execution/protection/recovery;
- freeze retry count, confirmation rule, risk budget, STOP/TAKE and invalidation
  before implementation;
- open/closed position cards must visibly mark the relationship, e.g.
  `Дочернее исполнение: 1m ← 5m`, with final wording to be refined.

Canonical specification:
`DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`.

## NOW — 2026-09-29 — FINAL OWNER FEEDBACK CHECKPOINT / HANDOFF

All remaining findings from today's owner run are documented and queued before
Geometry resumes.

New recovery blocker:
- after the CASHCATUSDT emergency close, owner saw
  `Робот: отклонено — Робот не готов к приёму новых сделок`;
- Robot status displayed `Запущен / Нужна сверка`;
- Robot did not visibly self-recover to READY;
- treat this as separate from the emergency-close trigger itself;
- do not assume internet/network loss without durable evidence;
- queue `OFR-3A`: investigate durable reconciliation/protection state and make
  the intended safe transition
  `emergency close -> authoritative flat/consistent -> READY` automatic if
  that is the canonical contract.

Current owner-feedback remediation queue before Geometry:
1. OFR-1 durable Robot failure diagnostics;
2. OFR-2 CASHCATUSDT emergency-close exact root cause / recurrence classification;
3. OFR-3 Box Robot handoff failures B2/BANK/BNB/BNC;
4. OFR-3A stuck reconciliation / missing self-recovery;
5. OFR-4 stale/completed Box suppression (1INCHUSDT; frozen TAKE reached);
6. OFR-5 crossed-grid Box catch-up;
7. OFR-6 Telegram position-card UI cleanup;
8. OFR-7 TradingView button on position cards;
9. only then resume Geometry at RVL-G2/G3/G4.

Today's position-card UX corrections are already frozen:
- visually rebalance the chart / remove excessive right-edge crowding;
- compact Entry/SL/TP level labels;
- `Размер` -> `Объем` and add USDT notional;
- add TradingView navigation under position cards while retaining
  `К позициям`.

Do not repeat TG-MON-1, RVL-G1, shutdown investigation or ARUSDT analysis; those
are already closed/classified.

## NOW — 2026-09-29 — OWNER FEEDBACK REMEDIATION MOVED AHEAD OF GEOMETRY

Owner priority is now explicit: today's operational/product findings are handled
before Geometry implementation resumes. RVL-G1 stays complete; do not repeat it.

Canonical queue:
`DOCUMENTS/OWNER_FEEDBACK_REMEDIATION_QUEUE.md`.

Order after the current RVL-R6 evidence capture:
1. OFR-1 — durable sanitized diagnostics for Robot candidate/protection failures;
2. OFR-2 — CASHCATUSDT emergency-close root cause and recurrence classification/fix;
3. OFR-3 — B2/BANK/BNB/BNC Box Robot candidate handoff failures;
4. OFR-4 — suppress already-completed Box setups after frozen TAKE was reached;
5. OFR-5 — crossed-grid Box catch-up: MARKET per crossed slot, untouched LIMITs,
   paired closing LIMITs, existing shared STOP/protection;
6. OFR-6 — Telegram position-card cleanup: center chart better, compact SL/TP/
   Entry labels, `Размер` -> `Объем` with USDT notional;
7. OFR-7 — TradingView button under position cards while preserving
   `⬅️ К позициям`.

CASHCATUSDT diagnostic evidence 2026-09-29:
- top-level log search produced no actual CASHCATUSDT emergency/protection event;
- CASHCATUSDT appeared only in Scanner-result logs;
- the EMERGENCY_CLOSE text hit in SQLite was schema text, not proof of the event;
- binary SQLite must be queried structurally before blaming network lag;
- this absence itself confirms the current protection observability gap.

Geometry resumes at RVL-G2/G3/G4 only after this queue, unless the owner
reprioritizes again.

## NOW — 2026-09-29 — OWNER FEEDBACK / ACCEPTANCE CHECKPOINT

Today's owner feedback and acceptance findings are preserved; do not rediscover
them in the next chat.

Completed/accepted:
- owner checkout started the fresh runtime from local `7196110`;
- TG-MON-1 owner acceptance PASS: `/monitoring` returned the active candidate
  list and inline buttons after PR #325;
- RVL-G1 repository Geometry Gold inventory completed and merged in PR #327;
- canonical owner-feedback problem register added and merged in PR #328.

Active RVL-R6 evidence:
- same-process baseline captured for backend instance
  `be72ef65-5167-44ef-a645-5c6ce447e49d`;
- baseline: Scanner RUNNING, Robot admission ready, PAPER live-safe, protection
  healthy, ingress pending 0/64, high-watermark 0;
- final same-process post-load metrics are still required before declaring R6
  PASS.

New owner-observed Robot handoff defect:
- B2USDT/BANKUSDT/BNBUSDT/BNCUSDT 5m Box signals were delivered without
  `🤖 Робот` and with the explicit candidate-creation failure warning;
- later BRETTUSDT showed a normal Robot button, so this is not a global
  Robot/Telegram outage;
- exact failure cause was lost because it existed only in scrolling Scanner
  stdout;
- preserve RH-FAIL-1 and RH-DIAG-1: durable sanitized candidate-preparation
  diagnostics before speculative planner changes.

New Box execution strategy gap:
- late admission after price has crossed part/all of P1..P4 requires
  slot-preserving market catch-up;
- each crossed slot is acquired by MARKET for that slot's equal quantity;
- untouched slots remain at their frozen LIMIT levels;
- every market-caught slot gets a corresponding closing LIMIT;
- existing shared STOP/protection lifecycle remains authoritative;
- exact closing-LIMIT price mapping is intentionally unresolved and must be
  frozen before implementation;
- do not implement one aggregate 1-RO market fallback.

Canonical detail:
`DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`.

## NOW — 2026-09-29 — OWNER FEEDBACK PROBLEM REGISTER

All currently known owner-observed product/runtime/geometry problems are now
consolidated in:

`DOCUMENTS/OWNER_FEEDBACK_PROBLEM_REGISTER.md`

This register is canonical for feedback findings and their status. It includes:
- Telegram Menu visibility debt;
- resolved TG-MON-1 silent monitoring bug;
- new Box Robot handoff failures on B2/BANK/BNB/BNC and the missing durable
  failure diagnostics;
- BSV/CORE malformed first-impulse geometry;
- CARV/CPU/CROSS/CLO post-breakdown secondary-Box family;
- cross-pattern coexistence invariant;
- CELOUSDT manual PAPER reconciliation debt;
- future manual-position adoption / Robot-owned-symbol awareness requirements;
- current RVL-R6 same-process evidence gap;
- resolved shutdown incident and ARUSDT correctly classified non-defect.

Do not create parallel duplicate tickets for these findings; update the register
and owning task/spec when new evidence changes classification or status.

## NOW — 2026-09-29 — RVL-G1 GEOMETRY GOLD INVENTORY COMPLETE

RVL-G1 was completed in parallel while the owner RVL-R6 Scanner run continued;
no runtime/process state was changed.

Canonical inventory:
`DOCUMENTS/GEOMETRY_GOLD_INVENTORY.md`.

Key result:
- exact reusable OHLC already exists for the 11-case formation-fit pack,
  1000TOSHIUSDT/1000XECUSDT locality cases, 1000BONKUSDT anchor case, and
  CAKEUSDT L-shape stale-signal case;
- existing synthetic Ikigai tests remain FAST controls and are not mislabeled
  as archived Bybit Gold;
- BSVUSDT/COREUSDT first-impulse defects and CARV/CPU/CROSS/CLO secondary-Box
  family are RECOVERABLE until exact source-time candles/cutoffs are frozen;
- screenshot/annotation training material remains VISUAL_ONLY unless exact
  candle evidence is separately available;
- G2 seed is defined by references to existing fixtures rather than copying
  candles.

Next Geometry slice after/alongside the owner R6 gate: RVL-G2 compact manifest
and runner only; no production detector change.

## END-OF-DAY CHECKPOINT — 2026-09-28

Stop here for the night. Preserve the current evidence and do not repeat already-closed diagnostics.

Completed / proven today:
- PR #299: Ikigai Box WATCH is not an owner-facing product mode; local WATCH flags were disabled for acceptance;
- PR #300: fixed raw Fibonacci grid/TAKE tick-alignment rejection by deterministic instrument-tick normalization;
- exact frozen production case `2ZUSDT 1m` replays GREEN on the fix:
  grid `0.06726 / 0.06720 / 0.06714 / 0.06708`, TAKE `0.06765`;
- focused `tests.test_ikigai_box_plan`: 11/11 PASS on the fix branch before merge;
- one-action desktop runtime path reached Robot READY + Scanner RUNNING on current code;
- real CONFIRMED `AKEUSDT 5m` showed `🤖 Робот`; owner admission returned
  `Сигнал принят: AKEUSDT ✅`;
- Telegram Bot API proved owner `menu_button.type=commands` and all eight expected commands. The desktop client still did not visibly render Menu; do not repeat server-side menu checks without new evidence.

Morning classification update:
- `ARUSDT 1m` is **not** an implementation blocker. Frozen stop-math proves
  `NO_VALID_STOP_EXISTS` under the approved P4 + fee-aware net RR >= 2 rules;
- required RR tick is `4.780`, nearest tick beyond P4 is `4.777`; no overlap;
- therefore the no-Robot-button result is correct fail-closed behavior;
- PR #300 remains closed and no STOP-search code change is required.

The active engineering gate is now RVL-R6. RVL-R2 through RVL-R5 are
complete; do not repeat their replay/boundary/fix/CI work.

Shutdown sub-incident update 2026-09-28:
- canonical stop repair chain #310-#322 is closed and documented in
  `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md`;
- clean owner cycle on main `d3504c695c5793dde6c41cf952276535d56a324a`
  reached Robot READY + Scanner RUNNING, then one desktop stop action left no
  listeners on 8765/8766, no backend/Telegram process and no new stop-shell;
- five historical #316 `pause` shells were identity-checked and removed once;
  they did not recur;
- this proves the canonical shutdown path, but does **not** complete RVL-R6:
  sustained real multi-symbol traffic, healthy protection/no
  `ingress_overflow`, queue drain and normal reconcile/restart evidence are
  still required.

Runtime is currently fully down after the clean stop proof. Verify actual host
state before any future mutation or restart rather than assuming this snapshot
remains current.

## OWNER TELEGRAM UX FEEDBACK — 2026-09-28 — MENU STILL NOT VISIBLE

Current real owner run again shows no visible Telegram Menu button in the desktop
client.

Known prior evidence:
- Bot API previously proved owner `menu_button.type=commands`;
- all eight expected commands were published;
- therefore do not assume missing client UI means missing server configuration.

Queued task **TG-MENU-1**:
- after the current RVL-R6 run, perform one bounded server-side re-check of the
  owner chat menu/button + command list;
- if server-side state is still correct, do **not** repeat Bot API/menu wiring
  work already proven;
- isolate the owner-visible client/UX failure and determine whether Telegram
  desktop client behavior, menu-button presentation semantics, or the current
  bot control surface requires a reliable fallback;
- preserve the existing single Telegram update owner and Scanner/Robot runtime
  authority; do not restart or duplicate Telegram monitoring merely to make a
  button appear;
- acceptance is owner-visible access to the permanent control surface after
  ordinary runtime start/restart, not merely a successful Bot API response.

This is a UI/control-surface debt discovered during acceptance. It does not
invalidate the current Robot Stability traffic evidence and must not interrupt
RVL-R6 unless Telegram command handling itself is shown broken.

## OWNER SIGNAL FEEDBACK — 2026-09-28 — GEOMETRY TASKS QUEUED

Two owner-observed Scanner signals are now frozen as explicit Geometry Quality
tasks. They are **not** grounds to interrupt the active RVL-R6 Robot Stability
acceptance; they enter RVL-G1/G2 after R6 unless the owner reprioritizes.

### G-BOX-1 — BSVUSDT 5m false-positive Ikigai Box first impulse

Owner observation:
- the displayed first impulse contains a clear internal correction / zigzag;
- this is not merely one or two opposite-colour pause candles;
- the A→B leg is therefore not one continuous structural impulse and should not
  be admitted as a valid Ikigai Box first impulse.

Required fix task:
- freeze the exact source-time BSVUSDT 5m candles when available;
- add BSVUSDT 5m as a **negative Geometry Gold case**;
- encode the general rule, not a symbol-specific filter: small opposite-colour
  candles may remain valid only while they do **not** form a confirmed internal
  corrective swing/zigzag;
- a confirmed internal correction inside A→B must invalidate that first impulse
  or terminate it at the earlier structural pivot, according to the existing
  first-impulse construction contract;
- preserve accepted controls such as AIGENSYN/FLOCK and do not restore a
  colour-only veto.

Acceptance:
- BSVUSDT 5m no longer produces the same malformed Box candidate;
- already-valid first impulses with short non-structural pauses remain valid;
- one bounded detector/gold regression proves the general rule before the final
  full Scanner acceptance.

### G-BOX-2 — CARVUSDT 5m missed post-Triangle Ikigai Box

Owner observation:
- the Scanner emitted a Compression Triangle;
- after the triangle structure, the later right-side price action contains a
  separate compact Box-like consolidation that was not emitted as Ikigai Box;
- the suspected Box is later and structurally distinct from the already-found
  Triangle.

Required fix task:
- recover/freeze the exact CARVUSDT 5m source-time candles and detection cutoff
  before changing detector logic;
- add CARVUSDT 5m as a **positive/missed Geometry Gold case** only after the
  saved evidence confirms the owner-marked later Box under the authoritative
  Ikigai rules;
- inspect candidate enumeration/selection/dedup across pattern families and
  time windows;
- prove that an earlier Triangle signal does not suppress a later independent
  Ikigai Box on the same symbol/timeframe;
- do not weaken Box geometry gates merely to force this screenshot to PASS.

Acceptance:
- if the frozen source-time evidence satisfies the Box contract, the later Box
  is emitted independently while the Triangle remains intact;
- if the frozen evidence fails an existing Box invariant, document the exact
  invariant instead of inventing a detector exception;
- preserve independent pattern identities/dedup and existing positive/negative
  Box controls.

These two tasks are intentionally separate defect classes:
**BSV = false positive / malformed first impulse**;
**CARV = possible false negative / missed later Box**.

### G-BOX-3 — recurring post-breakdown secondary Box family

Owner feedback from the same real run shows this is broader than CARV alone.

Observed examples include:
- `CARVUSDT 5m`;
- `CPUSDT 5m`;
- `CROSSUSDT 5m`;
- `CLOUSDT 5m`;
- additional similar signals may be added from the same acceptance run when
  source-time evidence is available.

Recurring visual structure:
**compression / wedge / triangle → downside break of the active sloping
boundary → separate compact post-breakdown consolidation / Box**.

Owner trading intent:
- these are the kinds of setups the owner would manually pick for a later entry
  if trading them by hand;
- therefore treat them as a candidate recurring edge/family to investigate,
  not merely as isolated screenshots.

Required investigation:
- recover exact source-time OHLC + detection cutoff for representative examples;
- determine whether the later compact structure satisfies the existing Ikigai
  Box contract or requires an explicitly new `post-breakdown secondary Box`
  subtype;
- inspect candidate enumeration/windowing/ranking/dedup so an earlier
  Wedge/Triangle does not suppress a later independent Box;
- distinguish a genuine secondary Box from ordinary continuation/noisy rebound;
- preserve negative controls and do not make "triangle broke down" sufficient
  by itself for Box admission.

Acceptance:
- one general structural contract explains the representative positives and
  negatives;
- valid later Boxes can coexist with the earlier compression signal;
- no symbol-specific exceptions or screenshot tuning.

### FUTURE EPIC — Manual Chart → Autopilot Handoff / Position Adoption

Authoritative design:
`DOCUMENTS/MANUAL_CHART_AUTOPILOT_HANDOFF_DECISION.md`.

Owner UX direction:
- one context-aware **Autopilot** action in the terminal;
- if a manual position is open on the current symbol, ask:
  **«Хотите передать эту сделку роботу?» — Да / Нет**;
- `Нет` leaves the manual position untouched and opens the normal Robot
  workspace / Robot-owned open-position list;
- `Да` performs an explicit fail-closed Position Adoption Gate and, only on
  success, opens the same Robot workspace focused on the adopted trade;
- if the current symbol is already Robot-owned, do not ask for adoption: show
  that the coin is already traded by Robot and route directly to that position;
- this Robot-owned awareness must trigger on **every symbol transition** in the
  terminal, including navigation from a free ticker to a ticker already in
  Robot work;
- manual chart/Fibonacci markup intended for Robot must be machine-readable
  (`Manual Pattern Draft`), not an arbitrary drawing that Robot has to guess;
- Scanner, future Autopilot discovery and manual chart markup should converge
  into the same immutable candidate/admission/execution/protection lifecycle;
- already-open manual positions remain manual unless explicit adoption succeeds.

This epic is **queued only**. Do not pre-empt RVL-R6 or Geometry Quality, do not
enable LIVE, and do not create a second execution/protection/reconcile stack.

## NOW — 2026-09-29 — RVL-R6 NIGHT CHECKPOINT

Preserved owner evidence:
- one full Scanner pass completed: 778/778 symbols, 186 signals found, 200
  Telegram deliveries reported, 43 Ikigai Box observations, 104:55 elapsed;
- subsequent fresh backend instance: Robot admission READY, PAPER live-safe,
  protection healthy, no covered/armed/unhealthy symbols, ingress pending 0,
  high-watermark 0, Scanner STOPPED;
- fresh-runtime Telegram `/robot`: Robot Running/Ready, 6 candidates, 0
  Robot-owned open positions.

Do **not** overclaim the fresh zero ingress metrics: they belong to a new backend
process and cannot prove the previous 104-minute process never overflowed.
RVL-R6 remains ACTIVE until same-process historical evidence is sufficient or
one clean sustained owner run captures the required no-overflow proof.

### TG-MON-1 — fixed in code, owner re-acceptance pending

Real owner defect:
- `/monitoring` update was consumed but produced no reply while `/robot`
  showed 6 APPROVED candidates and Telegram Monitoring health remained ready.

Root cause:
- full Box durable candidate IDs made inline `callback_data` exceed Telegram's
  64-byte limit;
- `sendMessage` returned `ok:false`, which the old list path ignored.

PR #325 merged as
`4ab838857519adbacfa8fb4d780b3461f2717851`:
- bounded callback token;
- current-candidate token resolution, collision fail-closed;
- legacy callback compatibility;
- delivery failure no longer silent;
- Robot PAPER acceptance GREEN.

Remaining exit gate:
- sync owner checkout to #325 or later;
- fresh canonical runtime;
- one `/monitoring` owner check returns the candidate list/buttons.

### CELOUSDT manual PAPER reconciliation debt

Current `/positions` evidence:
- CELOUSDT Long 1.3, average entry 0.075347;
- projection `sync_state=reconciliation_required`;
- position card explicitly reports **not Robot-owned**;
- Robot status reports 0 Robot-owned open positions.

Do not close/adopt this exposure implicitly. Resolve later through explicit
manual PAPER reconciliation or the future Position Adoption contract.

## NOW — 2026-09-27 — OWNER CORRECTION: IKIGAI BOX HAS NO WATCH USER MODE

Binding owner decision: Ikigai Box uses the normal CONFIRMED signal path only.
A separate Box WATCH mode was not requested and is not part of the product UX.

Implementation implications:
- no separate WATCH Telegram cards;
- no WATCH-based explanation for a missing Robot button;
- WATCH is excluded from Robot admission, Autopilot discovery and owner acceptance;
- existing Box WATCH-specific code/flags are legacy cleanup debt and must not be expanded;
- current acceptance checks only normal CONFIRMED Ikigai Box signals and their Robot affordance.

Owning strategy authority:
`DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`, section
"Owner correction — no Ikigai Box WATCH product mode (2026-09-27)".

## NOW — 2026-09-27 — BINDING IMPLEMENTATION QUEUE: ROBOT STABILITY -> GEOMETRY QUALITY

Authoritative execution plan:
`DOCUMENTS/DEVELOPMENT_VALIDATION_LOOP_PLAN.md` §§10–13.

This queue supersedes older "next" wording, including immediate Autopilot
continuation, until the two blocking quality gates are green or the owner
explicitly reprioritizes.

| Order | ID | Priority | Task | Exit gate |
|---:|---|---|---|---|
| 1 | RVL-R1 | P0 | **DONE** — Minimal Runtime Replay contract + deterministic runner (PR #296; Robot PAPER acceptance #226 PASS) | continuous events replay through real SerializedPaperRuntime with deterministic FIFO/metric surface |
| 2 | RVL-R2 | P0 | **DONE** — deterministic pre-LIMIT manager-path overflow replay (PR #305) | current main reproduced the overload class without artificial drain barriers |
| 3 | RVL-R3 | P0 | **DONE** — exact ENTRY_PENDING ingress + lifecycle boundary frozen (PR #305) | tests prove start/end boundary and first-fill ordering requirement |
| 4 | RVL-R4 | P0 | **DONE** — temporary coverage arm + durable resting-LIMIT handoff (PR #305) | R2 GREEN; capacity 64 unchanged; no coalescing/drop/second runtime |
| 5 | RVL-R5 | P0 | **DONE** — replay/regression pack + Robot PAPER acceptance CI | run #36400222441 SUCCESS, 385 passed; local focused gaps also green aside from pre-existing unrelated failures |
| 6 | RVL-R6 | P0 | **ACTIVE** — one canonical owner PAPER acceptance | no ingress_overflow; protection healthy; real queue sustains traffic |
| 7 | RVL-G1 | P1 | Geometry Gold schema + inventory of saved real cases | exact available OHLC/evidence mapped; gaps explicit |
| 8 | RVL-G2 | P1 | Seed first compact Geometry Gold set | real Wedge/Triangle positive/negative/anchor/stale cases replayable |
| 9 | RVL-G3 | P1 | Geometry baseline report | per-case PASS/FAIL and anchor deltas visible in one run |
| 10 | RVL-G4 | P1 | Fix geometry defect classes one bounded slice at a time | targeted gold failures turn GREEN without regressing accepted cases |
| 11 | RVL-G5 | P1 | Add high-value geometry/state invariants | invariants complement gold cases without broad test inflation |
| 12 | RVL-G6 | P1 | **FULL PASS COMPLETE / GEOMETRY GATE NOT PASSED** | 782/782, 112 signals, 128 Telegram deliveries, 28 Box observations, 73:39; owner found systematic geometry defects -> GEO-U1/U2 |
| 12a | GEO-U1 | P1 queued | Universal Pivot-Consensus Envelope Geometry for Wedge/Triangle/Compression | source recovery + shadow consensus/oscillation metrics, then evidence-gated selector change; does not interrupt active G6 |
| 12b | GEO-U2 | P1 queued after GEO-U1 | Broadening Formation / «Рупор» Scanner family | recover ENAUSDT 1m source-time case, classify widening consensus pairs separately from wedge/triangle, Telegram-first Scanner integration; Robot strategy deferred |
| 13 | RVL-V1 | P2 | Compact validation report command | one report shows FAST/REPLAY/Geometry/PAPER/owner gate states |
| 14 | RVL-V2 | P2 conditional | Bounded normalized incident capture | only if production-shape replay fidelity proves insufficient |
| 15 | RVL-V3 | P2 | Tier-aware CI routing | focused FAST/REPLAY automatic; broader PAPER CI remains bounded |

**2026-09-30 G6 checkpoint:** full owner Scanner traversal completed: 782/782 tickers,
112 signals, 128 Telegram deliveries, 28 Box observations, 73:39 elapsed.
Traversal/Telegram evidence is complete. Geometry Quality is not accepted because
the same review exposed systematic anchor/shape-selection defects now owned by
GEO-U1/GEO-U2. Do not repeat the full pass until geometry changes justify a new
owner acceptance.

Hard sequencing:
- no new production ingress fix before RVL-R2 RED and RVL-R3 boundary proof;
- no real owner PAPER acceptance before R1-R5 are green;
- Geometry Lab begins after Robot Stability owner gate R6, unless the owner
  explicitly runs it in parallel;
- Autopilot, new pattern families, secondary UX and nonessential refactors are
  preserved but parked behind these gates;
- replay/golden fixtures never replace existing owner acceptance contracts.

## NOW — 2026-09-27 — PROCESS OPTIMIZATION: REPLAY + GEOMETRY GOLDEN SET

Owner-approved development-loop improvement:
`DOCUMENTS/DEVELOPMENT_VALIDATION_LOOP_PLAN.md`.

Current product focus is reduced to two blocking quality fronts:
1. **P0 Robot Stability** — current protection ingress overflow remains RED. PR #293 reduced reconcile stall materially but runtime still reached 64/64 and later marked 2ZUSDT unhealthy with `ingress_overflow` while covered symbols were `ENTRY_PENDING`.
2. **Geometry Quality** — Wedge/Triangle geometry and anchor fidelity, developed against deterministic saved real cases before the mandatory full Scanner acceptance.

Process change:
- real incident -> deterministic fixture -> RED -> bounded fix -> replay GREEN -> minimum PAPER CI -> owner acceptance;
- first runtime replay must model continuous multi-symbol `ENTRY_PENDING` traffic without artificial drain barriers;
- establish `tests/fixtures/runtime_replays/` and `tests/fixtures/geometry_gold/` as developer evidence surfaces;
- use FAST / REPLAY / PAPER CI / OWNER ACCEPTANCE cost tiers;
- replay/local fixtures never replace the permanent full-universe Telegram Scanner acceptance rule;
- preserve FIFO protection evidence, fail-closed semantics, PAPER/LIVE boundaries and owner-manual runtime ownership;
- Autopilot and other feature expansion remain preserved but deferred behind Robot Stability and Geometry Quality unless the owner explicitly reprioritizes.

## NOW — 2026-09-27 — NEW BINDING OWNER PRIORITY: ROBOT AUTOPILOT

Owner direction: begin development of autonomous candidate discovery and PAPER
trading without per-candidate human approval, while reusing the existing Robot
execution/protection/recovery machinery.

Authoritative plan:
`DOCUMENTS/ROBOT_AUTOPILOT_IMPLEMENTATION_PLAN.md`.

Foundation already proven:
- PR #288 merged to main as `6e865536cd1cd1a5cf7a7211576e1fe5d8b57be8`;
- CONFIRMED Ikigai Box now freezes `BOX_PLAN_ONLY` and crosses into
  `BOX_ENTRY_READY` only through canonical admission;
- Wedge/L-shape already use the shared candidate/admission lifecycle;
- existing Robot execution, protection, ownership and reconciliation remain the
  only trading engine.

Binding implementation order:
1. **Stage A — OFF/SHADOW/PAPER_AUTO durable state + pure auto-admission policy.**
   Default OFF. SHADOW must be read-only and auditable.
2. **Stage B — shared read-only admission assessment** so manual and automatic
   admission cannot diverge.
3. **Stage C — RobotDiscoveryController in SHADOW**, reusing existing detectors,
   source-time OHLC and per-symbol 5m→1m traversal.
4. **Stage D — PAPER_AUTO canonical admission**, only after explicit
   portfolio/risk limits are frozen; auto path must call the same canonical
   admission boundary as the owner button.
5. **Stage E/F — portfolio protections + Telegram Autopilot controls/status.**
6. **Stage G — ranking/expectancy only after sufficient PAPER evidence.**

Hard constraints:
- no second execution engine, order journal, protection system or recovery
  coordinator;
- discovery never submits orders;
- Ikigai Box WATCH is not an owner-approved product mode and must not participate in discovery or admission; only normal CONFIRMED Box signals are in scope;
- do not invent cross-pattern score comparability or risk thresholds;
- unset required portfolio limits fail closed;
- OFF stops new automatic admissions but never abandons an already-open trade;
- LIVE mutations remain prohibited.

This priority supersedes the previous "next task" ordering. Older incomplete
acceptance/geometry/dual-timeframe work remains queued and is not deleted.

## TODAY — 2026-09-27 — BINDING OWNER ORDER

This order is the current owner priority and supersedes older 2026-09-26
"today"/next-step ordering until the owner changes it again.

### P0.1 — Fix the permanent Telegram control surface — MERGED

- PR #271 merged as `e0afeee`.
- One state-aware `/scanner` command remains:
  RUNNING → Pause, PAUSED → Continue, STOPPED → Start.
- Owner Menu is reasserted after owner messages/callbacks through the common
  Telegram update loop.
- Runtime acceptance still requires loading current `main` on the owner PC;
  the earlier pre-fix run is evidence only.

### P0.2 — Implement one Pattern → Robot integration platform — MERGED

Authoritative standard:
`DOCUMENTS/PATTERN_ROBOT_INTEGRATION_STANDARD.md`.

- PR #274 merged as `878d18d`.
- Wedge and L-shape now share `pattern_robot_integration.py` for executable
  capability + durable pre-admission candidate handoff.
- Existing common admission, execution ownership, protection, position,
  lifecycle and restart/reconcile paths remain authoritative.
- Pattern-specific strategy stays in adapters; no second execution engine was
  introduced.

### P0.3 — Migrate current pattern families to the common adapter boundary — SAFE BOUNDARY COMPLETE

- Wedge remains the reference adapter through the shared handoff/lifecycle.
- L-shape already uses the common admission, monitor, execution/protection and
  restart/reconcile lifecycle; only its strategy rules remain pattern-specific.
- PR #275 merged as `03d19cb`: non-executable Ikigai Box signals no longer show
  the misleading `🤖 Робот` status affordance.
- Box execution remains intentionally fail-closed: current Box plan is
  `execution_authorized=False` and admission rejects `IKIGAI_BOX / BOX_PLAN_ONLY`.
  Real Box admission requires a separate authoritative executable contract;
  do not invent strategy parameters to force it through.
- Triangle/future patterns must use the same shared route.

### P0.4 — Close remaining desktop-runtime composition debt — COMPLETE

- Canonical tracked start path remains `start_robot_runtime.bat` with PAPER DB
  identity, backend/Telegram readiness, admission/protection and Scanner gates.
- Existing desktop shortcut names remain the stable owner UX, but their targets
  are direct tracked launchers: `Запуск робота -> start_robot_runtime.bat`,
  `Остановить робота -> stop_robot_runtime.bat`, and
  `start_scanner -> start_scanner.bat`. Untracked local wrappers are not authority.
- **Owner portability decision 2026-10-07:** PC and laptop share the same
  `C:\\BybitScanner` repository root and the same shortcut semantics. Do not maintain
  separate PC/laptop launcher variants or require shortcut rewrites when switching
  machines. Shared launchers must use repo-relative paths; machine-local Desktop,
  OneDrive, username and hostname differences stay outside tracked runtime semantics.
  Git synchronization must not silently retarget the existing owner shortcuts or
  change “Запуск робота” into a different startup composition.
- **Intent contract (owner decision reconfirmed 2026-10-07):** `Запуск робота` is
  the normal one-action `ALL` start: Robot + Scanner through the shared Runtime
  Intent Reconciler. `start_scanner` remains `SCANNER` only. Dedicated Robot-only
  control paths may use `ROBOT`, but the desktop “Запуск робота” surface must not
  be narrowed to Robot-only. `start_robot_runtime.bat` with no argument remains
  `ALL` for backward compatibility.

- `tools/sync_owner_shortcuts.ps1` is the canonical one-shot repair/verification
  for those targets; it preserves the existing shortcut names and pins the
  `Запуск робота` shortcut argument to explicit `ALL` (verified after save).
- Owner runtime-check on 2026-09-27 proved the canonical start path.
- Abrupt-power recovery exposed a stale fail-closed
  `ROBOT_ENTRY_OWNERSHIP_MISMATCH` latch for BLENDUSDT after the durable
  candidate/trade/position evidence had already settled flat. The canonical
  `POST /api/robot/reconcile` path correctly cleared it to
  `ROBOT_RUNNING / PAUSED`; no DB hand-edit was used.
- The first canonical stop attempt then exposed a launcher-only defect:
  `ModuleNotFoundError: No module named 'terminal'` because the helper was
  executed as `tools\\stop_robot_runtime.py` instead of a repository module.
- PR #280 merged as `adcd44e1580a1f7648abb79c20a84c6980859660`:
  safe-stop now launches `python -m tools.stop_robot_runtime`; Robot PAPER
  acceptance #218 succeeded.
- Owner reran the real desktop/canonical stop path: success text returned,
  exit code 0, final durable state `ROBOT_STOPPED / ROBOT_STOPPED` version 80;
  backend/Telegram intentionally remained running.
- This P0.4 migration/repair is complete. **Do not repeat its investigation.**
  Reuse `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md` for future runtime
  incidents and broaden only when new evidence does not match a known path.

### P0.5 — One-action Runtime Intent Reconciler — COMPLETE

Owner runtime UX override from 2026-09-27 remains authoritative:

> The owner states the desired outcome once; BybitScanner must inspect,
> prepare, reconcile and verify the required PAPER runtime automatically.

Authoritative plan:
`DOCUMENTS/RUNTIME_INTENT_RECONCILER_PLAN.md`.

Implementation/evidence:
- PR #285 merged as `543168420afaab3b0dde9be083969ff867b69263`: shared
  `SCANNER / ROBOT / ALL` Runtime Intent Reconciler, PAPER backend boundary,
  desktop bootstrap and Telegram routing;
- the one-action `ALL` intent (Robot + Scanner) was owner-run from a stopped
  state to Robot READY/protection healthy + Scanner RUNNING without the former
  manual Robot-start prerequisite. **Owner reconfirmation 2026-10-07:** this is
  the intended permanent desktop behavior of `Запуск робота`; the temporary
  Robot-only reinterpretation in PR #404 was incorrect and must not be treated
  as product authority;
- canonical safe-stop remains separate and proven;
- backend/Telegram reuse is guarded by PAPER DB identity and readiness checks;
- LIVE/operator authority remains forced off for the PAPER bootstrap.

Do not reopen P0.5 unless new evidence contradicts the one-action contract.
The remaining owner gate is the complete full-universe acceptance, not runtime
intent implementation.

### P1 — Ikigai Box «Кривой первый импульс» — COMPLETE

- The required first production slice was completed on Opus 5.5 as commit
  `1ce2aaa12920d1e6a407fe2268173299ce69fdb6`
  (`fix: end Ikigai first impulse at its confirmed terminal pivot`).
- The fix reuses the mirrored existing
  `REVERSAL_LEFT_BARS=3 / REVERSAL_RIGHT_BARS=3` pivot semantics and rejects
  malformed A..B candidates before ranking when an earlier confirmed terminal
  pivot already exists.
- A short opposite-colour pause remains allowed when it does not form a
  confirmed counter-swing; the old colour-only veto is not restored.
- AIGENSYNUSDT 5m no longer re-anchors historical B from 19:05 to 20:00 when
  later second-leg progress appears.
- `Ikigai Box detector` CI run #82 on that commit completed **SUCCESS**.
- The production fix and regression now live in current `main`; do not repeat
  the RED gate, Opus implementation, or first-impulse diagnosis unless new
  evidence contradicts this result.

### Ikigai Box ARUSDT 1m STOP feasibility — CLASSIFIED / NOT A CODE DEFECT — 2026-09-28

Real acceptance evidence:
- normal CONFIRMED `ARUSDT 1m` Telegram signal was delivered without
  `🤖 Робот` and with the owner warning that the Robot candidate was not created;
- exact saved production anchors were recovered from `signals_history.json`
  and replayed through the real 199-candle detector window;
- the Box passes PR #300 grid/TAKE tick-normalization and reaches
  `plan_ikigai_box()`;
- frozen LONG inputs: tick `0.001`, grid
  `4.790 / 4.786 / 4.782 / 4.778`, average `4.784`, TAKE `4.811`,
  fee-aware reward/unit `0.021243`;
- analytical RR>=2 STOP bound is `4.77912`, which must round toward entry to
  `4.780`;
- the nearest tick strictly beyond P4 is `4.777`;
- therefore the valid-RR interval requires STOP >= `4.780`, while the
  structural P4 rule requires STOP <= `4.777`: the intervals do not overlap;
- RR is about `2.18` at `4.780` but that STOP is inside the grid; RR is about
  `1.67` at `4.777`, which is beyond P4 but below the required minimum.

Conclusion:
`NO_VALID_STOP_EXISTS`. The STOP search is not missing an executable tick;
this formation is correctly fail-closed as non-executable under the approved
rules. Absence of `🤖 Робот` on this ARUSDT card is truthful behavior, not a
Robot-candidate bug.

Do not weaken RR >= 2:1, move STOP inside P4, or invent a fallback STOP.
Do not reopen PR #300 or ARUSDT STOP search without contradictory new evidence.

### P1 final gate — one clean owner-run full acceptance

**Current checkpoint — 2026-09-28 (partial evidence only, full-pass gate still open):**
- local runtime loaded current main `e546e167c20bc97257e01fae4d90b400eed35e7e`;
- local Ikigai Box WATCH flags were disabled; owner-facing acceptance is
  CONFIRMED-only;
- real CONFIRMED `AKEUSDT 5m` rendered `🤖 Робот`; owner tap returned
  `Сигнал принят: AKEUSDT ✅` and Robot remained `Запущен / Готов`;
- PR #300 tick-normalization fix had already been verified on the exact frozen
  production-failing `2ZUSDT 1m` A/B case before merge;
- Telegram Bot API reports the owner chat menu button as `type=commands` and
  all eight expected commands, including dynamic Scanner pause, are published;
  the current desktop Telegram client nevertheless does not visibly render the
  Menu button. Treat this as a client-presentation discrepancy, not as missing
  server-side bot configuration. Do not repeat the same Bot API wiring checks
  unless new evidence changes;
- this checkpoint **does not** satisfy the permanent acceptance rule because the
  current full eligible-universe pass has not yet been reported complete.
- subsequent `ARUSDT 1m` stop-math classified its missing Robot button as
  correct fail-closed behavior, not a defect: RR>=2 requires STOP >= `4.780`
  while "strictly beyond P4" requires STOP <= `4.777`; no executable tick
  exists. This case therefore does not block acceptance.

After the P0 fixes that affect the owner/runtime surface are merged and loaded
into the canonical desktop path:

- one complete eligible-universe Scanner pass;
- normal Telegram delivery;
- all integrated patterns;
- verify Menu persistence and Scanner Pause/Continue on the same traversal;
- verify real Robot candidate admission where a pattern is Robot-capable;
- verify common monitoring/position/lifecycle surfaces as real events become
  available;
- no partial/subset run may replace this acceptance.

The currently running pre-fix pass remains useful exploratory evidence but
cannot accept code that was merged/loaded after it started.

### P2 — Full dual-timeframe Scanner 5m→1m

Per symbol: all 5m pattern work, then all 1m pattern work, with independent
symbol × timeframe × pattern × formation identity/dedup/evidence.

### Process standard completed today

- `DOCUMENTS/QUEST_REWARD_LEDGER.md` introduced as append-only canonical
  authority for XP/achievements/loot.
- `QUEST_STATE.md` becomes a projection; future verified quest outcomes must
  update both automatically as part of Definition of Done.
- `DOCUMENTS/PATTERN_ROBOT_INTEGRATION_STANDARD.md` defines the shared product
  and integration contract.
- `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md` records stable runtime failure signatures and canonical recovery/repair paths; recurring incidents use known-path diagnosis before exploratory probing.

## OWNER RUNTIME ENTRYPOINT — DESKTOP SHORTCUTS — 2026-09-27

Permanent owner UX rule: Scanner/Robot are started manually from the existing desktop
shortcut surface, currently `start_scanner`, `Запуск робота`, and the companion stop
shortcut. This is the stable user-facing path.

Future runtime/Scanner/Robot development must upgrade the scripts/targets behind these
shortcuts so newly merged behavior is available through the same owner workflow.
Do not create a parallel normal launch path and do not ask the owner to rediscover which
launcher he uses. Terminal commands are diagnostic/repair-only, not the normal start UX.
Before runtime acceptance, verify that this desktop surface reaches the current canonical
implementation and all readiness/safety gates. The actual start remains owner-manual.

## IKIGAI FIRST-IMPULSE IMPLEMENTATION — COMPLETED 2026-09-27

Historical RED checkpoint #268 is retained for provenance only.

Final implementation evidence:
- production commit: `1ce2aaa12920d1e6a407fe2268173299ce69fdb6`;
- implementation model recorded in commit metadata: Claude Opus 5.5;
- touched production boundary remained the intended Ikigai detector/test scope;
- AIGENSYN regression is present in current `main`;
- terminal first-impulse B is frozen by the first confirmed mirrored structural
  pivot, preventing later progress from retrospectively relocating B;
- legacy colour-only stopping semantics were removed in favor of structural
  counter-swing confirmation;
- `Ikigai Box detector` workflow run #82: **SUCCESS**.

Do not resurrect the pre-implementation wording
`Opus implementation pending`, do not repeat the RED diagnosis, and do not
create another Opus slice for the same AIGENSYN defect without new failing
evidence.

## TODAY — 2026-09-26

Today's owner execution sequence:

1. Open-PR weekly triage.
2. Robot open-position Telegram card refinement, including:
   - add **«Открыть в Trading View»** under each open-position card;
   - rename the shared TradingView button under all Scanner signals to exactly **«Открыть в Trading View»**;
   - keep the already queued position-card presentation refinements; no trading-logic change.
3. Ikigai Box first-impulse geometry — AIGENSYNUSDT 5m / general construction rule; do not reopen FLOCK without new evidence.
4. Full dual-timeframe Scanner 5m→1m — per symbol, 5m then 1m, with independent symbol × timeframe × pattern × formation state.

This daily order supersedes older next-step wording for today unless the owner changes it.

## BINDING OWNER EXECUTION ORDER — 2026-09-26

Current owner sequence, superseding earlier next-step ordering:

1. **Open-PR weekly triage** — review all currently open PRs touched/left hanging this week; close superseded/obsolete ones, retain only genuinely active work, and do not merge by age or convenience.
2. **Robot open-position Telegram card** — presentation-only refinement; no trading-logic change. Add an **«Открыть в Trading View»** URL button under each open-position card for its symbol, and rename the shared TradingView button under **all Scanner signals** to exactly **«Открыть в Trading View»** (currently `📈 Open TradingView`).
3. **Ikigai Box first-impulse geometry** — resolve AIGENSYNUSDT 5m and the general owner-defined first-impulse construction rule; do not reopen the already-fixed stale FLOCK fixture unless new evidence requires it.
4. **Full dual-timeframe Scanner 5m→1m** — per-symbol 5m then 1m processing with independent (symbol × timeframe × pattern × formation) memory/dedup/evidence.

The previously queued full owner PAPER acceptance remains mandatory when its corresponding implementation state is ready, but it is **not the immediate next task** while this owner sequence is active.

## P0 — FULL PAPER PROTOTYPE OPERATIONAL COMPLETENESS — 2026-09-26

Owner priority override: before another long owner acceptance pass, eliminate
the runtime-composition gaps that can make a partially running stack look
"fully ready". This exists to protect owner time; do not work around it with
manual repeated preflights.

Incident evidence from the 2026-09-26 run:

- PAPER backend and Robot were healthy/READY, but `telegram_monitoring.py`
  was not running, so Robot approval callbacks and Telegram menu commands had
  no consumer;
- the owner-visible Telegram buttons remained present, creating a false
  appearance of an interactive system;
- local `start_scanner_all.cmd` launches standalone `main.py`, while
  Telegram Scanner controls target the backend-owned
  `ScannerControlRuntime`; those are separate Scanner owners and may create
  duplicate scans if both are used;
- historical tracked `start_robot_runtime.bat` launched backend, Telegram
  monitoring and standalone `main.py` using fixed sleeps; PR #251 removed
  the standalone owner, but a new runtime check then exposed another launcher
  defect: it blindly POSTs `/api/scanner/start`, so persisted
  `SCANNER_PAUSED` cannot resume and the launcher must not be reused until
  state-aware dispatch is merged;
- local `start_robot_all.cmd` has better backend/Robot gates but starts
  Scanner before Telegram monitoring and is untracked, so it is not a
  versioned/testable canonical launcher;
- `/api/health` is liveness only and cannot establish full prototype
  readiness;
- `telegram_monitoring.py` has no enforced singleton ownership/readiness
  heartbeat, despite the code contract that it must be the sole getUpdates
  consumer;
- explicit 1m Wedge analysis is still marked
  `scanner_observational_only=True`, which intentionally suppresses the
  Robot candidate/button and conflicts with the owner's current requirement
  that executable supported Wedge signals keep the Robot action available.

Architecture direction, borrowing mature runtime practice without importing a
new platform: one canonical composition/start path, dependency readiness
barriers instead of sleeps, one owner per runtime component, startup
reconciliation/readiness before admission, and a compact status/preflight
surface. Do not add Docker/systemd merely for this Windows prototype.

Economical implementation sequence:

1. **DONE:** PR #249 merged as `2032188` — one-pass authoritative
   ScannerControlRuntime with pause/resume/stop; do not reopen or repeat it;
2. **DONE:** PR #251 merged as `b02e330` — canonical prototype launcher no
   longer spawns standalone `main.py`; Scanner start goes through the backend
   Scanner control API;
3. **DONE:** PR #252 merged as `1e07dec` — `telegram_monitoring.py` is
   single-owner, proves getUpdates ownership before READY, and startup waits
   for its identified health endpoint before Scanner mutation;
4. **DONE:** PR #254 merged as `fe56450` — PAPER backend binds/reserves its
   localhost HTTP listener before REST/WebSocket/SQLite/runtime/recovery side effects;
   a duplicate backend loses ownership before touching authoritative state.
5. **DONE:** PR #253 merged as `18fc8c2` — fresh backend recovers stale
   `SCANNER_RUNNING`/`SCANNER_PAUSED` to `SCANNER_STOPPED`; on an already-live backend
   launcher routes `STOPPED -> start`, `PAUSED -> resume`, `RUNNING -> reuse/no mutation`,
   unknown/unavailable -> fail closed;
6. **DONE:** PR #255 merged as `0f209e7` — backend `/api/health` now proves
   canonical PAPER component identity through the live serialized owner and exposes only
   allow-listed `database_identity`, `process_instance_id`, and `build_sha`;
7. **DONE:** PR #256 merged as `f7815fe` — canonical launcher reuses an already-running
   canonical PAPER backend only when health identity matches the launcher's intended DB;
   wrong/malformed identity fails closed and no duplicate backend is spawned. Early bind
   remains the process-ownership safety barrier. The untracked `start_robot_all.cmd`
   false-success remains recorded debt and is not startup authority;

8. **PARTIAL:** PR #257 merged as `00b250c` — fixed 2s PAPER backend sleep is gone;
   spawned backend now has a bounded 60s canonical health/DB-identity readiness wait.
   PR #258 merged as `1d9b258` — backend health now exposes owner-proven
   `robot_admission_ready`. PR #259 merged as `259161f` — Scanner routing is now gated on
   Robot admission plus existing protection health. PR #260 merged as `6c1dea9` — Telegram
   health now exposes the same PAPER `database_identity` definition. PR #261 merged as `91a1b18`
   — launcher now requires Telegram READY for that same DB identity. PR #262 merged as `087b00c`
   — backend health now exposes PAPER LIVE/config acceptance booleans. PR #263 merged as `2b2e097`
   — launcher now enforces them before protection/Scanner routing. Startup readiness path is closed;
   Telegram callback readiness and Scanner owner routing are bounded.
9. **DONE:** PR #265 merged as `15ad7aa` — when Robot candidate persistence fails,
   ordinary Scanner delivery remains intact and the owner receives exactly one bounded
   warning explaining the missing Robot button; secondary recipients are not warned and
   warning-delivery failure is non-fatal;
10. **DONE:** PR #264 merged as `5852a09` — explicit 1m Wedge is Robot-eligible only after canonical geometry/cursor evidence is built; projection/cursor failures remain fail-closed.
11. **DONE:** PR #266 merged as `90b8559` — stale FLOCK synthetic fixture now gives A a valid actual local reversal origin under the 2026-09-23 owner rule; detector unchanged; red-core plus 55% retrace / 12% overshoot coverage preserved; Ikigai Box detector CI SUCCESS.
12. next step: one owner-run full-universe Telegram/PAPER acceptance pass under the existing hard acceptance rule.

Each Codex task is one bounded micro-slice with one minimum changed-behavior
check. No broad refactor, supervisor framework, new persistence system,
Docker migration, repeated full suites, or agent-run Scanner pass.

## NEXT SESSION START — RECONCILIATION / SYNC DEBT — 2026-09-26

Owner direction: **start the next work session with the remaining synchronization /
reconciliation debt before resuming feature work.** Do not treat the seven
historical dirty worktrees as unresolved work; their audit directly below has
already proven them fully superseded.

The next-session checkpoint is the still-live/sensitive state outside those seven:

1. `C:\BybitScanner-box-robot-run` — runtime checkout; last observed with
   backend PID 21116, open RDWUSDT position and `RECONCILIATION_REQUIRED`.
   Re-check actual runtime/position/process state before any mutation; do not
   assume the recorded PID or position is still current tomorrow.
2. `C:\BybitScanner` — current dirty session checkout with untracked
   `runtime/`, launchers and other local state. Reconcile deliberately; do
   not overwrite or broadly clean user-owned local work.
3. `C:\BybitScanner-sync-20260926` — reconciliation working copy to be
   resolved/retired only after its role and remaining delta are re-established.
4. `C:\BybitScanner-reconciliation-backup-20260926` — preserved
   `start_robot_all.cmd` backup; keep until reconciliation is conclusively
   finished and no longer depends on it.

Start with **minimal state recovery** of these four items and current `main`,
then resolve only the narrowest remaining synchronization debt. Do not rerun
the already-completed seven-worktree history audit, do not recreate backups
without new evidence, and do not touch active runtime/trading state blindly.

**Checkpoint completed 2026-09-26.** The four sensitive paths were reconciled
without broad cleanup. `sync-20260926` and `box-robot-run` are on current
`main`; two unique local files from `C:\BybitScanner` were preserved in the
external reconciliation backup; the dirty checkout itself remains untouched.
The PAPER backend was started with LIVE gates off and Scanner still stopped.
Protection coverage recovered healthy, explicit operator reconciliation
succeeded, and Robot landed in `ROBOT_RUNNING / PAUSED` with the open RDWUSDT
PAPER lifecycle preserved. Unresolved protection obligations were zero.
Return now to the active L-shape PAPER Robot quest; do not repeat this
reconciliation unless new evidence changes runtime or repository state.

## DIRTY WORKTREE RECONCILIATION AUDIT — 2026-09-26

Read-only audit result for the seven previously dirty historical worktrees:
`.worktrees/ikigai-card`, `bv`, `ikigai-bands`, `ikigai-viz`,
`locality`, `lshape`, and `lshape-observer`.

**Outcome: all seven are fully superseded; no unique work remains in any of
them. Do not repeat recovery, patch preservation, or implementation work from
these worktrees.**

Evidence boundary:

- each worktree's complete dirty set (tracked changes plus untracked files
  where present) was compared by blob content against repository history;
- a match counted only when the whole dirty set corresponded to one historical
  commit/state rather than a mixture of unrelated versions;
- PR/branch history was checked for the corresponding merged work;
- tests were **not** rerun for this audit; the conclusion is repository-history
  equivalence, not fresh runtime/test acceptance.

Resolved mappings:

- `.worktrees/ikigai-card`: 6/6 dirty files = `5ad500d`, branch
  `origin/codex/ikigai-card-cleanup`, PR #205 squash `5f2afe2`; only the
  living `BACKLOG.md` has evolved afterward.
- `bv`: 3/3 = `a4ef2ff`, merged through PR #180; local HEAD is the pre-squash
  version, with only LF/CRLF warning noted.
- `ikigai-bands`: 5/5 = `8009997`, merged through PR #167.
- `ikigai-viz`: 4/4 = `4ea5ee4`, first commit of merged PR #166; its
  untracked overlay/test files are historical merged content, while main later
  evolved further.
- `locality`: 3/3 tracked+untracked = `d6a7df9`, merged PR #176; fixture
  files are identical to main.
- `lshape`: 4/4 untracked = `05eeae0`, first L-shape file version from
  PR #195, later superseded by subsequent L-shape work.
- `lshape-observer`: dirty `main.py`, `l_shape_scanner.py`, and test =
  branch tip `0a7e88d`, merged PR #197; local HEAD is three commits behind its
  upstream.

No standalone patch or backup is required for these seven worktrees; their
content is recoverable from Git history via `5ad500d`, `4ea5ee4`,
`d6a7df9`, `0a7e88d`, `05eeae0`, `a4ef2ff`, and `8009997` plus the
corresponding squash/merge commits.

**Do not touch as part of this cleanup/reconciliation without a separate
owner-authorized step:**

- `C:\BybitScanner-box-robot-run` — active runtime checkout; at audit time
  backend PID 21116, open RDWUSDT position, `RECONCILIATION_REQUIRED`;
- `C:\BybitScanner` — current dirty session checkout with untracked
  `runtime/`, launchers and other local state;
- `C:\BybitScanner-sync-20260926` — active reconciliation copy;
- `C:\BybitScanner-reconciliation-backup-20260926` — preserved
  `start_robot_all.cmd` backup.

The audit itself made no worktree cleanup, file transfer, runtime change, HEAD
change, branch change, stash change, or process launch/stop.

> Historical #249 checkpoint below; the current P0 operational-completeness priority and acceptance gate above take precedence over its next-work sequence and runtime snapshot.

## RUNTIME / L-SHAPE / SCANNER CONTROL CHECKPOINT — 2026-09-26

### Completed and proven — do not repeat

- PR #248 `feat(robot): connect L-shape to PAPER lifecycle` was merged to
  `main` as `753a800341fd66a2b0a616b0e934ed87141661aa`.
- L-shape now has a durable Scanner -> Robot candidate handoff, reuses the
  shared PAPER Robot lifecycle/protection/recovery path, and has the real
  owner Telegram `🤖 Робот` control.
- Owner explicitly authorized executable L-shape source timeframes **1m and
  5m**. Admission is bounded to exactly those timeframes; 15m/other timeframes
  are rejected rather than implicitly enabled.
- The #248 head passed `Robot PAPER acceptance` before merge. This proves the
  deterministic CI path, **not** the still-required owner runtime/PAPER
  acceptance.

### Runtime incident / open blocker

- The live PAPER Robot entered
  `ROBOT_RUNNING / RECONCILIATION_REQUIRED` after protection-feed
  `ingress_overflow`. REST recovery then produced the expected fail-closed
  `EMERGENCY_CLOSE` obligations for owned open Robot positions.
- The emergency-close behavior is consistent with the designed safety path;
  the unresolved root cause is **why protection ingress overflowed**. Do not
  weaken or bypass the reconciliation/protection fence to make admission READY.
- Before relying on Robot for new PAPER entries, complete the normal
  evidence-based Robot reconciliation and separately diagnose the
  `ingress_overflow` latency/queue-pressure cause from runtime metrics/logs.
- The current L-shape raid therefore remains **not runtime-accepted** and earns
  no completion XP yet.

### Scanner control defect discovered during acceptance

Observed owner runtime behavior: while Scanner durable mode remained
`SCANNER_RUNNING`, `ScannerControlRuntime` launched a new full-universe pass
after the prior pass returned. The owner observed a third traversal. The old
Telegram `/scanner` command also conflated pause/resume with “stop”:
`PAUSED` prevented a future pass from starting but did not abort the pass
already executing.

Owner-approved control contract:

1. **One manual start = at most one complete universe pass.** Natural
   completion -> `SCANNER_STOPPED`; never auto-loop into pass 2.
2. **Pause** is cooperative and preserves the current traversal cursor. The
   current symbol/timeframe may finish; execution then blocks before the next
   checkpoint.
3. **Continue** resumes the same in-memory traversal from that checkpoint; it
   must not restart from ticker 1.
4. **Stop Scanner** is a separate command. It aborts the current pass at the
   next safe symbol/timeframe checkpoint and leaves `SCANNER_STOPPED`.
5. Scanner lifecycle actions must not start/stop/pause Robot or otherwise
   mutate Robot admission state.

Draft PR #249 implements this boundary:
- cooperative Scanner checkpoint in `run_scan_pass()`;
- explicit runtime/API `stop_scanner`;
- natural one-pass completion -> STOPPED;
- dynamic Telegram command: `⏸ Пауза сканера` /
  `▶ Продолжить сканер` / `▶ Запустить сканер`;
- separate permanent `⏹ Остановить сканер` command;
- Telegram command-menu button self-check/recovery via
  `getChatMenuButton` -> `setChatMenuButton` when needed;
- focused runtime/Telegram regression coverage.

Latest #249 code-bearing head before this documentation checkpoint:
`d2a6473fe654134a017d48840232cfe16b83e05f`, status **DRAFT / NOT MERGED**.
Subsequent commits in this branch are documentation-only, so do not confuse
the branch tip with a new runtime-code change. The first direct Scanner-control CI run exposed
a race in the new pause/resume test itself (`ConcurrentUpdate` caused by the
test allowing the background pass to cross the checkpoint before PAUSED was
committed). Commit `d2a6473...` made the test ordering deterministic without
changing runtime code. Robot PAPER acceptance run #191 is now green, including
the direct `tests.test_scanner_control_runtime` +
`tests.test_telegram_monitoring` step. The separate Ikigai Box workflow remains
red on the pre-existing FLOCK baseline and is not a #249 Scanner-control
regression.

### Separate Box blocker — keep out of #249

The `Ikigai Box detector` workflow on #249 failed only
`test_flock_style_green_wick_anchors_red_core_and_55pct_box_gate`
(expected one FLOCK-style watch, got zero). The same test and detector logic
already exist in current `main`; #249 does not modify Box geometry. Treat this
as the existing Box geometry boss, not as justification for Scanner-control
patching. Resolve it in the dedicated Ikigai first-impulse/FLOCK slice.

### Tooling/runtime audit blocker discovered 2026-09-26

- Owner requested a read-only audit of what PAPER Robot traded on 25.09.2026
  (plus any post-midnight 26.09 MSK records): per-trade ownership, entry/exit,
  gross PnL, fees, net PnL, close reason, emergency closes, open trades and
  durable Robot state. This audit is still **pending**; do not infer trading
  performance from partial Telegram evidence.
- The intended host-local read-only audit through Codex Desktop is currently
  blocked by repeated `401 Unauthorized: Incorrect API key provided` responses.
- Diagnostics prove the normal credential sources are not the cause:
  current/process/user/machine `OPENAI_API_KEY` and `CODEX_API_KEY` are
  absent; `~/.codex/auth.json` reports `auth_mode=chatgpt`, no stored API key
  and valid ChatGPT tokens; `codex doctor` reaches the ChatGPT websocket with
  HTTP 101.
- Codex Desktop is still installed as build `26.917.9434.0` while
  `codex doctor` reports build `26.924.1866.0` available. The in-app updater
  repeatedly says the update is ready but relaunches without changing the
  installed package version. Resolve/update the Desktop client before spending
  more owner time on credential hunting.
- `codex doctor` also reports
  `helper_sandbox_lock_failed` for elevated Windows sandbox provisioning.
  Treat that as a separate Codex host-tooling issue unless evidence connects it
  to the 401; do not conflate it with BybitScanner runtime defects.

### Next dependent work

1. #249 now has direct green Scanner runtime + Telegram menu CI evidence on
   `d2a6473...`; merge decision remains owner-controlled.
2. If merged, synchronize/restart the PC runtime only when the owner explicitly
   chooses to do so.
3. Owner acceptance for Scanner control: start -> pause -> continue same pass ->
   stop; separately prove one uninterrupted complete pass ends in STOPPED and
   does not auto-start another cycle.
4. Complete evidence-based Robot reconciliation before accepting new PAPER
   Robot entries.
5. Diagnose the `ingress_overflow` root cause without weakening fail-closed
   protection.
6. Finish L-shape real PAPER acceptance; only then close «Г-образные врата».
7. Continue to Ikigai Box «Кривой первый импульс» / FLOCK geometry.

The interrupted/repeating Scanner session from this incident is **not** a valid
full Scanner acceptance run.

## BOX ROBOT IMPLEMENTATION ROUTE — 2026-09-25 UPDATE

Mature-engine cross-check (LEAN / Hummingbot / Freqtrade patterns) confirms the project-specific architecture: Box is a multi-order **entry policy** over the existing Robot trade/order lifecycle, not a parallel trading subsystem.

Current sequence:
1. finish #227 recovery compatibility and the linked inert Box->Robot handoff;
2. add one guard so `BOX_ENTRY_READY` never falls into the Wedge candle state machine;
3. next shared blocker: allow one OPEN `robot_trade` to refresh its durable aggregate entry attestation after later **owned** entry fills (quantity + VWAP + position version), without changing the frozen STOP/TAKE prices;
4. update restart/reconciliation to compare the live position with that latest aggregate attestation;
5. only after that, connect the four Box LIMITs and keep unfilled approved grid orders alive after the first fill;
6. reuse existing matcher, execution journal, protection, obligations and recovery.

Do not add Box-specific trade states such as GRID_PARTIAL/GRID_FILLED, a Box recovery coordinator, a second execution journal, a second matcher, or a STOP-quantity synchronizer. One focused verification per new invariant; do not rerun already-green prior slices without changed inputs.

## FOCUSED POST-DISCOVERY PATTERN MONITOR — PLANNED 2026-09-25

Owner requirement: after Full Scanner discovers a structurally interesting
symbol and moves on, the project must continue following that symbol without
waiting for the next full-universe pass.

### Candidate monitoring chart — OWNER REQUIREMENT 2026-10-07

When an existing Robot candidate is shown through the monitoring surface, the
owner must receive a chart together with the candidate state. A text-only
candidate card is not sufficient.

Presentation/behavior contract:
- render the candidate on its own signal timeframe using current closed candles;
- preserve the candidate's frozen source identity, anchors/geometry and trading
  levels; monitoring must not silently re-detect or re-anchor the setup from
  later candles;
- show current price progression relative to the frozen setup and relevant
  entry/STOP/TAKE/grid levels when that data exists;
- keep the normal candidate caption/status and the existing
  «Открыть в Trading View» navigation;
- each owner monitoring refresh must be able to return an updated chart for the
  same durable candidate rather than only text;
- chart-generation failure must degrade to the existing text/status response and
  must not block Robot state, admission, protection or trading lifecycle.

Implementation should reuse the existing Scanner/Robot chart and candle
infrastructure rather than creating a parallel renderer. This is a
presentation/observability requirement only; it does not authorize strategy,
risk, admission or execution changes.

Architecture is split into three responsibilities:

- Full Scanner: broad universe discovery;
- existing Robot candidate monitor: evolution of the **same** setup
  (breakout, mirror/retest, bare-candle trigger, entry/fill/protection);
- new `FocusedPatternMonitor`: discovery of **new independent structures**
  on watched symbols (Ikigai Box, L-shape, future Flag/channel, later
  Wedge/Triangle).

Do not make Robot call the whole Scanner again and do not move pattern
detectors into Robot execution logic. Focused monitoring must reuse the same
detectors and shared market-data/candle infrastructure as Scanner.

A discovery may create a durable focused-watch subscription keyed by symbol,
timeframe, parent observation/candidate and reason. Watches are monitoring
subscriptions, not order permissions.

Initial symbol-ownership policy remains fail-closed: if a new opposite or
conflicting pattern appears while an earlier Robot trade still owns the
symbol, persist the new observation as `WAIT_FOR_FLAT`, then re-check its
freshness/eligibility after the symbol becomes flat. Do not add automatic
close-and-reverse or simultaneous Robot owners in the first slice.

Watch lifetime is structural, not one arbitrary global TTL. End the watch when
the parent episode is stale/invalid, no active candidate/trade/child
observation remains, and the post-breakout continuation/reversal window has
closed.

Implementation dependency/order:

1. complete the Scanner multi-pattern per-symbol orchestration plan;
2. add durable focused-watch registry with no trading side effect;
3. add FocusedPatternMonitor using existing shared market-data sources;
4. route new observations through the normal observation/admission boundary;
5. add `WAIT_FOR_FLAT` revalidation;
6. only later add future Flag and any explicit close-and-reverse policy.

Owning design:
`DOCUMENTS/FOCUSED_PATTERN_MONITOR_PLAN.md`.

Status: **PLANNED / NOT IMPLEMENTED**.

## SCANNER MULTI-PATTERN PER-SYMBOL ORCHESTRATION — PLANNED 2026-09-25

Owner requirement: for each ticker, Scanner must evaluate **all enabled pattern
families on 5m, then all enabled pattern families on 1m, and only then move to
the next ticker**. Multiple valid patterns on the same ticker/timeframe must be
able to produce independent signals; first-match/one-best-result behavior is
not the target contract.

Repository diagnosis before implementation:

- current `run_scan_pass()` already loops `symbol -> ("5", "1")` and contains
  no explicit Wedge-triggered `break`/`return`;
- L-shape and Ikigai Box are already called independently of Wedge notification
  admission, so a missing L-shape on a Wedge chart is not proven to be caused
  by ticker/timeframe short-circuit;
- however, L-shape/Box still receive candles through `analyze_symbol()`, which
  also owns Wedge/Triangle analysis, chart and report side effects;
- `geometry.engine.analyze_geometry()` evaluates many envelope candidates but
  returns only one `best_geometry`, so Wedge/Triangle currently remain a
  single-winner family and cannot emit several distinct valid envelope
  structures on one `symbol x timeframe`.

Implementation route is fixed in
`DOCUMENTS/SCANNER_MULTIPATTERN_ORCHESTRATION_PLAN.md`:

1. Scanner-owned one-snapshot-per-`symbol x timeframe` boundary;
2. fan-out the same snapshot to every enabled detector with failure isolation;
3. finish all 5m detectors, then all 1m detectors, then next symbol;
4. introduce a thin multi-observation collection boundary;
5. add bounded plural envelope-candidate support with stable dedup of equivalent
   line-pair representations while preserving distinct valid structures;
6. keep pattern-specific geometry and Robot admission separate;
7. preserve independent signal memory by `symbol x timeframe x pattern` plus
   formation identity where available;
8. verify with focused traversal/fan-out/error-isolation/plural-envelope tests;
9. final owner acceptance remains one complete real Scanner pass over all
   eligible tickers, both timeframes and all connected patterns with normal
   Telegram delivery.

Mature-engine principle adopted: shared market-data snapshot -> multiple
independent detector/strategy consumers -> collect all observations. Do not
solve this with separate scanner loops/processes, repeated candle fetches per
pattern, a universal geometry engine, or first-result short-circuiting.

Status: **PLANNED / NOT IMPLEMENTED**. Existing experimental code branches do
not change this status until a reviewed implementation is merged and accepted.

## TODAY PRIORITY INDEX — 2026-09-25

Owner reprioritization at 23:15 MSK: **first do the previously listed items 4,
5 and 7**, interpreted as the user-facing list immediately preceding this
change:

1. **L-shape PAPER Robot integration + real `🤖 Робот` button — ACTIVE NEXT.**
   Reuse the shared Robot lifecycle. Implement the actual L-shape
   Scanner/Telegram -> Robot handoff first; add the owner-visible Robot button
   in the same slice so it is backed by a real executable PAPER capability,
   not a decorative control. Preserve L-shape-specific geometry, minimum
   potential 0.8%, RR >= 2:1, frozen STOP/TAKE rules, and shared Robot
   protection/recovery ownership.

2. **Ikigai Box first-impulse geometry correction — NEXT AFTER L-SHAPE.**
   Use AIGENSYNUSDT 5m as the concrete defect. A distinct corrective
   counter-wave terminates the first impulse. At most 1-2 small opposite-colour
   candles may remain inside the impulse only when they form a brief pause and
   not an independent local counter-swing. Keep Robot execution unchanged while
   correcting detector geometry. Resolve the known FLOCK baseline detector
   failure in this same Box-geometry slice if it shares the same rule boundary;
   do not reopen already-completed Box Robot integration.

3. **Telegram open-position card refinement — THIRD.**
   Presentation-only slice: increase right-side chart clearance; remove the word
   `Вход` while keeping entry price/line; rename `Стоп`/`Тейк` to
   `SL`/`TP`; reduce execution-triangle size and use direction-matched
   outline; show `Размер` as quantity plus USDT notional. No trading logic
   changes.

### Deferred until the three owner-prioritized tasks above are completed

4. **Per-symbol multi-pattern Scanner orchestration.**
   Plan remains authoritative in
   `DOCUMENTS/SCANNER_MULTIPATTERN_ORCHESTRATION_PLAN.md`.
5. **Focused post-discovery pattern monitoring.**
   Plan remains authoritative in
   `DOCUMENTS/FOCUSED_PATTERN_MONITOR_PLAN.md`.
6. **PC runtime synchronization/restart for today's merged changes.**
   Required before relying on those changes in a new PAPER runtime session,
   but do not interrupt the current owner-run runtime solely for repository
   synchronization unless explicitly requested.

### Completed today — do not repeat

- Ikigai Box first-attempt PAPER Robot integration/authorization chain through
  Scanner -> Robot, shared multi-LIMIT lifecycle and fixed protection terms.
- Box owner card `🤖 Робот` status/control button merged in #238.
- 4STOCKUSDT protection-continuity false-positive fix merged in #237; Robot
  PAPER acceptance passed.
- Manual reconcile completed; Robot was returned from PAUSED to
  `ROBOT_RUNNING / READY` through the normal Telegram control path.
- Multi-pattern Scanner and focused-monitor architecture are documented and
  remain planned, not implemented.

## ИГРОВОЙ СЛОЙ GTD — АКТИВЕН С 2026-09-25

BybitScanner использует русскую игровую систему из
`DOCUMENTS/GTD_QUEST_SYSTEM.md`.

Правила:

- GTD / BACKLOG / governance остаются источниками истины;
- игровые названия не меняют приоритет, safety, acceptance или trading authority;
- XP выдаётся только за доказанный результат, а не за активность;
- ачивки открываются только по evidence;
- ожидание уходит в **Таверну ожидания**;
- Someday/Maybe — на **Карту мира / в Туман войны**;
- Weekly Review можно проводить как **Привал у костра**;
- `DOCUMENTS/QUEST_STATE.md` хранит компактное состояние кампании для
  автоматического восстановления нового чата;
- новый BybitScanner-чат не требует от владельца ручного переноса игрового
  контекста;
- если QUEST_STATE и BACKLOG расходятся, побеждает BACKLOG/текущая команда
  владельца, а QUEST_STATE обновляется;
- игровая механика не должна создавать лишний учёт.

Текущая кампания **«PAPER Robot: Гильдия паттернов»**:

1. **Рейд «Г-образные врата»** — L-shape -> PAPER Robot + настоящая кнопка «🤖 Робот».
2. **Босс «Кривой первый импульс»** — исправление первого импульса Ikigai Box.
3. **Побочный квест «Приодеть карточку позиции»** — Telegram open-position UI.
4. **Рейд «Много зверей — один тикер»** — отложенный multi-pattern Scanner.
5. **Квест «Ночной дозор»** — отложенный FocusedPatternMonitor.

Текущий игровой checkpoint всегда читается из
`DOCUMENTS/QUEST_STATE.md`.

Для новых ChatGPT-чатов и bounded refresh существующего чата используется
стабильный Custom Instructions bootstrap из
`DOCUMENTS/CUSTOM_INSTRUCTIONS_BYBITSCANNER.md`. Он не хранит volatile
состояние, а направляет к AGENTS -> QUEST_STATE -> BACKLOG/owning spec.


# Backlog (working queue, priorities, rules)

Status: WORKING BACKLOG (living document)
Last updated: 2026-09-23 (current owner work index; older entries retain historical dates)
Owner: user. When a task starts, Claude Code registers it as a ChangeRequest per the project rules; this file is the
single place where new ideas are parked until then.


## CURRENT owner work index — 2026-09-23 (supersedes stale next-step claims below)

**Do not repeat completed work.** The 23 September owner-manual real Scanner
pass completed one universe traversal: 777 tickers, 65 detected patterns
(including 6 Ikigai Boxes), 62 sent signals, duration 2h 42m 56s. The owner
stopped the automatic next cycle. This is evidence for the version used in
that pass, **not** visual acceptance of later code changes. Do not commission
an additional run just to reconcile this document.

**Scanner / Telegram delivered to GitHub main:** PR #210 (L-shape latest
closed-candle breakout), #211 (Box potential), #212 (Wedge slope arrows and
Box arrow/axis labels), #213 (Box separate text before captionless image and
30%-narrower candles) are merged. #204 L-shape Telegram integration and
#205 Box simplified presentation were also merged earlier. Do not reopen
their implementation tasks; owner visual acceptance of the changed output
is pending a subsequent **single complete manually started real pass** across
all eligible symbols and integrated patterns, with ordinary Telegram delivery.
The currently running/finished pass is not to be interrupted, restarted or
assumed to contain changes merged afterward.

**Immediate Scanner correction:** IOTXUSDT 5m Wedge status circle removal
is in [PR #214](https://github.com/svobodaXXI/BybitScanner/pull/214),
OPEN / NOT MERGED (head `0a0244c`). It changes only the shared
`notification.format_signal` text; Box and L-shape already omit status
circles. Its GitHub-only code edit has **no verified focused test result**;
review the minimal changed formatting, perform only the required verification
when the test environment is available, and do not claim visual acceptance.
Do not duplicate the completed documentation capture or launch Codex to
repeat the same source investigation. Once verified, merge through the normal
approval flow and include it in the next full-pass acceptance. Its absence
from current local acceptance checkout until explicitly synchronized is
expected; never modify a running checkout.

**Ikigai Box PAPER development — CURRENT ACTIVE ROBOT TRACK,
no trade activation yet:** first-attempt planner/persistence/protection/
ownership foundations are already merged and must not be repeated:
PR #215 planner; #218 immutable `BOX_PLAN_ONLY`; #219 planner persistence
adapter; #220 fixed STOP terms; #221 durable ownership + remaining-exposure
proof; #222 atomic owned LIMIT persistence; #223 all-or-nothing four-order
first-grid persistence. PR #224 is the current non-executing slice for
deterministic restart-safe four-order specs.

The current goal is **not** to add more persistence layers or build a
Box-specific trading lifecycle. The existing Wedge Robot path is the shared
execution engine and must be reused.

Canonical next sequence:

1. finish #224 deterministic four-order specs;
2. add a Box entry-policy adapter to the existing Robot execution lifecycle;
3. parameterize only the entry-specific behavior that differs from Wedge:
   four preplanned LIMITs, owned sequential fills/top-ups, Box eligibility and
   Box fixed STOP/TAKE inputs;
4. after the first proven owned fill, reuse the existing durable Robot trade,
   full-position protection, protection obligations, execution journal,
   matching, restart reconciliation and fail-closed escalation;
5. expose Box through the existing Robot admission/runtime path only after
   this adapter passes focused PAPER tests.

The existing Wedge behavior that cancels the unfilled remainder after a first
partial fill is **not** copied to Box: Box intentionally keeps the remaining
approved grid orders active under its own entry policy. That is the principal
lifecycle delta; it does not justify a second lifecycle engine.

Any Box-specific ownership/atomic-grid persistence already merged is retained
as evidence for the four-order entry policy, but no further parallel recovery
state machine/coordinator is to be built.

Reuse existing PAPER components: one execution journal, current matching
engine, current full-position protection, and durable protection obligations.
Do **not** add a Box-specific STOP quantity synchronizer, second execution
journal, second matching/protection engine, random retry identities or a
message-bus layer for this grid.

Still out of current first-attempt execution scope: replenishment/re-arm,
attempt 2 around F2.618, and any unresolved economic rules specifically
needed by those later features. Existing approved first-grid geometry,
frozen TAKE/STOP policy and ownership rules stay unchanged. No LIVE or
autonomous PAPER orders are authorized by this planning state. Detailed
contract: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`.

**Reuse-first checkpoint — 2026-09-25:** PR #224 is merged (`b537865`), providing deterministic four-order Box entry specs. PR #225 is the current bounded slice and extends the existing Robot entry proof to aggregate fills from multiple owned LIMIT IDs while preserving the Wedge single-order path. This is the intended integration direction: Box-specific logic stops at entry-policy differences; `robot_trades`, protection, obligations, recovery, matching and reconciliation remain shared.

**Next after #225:** connect the already-frozen Box four-order specs to the existing Robot execution path with the smallest pattern-specific branch/adapter. The critical behavioral delta is that Box keeps its remaining approved grid orders after the first fill instead of applying Wedge's cancel-remainder rule. No parallel Box lifecycle is to be introduced.

**L-shape PAPER Robot — owner timeframe decision 2026-09-26 / PR #248 merged:** inherit the
existing Wedge Robot entry/retest, order, protection, closure and recovery
lifecycle **except** pattern-specific L-shape geometry, 0.8% potential floor,
RR >= 2:1 and trough-derived/ratio-limited STOP. The owner explicitly authorizes
PAPER Robot execution from **both 1m and 5m L-shape Scanner source timeframes**.
No other source timeframe is implicitly authorized. A 5m L-shape keeps its own
frozen L-shape terms and enters the same shared Robot lifecycle; it does not need
to masquerade as or project into a 1m Wedge geometry handoff.

PR #248 is merged in `main` at `753a800` and implements this L-shape adapter/handoff
within the shared lifecycle: no second execution engine, no separate
protection/recovery stack, and no LIVE activation. The implementation/merge
gate is complete; **real PAPER acceptance remains pending** and is the next
uncompleted evidence gate for this quest. This 1m+5m authorization does **not**
by itself complete or authorize the deferred Scanner multi-pattern
orchestration, nor does it permit simultaneous Robot exposure owners for one
symbol.

**Geometry and Scanner follow-ups:** AEONUSDT 5m Box source-time candles
were recovered; early A 14:30 UTC → B 15:10 UTC passes implemented
first-leg gates. A later 16:00→16:10 UTC segment is too short, while
16:00→16:35 UTC gives a valid first impulse and provisional consolidation
but no confirmed second impulse through the recovered 18:45 UTC window.
The original detection cutoff is absent from signal history: exact
historical eligibility and selection precedence remain **unproven**; do
not alter geometry based solely on this example. Separate queued
RPLUSDT/CPUSDT Box anchor, APTUSDT/B3USDT/DASHUSDT wedge/triangle,
ATHUSDT Box, and 5m→1m per-symbol integration remain NOT completed; follow
the applicable geometry index and preserve the positive B2USDT control.
Do not treat old generic priority/order paragraphs below as a fresh
instruction to redo completed Telegram/card work.

**Execution:** one bounded step → minimum mandatory verification → publish
or report precise blocker. Only the owner manually launches the full real
Scanner pass, through a verified Scanner-only entrypoint, and never via
Codex/ChatGPT/Claude Code. No isolated owner chart previews or agent waiting
during a pass. No unchecked local sync, global process stops or automatic
PAPER/LIVE activation.

## Owner feedback register — real Scanner Telegram pass (2026-09-23)

- **IOTXUSDT · 5м · Wedge — CODE FIX IN OPEN PR #214; targeted verification and owner visual acceptance PENDING.** Observed: ordinary Scanner text `📡 Сканер: IOTXUSDT 🟡`. Required: omit every status-circle color from every ordinary Scanner signal without changing direction arrow, pattern, potential, timeframe or score. GitHub-only shared-formatter correction at `0a0244c` is not merged; Codex's earlier attempt ended at quota exhaustion. Do not misstate the pending PR as an absent fix.


**Permanent capture rule:** Immediately when the owner supplies a specific real
Telegram chart/screenshot and a correction, append a separate item here
(symbol, timeframe, pattern, observed vs wanted, status), using available
GitHub tools without requesting a Codex relay. Do not silently mark feedback
accepted, infer missing candle anchors, or replace the owner's examples with
one generic issue. Documentation alone does not authorize a Scanner restart,
a trading change or a separate owner visual check.

- **AEONUSDT · 5м · Ikigai Box — OPEN, geometry feedback (owner screenshots,
  signal around 19:58 MSK).** The emitted Box takes an earlier, extended/
  low-momentum first-impulse segment; the owner instead points to the later,
  sharp upward impulse on the current TradingView chart. Compare both local
  episodes against source-time closed candles; establish structural A/B and
  independent consolidation without hindsight-fitting Fibonacci. Keep the
  two possible formations distinct; do not modify Robot or trading rules.
- **APRUSDT · 5м · Ikigai Box — CODE FIX MERGED PR #213, owner visual acceptance PENDING (owner screenshot,
  around 20:00 MSK).** Current: one Telegram photo with a repeated caption
  underneath, e.g. `APRUSDT · 5м · ↑ Коробка Икигаи (+2.25%)`.
  Required: **separate text message BEFORE the chart**, starting
  `📡 Сканер: APRUSDT`, with `↑ Коробка Икигаи (+2.25%)` and `5м`
  in the established Scanner style. Send the chart as a separate photo
  **without duplicating that caption beneath it**. Do not fabricate
  `Баллы` or a stage/status circle when no such field exists.
  This is an owner override of the older L-shape/Box one-line exception
  stated below; update the owning notification format when implementing.
- **AVAXUSDT · 5м · Ikigai Box — OPEN, acceptance not verified.** Owner
  observed a Box chart title with no potential. PR #211 introduced the
  frozen F(1.0)→F(1.618) percentage; verify in a complete owner-run pass,
  not via an isolated owner preview.
- **CAKEUSDT · 5м · L-shape — CODE FIX MERGED, visual acceptance pending.**
  Owner identified a chart sent at ~15:47 MSK despite a ~06:40 breakout,
  when current price had long since moved on. PR #210 limits sending to
  the latest closed breakout candle at each symbol evaluation; review in
  the owner-run full pass.
- **1000TURBOUSDT · 5м · Falling Wedge — CODE FIX MERGED, visual acceptance
  pending.** Owner's initial Telegram text had no direction arrow.
  Owner specified the immutable geometry arrow `↘` for falling and `↗`
  for rising wedges, including after breakout; PR #212 implemented it.
- **1000XECUSDT · 5м · Ikigai Box — CODE FIX MERGED, visual acceptance
  pending.** Owner requested its arrow BEFORE pattern name on both
  chart header and Telegram caption, plus removal of `МСК` / `Price`
  axis-label text (not scale ticks); PR #212 implemented the presentation
  change.

**Outstanding:** AEONUSDT historical selection cutoff remains unknown; APRUSDT and other merged presentation/delivery fixes await owner full-pass visual acceptance; IOTXUSDT removal awaits PR #214 verification/merge and then full-pass acceptance. See the CURRENT owner work index above.

## Unified Scanner Telegram signal caption — PERMANENT FORMAT RULE (2026-09-23)

**Binding for every current and future pattern's ordinary Telegram signal
caption** (the text posted before the chart). All status circles are removed in proposed PR #214, not yet merged. L-shape keeps its minimal
photo caption; Ikigai Box uses a separate three-line text message before
a captionless photo, without inventing a score or status circle. Both
retain the approved arrow and parenthetical potential (see "conformance
check" below). Applies to the Wedge/Triangle Scanner caption
(`notification.format_signal`), implemented 2026-09-23:

```
📡 Сканер: <TICKER>
<arrow> <Pattern Name> (<potential>)
<TF>
Баллы: <score>
```

Example (target format after PR #214): `📡 Сканер: 1000TURBOUSDT` / `↘ Клин (+4.78%)` / `5м` / `Баллы: 95`.

- Direction is shown only as an arrow, never as a textual word ("LONG"/
  "SHORT", "Нисходящий"/"Восходящий"). The pattern name itself becomes
  non-directional where it previously encoded direction (Falling/Rising
  Wedge → `Клин`); a pattern whose name is already non-directional
  (Triangle Compression) keeps its name and still gets an arrow.
- **Wedge geometry arrow (2026-09-23, owner correction):** Falling Wedge is
  always `↘` and Rising Wedge always `↗` — the wedge's own slope, fixed for
  the pattern and never changing after breakout. This replaced an earlier,
  wrong version of this rule that used the breakout direction (`↑`/`↓`) for
  wedges too, which could show a wedge sloping one way with an arrow
  pointing the other. Only Falling/Rising Wedge use the geometry arrow;
  every other pattern (Triangle Compression, and L-shape/Box below) still
  uses `↑`/`↓` from its own actual direction (breakout, or first-impulse
  A→B). `notification.WEDGE_GEOMETRY_ARROWS` /
  `chart_clean.WEDGE_GEOMETRY_ARROWS` (mirrored copies, same convention as
  the pattern-label dicts).
- Potential is `(<signed_percent>%)`, or `(±<percent>%)` for a symmetric
  potential, or `(РАСЧЁТ НЕДОСТУПЕН)` when unavailable — reusing the exact
  formatting already used by the chart header, not a new convention.
- No word "Таймфрейм"; only the compact value (e.g. `5м`).
- No blank line before `Баллы:`.

**Chart header** (`chart_clean.build_chart_title`), same date: the line
`ПОТЕНЦИАЛ ДВИЖЕНИЯ: <value>` is renamed `Потенциал: <value>` and moved
immediately after the pattern name (before `Тип клина`/`КАЧЕСТВО
СТРУКТУРЫ`). The chart header's own pattern name keeps its existing
directional wording (unlike the Telegram caption); only the label and its
position changed. The final diagnostic line "Предшествующий импульс
показан не полностью" is no longer shown in the chart title (presentation
only — `chart_clean._chart_window`'s own returned warning value is
unchanged, so nothing that reads it directly is affected). The wedge
geometry arrow above is also shown here, before the pattern name (e.g.
`↘ Нисходящий клин`).

**Axis-label text (2026-09-23):** the "МСК" x-axis label and mplfinance's
default "Price" y-axis label are removed from the Wedge/Triangle chart
(`chart_clean.draw_chart`), the L-shape chart
(`geometry.l_shape_preview.render_l_shape_preview`) and the Ikigai Box
chart (`geometry.ikigai_box_chart.render_ikigai_box_chart`) — `ylabel=""`
passed to `mpf.plot()`, `ax.set_xlabel("")` instead of the label text. Tick
values and the time/price scales are unchanged.

Detection, scoring, confirmation/breakout logic, and Robot behavior are
unchanged by this presentation-only rule.

**L-shape/Ikigai Box conformance check (2026-09-23):** neither pattern has a
score/`confirmation` breakout-stage field, so the full `Сканер:`/`Баллы:`
template does not apply to them without inventing data (out of scope; this
rule stays presentation-only). Box now follows the owner's APRUSDT override:
a separate Scanner text message before the photo, with no repeated photo
caption. L-shape's potential was a trailing `· +8.05%`, not in parentheses after the
pattern name; `geometry.l_shape_preview.l_shape_caption` now renders
`... ↑ Г-образная (+8.05%)`, matching the parenthetical sub-rule above while
keeping its own single-line ticker/timeframe layout.

**Ikigai Box potential (2026-09-23, owner follow-up):** `IkigaiBoxFormation`
has no dedicated potential field, but does carry the frozen `fibonacci_1_0`
(F1, the first impulse's terminal B) and `fibonacci_1_618` levels already
used for the chart/target. Reusing them, not recalculating anchors:
`potential_pct = abs(F1.618 - F1) / F1 * 100`, shown in parentheses right
after "Коробка Икигаи", sign `+` for an UP first impulse (arrow `↑`) and
`-` for DOWN (arrow `↓`) — the same UP/DOWN test the arrow already uses.
The frozen values are shared by CONFIRMED and WATCH
(`IkigaiBoxWatch` carries the same two fields). The chart title keeps
`symbol · timeframe · arrow pattern (potential)`; Telegram uses those
same values in its separate Scanner text before a captionless chart.
Detection, targets, scoring, and Robot are unchanged.

**Arrow position (2026-09-23, owner correction):** the arrow moved before
the pattern name, matching the Wedge/Triangle/L-shape convention (arrow
first). `ikigai_box_caption` now renders `... · ↑ Коробка Икигаи
(+X.XX%)`, not `... · Коробка Икигаи (+X.XX%) · ↑`. The potential text
itself is unchanged.


**Canonical notification examples — target after pending PR #214 (current main still has Wedge/Triangle status circles):**

```text
Wedge / Triangle — separate Telegram text before chart:
📡 Сканер: 1000TURBOUSDT
↘ Клин (+4.78%)
5м
Баллы: 95

L-shape — shared Telegram caption and chart title:
TESTUSDT · 5м · ↑ Г-образная (+8.05%)

Ikigai Box CONFIRMED / WATCH — separate Telegram text before captionless photo:
📡 Сканер: TESTUSDT
↑ Коробка Икигаи (+3.42%)
5м

Ikigai Box chart title:
TESTUSDT · 5м · ↑ Коробка Икигаи (+3.42%)
```

Values above are **format examples, not live signals**. For Wedge/Triangle,
status circles are omitted from Telegram presentation after #214; the existing
stage/quality classification itself remains unchanged. `<potential>` comes
from the existing signed/symmetric potential; missing values
use `(РАСЧЁТ НЕДОСТУПЕН)`. The chart header keeps its existing directional
pattern name, with `Потенциал: <value>` immediately below it and no final
`Предшествующий импульс ...` line. L-shape and Box have no score/status
circle, so neither acquires invented `Баллы` or status values. Box arrow
describes the **first impulse A→B**, and its signed potential uses frozen
F(1.0)→F(1.618), including WATCH; it appears before the pattern name. These are
presentation contracts only: no new detector, score, target, or trading rule.

## HAEDALUSDT 5m — Box early-grid/slice TP/re-arm strategy feedback (2026-09-23)

Queued **only in the existing later Ikigai Box PAPER Robot lifecycle stage**;
not a Scanner acceptance blocker and not executable trading authorization.
The owner requires the first 1/4 РО advance LIMIT at F(1.0) + 0.75 ×
(F(1.618) − F(1.0)), three further equally spaced 1/4 РО LIMITs in the
second-impulse direction, and the furthest beyond F(1.618). A confirmed
partial fill requires immediate protection and a matching-quantity opposite
TAKE LIMIT slightly before F(1.0); after proven profitable closure, restore
only freed quantity to its first-grid level if the same frozen formation is
still eligible. No doubled exposure, duplicate orders or re-arming completed/
STOP-terminated setups. The screenshot alone cannot establish same-candle
fill/TP or profitable realized execution. The precise fourth grid price, second-attempt first-entry level,
TAKE offset/net-fee rule, partial-fill exposure budget and re-arm lifecycle
remain open financial decisions; the STOP price/activation policy was
superseded by the frozen full-grid-average trial design in the owning spec.
Do not invent defaults or enable trading.
Owning detailed specification: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`,
"Owner strategy amendment — advance 75% entry, slice TP and re-arm".
Current acceptance → 5m/1m → source geometry → Box construction/lifecycle →
L-shape → Telegram control → separately authorized PAPER Robot order remains
unchanged. No additional full scan is triggered by this documentation alone.

## Telegram Scanner menu: owner-controlled discovery, pause/resume and safe start — QUEUED (2026-09-23)

Owner request after stopping an incomplete 302/777 pass: make the existing
Telegram Scanner menu button the **manual owner control** for the Scanner,
regardless of whether its worker is running on the PC or VPS. On owner tap,
discover the actual live owner/host and current pass state instead of assuming
a host from stale DB state. If running, pause the current pass durably at a
safe symbol boundary, without killing Telegram pollers, Robot, backend, or
open positions; on the next tap resume the **same** pass from its persisted
cursor, without rescanning already completed symbols or duplicating sent
signals. If no Scanner worker is running, the owner tap requests a safe start
of the required components from an **available, verified host**, equivalent
to the owner's existing batch-file workflow, but only after tracing which
components the batch file actually starts and checking live host reachability,
process/poller ownership and Robot/position safety. Do NOT infer that a
Telegram callback can wake a powered-off PC; if no existing reachable and
authorized remote launcher is available, report the specific unavailable
host/dependency rather than pretending to start it. Never spawn a duplicate
poller or Scanner, enable Robot/trading, restart unsafe infrastructure, or
silently switch PC/VPS runtime and account. Ambiguous ownership or missing
reachable host => fail closed and show status, not a blind launch.

Manual owner menu taps (unlike autonomous agent action) satisfy the manual-
start-only rule. Codex must not run the Scanner or stay active to supervise
it. Distinguish PAUSED vs STOPPED: a paused pass retains its frozen eligible
universe/cursor; a stopped/interrupted 302/777 pass is not complete acceptance
and must never be reported as 777/777. The first actual implementation slice
must inspect existing Telegram callback, ScannerControlRuntime, host control
surface and batch-file dependency/side-effect chain; reuse them instead of
building an additional remote process manager. Reconcile the button's
availability, auth and deployment before enabling start. Implement only at
the authorized turn in the established task sequence; no runtime start or
process termination is authorized by this backlog entry. Owner visual
acceptance for Scanner changes remains a complete real eligible-universe
Telegram pass, not a partial/selected preview.

## Owner manual Scanner run; agent quota protection — BINDING (2026-09-23)

The owner, not Codex/Claude Code/ChatGPT, manually launches each real Scanner
pass through a verified Scanner-only entrypoint. Agents must not start,
restart, resume, supervise, poll or wait through a full Scanner/Telegram
acceptance run: doing so wastes the owner's agent quotas. A bounded read-only
host-state/preflight task must exit immediately after its concise report;
subsequent manual Scanner execution does not require an active agent session.
Before any instruction to stop a possibly running process, distinguish Codex
job, Scanner worker, Telegram poller, Robot/backend and positions; never blindly
stop trading infrastructure. The full eligible-universe Telegram acceptance
requirement remains unchanged; an interrupted run remains unaccepted.

## RPLUSDT 5m Ikigai Box — owner-corrected A/B reference (2026-09-23)

The owner reports that the Scanner Box first-impulse anchors disagree with
his corrected TradingView drawing: approximately F(0)=1.979,
F(1)=1.998, F(2.618)=2.029 on a rising first leg, with a later visible
reaction around 2.618. The earlier CPUSDT-derived near-single-colour
impulse heuristic MUST NOT be promoted to an absolute first-leg anchor rule;
retain CPUSDT as the contrasting case where sideways candles were wrongly
included. Investigate both with frozen decision-time OHLC and local episode
structure; do not select A/B retrospectively merely because 2.618 fits the
later move or treat a wick as an actual Robot fill/exit. Detailed owning
rule and precedence: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`,
"RPLUSDT 5m — revised first-impulse anchor interpretation". This is part
of the existing second-priority Box geometry task (after L-shape), not a
new task or permission for an isolated owner visual-review pass.

## CPUSDT 5m Ikigai Box: first-impulse construction correction — QUEUED (2026-09-23)

Owner's visual feedback: first impulse must begin at the actual local reversal
extremum, not an arbitrary later candle, and terminate at the last candle of
the initial directional move **before** subsequent consolidation/sideways
movement. Predominantly same-colour candles: UP predominantly green, DOWN
predominantly red. Only small opposite-colour candles that do not produce a
zigzag/meaningful countertrend swing may occur inside that first impulse.
Do not mechanically terminate on the first tiny opposite-colour candle, nor
include later sideways candles in the first impulse or move frozen A/B to fit
later prices. The first substantial opposite-direction candle/zigzag marks the
end of the directional leg; use the source-time candles to determine its exact
boundary and ensure terminal B is a candle of the impulse's own direction.
For UP use reversal LOW→terminal HIGH; DOWN mirror HIGH→terminal LOW. Keep
subsequent consolidation independent, regardless of its candle colours.
At implementation, establish reproducible pattern-specific evidence for
"small" and "non-zigzag" (no arbitrary one-example thresholds), repair the
first-leg candidate construction rather than a chart/score/Telegram reject,
and keep both CONFIRMED and WATCH consistent. This supersedes earlier
opposite-colour-core/wick-path exceptions wherever they conflict; defer any
financial Robot change. Preserve existing task order: manual full current-
Scanner pass, 5m→1m integration/full acceptance, then authorized geometry
fixes. No isolated screenshot/card visual acceptance.

## Permanent owner-only visual acceptance protocol — FULL PASS OR NO ACCEPTANCE (2026-09-23)

For any Scanner change whatsoever, including a chart-only/caption/button
change, **owner visual review happens only from the normal Telegram signal
feed produced by one COMPLETE real Scanner pass over EVERY available eligible
ticker and ALL integrated patterns**. Do not offer a separate "updated Box
card", one-off chart, selected symbol, local PNG, offline replay, partial
302/777 run, or short demonstration *before or instead of* the full pass.
Agent and Codex prompts must request the full pass as the ONLY visual-review
route, after minimal necessary developer-side technical verification. The
owner judges the resulting live Telegram charts, not developer-generated
examples. An interrupted or unsafe run leaves acceptance **PENDING**.

**Anti-regression check for every next-step prompt:** (1) Is this a request
for owner visual inspection? If yes, prescribe exactly the complete
real eligible-universe Scanner pass with ordinary Telegram delivery of every
integrated pattern; never a single-chart preview. (2) Is a complete safe pass
currently possible? Check the actual launcher, process/poller ownership and
Robot/position fail-closed conditions; if blocked, name the concrete blocker
and do not offer a smaller substitute. (3) Did the pass complete? Report
eligible/included/error counts, signal delivery and actual Telegram charts;
otherwise do not mark visual acceptance complete. When the future 5m→1m
per-symbol implementation is complete, include both intervals in the
full pass; before it, do not claim they were scanned.

**Current queue correction:** PR #204 (L-shape Telegram) and PR #205 (Box
card and 40% narrower chart) are both MERGED, but no complete owner-visible
full pass for the current implementations is confirmed. The next visual
acceptance action is ONE complete safe full pass displaying both patterns
through ordinary Telegram delivery, not an isolated Box card review. After
that proceed to the queued 5m→1m per-symbol Scanner integration and the
geometry corrections. No Robot/PAPER/LIVE activation is authorized.

## Permanent Scanner scan cadence and current task placement — OWNER RULE (2026-09-23)

**Every symbol: 5m first → immediately 1m → next symbol.** Evaluate all
integrated patterns independently on both intervals; send their real charts
to Telegram with the correct interval and pattern. Preserve separate
(symbol, timeframe, pattern, formation) anchors, candle data, identity,
state, deduplication and chart paths; a failure on one interval does not
block or falsify the other. Do not replace this with a full-universe 5m
pass followed by a full-universe 1m pass, or silently leave 1m patterns
unwired. Do not automatically extend Robot/PAPER/LIVE trading to 1m.

**Execution queue update:** the L-shape Telegram integration is merged
(PR #204), but full user-visible acceptance has not been reported. The
owner has explicitly moved the full scan later. First finish the ongoing
Ikigai Box Telegram/chart simplification, including **candles about 40%
narrower** (presentation only), without interrupting it. **Next** implement
the universal per-symbol 5m→1m Scanner/Telegram path; **then** tackle the
existing geometry-construction cases APTUSDT, B3USDT, DASHUSDT, ATHUSDT
(with B2USDT Box positive control). For each completed Scanner correction,
follow the owner's mandatory full eligible-universe Telegram visual
acceptance rule when the owner authorizes the actual run. The user judges
the charts visually; developer verification stays limited to necessary
technical checks, not extra test campaigns.

## Binding owner execution order — 2026-09-23 (LATEST OWNER OVERRIDE; READ FIRST)

The owner explicitly changed the priority to **former tasks 5 → 4 → 2 → 6;
all remaining tasks afterwards**. This section supersedes the previous
numbered order and any contrary "next/immediate" wording elsewhere in this
backlog or geometry index. Preserve task content, but execute in this order:

1. **Former #5 — L-shaped geometry and Telegram card.** Implement the B2USDT
   5m owner definition and the METISUSDT 5m possible missed independent
   L-shape alongside a delivered Box: local HIGH → trough → HIGH breakout, without a
   mandatory shelf; source-time upper edge of trough candles determines
   depth. Draw only rightward breakout HIGH ray and horizontal target with
   potential measured from HIGH; minimal ticker/timeframe/direction-arrow-
   before-pattern/potential caption. Remove diagonal, START, shelf box/text,
   green formula and other annotations. Do not activate L-shape Robot.
2. **Former #4 — Ikigai Box first-impulse and missed-pattern geometry.** Apply
   the CPUSDT 5m reversal-origin, predominantly single-colour non-zigzag
   first-impulse rule; freeze first-leg A/B before the independent sideways
   consolidation, for CONFIRMED and WATCH. Diagnose INTUUSDT 5m possible
   missed downward Box independently of the L-shape, using historical
   decision-time candles and the detector's decision/rejection path. Preserve
   historical completion vs actionable setup vs actual Robot execution;
   never fabricate a Box just because its screenshot looks plausible.
3. **Former #2 — Per-symbol Scanner 5m → immediately 1m**, all integrated
   patterns and ordinary separate Telegram notifications; independent
   candles, anchor/formation identities, state and dedup per timeframe.
   Robot/PAPER/LIVE stays on its separately authorized trading scope.
4. **Former #6 — Telegram Scanner-menu owner control.** Discover actual
   reachable host/worker, safe symbol-boundary pause, durable resume of the
   same pass and manual owner-tap start through the verified existing
   launcher/control mechanism. No autonomous Codex run, duplicate workers/
   Telegram pollers, blind PC wakeup/VPS switch, Robot enablement or unsafe
   backend restart. Fail closed on unavailable host/ambiguous ownership.
5. **Only afterwards — former #1, #3, #7 and all other queued work.** Resolve
   outstanding acceptance of the earlier #204/#205 changes and any newly
   implemented Scanner changes using the owner's mandatory ONE COMPLETE
   eligible-universe, ALL-pattern, ordinary-Telegram visual pass; the earlier
   interrupted 302/777 pass is not accepted. Then resume APTUSDT/B3USDT/
   DASHUSDT/ATHUSDT source-geometry defects (B2USDT Box positive control),
   remaining Ikigai setup lifecycle and separately authorized PAPER Robot
   work according to dependencies. Record existing valid complete-pass
   evidence, if recovered, instead of commissioning a redundant pass.

**Acceptance scheduling:** focused developer checks during each implementation
are permitted, but the owner never reviews selected cards, local PNGs or
partial scans. Do not insert a new full runtime pass ahead of the owner’s
newly prioritized development tasks merely to satisfy the OLD ordering.
Before claiming visual acceptance of any delivered Scanner changes, require
one complete real pass under the then-current implementation with all
integrated patterns and ordinary Telegram delivery, started **manually by
the owner**. An interrupted/unsafe pass remains unaccepted. Agents never
launch or supervise Scanner runtime and do not wait/poll in Codex.

**Implementation boundaries:** handle one dependent micro-slice at a time;
preserve dirty user-owned local work and use an isolated worktree for local
edits. No Robot/financial/risk activation, LIVE trading, or service/process
mutation is authorized by this plan. Existing detailed task specifications
in this backlog and `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md` remain in force
except for their now-superseded scheduling claims. The HAEDALUSDT 75%-entry/
partial-TP/re-arm proposal remains in the later, separately authorized PAPER
Robot stage; the B2USDT L-shape is distinct from the B2USDT Ikigai Box.

## L-shaped PAPER Robot strategy — owner decision (2026-09-23; DESIGN ONLY)

Reuse the existing Wedge PAPER Robot entry, breakout/retest, order,
position-management, protection, closure and recovery lifecycle wherever
compatible with L-shaped geometry. **L-shape-specific rules take precedence**:
its own confirmed breakout level, frozen target, trough-derived structural
STOP (or ratio-limited fallback), minimum signal potential 0.8%, and
minimum planned reward/risk 2:1. Do not apply Wedge boundary/apex geometry
or silently override L-shape thresholds with Wedge defaults. The Scanner
signal's reference entry/RR is not proof of an executable post-retest fill:
check actual planned entry, fees, tick/quantity constraints and protection
before admitting PAPER orders. Existing Scanner visual acceptance and
Robot activation are separate; no LIVE admission, runtime launch or order
activation is authorized by this design note.

## L-shaped signal eligibility and protective STOP — OWNER DECISION 2026-09-23

Applies to the currently open L-shape PR #208 and subsequent Scanner signal
admission, **not** to the structural candidate generator or to Robot order
placement. Construct the genuine HIGH → trough → breakout geometry first,
with independently frozen anchors and target. A candidate with potential
below **0.8%** from its breakout reference is not a deliverable L-shape
signal. The expected target-distance / STOP-distance ratio must be **at
least 2:1** using the *same* reference entry (the breakout level). Prefer
the structural STOP beyond the trough's actual low for LONG, above the
trough's actual high for SHORT, with the existing protective tick/buffer
rules where applicable. If its distance would exceed one half of target
distance, use the **default ratio-based STOP** at no more than half the
measured target distance from the breakout reference, in the adverse
direction. Do not artificially move the formation anchors/target or reject
a structurally valid formation only because the structural STOP is far away;
the trade-plan reference STOP is separate geometry. Do not assume that a
2:1 mathematical STOP makes a trade safe or that a fallback STOP inside the
trough is structurally protected. If a broker/tick/fee constraint renders
such a STOP nonviable, do not label it executable; fail closed for actual
trading until separately specified. In this stage use the STOP solely for
Scanner-side indication/eligibility without activating L-shape Robot,
creating orders, or changing any existing Robot/PAPER/LIVE risk controls.

The previously valid METIS +0.06% and +0.47% geometries remain valid
*structures*, but fail the **0.8% signal-delivery threshold** and must not
be presented as new eligible trading signals. B2USDT +8.05% is above the
potential floor, subject to its separately computed reference STOP. These
thresholds are pattern-specific; do not retrofit to Box, wedge or triangle.
Owner visual acceptance remains ONE complete owner-manual real all-symbol,
all-pattern Telegram pass at the scheduled stage; no isolated picture or
partial pass. Record the same decision in PR #208's owning task documentation
when updating its branch, without overwriting user-owned work.

## METISUSDT 5m — missing independent L-shaped signal (owner feedback, 2026-09-23)

During owner Telegram review a real Ikigai Box signal was delivered for
METISUSDT 5m. The owner also identifies an apparent L-shaped structure on
the same candles and expects a **separate normal Telegram L-shape signal**
when its independently evaluated geometry is valid. The Box notification
must not consume a per-symbol slot or otherwise suppress the L-shape, and
vice versa. This is a candidate missed-pattern reference for the **current
first-priority L-shaped geometry task**, not proof of a confirmed detection
from a screenshot alone.

At the task's implementation stage, recover the source-time closed candles,
actual L-shape detector candidate/rejection and Scanner notification path
for METISUSDT 5m. Distinguish absence of a structurally valid candidate from
signal-memory/dedup/delivery suppression; fix the first demonstrated cause
at its owning stage. Assess alongside B2USDT's HIGH→trough→breakout owner
rule; do not force a positive by coin-specific exceptions, relaxing gates,
retroactive anchors or chart-only adjustments. Valid coexisting Box/L-shape
must each have distinct (symbol,timeframe,pattern,formation) identities,
real charts and ordinary owner buttons; no L-shape Robot admission.

No isolated chart/selected-ticker owner review. After the scheduled changes,
acceptance remains one complete manually started eligible-universe Scanner
pass with all integrated patterns and ordinary Telegram delivery, per the
latest binding execution order. No extra scan now just for this observation.

**Investigation result (2026-09-23, source-time Bybit 5m candles).** The Box
and L-shape paths are independent in `main.py` and use distinct memory keys
(`ikigai_box:*` vs `l_shape:*`), so no slot/dedup/delivery suppression was
involved. The earliest cause was the detector: the old shelf model returned
no candidate for METISUSDT at any bar (and only evaluated a shelf ending on
the latest closed candle). With the HIGH → trough → breakout detector and
latest-breakout reporting, the closed candles up to the scan (13:45 MSK)
yield LONG HIGH 12:25 (3.613) → trough 12:30–12:50 → breakout 12:55, U =
3.611 (12:40 body top), target +0.06%.

**Owner decision applied (PR #208):** the impulse origin is the nearest
structurally valid reversal LOW before the HIGH (the `pivots.find_pivots`
rule: strictly below 3 candles on each side, confirmed by the HIGH, and
still the lowest low up to it), never the 30-candle window minimum; no
fallback, unchanged impulse gates, no minimum target. METISUSDT now yields
12:40 LOW (3.593) → 13:05 HIGH (3.647) → trough 13:10–13:35 → 13:40
breakout, U 3.630 (13:20), T 3.664, +0.47% (3.7 ATR, 0.62 ATR/bar). The
earlier 11:50 → 12:25 → 12:55 structure still qualifies independently.
A pass sends a formation only if its breakout is the latest closed
candle at that symbol's evaluation (see the stale-signal fix below). B2USDT is unchanged (origin 11:10, +8.05%).

## L-shaped formation: owner correction from B2USDT 5m chart — IMPLEMENTED, ACCEPTANCE PENDING (2026-09-23)

**Implementation (2026-09-23):** `geometry/l_shape.py` now detects impulse →
local HIGH → trough → first closed candle whose high exceeds H (SHORT is the
mirror). No shelf condition remains. Owner decision on U: body top
max(open, close) of the trough candle with the lowest low (earliest on a
tie); T = H + (H − U). Scanner reports the most recent breakout in the
closed candles, deduplicated by HIGH + breakout candle times. B2USDT 5m
reproduces H 0.5168 (11:30), U 0.4752 (11:35), breakout 12:25, T 0.5584,
+8.05%. Chart/caption: `B2USDT · 5м · ↑ Г-образная · +8.05%`, breakout ray and
`Цель` level only. Owner visual acceptance remains pending on the next
complete owner-started Scanner pass.

**Signal eligibility implemented (PR #208, owner decision above):**
`l_shape_signal_plan` in `geometry/l_shape.py` is separate from detection and
never moves anchors/target. Reference = breakout level for both target and
STOP. Structural STOP = the trough's actual low (LONG) / high (SHORT); no
Scanner-side tick/fee buffer exists, so it is an indication only, never an
executable order. If its distance exceeds half the target distance, the
default STOP sits at exactly half the target distance, adverse side.
Eligible only with potential ≥ 0.8% and reward/risk ≥ 2:1. **Stale-signal fix
(2026-09-23):** the Scanner emits an L-shape only when its breakout is the
latest closed candle at that symbol's evaluation, with no fallback to an older
eligible breakout. The earlier fallback sent CAKEUSDT 5m's 06:40 breakout at
15:47 (108 candles late) and 105 of 113 acceptance-pass L-shapes older than
1 hour. An ineligible latest breakout is logged
(`L-SHAPE structure not signalled … reason=…`). Results:
B2USDT eligible, STOP 0.4960 (ratio fallback; structural 0.4388 is 0.078
away), 2:1, +8.05%. METISUSDT +0.47% and +0.06% remain detected structures
but are not signalled (`potential_below_minimum`). Chart and caption are
unchanged (no STOP drawn); no Robot, Box, Wedge or Triangle change.

**Original status: specification feedback only.**
The owner rejects the current mandatory post-impulse narrow "shelf" model and
its shelf box/labels for this example. The intended search structure is a
local HIGH, a subsequent trough/pullback ("впадина"), then a breakout of
that local HIGH. Construct the correct local episode, HIGH and trough from
closed decision-time candles at the detector/candidate stage; do not merely
redraw a shelf-based or otherwise invalid candidate. The owner measures
trough depth from the local HIGH **to the upper edge of the trough candles**
(as indicated by the owner's black arrow), not automatically to the trough's
lowest wick. Before coding, resolve the exact reproducible candle/price
selection for that upper edge from source-time evidence; do not silently
reuse the previous `shelf_low` as this price or invent a numeric threshold.

For this HIGH-breakout / LONG example, draw a horizontal rightward signal
ray at the local HIGH breakout level H. Let U be the agreed upper-edge price
of the trough candles and D = H - U; project D upwards from H to obtain the
target T = H + D, with potential 100*(T/H - 1)% from the **breakout level**.
Draw one horizontal target level labelled `Цель` and its potential percentage.
Chart/card caption: only ticker, timeframe, upward direction arrow directly
before the pattern name, and potential to target. Remove the blue diagonal
impulse ray and its labels, the shelf outline and caption, green `T = 2H-L`
text, START and other nonessential annotations. No shelf condition or shelf
terminology is to be retained in the intended detector or owner-facing card.
This screenshot's B2USDT **L-shape** example is distinct from the B2USDT
**Ikigai Box** positive control elsewhere in this backlog.

**Execution order unchanged:** first complete the currently queued safe full
real Scanner/Telegram pass, then per-symbol 5m→1m integration and its full
pass, then the queued APT/B3/DASH/ATH geometry work. Take this L-shape
correction only at its authorized turn; do not modify the current running
Scanner or Robot in response to this documentation. After implementation,
owner visual acceptance is ONLY one complete real pass over every eligible
ticker and all integrated patterns via ordinary Telegram notifications;
no isolated image/card or shortened-pass substitute. L-shape Robot trading
remains unauthorized.

## Box presentation implementation — 2026-09-23

The Box chart header and separate Telegram text share only ticker, formatted
timeframe, pattern name and the first-impulse A→B arrow (not the opposite
trade direction). The text precedes a captionless chart photo.
No A/B/START, status, zone/STOP captions or planned limit-grid overlay appear.
Frozen Fibonacci prices/bands and source-time candle/anchor selection remain unchanged.
The canvas width is now 5.04 inches instead of 7.2 at the same 125 DPI and
height: candle bodies and visible gaps are about 30% narrower than the previous
Box chart. Time/price scales and formation coordinates are unchanged.
Use the shared TradingView keyboard with review buttons for the owner only;
no Robot button or candidate is supported. This minimal identity and applicable
safe shared buttons are the presentation reference for future new patterns.
The implementation has been merged as PR #205; full Scanner/Telegram
visual acceptance is pending. Do not offer a single Box card for owner review:
the owner inspects this and all other Scanner changes only during the
complete real eligible-universe Scanner pass above.

## IMMEDIATE owner-visible milestone — L-shape Telegram (2026-09-23)

**Owner correction, superseding the older queue's deferral of L-shape delivery:**
All newly developed Scanner patterns must appear as **normal Telegram chart
signals with the common caption and applicable existing safe buttons during
their initial integration**. The owner evaluates the real delivered charts
visually. A local-only detector/observer or private `charts/` PNG is developer
diagnosis, **not** completed integration, user-visible acceptance, or a valid
substitute for Telegram delivery. Do not send the owner into a local filesystem
to review a new pattern and do not silently disable configured notifications.

**Implementation update:** L-shape Telegram delivery merged as PR #204,
and Ikigai Box card simplification merged as PR #205. The remaining
user-visible step is ONE complete real eligible-universe Scanner pass with
ordinary Telegram notification delivery for ALL integrated patterns. Owner
visual acceptance is pending; no isolated L-shape/Box chart inspection,
short run or local-PNG substitute. Robot admission/orders stay OFF for
L-shape until independently authorized.

**Workflow for every future new pattern:** implement valid pattern-specific
candidate construction and its ordinary Telegram visualization/delivery
together as the initial user-visible Scanner milestone. Focused offline
tests help coding only; a hidden observer is never offered as the final
visual acceptance path. A full-pass acceptance must display actual charts
to the owner in Telegram. Scanner signal presentation does NOT authorize
PAPER/LIVE orders or bypass independent Robot safeguards. See `AGENTS.md`
"Telegram-first visual development" and its full-pass rule.

## ACTIVE owner-feedback action plan — 2026-09-23 (read this first)

**Outcome, not downstream suppression:** each pattern's search/generation stage
must construct only geometry consistent with the owner's pattern definition.
Never generate malformed geometry and conceal it later through scoring,
Telegram delivery or Robot admission. Preserve original source-time candles
and candidate identity when diagnosing examples. This plan supersedes older
queue ordering when tasks conflict; it does **not** claim that the defects are
already fixed or that a screenshot proves the exact code-level cause.

**P0 — source-time geometry construction (one dependent fix at a time).**
- **Wedge/Triangle:** use the owner's APTUSDT 5m wedge, B3USDT 5m
  triangle and **DASHUSDT 5m falling-wedge** charts as reported
  false-geometry cases. DASHUSDT has two same-period visual references:
  the Scanner's selected wedge (START and both boundaries around the later
  local segment) and the owner's TradingView drawing showing a different,
  broader descending channel/wedge with boundaries starting from earlier
  local extremes. Treat the owner drawing as the intended geometry to test,
  **not** as proof that the broader figure already meets every confirmed
  pivot, A/B/C or source-time rule. Recover the matching closed-candle
  decision cutoff and candidate provenance; trace impulse episode,
  chronological A/B/C, START, candidate generation, boundary selection
  and display to the *first* divergence from the pattern contract.
  Compare the selected Scanner geometry to the owner's drawing using the
  same source-time candles. Fix generation/anchor selection, **not** score,
  chart window or Telegram filtering. For wedges retain the owner's
  universal A/B/C rule; triangle constraints are pattern-specific. If an
  original frozen snapshot is absent, state the missing provenance and
  collect a reproducible source-time case from the next complete pass
  rather than assert a guessed cause.
- **Ikigai Box:** ATHUSDT 5m: the owner rejects an opposite-colour candle
  within the *core* of the first impulse. Resolve the precise directional/
  boundary-candle rule in `IKIGAI_BOX_STRATEGY_SPEC.md` before editing the
  shared construction gate; the existing red-body-core exception applies only
  to DOWN impulses, and the UP path still admits mixed colour. Enforce the
  approved rule at first-leg construction for CONFIRMED and WATCH, not with a
  downstream reject. Preserve B2USDT 5m as a visually valid LONG control
  showing a move from the 2.618 area back toward/through 1.0.
- **Scope:** these cases are distinct; address one causative defect at a
  time. Do not convert a single chart observation into a universal numeric
  threshold, retrofit wedge rules onto Box, or merge all patterns into one
  large unverified rewrite.

**P1 — market setup lifecycle, independently of trade execution.**
- ATHUSDT is the owner's example of price reaching the first 1.618 entry
  region and then returning to the frozen 1.0 target: the original Box setup
  must become completed/historical and must not be reconstructed or offered
  again as an actionable entry for the same frozen A/B episode. Determine
  the exact closed-candle touch/return sequence from saved evidence; retain
  distinct attempted-entry and completion status and source-time provenance.
- The B2USDT move around 2.618 is a reference for evaluating the *second
  attempt*, not permission to open it merely because price reached 2.618.
  The strategy permits attempt two only after a verified STOP closure of
  attempt one, verified FLAT and no unresolved limits/protection obligation.

**P2 — reliable PAPER lifecycle, separately authorized.**
Implement only after the geometry and setup lifecycle are credible: approved
Box entry grid, partial fills, immediate protection, confirmed STOP/TAKE,
fee-aware profit-taking/flat closure, cancellation, durable restart-safe
ownership. Resolve still-unspecified grid spacing and partial-exit/BE policy
with the owner before placing orders. Historical chart price action cannot
prove an executed profitable trade; do not enable LIVE or alter risk.

**P3 — consistent Telegram presentation for every new pattern.**
For Box and then new patterns reuse the common notification/card button
model. The chart and caption show only ticker, timeframe, pattern name and
impulse-direction arrow; remove service-status/limit-grid/Fibo labels,
A/B/START, planned STOP/zone and other unwanted overlay text from the
user-facing Box presentation without changing frozen source geometry or
entry policy. Existing Box sender presently uses a separate photo/caption
path and does not give every normal owner button; this is pending.

**P0 immediate delivery gap — L-shape is NOT a Telegram signal yet.**
PR #197 added only an opt-in local observer. In `main.py`, the flag
`BYBITSCANNER_L_SHAPE_OBSERVATIONS=1` calls `observe_l_shape`; that function
logs candidates and saves local PNGs to `charts/l_shape` only. It never calls
Telegram/photo delivery, `signal_memory` or Robot admission. No flag can
turn the current observer into a Telegram sender. **Finish normal Telegram
chart delivery now, before any further owner-facing full-pass acceptance**
and without waiting for all older wedge/Box geometry tasks to finish.
Reuse the common caption/applicable safe buttons, dedup and retries; do not
activate Robot for L-shapes. Do not describe missing Telegram notifications
as detector failure or guess the host's current flag/deployment state.

**Mandatory acceptance for each changed Scanner pattern/geometry path:**
focused proof during implementation, then **one complete real Scanner pass
through every available eligible instrument**, with ordinary configured
delivery and the intended pattern integration enabled. Return all candidate
charts and a full pass count/error summary for the owner's visual acceptance.
Do not replace it with short/sampled/offline-only runs; do not start Robot,
LIVE, deploy or restart multi-service launchers without separate safety checks
and authorization. See `AGENTS.md` for the binding rule.

**Next dependent task (owner override 2026-09-23):** first deliver
L-shape candidate charts in the ordinary Telegram signal feed, without Robot
execution; then perform one complete real Scanner pass and obtain owner visual
feedback from its Telegram posts. After that, resume the geometry-construction
queue using APTUSDT/B3USDT source-time evidence. Keep ATH/B2 Box and PAPER
work as later scoped tasks, not parallel implementation campaigns.

## 0. Rules to avoid loose ends

1. WIP limit: one active task plus at most one background task that is only waiting (CI, review, deploy, live check).
2. A task is DONE only when: merged; deployed where relevant; verified live by a named check; run log / spec updated;
   the local branch is deleted; follow-ups are written here.
3. New ideas go into this file first, never into a running task.
4. Backend restart only with no open positions or with the robot PAUSED.
5. Until PR #153 (candle cache) runs on the machine that trades and is verified: do not press Pause, Stop, Close-all and do not
   call reconcile while positions are open (owner-thread REST stall, see run log section 9).
6. A second agent (Codex) works only in a separate `git worktree` on its own branch.
7. Commits are staged by explicit file list, never `git add -u` while unrelated edits sit in the tree.
8. At most 2 commands per message to the user; no manual file placement (ASSISTANT_PROTOCOL 2.2.2 and 8.11, DECISION-010).
   Repo and runtime routine goes to Claude Code prompts.

## 1. State snapshot (2026-09-19 late)

- `main` contains PRs #148-#153: emoji labels, position card + chart, lifecycle posts, unsupported-pattern fix, owner-queue
  diagnostics, light candidate reads, signal-timeframe chart, owner-thread candle cache.
- The live run is on the PC (PAPER backend + Telegram listener; no scanner running). PC robot state: `RECONCILIATION_REQUIRED`
  (`ingress_overflow`, CFXUSDT, 2026-09-19 21:15), open STGUSDT LONG, 3 APPROVED candidates. Next: restart the PC processes onto `main`
  (running processes keep old code), reconcile, resume. One Telegram poller only (the PC).
- The VPS has only the backend service (code `c363008`, without #153): robot `RECONCILIATION_REQUIRED`, open AAVEUSDT and LUNA2USDT,
  no listener and no scanner, so no Telegram posts. Leave it until they close, then stop the service.
- Scanner timeframe: VPS `TIMEFRAME = "5"` (decision: keep); the PC config still has "1" (see P3-9).
- Times: VPS is CEST, the user's Telegram and the PC are MSK (+1 h).

## 1a. CURRENT queue: Scanner acceptance follow-ups (2026-09-22)

**Evidence:** one full 5m pass 2026-09-21 23:15–2026-09-22 00:30, 774 symbols, 156 Telegram deliveries (85 Wedge/Triangle, 71 Ikigai Box), zero Telegram errors. 9 symbols had market-data errors; 47 lacked pivots. Only ONE pass was authorized and executed. The analysis of B2/AZTEC/HIMS/FWDI used reconstructed matching-as-of windows; the Scanner does not persist its candle windows. No new implementation was committed after PR #180; current checked-out main was `a4ef2ff` at acceptance. This section supersedes outdated Scanner/PC-runtime assertions elsewhere in this backlog **only where verified below**; older Robot, VPS, financial and risk work is NOT resolved by this scan.

**Priority rule:** minimize user time to verified, reliable Scanner/PAPER Robot results, with process safety first; one active coding task, reuse recorded evidence, no repeated 774-symbol scans to diagnose one case. Findings are a queue, not authority to change strategy/risk or to launch Scanner/Robot. Do not create separate projects/PRs for each symbol.

| Priority | Task / existing evidence | Next bounded outcome and gate |
|---|---|---|
| **P0 — before next launcher start** | Resolve **pre-existing duplicate local processes**: 2 PAPER backends and 2 Telegram Monitoring workers were observed **before** the scan, sharing backend port 127.0.0.1:8765 and risking Telegram long-polling contention. One-shot `main.py` completed; Robot state `ROBOT_RUNNING/READY` was unchanged, 0 APPROVED candidates, 27 trades in DB; this does **not** prove that the runtime is safe to restart or that no positions are open. | Read-only identify process owners, bound ports, worker ownership, actual Robot/position state and existing lifecycle constraints. Keep one authorized owner per service, only through a safe, specifically approved stop/start plan; do NOT kill all Python processes or restart a backend with uncertain positions. No new infrastructure. |
| **P1 — next geometry task** | Restore **credible formation selection / envelope fit** with AZTEC (U70/L109; 17 upper-body prefix breaches outside common_start), HIMS (19 lower-body breaches and no confirmed outside pivot), QQQ (56/80 breaches), CHIP (0.42 breach ratio) as counterexamples. PR #180's confirmed-pivot+same-body gate catches AAVE/POL but intentionally cannot detect body-only dislocation or earlier-prefix evidence. An own-anchor extension already rejected the AEVO reference and moved INJ/WLD; a generic hard body-containment reject is NOT authorized by the owning decision. | ONE evidence-led geometry task on saved or matching-as-of examples: distinguish boundary support, prefix affiliation, structurally unsupported lines, and later legitimate breakout. Propose a **general, contract-compatible** minimal fix or report the exact required contract decision; include AEVO, INJ, WLD, XRP, PONS regressions and altered winner shape. No global `min_line_span`/coin-specific threshold/blanket score gate, no refitting references to force PASS, no broad scan during diagnosis. If evidence cannot justify a safe fix, stop rather than multiply diagnostic rounds. |
| **P1 — same geometry acceptance, not separate campaign** | **Quality-score interpretation:** 40 of the 74 examined wedge/triangle signals show 100/100 despite malformed envelopes; QQQ 95/100 at 56/80 breaches, HIMS 100/100 at 19 lower-body breaches. Existing quality/containment evaluator remains disabled by contract. | In the geometry task, separate structural scoring from containment validity; verify where 100/100 is computed and whether presentation should identify score scope rather than imply proof of boundary quality. Do not silently enable disabled penalties or add a new hard threshold; if a new policy is necessary, request a narrow explicit decision **after** geometry evidence. |
| **P2 — Ikigai, independent from wedge geometry** | **FWDIUSDT SHORT first impulse:** candidate A176/B189 failed ordinary first-leg close-progress and green-bar share; entered via existing wick alternative, despite larger earlier advance and ~0.59-span intraleg pullback. Opposite-color candles alone do not invalidate an impulse. `CONFIRMED` means completed geometry, **not** that 1.618 was reached or that a trade is authorized. | One scoped Ikigai task, after geometry priority: verify existing wick-path intent against the owning strategy spec and saved FWDI example, then correct the *general* first-impulse eligibility/anchor choice if evidenced and authorized. Preserve WATCH cold-start and no Robot admission/order behavior; do not tune thresholds to one ticker or mix with wedge PR. |
| **P2 — presentation quick fixes (batch together)** | B2: START dot is drawn at `common_start` although model START=88; 7 upper-body breaches at 193–199 are **after END=187**, i.e. acceptable breakout. Ikigai chart's `CONFIRMED` caption can be confused with trade/1.618 confirmation. | Small presentation-only batch: draw actual formation START (and make earliest line anchor intelligible); explicitly label Ikigai `CONFIRMED STRUCTURE / observation; 1.618 not reached` when appropriate. Verify graphs using existing artifacts; do not change geometry/entry/score. User-owned dirty `geometry/ikigai_box_chart.py`: never overwrite; delegate safe review to local agent and preserve edits. |
| **P2 — reliability, scoped** | Bybit rate-limit 10006 and SOCKS timeout/SSL led to 9/774 symbol fetch failures (DUSK, DYDX, DYM, EBAY, EDEN, EDGE, EDU, EGLD, EIGEN). | First reuse logs and existing fetch policy; only if justified add bounded, rate-limit-aware retry/backoff within existing API path, focused network-failure tests; no extra full scan or retry storms. |
| **P3 — later acceptance** | One complete run confirmed Falling/Rising Wedge, Triangle and Ikigai Box SIGNALS wiring; WATCH flag on but 0 cards on **cold start by design**. `structures/` and root `scanner.py` are unused legacy prototypes, not ready patterns. 85 Wedge/Triangle + 71 Box notifications; 239 approved patterns include 154 STABLE/WEAKENING not re-sent. | After fixes, ONE user-approved full production Scanner acceptance with real Telegram; check one controlled continuous WATCH transition **only if specifically relevant**. Do not treat zero WATCH on the initial one-shot run as a defect, promise a further run, or enable Robot autonomously. No blanket connection of unfinished L-shape/flags/HS/Double Top/Bottom prototypes until separately implemented and accepted. |
| **P3 — cleanup / deferred** | Two old worktrees `C:\\BybitScanner-pr178` and `C:\\BybitScanner-bv` plus other historical worktrees remain; root `analyzer.py` is shadowed by live `analyzer/core.py` and can mislead reviews. Scanner doesn't persist exact candle snapshots. | Do not delete user worktrees or refactor imports just for hygiene. On the next *relevant* scoped task, consider reproducible capture of the single signal-time OHLC snapshot **only if** it measurably saves more user-time than it costs; no new ingestion infrastructure. Cleanup requires separate verification of ownership and explicit authorization. |

**P1 decision/result update — 2026-09-22:** The owner now permits evidence-backed
revision of defective references; isolated excursions must not automatically
reject. The earlier P1 prohibition above is superseded only by the bounded rule
in `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`: seven consecutive body breaches
beyond existing ATR tolerance on each boundary's own-anchor..END interval,
replacing #180's single pivot/body veto; selection counts use the same intervals.
Eleven historical cases and cutoff sensitivity 4..8 are verified. AEVO/HIMS/QQQ/
CHIP/POL have no admissible pair; INJ's lower anchor changes 68->77; WLD changes
to supported U129/L61 triangle; AZTEC keeps only stale U106/L102 END148; XRP,
PONS and AAVE's stale diagnostic selection are unchanged. Evidence and tests:
`CR-SCANNER-GEOMETRY-FORMATION-FIT-001`. Next: protected final verification and
one PR review/integration; no runtime acceptance is claimed. Score 100/100
remains structural-plus-confirmation, not an envelope guarantee. Other queue
items and all runtime/risk authorization boundaries are unchanged.

**Sequencing:** P0 runtime ownership/safety before any next multi-service launcher; P1 one geometry correction and score interpretation; P2 Ikigai and a combined display batch; P2 data resilience when it blocks acceptance; P3 one authorized full rerun only after material fixes. These are distinct issues, not a license to open them all simultaneously. The older Robot/v0.1 financial-risk backlog retains its own authorization/safety gates.

## 2. Prioritized queue

### P0 — stability of the live run
| # | Task | Status / next step |
|---|---|---|
| P0-1 | Owner-thread candle cache (PR #153): MERGED. Remaining: sync the PC, restart PC backend+listener (Claude Code prompt), reconcile, resume | Then a 30-minute load check on the PC (`protection-health`: `high_watermark`, `candle_cache_misses_owner`; backend window for `Slow PAPER owner task`). The PC also hit `ingress_overflow` on 2026-09-19 21:15 (CFXUSDT), so the fix is needed there |
| P0-2 | Conditional: only if overflow persists after P0-1, on whichever machine runs the robot (currently the PC) | Reconcile recovery-policy geometry index (`load_candles` per APPROVED candidate), admission catch-up loader; then a disk fsync benchmark (`synchronous=FULL`) on that machine |

### P1 — money-relevant, small
| # | Task | Status / next step |
|---|---|---|
| P1-1 | Analysis of PC closed trades (fees entry+exit) | DONE 2026-09-19: 25 trades, clean sample 10 (3 TAKE / 7 STOP, net -1.63 USDT), see section 6 |
| P1-2 | Minimum stop distance 0.7% (`structural_stop` floor) | Spec written, not started. Decide after the back-test A-3 |
| P1-3 | Chart window from pattern start (left margin, current candles right) | Small Telegram-side task; spec in section 3 (G1) |
| P1-4 | Reward/risk filter (skip entry if take distance < k x stop distance) | APPROVED by the user 2026-09-19: configurable `MIN_TAKE_TO_STOP_RATIO`, start value 1.5, tune later; next backend task after the PC restart |

### P2 — features that need a spec first
| # | Task | Status / next step |
|---|---|---|
| P2-1 | Geometry and patterns program | Section 3 (G0-G7) |
| P2-2 | Fee attribution in the DB (`realized_pnl_pct` lacks entry fee, `realized_pnl_usdt` is gross) | Posts already compute entry+exit from executions; DB fix is separate |
| P2-3 | Distinguish exit reasons: feed-gap emergency exit vs operator "Close all" (both `EMERGENCY_CLOSE` today) | Analytics quality; small |

### P3 — hygiene
| # | Task | Notes |
|---|---|---|
| P3-1 | Buttons "Под наблюдением" and "Обновить" have no handlers | Every lifecycle post carries only "Все позиции" until fixed |
| P3-2 | Listener and Scanner as systemd services on the VPS (paused: the live run is on the PC now) | Resume when the run moves back to the VPS |
| P3-3 | CI for the Telegram side (workflow paths cover only trading backend and dev tooling) | Add `telegram_*.py`, `robot_position_*.py`, `robot_telegram_feed.py`, `tests/test_telegram_*.py` |
| P3-4 | Stop/Pause semantics: Stop left WAITING_* candidates alive (CSOPSAMSUNG2LUSDT, 5 more on 2026-09-19) although the decision doc says zero-exposure pending candidates are terminalized | Decide: fix behaviour or correct the doc |
| P3-5 | Old manual-test residue: CELOUSDT dust position (sync_state reconciliation_required), 5 commands stuck in `submitting` (OGUSDT x2, CELOUSDT x3) | Keeps the `/positions` warning permanently on; needs a proper task, no manual journal edits |
| P3-6 | Chart axis: date labels for windows longer than 24 h | Small |
| P3-7 | Flaky test `test_dispatch_fails_closed_on_replacement_lifecycle_with_same_quantity` (failed once under load) | Re-run first; investigate only if it recurs |
| P3-8 | Stale GitHub state: open PRs #143, #144, #63, #66, #121; merged local branches; 5 stashes; local-only branches | Clean only after review, nothing was deleted so far |
| P3-9 | PC config: set `TIMEFRAME = "5"` before the PC scanner is used again | One line; PC and VPS trades stay separate in statistics |
| P3-10 | Run log: add section 10 (2026-09-19 incidents 2 and 3, owner-thread REST finding, PRs #151-#153) and DECISION_LOG entries | Do together with P0-1 |
| P3-11 | Pre-existing failing tests: `tests/test_task_context.py`, `tests/test_task_harness.py` (10 of 11 fail on `main` without any change) | Cause not investigated |

## 3. Epic: Geometry and patterns (queued, one item at a time)

User request (2026-09-19, from the ChatGPT conversation): rework wedge and triangle geometry; add two wedge categories;
add triangle, box and L-shaped patterns for robot trading. First fix scaling so a pattern start never falls off the left
edge of the chart, then move to adequate anchor detection. Work through Codex/Claude Code, light and fast, edit through
GitHub with timely synchronization. Also: check earlier groundwork and borrow proven solutions from mature projects.

### G0 — Research and groundwork (docs first)
Findings so far:
- Anchor groundwork exists: `DOCUMENTS/ROADMAP.md` FUTURE_MISSION_ANCHOR_QUALITY_LEARNING (several anchor candidates kept
  with immutable detection-time geometry, ranking evidence), `FUTURE_FEATURES.md` ANCHOR_GEOMETRY_INTEGRATION, the
  Anchor/START button in scanner posts.
- Triangle Compression is detected by the scanner (`ARCHITECTURE.md`) but Robot v0.1 rejects it (only Falling/Rising Wedge are in
  `robot_state_machine._PATTERN_DIRECTION`; button and admission now refuse it).
- L-shaped continuation: only in `AUTOPILOT_STRATEGY_ACCUMULATED_DESIGN.md` ("L-shaped post-impulse consolidation"); the exact
  structure definition is an open item there (item 7). No code.
- Ikigai Box is NOT a generic rectangle/breakout. Existing archived cases are in `training/reference_patterns/HEIUSDT/post_pump_two_drop_fib_1618_1h/`, `AEONUSDT/ikigai_box_15m/`, and `VELVETUSDT/ikigai_boxes/`; authoritative design: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`. The older generic-range wording in this backlog was incorrect.
- Geometry code lives in `wedge/` (detector, classifier, integrity, potential) and `structures/`.
To do: a short survey of mature open-source pattern-detection approaches (anchor/pivot selection, scaling), written to a doc,
with concrete ideas to borrow. Output: `DOCUMENTS/GEOMETRY_RESEARCH_<date>.md`.

### G1 — Chart window from pattern start (small, do first)
Window must cover the whole figure: from the earlier of pattern start and entry, minus a left margin, to the current candles.
Data: frozen `robot_geometry` lines carry `anchor_index` in 1m index space; time = `scanner_geometry_cursor.source_candle_time_ms`
minus (`geometry_index` - `anchor_index`) x 60 000 ms. Margin: max(10 candles, 8% of the span). Cap 1000 candles; if the start is
still earlier, caption "Начало паттерна раньше окна графика". Acceptance: on real signals the START point of both boundaries is
visible with margin on both 5m and 1m cards.

### G2 — Adequate anchor detection
Depends on G0 and G1. Inputs from the user: 3-5 chart examples where anchors were wrong (Anchor/START feedback already exists in
the Telegram posts). Output: spec (which pivots are candidates, ranking, tolerance), then implementation behind a flag with
side-by-side comparison on saved signals.

### G3 — Two wedge categories
Inputs from the user (blocking): definition of the two categories with one example each. Robot already handles Falling -> LONG and
Rising -> SHORT; new categories need their own direction and entry rules.

### G4 — Triangle in the robot
Scanner detects Triangle Compression. Needs the trading rule decision: symmetric, ascending, descending or all three; direction of
the breakout trade; stop/take source; whether `_PATTERN_DIRECTION` becomes per-variant. Depends on G2 (anchors).

### G5 — Ikigai Box (two-impulse Fibonacci reversal; NOT a range breakout)
Authoritative definition and historical references: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`.
First impulse and second impulse are in the SAME direction, separated by consolidation. Freeze first-impulse A/B;
F(0)=origin, F(1)=first-impulse terminal, F(1.618) and F(2.618) extend along that impulse.
SHORT on second UP impulse near 1.618; mirrored LONG on second DOWN impulse. Four advance LIMITs of 1/4 РО,
outermost beyond extension. Confirmed reversal candle's extremum for STOP if valid; otherwise -1.5% from actual
average entry. Following a confirmed first STOP, verified flat/cancelled, one sequential second grid at 2.618;
main target F(1.0), partial profit-taking before target and then fee-aware breakeven. Exact grid spacing,
partial-TP and breakeven triggers remain undefined, so no Robot order execution is authorized by this description.
Priority after user-requested L-shape work: detector + visual Scanner/Telegram signal, then separate PAPER Robot lifecycle.

### G6 — L-shaped continuation
Offline detector and preview published to `main` in
[PR #195](https://github.com/svobodaXXI/BybitScanner/pull/195): impulse, then a
narrow shelf near the extreme; HIGH-first (LONG) preview draws only the
impulse-HIGH ray and target `T = 2*H - L`, no Fibonacci. Current status,
what remains unimplemented (preceding-impulse-vs-ordinary-swing proof) and
the exact next step are recorded in
`SCANNER_GEOMETRY_CURRENT_COURSE.md` ("Active development priority —
L-shaped formation, not wedge S1"); not duplicated here. Entry rule and
Robot wiring are still open design items, unchanged from before.

### G7 — Dual-timeframe scanner (5m + 1m per ticker) — REQUIRED (owner-updated 2026-09-30)
Authoritative Scanner contract:
- process each symbol as `5m -> 1m` before advancing to the next symbol;
- evaluate all enabled pattern families independently on both timeframes;
- preserve independent `symbol × timeframe × pattern × formation/source`
  state, evidence and dedup;
- a delivered/detected 5m signal must not terminate discovery for that symbol or
  suppress a valid 1m signal/different pattern.

Known implementation constraints remain relevant: `TIMEFRAME` has historically
been a global constant and older signal memory was symbol-only. Robot currently
has stricter one-owner-per-symbol execution constraints; that is a separate
admission/execution problem and must not be solved by hiding valid Scanner
signals. BOX-MTF-REENTRY-1 is also separate: it is a parent/child execution
strategy, not ordinary multi-signal Scanner traversal.

Latest user priority (2026-09-20): finish L-shaped (G6) visualization and its signal path first; then Ikigai Box (G5)
with the correct two-impulse Fibonacci design, ahead of triangle and additional wedge taxonomy. Earlier ordering
was superseded. Draft PR #156 and the unpublished local L-shape worktree remain separate; neither is a prerequisite
for the Box's offline detector. G7 (dual timeframe) is deferred.
Blocking input for G3: description of the two wedge categories with one example chart each.
Every pattern follows the same path: definition with examples -> spec -> detection -> signal/post -> robot rules -> tests ->
live verification -> record.

## 4. Decisions waiting for the user
1. Reward/risk filter: RESOLVED, yes, configurable, start 1.5, tune later.
2. Minimum stop 0.7%: confirm after the back-test A-3.
3. Pattern order RESOLVED (2026-09-20): L-shaped first, Ikigai Box second, others later. Box reference examples and
   primary/secondary entry, fallback STOP and principal target are in `IKIGAI_BOX_STRATEGY_SPEC.md`; exact grid spacing,
   early TP split/price and breakeven trigger still require user approval before executable PAPER Robot integration.
4. Dual timeframe: RESOLVED, required. Still open: how to resolve two signals (5m and 1m) on one ticker (which one the robot takes).

## 5. Facts to keep in mind when reading results
- PC trades before 2026-09-19 evening came from 1-minute signals, VPS trades from 5-minute ones; do not merge them in statistics.
- `EMERGENCY_CLOSE` is not a strategy exit (feed-gap fail-safe or operator close); exclude it from stop/take statistics.
- `realized_pnl_usdt` is gross and `realized_pnl_pct` includes only the exit fee; the posts compute entry+exit fees from executions.
- Cleaning candidates without SQL: "Stop" (only with no open position) does not touch WAITING_* candidates; the guarded cleanup script
  writes through `SQLiteStore` with a DB backup first.

## 6. Findings from the PC database (25 closed trades) and related queue items

| # | Priority | Task | Notes |
|---|---|---|---|
| A-1 | done | Single Telegram poller | Checked 2026-09-19: only the PC runs a listener; the VPS has none |
| A-2 | P1 | Investigate outliers MINAUSDT (-22.9% in 0 min with a 2% stop) and AAOIUSDT (stop 0.00%, 0 min) from 2026-09-14 | Bug of the early version vs thin-book slippage; read the trade row, exit price vs stop, executions |
| A-3 | P1 | Back-test on real 1m paths: 0.7% minimum stop and reward/risk filter on the clean sample (about 10 trades) | Script sent to the user, awaiting output; decides P1-2 and the first tuning of P1-4 |
| A-4 | P2 | Mark trades closed at the first check after downtime (robot/backend off for hours or days) with a distinct flag/exit reason and exclude them from strategy statistics | Five trades (BR, COTI, H, AEHR, 1000TAG) made +178.6 USDT this way; AKT/CL/MINA distort the other direction |
| A-5 | live prerequisite | Protective orders on the exchange side (software stops only work while the backend runs) | Not needed for PAPER; must be designed before any live use |

Clean sample definition (for statistics): holding time < 24 h, size >= 100 USDT, not `EMERGENCY_CLOSE`, not a 0-minute
artifact. PC result: 10 trades, 3 TAKE / 7 STOP, net -1.63 USDT (fees entry+exit included), hit rate 30%. VPS 5m: 0 TAKE / 5 STOP
so far (small sample). The raw database total (+99.76 USDT over 25 trades) is not meaningful: it is dominated by downtime gap exits and one outlier.
