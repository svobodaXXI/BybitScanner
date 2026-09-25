# Ikigai Box — two-impulse Fibonacci reversal (user-defined PAPER strategy)

Status: **observational geometry/opt-in Scanner WATCH, pure first-grid planner and BOX_PLAN_ONLY persistence implemented; planner-to-persistence adapter implemented (not wired to Scanner); PAPER Robot order execution BLOCKED / NOT implemented**.
Scope: Scanner recognition, Telegram observation charts, and later separately
authorized PAPER Robot execution. This is **not** the
ordinary horizontal-range breakout/rectangle pattern. The 2026-09-20 user screenshot and
explicit trading decisions in the current conversation take precedence over the obsolete
`DOCUMENTS/BACKLOG.md` G5 "horizontal range / breakout" text.

## Completed implementation and no-repeat checkpoint (2026-09-24)

- PR #215: pure PAPER first-grid planner; merged into main.
- PR #218: immutable, non-executable `BOX_PLAN_ONLY` SQLite persistence; merged into main. This does **not** authorize opening or migrating a running Robot database.
- PR #219: planner-to-persistence adapter (`terminal/application/ikigai_box_plan_persistence.py`); merged as `a155433e0323e2cf11edcdbc05c7c23a22851c94`. Protected task `20260924T164048Z-e41a91ef225c`: PASS; focused adapter test and protected delta checks PASS, blockers NONE.
- PR #220: pure fixed-price Box STOP terms (`robot_protection.py::prepare_box_stop_terms`) and targeted LONG/SHORT tests; merged as `da52f7c6a05c624d3a6ca7d435ea67db42973486`. Protected task `20260924T172017Z-3553707ea8bf`: PASS; focused protection test and protected delta checks PASS, blockers NONE.
- The PC worktree `C:\\BybitScanner-box` was fast-forwarded to `da52f7c`. Earlier safety stashes were preserved; do not reapply them over already merged changes.

**Do not repeat completed work.** Do not recreate these adapters, STOP-term functions, PRs, specifications or tests; do not repeat their protected verification, re-audit already resolved design choices, restore the backup stashes, or request another local sync of these merged commits. Reopen a completed item only if a concrete new defect, changed dependency/code, or conflicting evidence makes it relevant; identify that trigger and verify only the affected delta.

**Open execution boundary:** `BOX_PLAN_ONLY` remains non-executable. The ownership/proof storage slice below is implemented separately; Box admission, fill routing, durable execution lifecycle, protective STOP/TAKE submission and execution recovery have **not** been connected or accepted. `PaperStopMutationRequest` carries a trigger price, not an explicit quantity: inspect whether existing full-position PAPER STOP tracks authoritative position size before adding quantity synchronization. Reuse the existing protection engine where valid; do not wire Box into the Wedge breakout/retest admission monitor or silently relax its execution gate. Resolve the one actual remaining execution gap with the smallest code slice and one scoped verification; no redundant plans, documentation cycles, or Scanner/Robot launches.

### Bounded ownership and remaining-position proof (local implementation, 2026-09-24)

- `SQLiteStore.begin_box_attempt_ownership` records an immutable first-attempt,
  PAPER/linear FLAT baseline: actual position version/time and existing journal
  count/SHA-256. A missing, unsynced or non-flat projection, nonzero journal net,
  or journal evidence beyond the baseline time rejects initialization.
- `reserve_box_order_identity` binds an exact account/order ID to the frozen
  candidate, ENTRY/EXIT role and grid slot **before** order submission or fill
  ingestion. Repeating the same binding is idempotent; conflicting owners/slots
  and retrospective adoption of existing orders/commands/executions reject.
  ENTRY slots 1..4 and EXIT slots 0..4 support the first grid only (0 denotes an
  aggregate exit). One immutable identity per role/slot is a limit of this slice,
  not a new trading rule. Replenishment identities and attempt 2 remain pending.
- Schema **22 -> 23** adds `box_attempt_ownership` and `box_order_ownership`,
  with foreign keys, uniqueness and update/delete rejection. It does not rewrite
  `BOX_PLAN_ONLY`, Robot trade entry attestations or the existing execution journal.
  Migration is transactional; schema-22 binaries cannot open schema 23, and
  downgrade is unsupported. Runtime database migration is not authorized here.
- `prove_box_owned_position` reads ownership, the existing deduplicated
  `executions` journal and the PAPER position projection in one transaction.
  Remaining quantity is owned entry fills minus owned exit fills, reconciled
  with actual side, quantity, average entry and projection version. Each fill
  must belong to the exact attempt/order/symbol/category. Foreign executions
  (including balanced mutations), missing/late evidence, unexplained projection
  writes, ambiguous equal-timestamp chronology, wrong directions, over-exits
  and frozen grid-part overfills fail closed. No second journal is created.
- Proof is read-only and always `execution_authorized=False`. Existing journal
  duplicate handling is reused; restart reloads the same baseline and bindings,
  never authorizes execution. Wedge execution and original `entry_quantity` /
  `entry_position_version` attestations are unchanged.
- Scoped verification target: `tests/test_box_order_ownership.py`, invoked by
  protected task finish; only isolated temporary databases. Prior PR #215/#218/
  #219/#220 evidence is reused, not rerun. Known verification compatibility
  blocker outside this transaction: `tests/test_box_plan_persistence.py` still
  constructs schema 21 by slicing the latest SQL tail and expects schema 22;
  that fixture/assertion requires a separately protected update for schema 23.
