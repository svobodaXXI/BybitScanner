# Development Validation Loop Optimization Plan

Status: **OWNER-APPROVED PROCESS DIRECTION — 2026-09-27**

Purpose: shorten the path from a real defect to a verified fix, reduce repeated
manual/runtime acceptance cycles, and make every discovered failure reusable as
future regression evidence.

This plan does **not** relax any existing Scanner visual acceptance, PAPER/LIVE
safety, Robot ownership, protection, fail-closed, or owner-manual runtime rules.

## 1. Core operating model

BybitScanner development is split into two developer validation labs:

### Geometry Lab

Use deterministic saved OHLC fixtures to develop Wedge/Triangle/anchor logic.

Each accepted fixture should contain:
- source-time candles used by the detector;
- pattern family / direction;
- expected formation identity;
- expected anchor/pivot locations or explicit acceptable ranges;
- negative cases where no formation should be admitted;
- provenance to the real owner-observed case.

Target location:
`tests/fixtures/geometry_gold/`

The Geometry Lab is a developer regression surface only. It does **not** replace
the owner's mandatory one complete real Scanner pass with ordinary Telegram
delivery across the eligible universe and all integrated patterns.

### Robot Runtime Lab

Use deterministic replay of real runtime incidents instead of repeatedly waiting
for the same failure on live Bybit market data.

Each replay fixture should preserve the minimum evidence needed to reproduce the
failure:
- ordered market-data events;
- symbol and lifecycle role;
- event identity / generation / sequence where relevant;
- runtime commands or state transition that preceded the incident;
- relevant timing/queue metadata;
- expected safety outcome and forbidden outcomes.

Target location:
`tests/fixtures/runtime_replays/`

The current 2026-09-27 protection ingress overflow is the first priority replay:
continuous multi-symbol `ENTRY_PENDING` order-book traffic must reproduce the
real saturation behavior without artificial drain barriers between small batches.

## 2. Incident-to-regression rule

For every repeatable real defect:

1. capture the smallest deterministic fixture that reproduces it;
2. prove RED on current code;
3. implement one bounded fix;
4. prove the exact fixture GREEN;
5. run the minimum relevant broader regression gate once;
6. only then spend owner time on real runtime / full Scanner acceptance.

Do not keep a production incident only as prose/log evidence when the relevant
inputs can reasonably be captured and replayed.

A discovered defect should therefore reduce future diagnostic cost rather than
requiring another manual rediscovery.

## 3. Validation tiers

Use four explicit cost tiers.

### FAST

Pure/unit/property tests. Seconds. Run for the changed behavior.

### REPLAY

Saved real geometry/runtime fixtures. Deterministic. Usually seconds to tens of
seconds. Required when the task fixes a previously observed real incident that
can be replayed.

### PAPER CI

Repository integration/contract checks for the affected Robot/PAPER boundaries.
Run once after the focused checks are green.

### OWNER ACCEPTANCE

Expensive real-world proof only after lower tiers pass.

Scanner visual acceptance remains exactly the existing owner rule:
one complete real eligible-universe Scanner pass, normal Telegram delivery, all
integrated patterns. No replay, local PNG, subset, or single-symbol fixture may
substitute for it.

Robot acceptance remains owner-manual real PAPER proof of the required lifecycle
after replay/CI pass.

## 4. Runtime replay requirements

Do not hide overload with test-only pacing that the real producer does not have.

For queue/ingress incidents:
- preserve continuous producer behavior;
- do not insert owner-drain barriers unless the production path has them;
- preserve per-event FIFO and distinct crossing evidence;
- do not increase queue capacity or coalesce safety evidence merely to make the
  replay pass;
- assert safety invariants as well as throughput outcome.

For the current ingress incident, the replay must distinguish:
- `ENTRY_PENDING` traffic;
- `EXPOSURE` / `OBLIGATION` traffic;
- owner processing rate;
- queue high-watermark / overflow;
- durable fail-closed latch.

## 5. Stateful/property testing

Use property/stateful testing selectively for lifecycle invariants, not as a
replacement for deterministic incident fixtures.

