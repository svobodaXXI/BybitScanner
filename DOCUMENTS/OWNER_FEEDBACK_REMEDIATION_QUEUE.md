# Owner Feedback Remediation Queue — 2026-09-29

Status: ACTIVE / OWNER-PRIORITIZED  
Scope: today's real owner feedback, acceptance findings and blockers that must be handled **before Geometry implementation resumes**.

This queue sits after the current RVL-R6 owner PAPER acceptance and before
RVL-G2/G3/G4 production Geometry work. RVL-G1 inventory remains complete and is
not repeated.

## Priority order

### OFR-1 — Durable Robot failure diagnostics
**Priority:** P0  
**Status:** IMPLEMENTED / NEXT REAL READBACK PENDING

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

Discovery after completed G6 (2026-09-30):
- APRUSDT produced the owner warning, but no durable incident directory/file;
- code inspection found the exact observability gap: the dedicated Ikigai Box
  `_prepare_owner_robot_handle(...)` path catches planner/handle exceptions
  locally and only prints `[ROBOT CANDIDATE ERROR]`; it bypassed
  `record_robot_incident(...)`, unlike the common Wedge/L-shape handoff path;
- therefore APRUSDT could never produce the expected durable OFR-1 candidate
  incident on runtime commit `adfb50b`; the missing file is explained by code,
  not by an unknown filesystem location.
- bounded fix: persist the Box planner failure through the existing sanitized
  incident sink with stage `box_plan_preparation` and reason
  `BOX_PLAN_PREPARATION_EXCEPTION`, without changing delivery/admission logic.
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

Implementation evidence already present on main:
- `robot_failure_diagnostics.py` provides bounded sanitized JSON incident records
  with fail-open diagnostic persistence and bounded retention;
- candidate handoff failures persist normalized evidence from
  `pattern_robot_integration.py` (including persistence exception / missing id);
- initial-protection emergency close persists
  `INITIAL_PROTECTION_FAILURE` from `RobotBreakoutMonitor`;
- market-data continuity emergency close persists
  `MARKET_DATA_CONTINUITY_LOST` and deciding facts from `PaperRuntime`;
- focused tests cover sanitization/retention/write failure, initial protection
  incident persistence, and PAPER acceptance continuity-loss incident persistence.

Relevant implementation commits already in main:
- `ce923729` — bounded Robot incident diagnostics;
- `d6ea8c8c` — candidate handoff failure persistence;
- `1cd3a8ab` — emergency-close deciding facts;
- `140ff5a3` + `2351b302` — initial protection incident + runtime wiring.

Remaining OFR-1 gate:
- harvest the next real incident from the owner's active runtime after G6
  completes (APRUSDT candidate failure is the first expected candidate) and
  confirm the durable record is practically sufficient for OFR-3 diagnosis.
- do not restart/interrupt G6 just to perform that read.

Acceptance:
- next candidate-preparation failure can be investigated without scrolling stdout;
- next emergency close reports the exact reason deterministically.

### OFR-2 — CASHCATUSDT emergency-close root cause and recurrence fix
**Priority:** P0  
**Status:** ROOT CLASS PROVEN / PRIMARY REASON HISTORICALLY UNRECOVERABLE

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

2026-09-30 evidence result:
- authoritative `C:\BybitScanner\paper_runtime.sqlite3` proves the CASHCATUSDT
  trade closed through `paper_protection_obligations.winning_leg = EMERGENCY_CLOSE`;
- the durable event id is `CASHCATUSDT:rest-recovery:<sequence>:<update_id>`,
  which is emitted only by `RobotProtectionCoverageManager` active recovery of
  a symbol already marked unhealthy for protection continuity;
- the recovery snapshot observed bid/ask near 0.17502/0.17509 while STOP was
  0.17755 and TAKE 0.16384, so the close was not an ordinary STOP/TAKE crossing;
- exhaustive text-log search across all local `C:\BybitScanner*` trees found no
  surviving continuity reason. The historical primary trigger among
  `ingress_overflow`, `websocket_disconnect:*`, `event_identity_mismatch`,
  `admission_failed`, or `subscribe_failed` is therefore not recoverable;
- current durable protection incident diagnostics record the broad reason
  `MARKET_DATA_CONTINUITY_LOST` but omitted the specific `reason` passed into
  `recover_robot_protection_continuity_loss(...)`; this is the remaining
  observability gap. The bounded fix is to persist sanitized `continuity_reason`
  in incident facts without changing fail-closed behavior.

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
**Status:** IMPLEMENTED / OWNER REAL-RUNTIME REACCEPTANCE PENDING

Owner evidence 2026-09-29:
- after CASHCATUSDT was closed by `EMERGENCY_CLOSE`, a later owner action was
  rejected with:
  `Робот: отклонено — Робот не готов к приёму новых сделок`;
- status shown to the owner:
  `Запущен / Нужна сверка`;
- no evidence was seen that Robot automatically returned to READY after the
  emergency close/reconciliation condition cleared.

Repository reconciliation 2026-09-30:
- production commit `8a66daaf15ad2563ac85480d8357a4238977d8a1` already implemented
  evidence-based self-recovery after a transient protection continuity close;
- `recover_robot_protection_continuity_loss(...)` records the prior Robot state,
  performs the emergency-close/recovery path, runs canonical `robot_reconcile()`,
  preserves an intentional PAUSE, and resumes to `READY` only when the prior
  state was `READY` and reconciliation succeeds;
- a pre-existing unrelated `RECONCILIATION_REQUIRED` fence is deliberately not
  auto-cleared;
- focused deterministic PAPER coverage now explicitly asserts
  `EMERGENCY_CLOSE -> authoritative reconciliation -> ROBOT_RUNNING/READY` and
  `robot_admission_ready() == True`.

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

Additional owner-frozen visual case — 2026-09-30:
- `SOMIUSDT 5m` LONG Ikigai Box, owner screenshot captioned approximately
  `+1.18%`;
- the displayed 5m Box had already completed its actionable move upward: price
  had progressed beyond the common frozen TAKE area and continued into the
  upper extension of the old formation;
- the owner then observed a **new, separate 1m Ikigai Box** forming on the same
  symbol;
- therefore lifecycle ownership must be timeframe/setup-specific: the completed
  5m Box becomes stale for fresh delivery/admission, while the later 1m Box is
  evaluated independently from its own frozen anchors/plan;
- this case is retained as a future regression/evidence example for OFR-4 and
  must not be collapsed into dedup suppression of the new 1m setup.

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
**Status:** CLOSED — PR #337 merged as `8b3dc4ead6443ac39ddc8d737d115fac5be68319`

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
**Status:** CLOSED — PR #337 merged as `8b3dc4ead6443ac39ddc8d737d115fac5be68319`

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

## Sequencing relative to Geometry

Authoritative owner order:

```text
RVL-R6 current owner PAPER acceptance
  -> OFR-1 durable diagnostics
  -> OFR-2 CASHCATUSDT emergency-close root cause/fix
  -> OFR-3 Box Robot handoff failure root cause/fix
  -> OFR-3A Robot self-recovery after emergency/reconcile incident
  -> OFR-4 stale/completed Box suppression
  -> OFR-5 crossed-grid catch-up contract + implementation
  -> OFR-6 position-card presentation cleanup
  -> OFR-7 TradingView button on position cards
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
- OFR-6/OFR-7 position-card UX completed in PR #337; Robot PAPER acceptance run #316 passed.