- Next dependent implementation: connect these reserved ownership identities
  and proven remaining quantity to the separately authorized Box lifecycle /
  existing protection path, preserving atomic order identity at submission.
  This slice creates no orders, enables no admission and wires no runtime
  protection. PAPER execution remains blocked; common TAKE, fixed STOP,
  replenishment, risk and attempt rules are unchanged.

## Implementation course correction — mature execution engines (2026-09-25)

The next implementation order is intentionally tightened to avoid building an
entry path before restart/partial-fill safety exists.

External reference patterns reviewed:
- QuantConnect LEAN: pre-check a set of order requests before submission;
  track durable order identities/tickets and drive lifecycle from asynchronous
  order events, including partial fills; contingent/bracket/OCO/OUO sets keep
  related entry/exit orders coordinated.
- Hummingbot: reconcile persisted active orders and recover positions before
  executors start after restart/crash.
- Freqtrade: persist the trade lifecycle and attach protection immediately
  after confirmed entry rather than treating STOP as a later independent step.

Applied to BybitScanner, without importing their architectures wholesale:

1. **Keep the completed atomicity work.** Stable Box order IDs, immutable
   ownership, one execution journal, atomic owned LIMIT persistence and
   all-or-nothing first-grid persistence are the correct foundation.
2. **Finish the deterministic first-grid spec adapter.** It remains pure and
   non-executing; replay/restart must derive the same four identities.
3. **Before any runtime entry activation, add one Box lifecycle/recovery
   coordinator, not more persistence layers.** It must derive a fail-closed
   state from the existing frozen plan, ownership rows, active PAPER LIMITs,
   execution journal, authoritative position projection and protection
   evidence. At minimum it must distinguish: no entry submitted; complete
   working grid while FLAT; partial/full owned exposure; protected exposure;
   completed FLAT; and inconsistent/foreign evidence requiring reconciliation.
4. **Reuse the existing full-position PAPER protection path.** It already
   follows authoritative position quantity, so do not add a Box-specific STOP
   quantity synchronizer. On the first proven owned fill, protection must become
   the next required lifecycle action before any new top-up is considered safe.
   Further partial fills reuse the same full-position protection semantics.
5. **Reuse the existing durable protection obligation/recovery mechanism.**
   Do not create a second Box execution journal, second matching engine, second
   STOP engine or generalized message bus. Box-specific work should only bridge
   candidate/order ownership into those existing mechanisms.
6. **Startup/restart reconciliation precedes execution.** A Box attempt with
   persisted orders/exposure must be reconciled before the Robot may create new
   Box entry orders. Unknown, foreign or contradictory evidence fails closed.
7. **Only after recovery + first-fill protection are proven** may the explicit
   Box execution gate be connected to the existing Robot/PAPER runtime. That
   activation is a separate step and must not be smuggled into planner,
   persistence or adapter work.

Optimized bounded implementation sequence:
- A. deterministic four-order spec adapter (current non-executing slice);
- B. pure/read-only Box lifecycle classification and restart reconciliation;
- C. bridge first confirmed owned fill to existing durable Robot
  trade/protection evidence, with STOP/TAKE recovery and fail-closed behavior;
- D. one execution coordinator that performs preflight -> ownership baseline ->
  atomic four-order grid -> event-driven fill/protection handling;
- E. only then enable the separately authorized PAPER Box admission/runtime
  path and perform PAPER acceptance.

Explicitly dropped as unnecessary:
- Box-specific STOP quantity synchronization;
- a second fill/execution journal;
- separate matching/protection engines;
- per-order ad-hoc retry IDs;
- infrastructure such as a message bus merely to coordinate this first grid.

This ordering is an engineering-safety optimization, not a strategy/economic
change. Grid geometry, TAKE/STOP prices, risk policy, attempt rules and
execution authorization remain governed by the existing owner-approved
strategy decisions.

## 1. Source references and status

- `training/reference_patterns/HEIUSDT/post_pump_two_drop_fib_1618_1h/annotation.json`:
  first downward impulse, consolidation, second downward impulse to extension 1.618,
  LONG reversal and target 1.0. Recorded historical levels ~0.1436 (1.0) and ~0.12235
  (1.618). The source's description of *dragging* the Fibonacci tool must not replace the
  explicit numeric-level orientation below.
- `training/reference_patterns/AEONUSDT/ikigai_box_15m/annotation.json` and
  `outcome_01.json`: a bearish wedge breakdown, two-drop setup and subsequent recovery;
  price can exceed 1.618 before bottoming. Observational, not a universal trigger.
- `training/reference_patterns/VELVETUSDT/ikigai_boxes/annotation.json`: recorded
  nested examples; moderate overshoot of 1.618 alone did not invalidate the example.
- `training/reference_patterns/CHIPUSDT/multitimeframe_confluence/annotation.json`:
  recorded 5m Ikigai Box reversal and separate 1m triangle/L-shape continuation.
- The user-provided 2026-09-20 screenshot gives the *mirrored SHORT example*: impulse 1
  UP (start marked 2, peak marked 1), intervening consolidation, second UP impulse
  through the 1.618 region toward 2.618, then declining price. Do not mistake the
  2.618 price extension for the first-impulse endpoint.
- `DOCUMENTS/TRADING_STRATEGY_SPEC.md` §6/H-011 describes a **separate**
  post-impulse mirror-range research hypothesis. Its statement that 1.618 is not
  an independent trigger for that *hypothesis* must not silently override the
  user-defined Ikigai Box advance-limit entry plan. Neither constitutes evidence
  of profitability; actual PAPER fills, stop risk and execution costs require validation.

## RPLUSDT 5m — revised first-impulse anchor interpretation (owner correction, 2026-09-23)