Priority Robot invariants:
- READY is impossible while protection is unhealthy;
- overflow closes admission/fences continuity;
- one symbol never acquires ambiguous Robot ownership;
- repeated reconcile/start/stop cannot duplicate an order or trade identity;
- lifecycle states cannot move backwards through illegal transitions;
- restart cannot silently discard durable ownership/protection evidence.

Priority Geometry invariants:
- historical anchors do not move merely because unrelated later candles are
  appended;
- anchors correspond to admissible pivots;
- forbidden body-boundary violations remain forbidden;
- identical OHLC input is deterministic;
- local geometry should not depend on irrelevant remote history beyond the
  explicitly allowed selection window.

## 6. Feature-freeze rule until the two primary quality gates are healthy

Current product focus is reduced to two bosses:

1. **Robot Stability** — current P0, including the unresolved protection ingress
   overflow.
2. **Geometry Quality** — Wedge/Triangle geometry and anchor fidelity.

Autopilot, secondary UX expansion, new pattern families, and architecture
improvements do not pre-empt these two unless the owner explicitly changes
priority.

Autopilot documentation/code already completed is preserved, not deleted; it is
simply non-blocking/deferred while Robot Stability and Geometry Quality are red.

## 7. Acceptance dashboard / compact report

Prefer one compact generated or textual report over repeated manual inspection.

The report should expose at least:
- Geometry Gold: PASS / FAIL / case count;
- Runtime Replays: PASS / FAIL / fixture count;
- focused PAPER CI: PASS / FAIL;
- owner acceptance: PENDING / PASS with the exact acceptance type.

A simple script/report is sufficient. Do not build a new service/dashboard
platform unless it demonstrably saves owner time.

## 8. Immediate application

### Current Robot P0

The 2026-09-27 runtime evidence is authoritative:
- #293 reduced reconcile from about 9.1 s to about 1.4 s;
- candle-cache owner misses remained zero;
- queue still reached 64/64;
- later `2ZUSDT` became unhealthy with `ingress_overflow`;
- covered symbols were all `ENTRY_PENDING`.

Before another speculative runtime patch, build the first continuous
multi-symbol `ENTRY_PENDING` replay that reproduces saturation without
artificial draining.

### Geometry

When Robot P0 is contained, establish the first compact golden set from known
good/bad Wedge/Triangle/anchor cases. Use it for implementation feedback; retain
the existing full Scanner acceptance as the only owner visual acceptance.

## 9. Definition of Done for this process improvement

The process improvement is considered implemented when:
- fixture directories and minimal harnesses exist;
- the current ingress failure is reproducible by replay;
- at least one real geometry defect is frozen in the geometry golden set;
- changed-behavior work uses FAST -> REPLAY -> PAPER CI -> OWNER ACCEPTANCE as
  applicable;
- project docs/quest state point to this plan;
- no existing safety/acceptance contract was weakened.


## 10. Implementation roadmap and queued work

The process change is implemented as a sequence of small dependent slices. Do
not start later slices merely because they are documented here.

### Phase R — Robot Runtime Lab (current P0)

#### RVL-R1 — Replay contract and minimal runner
**Status:** COMPLETE — PR #296, Robot PAPER acceptance #226 PASS
**Priority:** P0 / completed

**Goal:** create the smallest reusable replay boundary for ordered Robot market
events without creating a second runtime or simulator.

**Deliverables:**
- `tests/fixtures/runtime_replays/`;
- one versioned event-envelope schema containing only the fields actually needed
  by `process_robot_market_event` / protection ingress;
- a deterministic test helper/runner that feeds events into the existing
  `SerializedPaperRuntime` and real Robot/PAPER code;
- explicit support for continuous delivery with no artificial queue-drain call
  inserted between producer bursts;
- metrics/result object sufficient to assert pending/high-watermark/overflow,
  durable continuity latch, processed event order and owner processing stats.

**Non-goals:** no generic exchange simulator, no new production queue, no UI,
no capacity change, no coalescing.

**Done when:** one trivial fixture runs deterministically twice with identical
event order and metrics shape.

