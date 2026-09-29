# Owner Feedback Remediation Queue — 2026-09-29

Status: ACTIVE / OWNER-PRIORITIZED  
Scope: today's real owner feedback, acceptance findings and blockers that must be handled **before Geometry implementation resumes**.

This queue sits after the current RVL-R6 owner PAPER acceptance and before
RVL-G2/G3/G4 production Geometry work. RVL-G1 inventory remains complete and is
not repeated.

## Priority order

### OFR-1 — Durable Robot failure diagnostics
**Priority:** P0  
**Status:** IMPLEMENTED IN PR #334 / PAPER CI GREEN / awaiting merge

Two real classes now lose their exact cause after the console scrolls:

1. Box Robot handoff failure:
   - B2USDT 5m
   - BANKUSDT 5m
   - BNBUSDT 5m
   - BNCUSDT 5m
   Ordinary signal delivered, explicit owner warning emitted, no Robot button.
   Later BRETTUSDT succeeded, so this was not a global outage.

2. Protection/emergency-close diagnosis:
   - CASHCATUSDT SHORT closed with `EMERGENCY_CLOSE` while displayed STOP was
     still far above the close price.
   - top-level log search found no CASHCATUSDT protection/close event and no
     concrete emergency-close cause.
   - the only EMERGENCY_CLOSE string found in SQLite by line search was schema
     text; binary line search is not authoritative.

Required implementation:
- bounded durable sanitized incident record;
- timestamp, symbol, timeframe/pattern when applicable, lifecycle stage,
  candidate/trade id if safe, failure/error class and normalized reason code;
- for protection emergency close, persist the deciding facts:
  `stop_proven`, `take_proven`, `market_data_authoritative`,
  `intended_stop_crossed`, deadline/age and selected recovery action;
- no secrets, credentials, raw tokens or unsafe absolute-path leakage;
- bounded retention;
- diagnostic write must not become a new safety-critical blocker.

Acceptance evidence:
- PR #334 implements bounded sanitized durable incident records;
- candidate persistence failures persist normalized diagnostic evidence;
- protection continuity recovery emergency close persists deciding facts;
- post-fill initial-protection failure emergency close now persists a separate
  `INITIAL_PROTECTION_FAILURE` incident before the full-close path;
- diagnostics IO remains best-effort/non-blocking;
- Robot PAPER acceptance #261 at head `e53caa2bf9568d91f449e2f33e04b752addf8cc5`
  completed successfully.
- merge is still pending owner authorization.

### OFR-2 — CASHCATUSDT emergency-close root cause and recurrence fix
**Priority:** P0  
**Status:** HISTORICAL INVESTIGATION COMPLETE / exact initiating reason unrecoverable

Owner/runtime evidence:
- CASHCATUSDT Rising Wedge SHORT;
- average entry approximately 0.176958;
- STOP 0.17755;
- emergency exit approximately 0.175125;
- Stop and Take were created at 07:17:02 UTC / 10:17:02 MSK;
- recovery event arrived at 07:53:14.472 UTC through REST recovery;
- the protection obligation latched about 325 ms later and the exit execution
  completed about 2.935 s after that;
- `market_event_id` contains `CASHCATUSDT:rest-recovery:...`;
- emergency trigger price 0.17509 was neither STOP 0.17755 nor TAKE 0.163840;
- durable lifecycle is internally consistent:
  candidate -> trade -> command history -> execution -> protection actions /
  obligation -> final Flat/synced position;
- protection obligation resolved with winning leg `EMERGENCY_CLOSE`.

Conclusion:
- ordinary strategy STOP/TAKE did **not** cause this exit;
- the exit was initiated on the protection continuity REST-recovery path;
- the historical database preserved the recovery outcome but not the
  continuity-loss reason that caused recovery;
- targeted searches of repository-local 2026-09-29 `.log/.txt/.out/.err`
  artifacts found no CASHCATUSDT, `ROBOT_PROTECTION_COVERAGE_LOST`,
  `rest-recovery` or related reason marker;
- therefore the exact initiating cause (for example a real WebSocket
  disconnect, `ingress_overflow`, identity mismatch, subscription/admission
  failure or another continuity-loss reason) is **not recoverable from the
  surviving historical evidence**;
- do not claim that an internet lag caused CASHCATUSDT specifically.