The owner's TradingView drawing of RPLUSDT 5m is a **reference for an
alternative first-leg A/B selection** to the Scanner's Telegram Box chart.
The owner marks the rising first-leg Fibonacci approximately F(0)=1.979,
F(1)=1.998 and its extension F(2.618)≈2.029, around which the later rally
visibly reacts. These are visually read, approximate chart levels, **not**
verified source-time prices or proof of a profitable trade. The older
Scanner-proposed first-leg anchor/extent must not be considered correct just
because it yielded a structurally admissible Box.

**This observation invalidates an overly literal application of the earlier
"first impulse = uninterrupted, essentially same-colour bar run until the
first substantial opposite candle" rule as the universal anchor selector.**
Candle colour and absence of a large intraleg zigzag remain useful evidence
for detecting a genuinely directional move, but must not by themselves fix
A/B or exclude the owner's wider local swing/episode visible in RPLUSDT.
Choose A at the local reversal extreme that starts the relevant first
market leg and B at its actual terminal extremum before the independent
consolidation; inspect intermediate confirmed swings, directional progress
and episode boundaries using **only candles available at the original
historical decision time**. The following consolidation is independent and
cannot be appended to the first impulse simply to make the Fibonacci
extension fit later prices. The later reaction around 2.618 is a diagnostic
cross-check, NOT an admissible retrospective anchor-selection criterion,
confirmation of an entry, or permission to overfit this one ticker.

**Specification precedence:** this RPLUSDT correction supersedes the prior
CPUSDT single-colour/first-opposite-candle wording *where it would force an
anchor pair inconsistent with the demonstrated larger directional episode*.
Keep CPUSDT as a counterexample of wrongly absorbing sideways movement;
resolve both examples with a common reproducible first-leg construction
rule rather than choosing one screenshot as a universal threshold. Before
code changes, recover source-time OHLC for RPLUSDT and CPUSDT, compare
Scanner/owner A/B and competing local episodes, and identify which earlier
construction decision diverges. Preserve frozen A/B once a setup was
emitted, separate historical validity from current admission, and do not
modify Robot trade execution or Fibonacci arithmetic under this geometry
correction. The owning task is the existing Box stage in BACKLOG; user
visual acceptance remains a complete manual all-symbol Telegram pass only.

## Owner clarification: first-impulse reversal, candle colour and consolidation (2026-09-23)

For CPUSDT 5m and both directions generally, the first impulse A starts at
the **actual local reversal extreme**, not a later convenient candle. It is
an initially directional, predominantly single-colour candle sequence: green
for UP and red for DOWN. Small opposite-colour candles are allowed only while
they do not create zigzag price action or a material countertrend swing. Do
not apply an absolute "first opposite colour ends the impulse" rule. The
first substantial opposite-direction/zigzag move terminates the initial leg;
B must remain at the last valid impulse-direction candle/extremum, before the
independent consolidation. After B, consolidation may alternate colours in
any order and must never be merged into impulse 1 or used to relocate A/B.
Apply to upward and downward cases and both CONFIRMED and WATCH at initial
candidate construction, using decision-time closed candles. "Small" and
"zigzag" need reproducible source-time criteria validated against actual
reference windows before coding; do not silently invent a numeric threshold.
This rule supersedes older first-leg candle-colour/wick exceptions insofar
as they allow materially zigzag/mixed first impulses or consolidation candles
to be included in A→B. It does not change Fibonacci arithmetic, second-leg
rules, risk or Robot trading authorization. Implementation and full owner
Telegram acceptance remain queued under `DOCUMENTS/BACKLOG.md`.

## 2. Structure, anchors and Fibonacci math

**SHORT / upward mirror:**
1. Identify the beginning `A` (lowest valid origin of first UP impulse) and its
   ending peak `B` (highest valid terminal extremum before consolidation), using
   only evidence available at the detection candle. Store both exact candle indices,
   timestamps and prices; do not substitute a shelf extremum or later second-impulse high.
2. Confirm consolidation/box between impulse 1 and impulse 2. A horizontal range
   alone, without the ordered two-impulse structure, is not this pattern.
3. Detect an upward second impulse approaching the calculated 1.618 extension.
   Anticipatory SHORT entry grid is around 1.618; if the first trade is confirmed
   stopped and price continues, 2.618 is the one allowed secondary entry area.

**LONG / downward mirror:** `A` is the beginning HIGH of the first DOWN impulse
and `B` is its ending LOW before consolidation; the second impulse is DOWN, and
the entries near 1.618/2.618 are LONG. The first impulse and second impulse have
the **same** direction. Do not reinterpret the first leg as a preceding opposite
trend or replace the two-impulse sequence with a generic rectangle.

**First DOWN impulse / box boundary (FLOCK 5m acceptance, 2026-09-20):**
A and B are the wick extremes of the first impulse; each may belong to an
adjacent green boundary candle, provided all candle bodies strictly between
A and B form one uninterrupted bearish (red) run. A green or doji candle
*inside* that red core splits the run. A/B are frozen independently of later
box wicks or the second impulse; this narrower red-core rule currently applies
to DOWN impulses only, without silently changing the established UP detector.

A consolidation box may briefly wick **past B** before the second impulse
(for LONG, below B; for SHORT, above B). That wick does not redefine B.
The ordinary full box range remains limited to 55% of the A/B impulse span.
As a bounded alternative when full range exceeds 55%, retracement measured
*from B in the opposite direction* must remain <=55% of the span, and the
overshoot past B in the impulse direction must remain <=12% of the span,
subject to the existing impulse-specific retracement gates. This is a
geometry/WATCH allowance only, **not** proof of a valid entry or permission
to place an order. FLOCK's observed 5m example had 54.89% retracement and
5.33% overshoot; no threshold was increased to accommodate it.