**Completion evidence (2026-09-27):**
- `tests/runtime_replay.py` provides the versioned replay loader/runner;
- `tests/fixtures/runtime_replays/smoke_ordered_entry_pending_v1.json` is the first fixture;
- events are enqueued continuously, with only one final completion fence after producer delivery;
- `tests/test_runtime_replay.py` proves FIFO event order and stable metric surface across two runs;
- Robot PAPER acceptance workflow run #226 completed SUCCESS;
- no production runtime behavior changed in this slice.

#### RVL-R2 — Freeze the 2026-09-27 ingress overflow as RED
**Priority:** P0 / immediately after R1

**Goal:** reproduce the current real failure before changing production logic.

**Fixture/model:** five `ENTRY_PENDING` symbols from the observed incident
(`2ZUSDT`, `ARBUSDT`, `ARIAUSDT`, `ARKUSDT`, `CFGUSDT`) with
continuous order-book events and the same serialized owner boundary.

**Requirements:**
- no `owner.call(lambda: None)` or equivalent drain barrier between batches;
- producer cadence must be independent from owner completion;
- preserve distinct FIFO events;
- prove that current main can hit capacity 64 and fail closed;
- prove that the failure marks protection unhealthy and produces the durable
  continuity-loss behavior expected by the real runtime.

If exact raw production deltas are unavailable, use a deterministic
production-shape fixture for the first RED, clearly labelled as such. A future
bounded capture may replace/enrich it; do not block the current P0 on building
general telemetry infrastructure.

**Done when:** current main reliably REDs for the same class of overload without
wall-clock flakiness or sleeps used as correctness assertions.

#### RVL-R3 — Define the ENTRY_PENDING coverage boundary
**Priority:** P0 / architecture micro-slice

**Goal:** establish exactly when a pre-entry candidate starts needing per-book
FIFO protection ingress.

Answer and freeze with focused tests:
- whether `RETEST_DETECTED` without a durable `limit_order_id` needs
  continuous protection coverage at all;
- the exact transition that creates a resting PAPER entry limit;
- how coverage becomes active before any book event capable of filling that
  resting order can be missed;
- what happens for partial fill, cancelled/inactive order, missing order and
  restart/reconcile;
- how multiple approved candidates on one symbol are handled fail-closed.

**Preferred direction to evaluate:** do not subscribe a pre-limit candidate to
high-rate `ENTRY_PENDING` traffic merely because it is `RETEST_DETECTED`.
Coverage should begin at the durable resting-order ownership boundary, while
preserving first-fill evidence.

**Done when:** the lifecycle boundary is encoded in tests and no production
mutation has yet been made beyond any minimal testability seam.

#### RVL-R4 — Implement the smallest ingress fix
**Priority:** P0

**Goal:** make RVL-R2 GREEN by removing unnecessary producer load at the
correct lifecycle boundary, not by masking overload.

**Hard constraints:**
- queue capacity remains 64 unless a separate evidence-backed decision changes it;
- no event coalescing/dropping for covered symbols;
- `EXPOSURE` and `OBLIGATION` protection paths remain distinct FIFO;
- no LIVE changes;
- no second execution/protection engine;
- fail-closed semantics preserved.

**Expected implementation class:** coverage-role selection/subscription timing
around the durable entry-limit lifecycle. Exact code location is chosen only
after RVL-R3 proves the boundary.

**Done when:** focused tests + the exact continuous replay pass, and the fix does
not weaken first-fill/protection continuity.

#### RVL-R5 — Runtime regression pack and focused PAPER CI
**Priority:** P0 gate

Run once after R4:
- current ingress replay;
- disconnect/reconnect barrier replay/tests;
- recovery candle-cache regression;
- duplicate ownership/reconcile idempotency checks relevant to touched code;
- existing Robot PAPER CI gate.

Do not expand this into an unrelated broad campaign.

**Done when:** all applicable lower-tier gates are GREEN and no known runtime
incident fixture remains RED.

#### RVL-R6 — One real owner PAPER acceptance
**Priority:** P0 final gate / owner-manual

Use the canonical desktop runtime path only after R1-R5 are green.