Relevant repository history:
- #237 removed a false-positive stale-generation path while preserving genuine
  disconnect fail-closed recovery;
- #293 documented a real 64/64 protection-ingress overflow that produced
  `ROBOT_PROTECTION_COVERAGE_LOST ... ingress_overflow`;
- #305 fixed one proven source of excessive ENTRY_PENDING coverage while noting
  that other slow-owner causes were not yet excluded;
- these prove plausible classes of continuity loss, but none identifies the
  historical CASHCATUSDT reason.

Disposition:
1. **Stop historical digging here.** Repeating SQLite-wide or filesystem log
   searches is not expected to recover the missing reason.
2. Do not add a speculative recurrence fix for CASHCATUSDT without a proven
   trigger.
3. Preserve current STOP-first/fail-closed protection semantics.
4. OFR-1 is the forward fix: the next protection continuity emergency close
   must persist the normalized initiating reason and deciding facts durably.
5. If the same class recurs after OFR-1 is deployed, use that incident record
   to freeze the exact deterministic replay and fix only the proven cause.

Acceptance:
- historical CASHCATUSDT exit path classified as
  `REST recovery -> EMERGENCY_CLOSE`;
- normal STOP/TAKE excluded by durable evidence;
- exact initiating continuity-loss reason explicitly classified as unavailable
  rather than guessed;
- no further historical-search loop required;
- future recurrence becomes deterministically diagnosable through OFR-1.

### OFR-3 — Robot candidate handoff failures on valid Box cards
**Priority:** P0  
**Status:** CLOSED / correct fail-closed risk rejection

Cases:
`B2USDT`, `BANKUSDT`, `BNBUSDT`, `BNCUSDT` 5m.

Deterministic replay evidence:
- all four saved 2026-09-29 formation identities were recovered from Box PNG
  names + `signals_history.json`;
- current `detect_ikigai_box` reproduced every case with exact matching
  anchors and direction;
- approved first grid construction succeeded for every case;
- current instrument price/quantity/min-notional constraints were satisfied;
- PAPER equity was read from `paper_accounts` as 5000 USDT, therefore
  1 WV = 250 USDT;
- each slot was approximately 62 USDT and above minimum notional;
- all four cases failed at the same planner gate:

  `no tick-aligned STOP beyond P4 satisfies net RR >= 2`

Conclusion:
- these were valid Scanner Box detections but **not executable PAPER Robot
  plans** under the frozen Box grid, fees and net RR >= 2 contract;
- absence of the Robot button was therefore correct fail-closed behavior;
- no planner/persistence/admission bug is proven for these four cases;
- do not weaken RR, move P4, invent a per-symbol exception, or force candidate
  creation merely to make the Robot button appear;
- the owner warning was generic because the precise reason was previously
  console-only; OFR-1 now provides durable diagnostics for future failures.

Disposition:
1. No production trading-logic patch for B2/BANK/BNB/BNC.
2. Treat this failure class as `NON_EXECUTABLE_RR_STOP` conceptually in
   investigation/reporting; any future code naming change belongs to UX/
   diagnostics, not risk policy.
3. Reopen only if a replay that satisfies the approved risk contract still
   fails candidate preparation, or if the owner explicitly changes the Box
   strategy/risk contract.

Acceptance:
- representative failing class reproduced deterministically;
- exact common rejection gate established;
- fail-closed behavior proven correct;
- no per-symbol workaround required;
- no further historical replay required for these four cases.

### OFR-3A — Robot does not self-recover after protection/reconcile incident
**Priority:** P0  
**Status:** IMPLEMENTED IN PR #335 / PAPER CI GREEN / awaiting merge

Owner evidence 2026-09-29:
- after CASHCATUSDT was closed by `EMERGENCY_CLOSE`, a later owner action was
  rejected with:
  `Робот: отклонено — Робот не готов к приёму новых сделок`;
- status shown to the owner:
  `Запущен / Нужна сверка`.

Root cause:
- historical Robot safety contract deliberately made
  `RECONCILIATION_REQUIRED` sticky;
- #117 defined explicit `reconcile_robot()` as the only evidence-based escape,
  and successful reconciliation landed `PAUSED`, never `READY`;
- #129 intentionally preserved that fence across restart;
- therefore a transient protection-continuity incident that fully resolved its
  Robot-owned exposure still required operator reconcile + resume by design;