**Numerical convention, independent of the charting tool's click/drag direction:**

`F(r) = A_price + r * (B_price - A_price)`.

`F(0)=A_price` (first-impulse origin), `F(1)=B_price` (first-impulse terminal
extremum), `F(1.618)` and `F(2.618)` extend **beyond B in the same direction as
impulse 1**. For SHORT, `F(2.618) > F(1.618) > F(1)`; for LONG, inequalities
reverse. Freeze the two original anchors once the setup is emitted: no hindsight
re-anchoring from impulse 2 or later reversal candles.

The Telegram signal chart must show the entire first impulse, consolidation,
second impulse so far, exact A/B markers, Fibonacci 0/1/1.618/2.618 price lines,
both candidate entry zones and the tentative 1.0 target. Plot only information
known at signal time; label entry/STOP/TP as planned rather than filled or
guaranteed. This is a *different* Fibonacci convention and trading lifecycle from
the separate L-shape impulse-retracement preview.

## Owner strategy amendment — advance 75% entry, slice TP and re-arm (2026-09-23; PAPER DESIGN ONLY)

**Reference:** HAEDALUSDT 5m owner-supplied Telegram Box chart. The screenshot
suggests that a wick may touch an advance limit and rebound in one candle;
it does **not** prove exchange-order fill, intra-candle event ordering,
realized profit or that an executable TP could have filled. Verify on
source-time lower-resolution/trade-level evidence before claiming such results.

**First 1.618-area grid, owner intent:** the first of four advance LIMITs,
each sized at 1/4 working volume (РО), is at 75% of the distance from frozen
F(1.0) toward frozen F(1.618):
`P1 = F(1.0) + 0.75 * (F(1.618) - F(1.0))`.
For a DOWN first impulse this is a BUY/LONG limit below F(1.0); for an UP
first impulse it is a SELL/SHORT limit above F(1.0). Place it as an advance
resting order before the second impulse touches it, subject to ordinary
ownership, sizing and protection gates. The other three LIMITs, each 1/4 РО,
are evenly spaced further **in the impulse direction**, with the fourth
strictly past F(1.618), retaining the original beyond-1.618 requirement.
**Owner-approved first-attempt grid (2026-09-24; PAPER DESIGN ONLY):**
Let `D = F(1.618) - F(1.0)` be a signed price displacement (negative for
LONG, positive for SHORT). Freeze these four equal-quantity entry levels:
`P1=F(1.0)+0.75D`, `P2=F(1.0)+0.85D`,
`P3=F(1.0)+0.95D`, `P4=F(1.0)+1.05D`.
All adjacent LIMIT gaps are `abs(D)/10`; F(1.618) lies exactly halfway
between P3 and P4 **before tick rounding**. Each LIMIT is 1/4 working
volume; the four together are limited to one working volume. Quantize
to instrument tick/quantity steps and reject an unrepresentable, unequal,
or invalid grid rather than shifting anchors or silently changing spacing.

**Owner-approved common TAKE for the first attempt:** `TP=F(1.618)
+0.90*(F(1.0)-F(1.618)) = F(1.0)+0.10D`.
This is **90% of the return from F(1.618) toward F(1.0)**, NOT 90% from
P1. Every TAKE LIMIT has the same frozen price, but each reduce-only
TAKE quantity may cover only its own confirmed filled and still-open
slice. Apply tick rounding toward the entry side, then verify net profit
after applicable fees for every actual slice, including P1. The common
TAKE is a plan, never evidence of execution or a guaranteed fill.

For a STOP-terminated second attempt, use the same four-order, equal-interval
layout around F(2.618), with its final order strictly beyond F(2.618) in
the first impulse's direction. The first-attempt P4 is fixed by the formula above. The second attempt's
P4 overshoot and first-order anchor remain **unresolved owner price/risk
decisions**; do not invent them. Each grid totals at most 1 РО, without
simultaneously active attempt grids.

**Owner-confirmed fixed-price grid STOP (2026-09-23; PAPER DESIGN ONLY):**
Before placing any of the four entry LIMITs, calculate the hypothetical
fully-filled, equal-quantity grid average entry from their actual rounded
order prices. Choose one STOP price beyond the fourth entry LIMIT in the
adverse direction (SHORT: above P4; LONG: below P4). Prefer a structural
level when it fits; otherwise cap its distance using the planned full-grid
average entry, the approved common TAKE and fee-aware reward/risk >= 2:1. No fixed
-1.5% fallback. If there is no valid STOP beyond the entire grid meeting
these constraints, do not place that grid; do not move the STOP inside it.

Fix this STOP **price** before any entry is submitted. The same price
protects even the first filled slice and must NOT be moved as later LIMITs
fill. Immediately after the first confirmed entry fill, create/activate protection
for the actual open quantity; adjust only protective **quantity** for later
fills and TAKE closures, never the price. A position-free reduce-only STOP
must not be assumed executable before the first fill. Each confirmed entry
slice gets its own reduce-only TAKE LIMIT for no more than that slice's
remaining open quantity, including partial fills.

**Experimental PAPER STOP policy (owner confirmation, 2026-09-23):**
The precomputed, fixed-price STOP beyond the entire grid is a trial policy;
record the fully filled theoretical RR separately from realized partial-fill
RR, protective-stop hits and fee-inclusive outcomes. Do not tune this STOP
from anecdotal cases or promote it to LIVE without evidence and separate
authorization. This confirmation authorizes bounded PAPER-only development,
NOT runtime entry/order activation. Keep execution fail-closed until grid
endpoint prices, per-slice TAKE pricing, partial-fill exposure budget and
protective-order reservation/ownership are resolved and verified.