Acceptance evidence:
- new backend process on current main;
- Robot reaches legal READY state;
- protection remains healthy under real multi-symbol traffic;
- no `ingress_overflow`;
- owner candle-cache misses remain zero;
- queue drains under steady operation rather than repeatedly latching 64/64;
- normal reconcile/restart path does not recreate the incident.

This is the only step in Phase R that requires real owner runtime.

**Exit condition for Robot Stability boss:** R6 PASS. Until then the boss remains
open even if CI is green.

### Phase O — Owner feedback remediation (before Geometry resumes)

**Owner-prioritized 2026-09-29.**

Canonical queue:
`DOCUMENTS/OWNER_FEEDBACK_REMEDIATION_QUEUE.md`.

This phase was inserted after the real owner run exposed operational/product
defects that are higher priority than Geometry implementation work. RVL-G1
inventory remains COMPLETE and is not repeated; Geometry implementation resumes
at G2 only after the queued owner-feedback remediation slices are handled.

Ordered tasks:
- OFR-1 durable Robot candidate/protection failure diagnostics;
- OFR-2 CASHCATUSDT emergency-close root cause and recurrence classification/fix;
- OFR-3 B2/BANK/BNB/BNC Box Robot handoff failures;
- OFR-4 already-completed Box suppression using frozen TAKE, not literal F(1.0);
- OFR-5 crossed-grid Box catch-up execution;
- OFR-6 Telegram position-card chart/label/volume cleanup;
- OFR-7 TradingView button under position cards.

Safety:
- do not weaken STOP-first fail-closed protection;
- do not infer network failure without durable evidence;
- do not change geometry merely to solve execution/UX findings;
- LIVE remains prohibited.

### Phase G — Geometry Lab (starts after Phase O owner-feedback remediation)

#### RVL-G1 — Golden fixture schema and inventory
**Status:** COMPLETE — repository inventory/schema map captured 2026-09-29
**Priority:** P1; completed in parallel while RVL-R6 owner acceptance continued

Canonical inventory:
`DOCUMENTS/GEOMETRY_GOLD_INVENTORY.md`.

G1 intentionally did not create duplicate candle fixtures. Existing exact OHLC
is referenced in place; `tests/fixtures/geometry_gold/` is created in G2 only
when the compact manifest/runner is added.


Required case types:
- valid Wedge with expected upper/lower anchors;
- valid Triangle with expected anchors;
- false-positive / no-admissible-pair;
- stale structure / END case;
- locality or historical-anchor stability case.

Inventory already documented historical candidates before asking the owner for
new examples. Candidate pool includes AEVO/HIMS/QQQ/CHIP/POL negative cases,
INJ anchor movement, WLD triangle, AZTEC stale selection and XRP/PONS/AAVE
unchanged baselines where exact saved candles are available.

Owner-run additions from 2026-09-28:
- **BSVUSDT 5m / Ikigai Box** — negative first-impulse case: owner marked a
  clear internal corrective swing/zigzag inside the admitted A→B leg. Freeze
  source-time candles and prove the structural correction rule without
  restoring a colour-only veto.
- **CARVUSDT 5m / Ikigai Box** — possible positive missed-detection case after
  an independently emitted Compression Triangle. Freeze source-time
  candles/cutoff first, then determine whether candidate enumeration,
  cross-pattern selection/dedup or Box eligibility suppressed a valid later
  Box. Earlier Triangle presence must not by itself exclude a later independent
  Box.
- **Recurring post-breakdown secondary Box family** — CARVUSDT, CPUSDT,
  CROSSUSDT and CLOUSDT 5m are owner-observed examples of the broader visual
  sequence `compression -> downside sloping-boundary break -> compact later
  consolidation/Box`. Treat this as a candidate defect/edge family, not four
  ticker-specific exceptions. Freeze representative source-time positives and
  negatives and determine whether the valid implementation is existing Ikigai
  Box detection after independent pattern completion or a separately specified
  secondary-Box subtype.

**Done when:** available source-time OHLC evidence is mapped to candidate cases
and gaps are explicit; no invented expected anchors.

#### RVL-G2 — Seed the first compact Geometry Gold set
**Status:** COMPLETE — PR #338 merged as `6efeba677b30965a026b05f82284260280c60db3`
**Priority:** P1