- CELOUSDT is a separate old manual/non-Robot PAPER reconciliation debt and is
  not part of this root cause.

Implemented narrow contract in PR #335:
- capture the Robot recovery state before the continuity fence;
- after continuity recovery proves the affected Robot-owned exposure resolved,
  run the existing global evidence-based `robot_reconcile()`;
- if the pre-fence state was `READY`, reopen admission only after global
  reconcile succeeds and reaches `PAUSED`, then transition to `READY`;
- if the pre-fence state was owner `PAUSED`, preserve `PAUSED`;
- if `RECONCILIATION_REQUIRED` already existed before this continuity event,
  never auto-clear it;
- any unresolved candidate/trade/protection ambiguity remains fail-closed.

Safety boundaries:
- no STOP/TAKE/emergency-close policy change;
- no LIVE change;
- no manual/non-Robot position adoption or mutation;
- explicit operator `reconcile_robot()` semantics remain unchanged and still
  land `PAUSED`.

Validation:
- deterministic regressions cover READY self-recovery, PAUSED preservation and
  pre-existing fence preservation;
- Robot PAPER acceptance #262 completed successfully at
  `14717851b24d47b1d136770ca37c9dcfc2c3496b`.

Acceptance:
- transient continuity-loss recovery may self-return to READY only after the
  existing evidence-based global reconciliation proves safety;
- deliberate PAUSE and unrelated/pre-existing reconciliation fences survive;
- merge remains pending explicit owner authorization.

### OFR-4 — Box signal lifecycle: suppress already-completed setups
**Priority:** P0/P1  
**Status:** OPEN invariant / original 1INCHUSDT example NOT PROVEN completed

Owner concern:
- an old Box should not be delivered/admitted as a fresh actionable setup if
  its approved lifecycle had already become executable and subsequently
  completed at the frozen common TAKE before delivery/admission.

Historical 1INCHUSDT investigation:
- three saved 5m SHORT Box PNGs exist (21.09, 28.09, 29.09);
- the 28.09 and 29.09 Box identities were deterministically replayed from
  exact saved A/B anchors with the current detector and current approved grid/
  TAKE arithmetic;
- 28.09 Box:
  - decision `1790615700000`;
  - P1 `0.10139`;
  - TAKE `0.10052`;
  - first P1 touch occurred only at `1790664000000`;
  - no later returned closed candle reached TAKE;
- 29.09 Box:
  - decision `1790664000000`;
  - P1 `0.10165`;
  - TAKE `0.10103`;
  - P1 was available on the next 5m candle;
  - no later returned closed candle reached TAKE;
- therefore neither available replay proves `COMPLETED_STALE`;
- notably, the old 28.09 Box first reached P1 exactly at the 29.09 Box
  decision timestamp, so the two setups overlap in time.

Correction:
- do **not** use 1INCHUSDT as the regression proving completed/stale suppression;
- the prior interpretation that this specific setup had already completed at
  the frozen TAKE is withdrawn unless later source-time evidence proves it;
- do not infer completion merely because price nearly reached F(1.0), moved
  strongly after the signal, or visually looked "worked out";
- do not infer intrabar ordering when P1 and TAKE are contained in the same
  candle.

Required rule before implementation:
1. freeze a real source-time case where an approved Box entry became available
   first;
2. prove on a strictly later closed/authoritative candle that the frozen common
   TAKE was reached before delivery/admission;
3. only then add the suppression gate and regression;
4. preserve still-actionable overlapping/new Box identities independently.

Frozen completion predicate:
- Box TAKE is the approved common TAKE, not literal F(1.0);
- SHORT completion requires a later authoritative/closed price low <= frozen
  TAKE after entry availability has already been established;
- LONG mirrors with high >= frozen TAKE;
- same-candle P1 + TAKE is not sufficient without authoritative intrabar order.

Acceptance:
- a real proven completed-before-delivery Box is suppressed from fresh
  actionable delivery/admission;
- the 28.09 and 29.09 1INCHUSDT cases remain deliverable unless new evidence
  proves their frozen TAKE had already been reached after entry availability;
- no false suppression of a still-actionable or overlapping Box.

### OFR-4A — Post-STOP reversal watch and market re-entry attempt
**Priority:** P1  
**Status:** OPEN strategy/lifecycle design — core contract frozen except owner 5m acceleration