**Risk boundary:** the full-grid planned RR >= 2:1 does not imply the same
RR for the first one or two fills. Calculate and expose the worst-case
partial-fill loss and fee-aware RR at this fixed STOP; do not claim per-slice
RR >= 2:1 or treat partial fills as a fully filled average. If the permitted
partial-fill risk, order-reservation or protective-quantity rules cannot
be satisfied, keep Robot execution blocked pending an explicit risk decision.
The earlier proposal to wait for three filled LIMITs before any STOP is
superseded; no filled exposure may remain intentionally unprotected.

**Per-slice exit:** upon any confirmed slice fill (including partial quantity),
protect the actually filled exposure without delay and place a reduce-only
opposite-side TAKE LIMIT at the **same frozen common TAKE price** defined
above, for no more than that slice's confirmed remaining quantity.
The first-attempt TAKE offset is approved; minimum realized/net profit after
entry/exit fees, protective reservation, partial-fill risk budget, and
second-attempt TAKE policy must still be verified before execution.
A bar wick alone never proves fill or
exit; do not assume a pending TP/STOP executed within the same candle from
OHLC alone. Partial fills, reserved close quantity, other protective orders
and live exchange/broker events must be reconciled to prevent over-closure.

**Owner-approved grid replenishment (2026-09-24; execution pending):** after
confirmed profitable partial closure and reconciliation of the actual reduced
position and associated exit obligations, restore only the corresponding released
grid quantity at its original frozen entry price. Restore the farthest closed
entry first: P4 before P3 before P2 before P1, considering only entries with
proven released quantity. This supersedes the earlier P1-only replenishment rule;
it does not create a new grid or increase the allocation from realized profit.
The same frozen common TAKE applies to replenished fills; there are no individual
TAKE prices. No replenishment after STOP or while cancellation, closure, ownership
or available quantity is unresolved. Keep the existing eligibility/completion and
attempt boundaries; unresolved lifecycle details are not permission to execute.

Count confirmed open exposure together with all remaining entry quantities and
pending submissions against the approved four-part grid. Reserve released quantity
once before submitting its replacement; neither partial-fill processing, retries
nor restart may duplicate an entry or exceed its approved part or the total grid.
A cancellation request alone does not release capacity: reconcile terminal order
state and any concurrent fills first. Ambiguity blocks further entry/replenishment.

**Owner-approved STOP termination (2026-09-24; execution pending):** STOP is
strictly beyond P4 in the adverse direction and is placed immediately after the
first confirmed entry fill. Its precomputed price remains fixed for the attempt;
only protected quantity follows authoritative actual position size, including
partial entries and profitable partial closures. On STOP, block further entry and
replenishment, cancel all remaining entry orders of that attempt and close the
actual remaining position. Reconcile fills racing with cancellation; never size
the close from the planned full grid or assume a STOP trigger proves FLAT. Keep
closure/reconciliation outstanding until authoritative position is FLAT and all
remaining entry and exit obligations are settled. These rules do not authorize a
new attempt or change the existing second-attempt conditions.

**Implementation boundary:** this amends the intended first-grid placement
and introduces a proposed slice-exit/replenishment lifecycle; it does not
change the 2.618 second-attempt gate, F(1.0) principal target, current
Scanner/Telegram behavior, running services or live trading. The existing
§3 wording "exact spacing unspecified" and later historical grid notes
remain valid only for still-unresolved parameters; the P1 75% anchor here
supersedes any older first-entry placement. Robot/PAPER wiring is **NOT
AUTHORIZED FOR EXECUTION** until pending price/risk/lifecycle decisions
are resolved and fail-closed implementation has been verified at the
existing later Robot stage in `DOCUMENTS/BACKLOG.md`.

## 3. Entry and position management — user-approved intent, NOT wired to Robot

- **Attempt 1:** four approximately equally spaced price LIMITs in the zone of
  `F(1.618)`, each of size **1/4 РО** (user-defined working order volume),
  together limited to one total РО. The furthest limit extends *past* 1.618
  in the second impulse's direction: **above** 1.618 for SHORT, **below** for
  LONG. The grid is placed *before* the intended reversal; a reversal candle
  is desirable for structural STOP selection but is **not a prerequisite** for
  placing the advance grid when the fallback STOP is available. Exact spacing,
  zone width and anchoring are **not yet specified**; never hard-code a price
  distance or assume all four orders are filled.
- **STOP:** compute and freeze a single price **before** placing the grid,
  using the hypothetical fully filled, equal-quantity average and fee-aware
  RR >= 2:1 to the approved common TAKE. Prefer a valid structural STOP, otherwise the maximum
  ratio-compliant risk distance; in either case it must be beyond P4 (SHORT
  above, LONG below). If those requirements cannot coexist, reject the grid
  instead of placing STOP inside it. Activate the frozen-price STOP upon the
  first confirmed fill and update protective quantity as exposure changes,
  including partial fills and per-slice TAKE closures; never reprice it during
  the same attempt. Explicitly track partial-fill risk, which may have RR
  below 2:1 despite the planned full-grid calculation. Apply the same
  precomputed-price rule separately to any authorized second-attempt grid.