Freeze the first useful set, target roughly 8–15 real cases, but use the number
actually supported by exact saved candles and authoritative expected outcomes.

Each case includes:
- immutable OHLC;
- symbol/timeframe/source time;
- expected pattern/no-pattern;
- anchor/START expectations or allowed interval;
- reason/provenance.

**Done when:** detector output can be compared in one local run and existing
baseline behavior is recorded without tuning.

**Completion evidence (2026-09-29):**
- first compact seed contains 5 READY cases: PONS, 1000BONKUSDT,
  1000TOSHIUSDT, 1000XECUSDT and AEVO;
- manifest references existing frozen OHLC fixtures without duplication;
- runner executes the real production geometry engine;
- focused owner-machine run: 3 tests in 504.794 s, PASS;
- no production detector thresholds or Scanner/Robot/runtime behavior changed.

#### RVL-G3 — Geometry baseline report
**Status:** COMPLETE — PR #339 merged as `a7bd7c3d9a16a07952709343d7678e354b857146`
**Priority:** P1

Produce one concise machine-readable/text report:
- cases passed/failed;
- anchor deltas;
- false positive / false negative;
- changed cases versus baseline.

No aggregate vanity score is allowed to hide a structurally wrong case.

**Done when:** a geometry code change can immediately show which real cases
improved and which regressed.

**Completion evidence (2026-09-30):**
- focused report unit tests: 3/3 PASS;
- real Geometry Gold baseline: 5/5 PASS;
- changed-vs-baseline: none;
- false positives: none;
- false negatives: none;
- PONS anchor delta: all six tracked indices +0;
- no production geometry or detector behavior changed.

#### RVL-G4 — Fix geometry defect classes one at a time
**Priority:** P1

Order:
1. demonstrably false structures / impossible anchor pairs;
2. wrong anchor locality / historical re-anchoring;
3. missed valid structures;
4. score/ranking refinement only after structural correctness.

Each code slice must name the failing gold cases, turn only that class GREEN,
and preserve already-green cases. Do not threshold-tune a single screenshot.

#### RVL-G5 — Geometry invariants / property tests
**Priority:** P1 support gate

Add only high-value invariants:
- deterministic identical input;
- irrelevant later candles cannot move frozen historical anchors;
- inadmissible pivots cannot become anchors;
- explicit boundary/body-integrity rules remain enforced;
- remote history outside the allowed selection window cannot silently alter a
  local structure.

Property tests complement, never replace, the real golden fixtures.

#### RVL-G6 — One full owner Scanner acceptance

**2026-09-30 owner run completed (full traversal evidence):**
- Scanner reported `Сканирование завершено`;
- full eligible universe: **782/782 tickers**;
- **112** signals found;
- **128** Telegram deliveries;
- **28** Ikigai Box observations;
- elapsed **73:39**;
- normal Telegram delivery continued through the pass despite one previously
  observed transient HTTP `WinError 10053`.

This satisfies the **full-run/traversal and normal Telegram-delivery portion**
of G6. It does **not** close the Geometry Quality boss: during the same owner
review, systematic anchor/geometry shortcomings were observed and frozen as
GEO-U1 (universal pivot-consensus envelope geometry) and GEO-U2
(Broadening/«Рупор» classification, ENAUSDT reference). Therefore the G6 exit
condition "no owner-observed systematic geometry defect" is **NOT MET**.
Do not repeat this 782-symbol pass merely to prove traversal; reopen owner
geometry acceptance only after the relevant geometry changes are implemented.

**Priority:** P1 final gate / owner-manual

Exactly the existing permanent rule:
one complete eligible-universe real Scanner pass, normal Telegram delivery,
all integrated patterns. The golden set is implementation evidence only.

**Exit condition for Geometry Quality boss:** G6 PASS with no owner-observed
systematic geometry defect requiring reopening the gold set.

#### GEO-U1 — Universal Pivot-Consensus Envelope Geometry (future follow-up)
**Priority:** P1 queued; does not interrupt the active 2026-09-30 G6 run