Owner requirement:
- when an otherwise actionable signal/candidate has **not opened a position yet**
  and price moves beyond its currently planned STOP level, do not automatically
  terminalize the signal as dead;
- transition it into a dedicated reversal-watch state and continue monitoring
  source-time price action;
- allow a new **MARKET-entry attempt only after a valid reversal confirmation
  has fully closed**;
- this is a continuation of the same frozen setup identity/history, not a
  symbol-specific exception and not a blind immediate re-entry.

### Reversal confirmation catalog

General rules:
- confirmation uses only **closed candles / completed structures**;
- all confirmations are direction-aware: the reversal must point back toward
  the original source setup target;
- the formation must occur after the adverse move that invalidated the previous
  pre-entry attempt; an older pattern may not be reused;
- continuous crypto markets do **not** require classic session gaps for
  Morning/Evening Star or Piercing/Dark Cloud. Equivalent rejection through
  candle bodies/wicks is used instead.

Candlestick confirmations:

1. **Hammer / Hanging Man**
   - same candle geometry; context determines name/direction;
   - real body must be in the upper part of the candle range;
   - lower shadow must be at least **1.0x real-body height**;
   - lower shadow >= **2.0x body** is treated as a stronger textbook form but
     is not required for admission;
   - upper shadow may be absent; when present it must not be larger than the
     real body;
   - Hammer is bullish after a decline; Hanging Man is bearish after an advance.

2. **Inverted Hammer / Shooting Star**
   - mirror geometry:
     upper shadow >= **1.0x body**, >=2.0x is stronger;
   - lower shadow may be absent and, when present, must not exceed body height;
   - Inverted Hammer is bullish after a decline; Shooting Star is bearish after
     an advance.

3. **Bullish / Bearish Engulfing**
   - two closed candles;
   - second real body is opposite-direction and fully contains the first real
     body; wicks do not need to be engulfed;
   - equality at one body edge is allowed after tick normalization;
   - pattern must follow an adverse move in the opposite direction.

4. **Morning Star / Evening Star**
   - three closed candles;
   - candle 1 is a directional impulse body;
   - candle 2 has a small body <= **50%** of candle-1 body;
   - candle 3 is opposite-direction and closes at least **50% through candle-1
     real body**;
   - a session gap is preferred textbook geometry but is not required in the
     24/7 crypto implementation.

5. **Piercing Line / Dark Cloud Cover**
   - two closed candles;
   - candle 1 is directional with the adverse move;
   - candle 2 rejects beyond candle-1 adverse extreme by wick or open and
     closes past the **50% midpoint of candle-1 real body** in the reversal
     direction;
   - if candle 2 fully engulfs candle 1, classify it as Engulfing rather than
     duplicate both labels.

6. **Harami / Harami Cross**
   - two closed candles;
   - candle-2 real body is fully contained inside candle-1 real body;
   - ordinary Harami candle-2 body <= **60%** of candle-1 body;
   - Harami Cross uses a Doji second candle;
   - Doji threshold: real body <= **10% of total candle range**.

7. **Dragonfly Doji / Gravestone Doji**
   - Doji body <= **10% of total range**;
   - dominant reversal shadow >= **60% of total range**;
   - opposite shadow <= **10% of total range**;
   - Dragonfly is bullish at a local low; Gravestone is bearish at a local high.

Structural confirmations:

8. **Double Bottom / Double Top**
   - use confirmed local pivots, not arbitrary candle highs/lows;
   - two corresponding extrema are considered equal when their difference is
     no greater than **min(2% of their mean price, 0.75 * ATR(14))**;
   - the middle reaction must form a real opposite pivot, not a one-candle
     micro-noise notch;
   - confirmation occurs only on a **closed-candle break of the neckline/reaction
     level** in the reversal direction.

9. **Inverse Head and Shoulders / Head and Shoulders**
   - five-pivot structure with two shoulders, a more extreme head and two
     neckline pivots;
   - shoulder-height difference <=
     **min(2% of mean shoulder price, 0.75 * ATR(14))**;
   - head must extend beyond both shoulders by at least **0.5 * ATR(14)**;
   - neckline may slope;
   - confirmation occurs only after a **closed candle breaks the neckline** in
     the reversal direction.