- **Attempt 2 (only after stopped attempt 1):** after a **confirmed STOP close**
  of the first trade, **verified FLAT position**, no unresolved exit/protection
  obligation, and cancellation/terminal state of *all* unfilled limits from
  the first grid, wait for the second impulse's continuation toward `F(2.618)`.
  Only then allow a **new** four-limit grid, each **1/4 РО**, around 2.618,
  with the furthest limit beyond 2.618 in impulse direction. Distribute all
  four orders at equal price intervals; the exact first-order anchor and
  last-order overshoot for this second attempt are still unspecified. Use the same STOP,
  early partial exit and 1.0-target policy. An ambiguous STOP reason, unresolved
  partial position, uncertain ownership or still-active earlier LIMIT blocks
  attempt 2. **At most two sequential attempts per frozen formation**, no
  overlapping grids, doubling, martingale, or averaging the stopped trade.
- **TP:** the common principal target is **F(1.0)**. Start partial profit taking
  *before* that level, then move the remaining position's STOP to fee-aware
  breakeven. Exact partial-exit fraction, trigger price/offset and breakeven
  buffer are **user decisions still pending**: not an execution-ready policy.
  No position size, STOP or TAKE may be fabricated from these placeholders.
- **Potential (planning metric):** measured on the frozen first-impulse
  Fibonacci from the entry reference `F(1.618)` to the common target `F(1.0)`.
  Rising first impulse (SHORT setup): from `F(1.618)` down to `F(1.0)`. Falling
  first impulse (LONG setup): from `F(1.618)` up to `F(1.0)`. Percentage
  potential = `abs(F(1.0) - F(1.618)) / F(1.618) * 100`, reported as a
  magnitude. It is measured from the level, not from actual fills or the
  average entry, and is before fees/slippage. Example: FLOCKUSDT LONG
  `0.062549 -> 0.06533` = approximately +4.45%. It is a display/planning
  figure only and changes no STOP, TAKE, sizing or execution rule.

## 4. Minimal implementation boundary / non-goals

1. Read-only structure detector first: frozen A/B, impulse/box/second-impulse
   index ranges, directional Fibonacci levels, detection-time provenance;
   explicit UNKNOWN for ambiguous anchors. Reject standalone ranges and
   after-the-fact second-impulse rebasing. Conservative named, tunable pattern
   thresholds require focused offline validation against the reference cases.
2. Scanner/Telegram signal integration after deterministic detection and a
   visually checked example, reusing the same frozen geometry. **Do not** label
   a planned limit as placed or pass Box through the Wedge apex-based Robot
   lifecycle or its existing pattern-direction allowlist.
3. PAPER-only four-order entry and two-attempt Robot lifecycle require a
   separate, focused, test-verified implementation and explicit resolution of
   grid placement, available collateral/risk cap, partial fills and multiple
   protective/TP orders, early partial close/BE levels, STOP selection timing,
   restart persistence and fail-closed ownership. No LIVE execution authority.
4. This document records design intent and examples; it does **not** assert
   positive expectancy, completed implementation, actual exchange-side
   protective orders, or readiness to run against the working PAPER database.

## 5. Chart/card trade overlay — presentation only (implemented)

`geometry/ikigai_box_overlay.py` + `geometry/ikigai_box_chart.py` draw a PLANNED
trade overlay on the Ikigai Box chart. Detection, Scanner, Telegram, Robot
admission, order placement and candidate creation are untouched.

- **Fibonacci grid = the terminal tool.** The signal PNG mirrors
  `terminal/frontend/src/chart/drawingModel.ts` and `DrawingOverlay.tsx`:
  levels `0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236`,
  price `first + (second - first) * level` with first = A, second = B (equal to
  the frozen `fibonacci_price`), a translucent band between every ADJACENT pair
  of levels, the terminal's five-colour palette cycled by band index, the
  terminal line colour and `level  price` labels. Only the fill opacity is lifted
  for a white PNG; off-screen levels are clipped as in the terminal.
- Stage label: `BOX_READY` / `BOX_BREAK_OBSERVED` / `CONFIRMED`, plus whether
  `F(1.618)` has been touched by a closed candle after B (through `as_of` only).
- `F(1.618)` not reached: observation only, **no** entry zone, grid or STOP.
- `F(1.618)` reached: four LIMITs, each 1/4 РО, equally spaced. Most of the grid
  (3 of 4) sits on the APPROACH side of 1.618 — it fills before price reaches the
  level — and only the furthest LIMIT is beyond it (for LONG: three above 1.618,
  one below; SHORT is the mirror). This distribution is the user's instruction:
  the terminal Fibonacci tool defines NO limit-order placement rule, so nothing
  about spacing or the split was copied from it.
- STOP: extreme of the latest closed reversal candle (bearish engulfing /
  shooting star for SHORT; bullish engulfing / hammer for LONG) when it
  protects the planned entry and meets net reward/risk >= 2:1; otherwise use
  the maximum fee-aware ratio-compliant STOP distance (LONG below, SHORT above).
  This overlay is illustrative only; actual protection uses confirmed fills.
- Target: `F(1.0)`, with only a text note that partial profit-taking starts
  before it.

Still **not** decided or implemented: the real grid spacing (the drawn step is a
visualisation placeholder, `GRID_STEP_FRACTION`), partial-take trigger/fraction,
fee-aware breakeven stop, attempt 2 at `F(2.618)`, any order execution, and the
Scanner caption text. `build_entry_grid(anchor_level=...)` is reusable for the
2.618 grid but no second-attempt logic exists.

## Owner-approved implementation approach — PAPER Box (2026-09-24)