Design authority: `DOCUMENTS/UNIVERSAL_PIVOT_CONSENSUS_GEOMETRY_DESIGN.md`.

Future shared geometry for Wedge, Triangle, Triangle Compression / squeeze and
related two-boundary patterns. Boundaries are to be selected by deterministic
multi-pivot consensus, distinct touch clusters, two-sided oscillation and
compression evidence, while preserving locality/historical/body-integrity
gates. Start with source recovery and shadow metrics; no threshold tuning from
one screenshot and no production selector mutation before real-case evidence.

### Phase V — Lightweight validation tooling (after both labs exist)

#### RVL-V1 — Single validation report command
**Priority:** P2

Add one small command/report that summarizes:
- FAST;
- Runtime Replay;
- Geometry Gold;
- focused PAPER CI status when available;
- owner acceptance state as PENDING/PASS.

Do not build a service, web dashboard or persistent scheduler.

#### RVL-V2 — Bounded incident capture, only if replay fidelity still needs it
**Priority:** P2 / conditional

If production-shape fixtures are insufficient, add an opt-in bounded capture at
the normalized Robot protection boundary. It must:
- contain no secrets;
- have explicit size/time bounds;
- be disabled by default;
- preserve ordered event identity/timestamps/role;
- impose negligible work on the serialized owner thread;
- write outside the safety-critical event processing path where possible.

Do not implement this task merely because it is listed.

#### RVL-V3 — CI routing by validation tier
**Priority:** P2

Wire changed-path CI so focused FAST/REPLAY checks run automatically and PAPER
CI remains the broader gate. Avoid a monolithic always-run campaign.

## 11. Queue and dependency graph

The authoritative execution queue for this initiative is:

```text
P0 Robot Stability
R1 Replay contract/runner
  -> R2 Continuous ENTRY_PENDING RED
  -> R3 Coverage-boundary contract
  -> R4 Minimal production fix
  -> R5 Replay pack + focused PAPER CI
  -> R6 One owner PAPER acceptance

P0/P1 Owner feedback remediation
OFR-1 Diagnostics
  -> OFR-2 Emergency-close investigation/fix
  -> OFR-3 Box Robot handoff failures
  -> OFR-4 Completed-Box suppression
  -> OFR-5 Box crossed-grid catch-up
  -> OFR-6 Position-card cleanup
  -> OFR-7 Position-card TradingView

P1 Geometry Quality
G1 Inventory/schema (already COMPLETE)
  -> G2 First Geometry Gold set
  -> G3 Baseline report
  -> G4 Defect-class fixes (repeat bounded slices as needed)
  -> G5 High-value invariants
  -> G6 One owner full Scanner acceptance

P2 Process tooling
V1 Compact validation report
V2 Bounded capture (conditional only)
V3 Tier-aware CI routing
```

Autopilot, secondary UX work, additional pattern families and nonessential
refactors stay behind this queue unless the owner explicitly reprioritizes.

## 12. Task-size and stop rules

Every RVL task is a separately finishable slice.

For each implementation task:
- load only its owning code/tests and this plan;
- do not combine Robot Runtime Lab and Geometry Lab mutations in one PR;
- one focused changed-behavior check is enough before the next applicable gate;
- if a task uncovers a different defect, record it and keep the active slice
  bounded unless that defect blocks the current invariant;
- no owner runtime action before the lower-tier gate for that slice is green;
- no XP merely for creating harnesses/docs; reward only verified technical
  outcomes under the existing quest ledger.

## 13. v0.1 completion gates after this plan

For development planning purposes, v0.1 has two blocking quality gates:

**Robot Stability gate**
- all known runtime replay incidents GREEN;
- canonical PAPER lifecycle remains fail-closed;
- real owner acceptance runs without ingress/recovery failure.

**Geometry Quality gate**
- compact real golden set is GREEN for the accepted behavior;
- no known false-structure class is knowingly shipped;
- one complete real Scanner/Telegram acceptance passes.

Once both gates are green, the feature freeze may be reviewed and queued
Autopilot/dual-timeframe/secondary pattern work can be resumed in owner priority
order. Green lower-tier tests alone do not declare v0.1 finished.
