# Owner Feedback Remediation Queue — 2026-09-29

Status: ACTIVE / OWNER-PRIORITIZED  
Scope: today's real owner feedback, acceptance findings and blockers that must be handled **before Geometry implementation resumes**.

This queue sits after the current RVL-R6 owner PAPER acceptance and before
RVL-G2/G3/G4 production Geometry work. RVL-G1 inventory remains complete and is
not repeated.

## Priority order

### OFR-1 — Durable Robot failure diagnostics
**Priority:** P0  
**Status:** OPEN

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

Acceptance:
- next candidate-preparation failure can be investigated without scrolling stdout;
- next emergency close reports the exact reason deterministically.

### OFR-2 — CASHCATUSDT emergency-close root cause and recurrence fix
**Priority:** P0  
**Status:** OPEN / evidence investigation

Owner evidence:
- CASHCATUSDT Rising Wedge SHORT;
- average entry 0.176958;
- STOP 0.17755;
- emergency exit 0.175125;
- exit therefore occurred well before the ordinary STOP level;
- trade closed profitably but for a safety reason, not by strategy TAKE/STOP.

Current protection policy can emergency-close when STOP is unproven and one of
these conditions occurs:
- market data is not authoritative;
- intended STOP is considered crossed;
- 5-second protection deadline expires.

The current top-level logs do not identify which condition actually fired.

Required work:
1. query the authoritative PAPER SQLite rows for CASHCATUSDT/trade/protection/
   obligations/commands/executions before guessing;
2. determine the exact trigger and whether network interruption was involved;
3. if behavior was correct fail-closed, improve durable reason observability and
   owner-facing classification;
4. if a false protection failure/reconcile race is proven, freeze a replay and
   fix only that class;
5. preserve STOP-first fail-closed safety. Do not lengthen/remove the protection
   deadline merely to prevent emergency exits.

Acceptance:
- exact root cause established from durable evidence or next deterministic
  reproduction;
- recurrence either proven correct safety behavior or fixed with focused replay.

### OFR-3 — Robot candidate handoff failures on valid Box cards
**Priority:** P0  
**Status:** OPEN

Cases:
`B2USDT`, `BANKUSDT`, `BNBUSDT`, `BNCUSDT` 5m.

Required work after OFR-1:
- recover/classify the exact planner/persistence/admission failure from durable
  diagnostics or deterministic reproduction;
- keep ordinary Scanner signal delivery independent;
- never show Robot button unless durable candidate creation succeeded;
- fix the common root cause if one exists; no per-symbol exceptions.

Acceptance:
- representative failing class creates a valid durable Robot candidate or is
  rejected with an explicit, correct, durable reason.

### OFR-3A — Robot does not self-recover after protection/reconcile incident
**Priority:** P0  
**Status:** OPEN / owner-observed recovery blocker

Owner evidence 2026-09-29:
- after CASHCATUSDT was closed by `EMERGENCY_CLOSE`, a later owner action was
  rejected with:
  `Робот: отклонено — Робот не готов к приёму новых сделок`;
- status shown to the owner:
  `Запущен / Нужна сверка`;
- no evidence was seen that Robot automatically returned to READY after the
  emergency close/reconciliation condition cleared.

Interpretation:
- this is a separate recovery-liveness problem from the original emergency-close
  trigger;
- do not assume an internet lag caused the emergency close or the stuck
  reconciliation state until durable evidence proves it;
- a safety-triggered emergency close may be correct, but normal PAPER operation
  must not remain indefinitely blocked after the authoritative state is again
  provably consistent.

Required work:
1. inspect durable runtime/reconciliation/protection state after the
   CASHCATUSDT emergency close;
2. determine exactly which invariant keeps `recovery_status` in
   `RECONCILIATION_REQUIRED`;
3. prove whether the canonical reconciler is expected to clear that condition
   automatically and, if so, why it did not;
4. if automatic recovery is intentionally unsupported for this state, define the
   missing normal-flow transition instead of requiring ad-hoc owner repair;
5. preserve fail-closed admission while recovery is genuinely unresolved;
6. add deterministic replay/coverage for
   `emergency close -> authoritative flat/consistent -> Robot READY` if that
   transition is the intended contract.

Acceptance:
- after a correct emergency close and successful authoritative reconciliation,
  Robot returns to READY without owner crisis-repair;
- if recovery cannot be proven safe, Robot remains closed with one explicit
  durable blocker/reason rather than an opaque permanent "Нужна сверка".

### OFR-4 — Box signal lifecycle: suppress already-completed setups
**Priority:** P0/P1  
**Status:** OPEN strategy/runtime correctness

Owner example:
- `1INCHUSDT 5m` Ikigai Box arrived after price had already travelled far
  enough that the approved Box strategy would have realized the common TAKE.

Important strategy fact:
- Box TAKE is not F(1.0) itself;
- the approved common TAKE is 90% of the path from F(1.618) toward F(1.0);
- therefore a setup is already economically completed once price crosses the
  frozen TAKE, even if F(1.0) was only nearly touched.

Required rule:
- before owner delivery and before Robot admission, inspect source-time price
  history after the actionable entry phase;
- LONG: if a closed/authoritative candle high has already reached/crossed frozen
  TAKE, the old setup is completed/stale and must not be sent as a new active
  signal/candidate;
- SHORT: mirror with candle low <= frozen TAKE;
- preserve historical/review evidence separately; suppress only new actionable
  delivery/admission;
- do not use literal F(1.0) touch as the completion test.

Acceptance:
- recovered 1INCHUSDT case no longer appears as a fresh actionable Box after its
  frozen TAKE was already achievable;
- valid still-actionable Box cases remain deliverable.

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
   - exact machine definition remains pending the owner's next description.

### Attempt budget
- maximum **3 entry attempts per original signal**;
- an attempt is consumed when a valid reversal confirmation closes and the
  candidate reaches the MARKET-entry decision gate;
- a confirmed attempt that is rejected by the risk gate **still consumes one
  attempt**;
- after attempt 3, no further re-entry attempt is permitted for that signal.

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
  rejected by risk/RR/protection still consumes one of the three attempts and
  creates no order;
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
- confirmed but risk-rejected attempts increment the same 3-attempt budget;
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