Reuse the existing Robot durable candidate/store, PAPER execution, ownership,
protection and recovery mechanisms; implement a separate Box lifecycle rather
than treating Box as a wedge breakout/retest or adding a second order system.
This adopts applicable order-management practices from mature trading systems
without adopting their trading strategies or inventing new Box geometry.

1. Freeze one first-attempt plan per formation: frozen source-time A/B and
   Fibonacci levels, four approved equal-gap LIMIT prices (75/85/95/105%),
   quantities of 1/4 working volume, one common TAKE at 10% of the signed
   F(1.0)→F(1.618) displacement, one STOP beyond P4, and durable order IDs.
   Restore that plan after restart; never reconstruct a new one from later
   candles or repeat an already recorded submission.
2. Use the **actual common TAKE** (not F(1.0)) in all fee-aware profit, full-grid
   RR >= 2:1 and STOP calculations. Account for instrument tick/quantity
   rounding and reject a grid whose equal spacing, midpoint, nonzero slice
   size, valid STOP, or positive net slice TAKE profit cannot be represented.
3. Treat planned LIMIT quantities as reservations, not position fills. For each
   broker-confirmed partial/full entry fill, reconcile actual open quantity,
   activate/synchronize the precomputed-price STOP immediately, and create a
   reduce-only TAKE at the common frozen price for no more than that slice's
   confirmed still-open quantity. No unprotected deliberate exposure, phantom
   candle-wick fills, duplicate entry ownership, or close over-reservation.
   On uncertain fills, missing protection, or ambiguous order ownership, fail
   closed and use the existing Robot emergency/reconciliation path.
4. Create/amend/cancel only in response to authoritative order/fill/position
   state transitions, not on every Scanner/Robot loop. On restart reconcile
   persisted entry, protective and TAKE obligations before admitting new risk.
5. Preserve wedge execution and all LIVE behavior. PAPER order activation
   remains blocked until the owner sets an acceptable partial-fill risk budget
   and remaining exit/re-arm and second-attempt policy is resolved, followed
   by focused proof of fills, stop/TAKE synchronization and recovery. The
   already-approved static grid/TAKE arithmetic may be implemented and tested
   now with execution_authorized=False.

Implementation order: (a) align existing PR #215 pure planner/tests with the
approved formulas and actual TAKE-based fee-aware RR; (b) wire a separate
fail-closed Box PAPER lifecycle through existing durable execution; (c) verify
partial fills, protection, close reservations and restart. No new order
infrastructure, broad refactor, unattended full Scanner run, or LIVE enablement.

## Persisted first-attempt plan contract — implemented 2026-09-24

`BOX_PLAN_ONLY` is an immutable, non-executable PAPER record in the existing
`robot_candidates` SQLite table. It is not admission, risk reservation, an order,
or evidence of fills. Scanner wiring and automatic plan calculation are absent.

Identity is canonical `(venue, market, symbol, source timeframe, trade direction,
A candle UTC milliseconds, B candle UTC milliseconds)`, scoped to account `paper`,
pattern `IKIGAI_BOX`, attempt `1`. Venue/market are lowercase, symbol uppercase,
timeframe a canonical positive integer string. Use source candle times, never
moving-window indices. The candidate ID is `box-plan-` plus SHA-256 of canonical
JSON containing identity, account, pattern and attempt. Prices, decision time and
planner version do not create new identities. Equal identity plus equal canonical
snapshot returns the original row unchanged; different content fails with an
identity conflict. Later candles and restart never replace the frozen plan.

Contract v1 snapshot fields: `contract_version`, `planner_version`, `pattern`,
`environment`, `execution_authorized`, `attempt`, `identity`, `decision_time_ms`,
`anchors` (`a_price`, `b_price`), `fibonacci` (`f1`, `f1618`, `f2618`), `inputs`
(`working_quantity`, `tick_size`, `entry_fee_rate`, `target_fee_rate`,
`stop_fee_rate`, `structural_stop`, explicitly null when absent), and `plan`
(the complete existing `IkigaiBoxPaperPlan` result including all four exposures).
Decimal values are finite decimal strings, normalized without float conversion;
canonical JSON is hashed with SHA-256 and verified on reads. Save validates the
storage contract, not trading eligibility or fresh planner arithmetic. The caller
must supply an already computed plan and its frozen source inputs. Unknown risk
budgets are not invented; risk assessment and order identities are outside this
non-executable persistence slice.

State is always `BOX_PLAN_ONLY`, `approved_at_ms=NULL`, `robot_state=NULL`,
`state_revision=0`, `environment=PAPER`, `execution_authorized=false`.
No lifecycle transitions are permitted, including self-updates. SQLite rejects
updates to these rows; ordinary admission rejects both Box handoffs and attempts
to reuse a stored plan ID. Existing APPROVED-only monitoring and APPROVED/OPEN
recovery selection exclude plans. Existing trade creation requires APPROVED.
No approval, broker order, protection obligation or execution recovery is created.

Schema 22 transactionally rebuilds the candidate table from schema 21, preserves
legacy rows and Robot trade foreign keys, allows null approval time only for plans,
and restores foreign-key enforcement after checking integrity. Older databases
continue through the existing migration chain. Rollback preserves schema 21 on
migration failure. Older application binaries cannot use schema 22; downgrade is
not supported. Existing APPROVED/OPEN lifecycle semantics remain unchanged.

Execution remains blocked on the previously recorded partial-fill risk and
exit/re-arm/second-attempt decisions and their separate implementation evidence.
The verified planner's 10 passing tests are reused, not repeated by this slice.

### Completed persistence slice — implementation and verification record