10. **Lower-timeframe Falling / Rising Wedge**
   - reuse the existing BybitScanner Wedge geometry/detector instead of creating
     a second wedge definition;
   - for a 5m source setup, the lower confirmation timeframe is **1m**;
   - Falling Wedge confirms bullish reversal; Rising Wedge confirms bearish
     reversal;
   - the wedge itself is not enough: its breakout must be confirmed by a
     **closed candle in the direction of the original source target**.

11. **Owner 5m acceleration**
   - accepted as an additional reversal-confirmation family;
   - **EVENING DESIGN TASK**: freeze its exact visual/price-action definition
     from owner examples before any implementation;
   - do not infer or implement its machine rule before that owner review.

### Attempt budget
- maximum **3 entry attempts per original signal**;
- an attempt is consumed **only when there is an actual Robot-owned entry fill
  / position opening** from that re-entry attempt;
- a valid reversal confirmation that is rejected by RR/risk/protection before
  execution does **not** consume an attempt;
- an order/decision that never results in actual filled exposure does **not**
  consume an attempt;
- after the third actual entry attempt, no further re-entry attempt is
  permitted for that signal.

### Lifetime / expiry
- reversal-watch remains alive until the setup potential is realized, or until
  price travels beyond **50% of the distance from F(2.618) to F(3.618)** in the
  adverse extension direction;
- LONG: expiry extension threshold =
  `F2.618 + 0.5 * (F3.618 - F2.618)`;
- SHORT: mirror the same geometric midpoint in the opposite direction;
- OFR-4 remains authoritative: if the setup has already economically completed
  by reaching its frozen TAKE, it is stale/completed and must not be revived.

### Frozen MARKET re-entry terms
- **target remains the original frozen target** of the source setup;
- STOP is first placed beyond the relevant reversal-confirmation extremum;
- structural STOP distance is measured from the actual MARKET entry;
- if that distance exceeds **2.0%**, cap the STOP at **2.0% from actual MARKET
  entry** in the adverse direction;
- after the structural/2% STOP is known, recompute fee-aware RR from actual
  MARKET entry to the original frozen target;
- the ordinary current Robot risk gate remains authoritative; a confirmation
  rejected by risk/RR/protection creates no order and does **not** consume one
  of the three attempts;
- STOP price is normalized to instrument tick and must remain on the protective
  side of actual entry.

Safety constraints:
- crossing the old STOP never triggers an automatic MARKET entry by itself;
- confirmation must be closed/completed; no unfinished candle may trigger;
- an already-open Robot trade remains governed by the existing STOP/protection
  lifecycle; this task does not silently convert a real stopped-out position
  into an automatic re-entry loop;
- a TAKE-completed, midpoint-expired, or 3-attempt-exhausted setup cannot revive;
- one underlying reversal event should not consume multiple attempts merely
  because it matches several overlapping candle labels; deduplicate by the
  completed reversal event/end candle.

Acceptance:
- deterministic pre-entry STOP-crossing case remains in reversal-watch;
- no entry before valid closed confirmation;
- Hammer/Hanging-Man owner shadow rule is covered at 1x and stronger 2x cases;
- risk-rejected/no-fill confirmations do not increment the 3-attempt budget;
- each actual filled re-entry increments the same 3-attempt budget;
- valid later MARKET attempt keeps original target, uses structural STOP capped
  at 2%, recomputes RR from actual fill and enters shared protection;
- double-top/bottom and H&S require neckline close confirmation;
- lower-TF wedge reuses canonical Wedge detector and requires directional closed
  breakout;
- midpoint expiry, TAKE completion and attempt exhaustion terminalize the
  re-entry path deterministically.

### OFR-5 — Box crossed-grid late admission / catch-up execution
**Priority:** P1  
**Status:** OPEN / one strategy detail unresolved

Frozen owner intent:
- original P1..P4 grid remains fixed;
- each entry slot already crossed before submission is acquired by MARKET for
  exactly that slot quantity;
- not-yet-crossed slots remain at their original entry LIMIT levels;
- each market-caught slot retains slot ownership and gets its corresponding
  opposite/closing LIMIT;
- shared Robot protection/recovery remains authoritative;
- no one-shot aggregate `1 RO` market fallback.

Blocking decision before code:
- exact price mapping of each paired closing LIMIT still must be frozen;
- if real market catch-up fills conflict with existing frozen planned-average/RR
  STOP arithmetic, freeze the precise STOP rule rather than silently moving it.

Acceptance:
- deterministic scenarios for 0/1/2/3/4 crossed slots;
- exact slot ownership after mixed MARKET + LIMIT entry;
- paired close limits proven;
- familiar STOP protection active immediately for real exposure;
- restart/reconcile preserves the same slot identities.

### OFR-6 — Telegram position-card presentation cleanup
**Priority:** P1  
**Status:** OPEN UX

Owner example:
- CASHCATUSDT open/closed position card.

Required changes:
- remove the excessive rightward visual shift and keep the relevant pattern/
  latest candles visually balanced in the chart;
- replace bulky level labels:
  - `Вход` -> compact `Entry` or equivalent short label;
  - `STOP` -> `SL`;
  - `TAKE` -> `TP`;
- labels must remain readable without covering the latest candles;
- caption:
  `Размер: <qty>` -> `Объем: <qty> (<notional> USDT)`;
- USDT notional for an open card = authoritative quantity × authoritative
  average entry, formatted compactly (e.g. CASHCATUSDT:
  `Объем: 1410 (249.51 USDT)`);
- retain average entry, PnL, STOP, TAKE and pattern lines in the text card.

Acceptance:
- one representative 5m position card is owner-readable without right-edge
  crowding;
- caption shows quantity + USDT notional;
- lifecycle open/closed cards use the same formatter.

### OFR-7 — TradingView button on position cards
**Priority:** P1  
**Status:** OPEN UX

Current position-card keyboard only offers `⬅️ К позициям`.

Owner requirement:
- when entering a position card from `/positions`, show the same useful
  TradingView navigation affordance used on Scanner signals;
- button must open the selected symbol in TradingView;
- retain `⬅️ К позициям`;
- no trading mutation from this link;
- manual/non-Robot position cards should get the TradingView link too when the
  symbol is valid, even if no Robot chart can be rendered.

Acceptance:
- `/positions -> CASHCATUSDT -> position card -> Open TradingView` works;
- back-to-positions remains available;
- invalid symbols fail closed and do not produce malformed URLs.


### OFR-7A — Candidate monitoring card: chart + TradingView
**Priority:** P1  
**Status:** OPEN UX

Owner requirement:
- when opening a candidate from `/monitoring`, show the candidate chart in
  addition to the text card;
- add an **`Открыть в Trading View`** button for the candidate symbol/timeframe;
- retain **`⬅️ К кандидатам`** navigation;
- this surface is navigation/observability only and must not introduce a trading
  mutation;
- if the chart is unavailable or the symbol/timeframe cannot produce a valid
  TradingView target, fail closed without breaking the candidate detail view.

Acceptance:
- `/monitoring -> candidate -> candidate card` shows the candidate chart when
  available;
- **`Открыть в Trading View`** opens the correct symbol/timeframe;
- **`⬅️ К кандидатам`** remains functional;
- missing chart or invalid navigation data does not break the text detail card.

## Sequencing relative to Geometry

Authoritative owner order:

```text
RVL-R6 current owner PAPER acceptance
  -> OFR-1 durable diagnostics
  -> OFR-2 CASHCATUSDT emergency-close root cause/fix
  -> OFR-3 Box Robot handoff failure root cause/fix
  -> OFR-3A Robot self-recovery after emergency/reconcile incident
  -> OFR-4 stale/completed Box suppression
  -> OFR-4A post-STOP reversal watch / MARKET re-entry attempt
  -> OFR-5 crossed-grid catch-up contract + implementation
  -> OFR-6 position-card presentation cleanup
  -> OFR-7 TradingView button on position cards
  -> OFR-7A candidate monitoring card chart + TradingView
  -> Geometry resumes at RVL-G2/G3/G4
```

Small independent UX slices (OFR-6/OFR-7) may be implemented together if they
touch the same position-card surface and remain a bounded PR. They still stay
ahead of Geometry under this owner priority.

## Already closed today — do not repeat

- TG-MON-1 fixed in PR #325 and owner-accepted on 2026-09-29.
- RVL-G1 inventory/schema completed in PR #327.
- Owner feedback problem register created in PR #328.
- 2026-09-29 checkpoint/Box late-entry intent documented in PR #329.