**Implemented locally:** `SQLiteStore.save_box_plan_only()` stores explicitly
supplied snapshots in `robot_candidates`; canonical decimal-string JSON and
SHA-256 verification, deterministic formation identity, immutable reads,
idempotent duplicate handling and conflicting-snapshot rejection are implemented.
Admission rejects Box handoffs and reuse of a persisted plan ID. SQL immutability,
no lifecycle promotion, APPROVED-only monitoring and APPROVED/OPEN recovery
selection keep these records outside execution. This is a completed persistence
slice, not completion of Box-to-Robot trading integration or a publication claim.

**Migration implemented:** schema **21 -> 22**, with transactional table rebuild,
legacy APPROVED/OPEN and Robot trade preservation, foreign-key integrity checking,
and rollback on migration failure. Approval time is nullable only for
`BOX_PLAN_ONLY`. Legacy application binaries cannot open schema 22; downgrade is
not supported. These results concern isolated test databases, not migration or
acceptance of a running production database.

**Verification evidence (reused; no rerun for this documentation update):**

- Existing pure planner: **10 PASS** at `099cfedc`, reused unchanged.
- Focused initial run of `tests.test_box_plan_persistence` and
  `tests.test_robot_admission`: **15 tests; 13 PASS, 2 errors**.
- New rollback test assertions passed, but Windows temporary-file cleanup failed
  because the test left a SQLite connection open. The test was corrected to close
  it explicitly; only that failed test was rerun and **PASS**. Resulting evidence:
  **all 6 new persistence/safety checks and 8 existing admission checks PASS**.
- One existing admission check remains **UNRESOLVED / environment-blocked**:
  `RobotAdmissionGateTests.test_unsupported_pattern_is_rejected_before_sqlite_admission`.
  Its `telegram_review` import raised `ModuleNotFoundError: No module named 'config'`.
  No configuration was created or modified; do not report the entire admission
  module as passing.
- Protected task `20260924T151746Z-648d207de495` finished **PASS**: task-delta and
  inverse proofs, isolated candidate overlay, Python compile, focused new test
  module, scope/index preservation and diff check. The mandatory finish gate
  automatically repeated `test_box_plan_persistence.py`; planner tests were not
  repeated. This receipt covers the implementation slice before this subsequent
  documentation-only update.

**Pending / exact next step:** connect the already verified planner's explicit
result and frozen source inputs to `BOX_PLAN_ONLY` persistence. That adapter is
not implemented yet. Preserve deterministic identity, decimal serialization,
conflict rejection and `execution_authorized=False`; do not automatically derive
new plans from Scanner signals or invent quantities, risk budgets or fees.
Scanner handoff, execution admission and order lifecycle integration remain pending.

**Execution safety boundary:** PAPER order execution remains **BLOCKED**. A saved
plan is not an approved candidate, risk reservation, broker order, fill, or
protection obligation; restart cannot promote it into execution. Previously
unresolved partial-fill risk, exit/re-arm and second-attempt decisions and their
required execution evidence remain unchanged. No Scanner/Robot service, full
acceptance run or real-order operation was started for this slice.

### Approved execution-rule clarification — 2026-09-24 (NOT implemented)

The STOP-termination and grid-replenishment paragraphs above are the current
owner-approved design and supersede older P1-only wording. Immediate first-fill
STOP, fixed STOP price, actual protected quantity, cancellation plus actual-position
closure on STOP, farthest-closed-entry-first replenishment and duplicate/exposure
limits are now specified. The approved common TAKE remains unchanged:
`F(1.0) + 0.10 * (F(1.618) - F(1.0))`, shared by all slices and replacements.
No individual TAKE levels, new risk parameters, cooldowns or attempt rules are
introduced. References to unresolved exit/re-arm decisions elsewhere must not be
read as reopening these newly approved rules; other previously unresolved details
and risk approvals remain pending. PAPER order execution is still BLOCKED.

**Existing Wedge mechanisms inspected for reuse (not Box implementation):**

- `robot_entry_limit.py::_stable_client_action_id` demonstrates deterministic
  action identity; `robot_protection.py::_action_id` and
  `emergency_close_request` preserve identity across protective-close retries.
  Box needs distinct durable per-attempt/per-entry/replenishment identities;
  Wedge's single-entry identifiers are not a four-order ownership model.
- `terminal/application/robot_breakout_monitor.py` uses `cancel_limit` followed
  by `get_paper_limit` and broker-confirmed `filled_quantity`, persists lifecycle
  state, checks competing ownership and escalates ambiguous reconciliation.
  Reuse these execution/state mechanisms; its breakout/retest, repricing and
  partial-completion policies do not define Box replenishment.
- `robot_protection.py::submit_initial_protection` submits STOP before TAKE;
  `protection_recovery`, `submit_emergency_close` and `emergency_close_request`
  provide fail-closed protection recovery and full-close dispatch. Reuse the
  supported command/reconciliation mechanisms, not Wedge structural STOP,
  tightening or TAKE calculations. They do not yet implement Box fixed-price
  quantity synchronization or four-entry STOP cancellation.
- Existing SQLite snapshot hashing, idempotent identity/conflict handling and
  candidate-state revision checks provide persistence/concurrency foundations.
  `BOX_PLAN_ONLY` itself remains immutable and cannot become executable state.

**Smallest next implementation step remains:** connect an explicitly supplied,
already verified planner result and frozen source inputs to
`SQLiteStore.save_box_plan_only()`, with deterministic identity and lossless
Decimal-string serialization. No Scanner wiring or automatic sizing is included.
The execution rules documented here require a later separately scoped Box
lifecycle implementation; this documentation does not enable orders or alter the
completed non-executable persistence slice.

