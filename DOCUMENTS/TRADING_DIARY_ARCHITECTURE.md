# BybitScanner — Trading Diary Architecture

Version: 0.1

Date: 2026-09-08

Status: ACCEPTED DESIGN / IMPLEMENTATION NOT YET AUTHORIZED

Purpose: define the BybitScanner Trading Diary and research-data architecture by integrating the strongest applicable ideas from the temporary donor Trading Journal with the existing Scanner, strategy-research, Trading Workspace, risk and execution architecture.

The donor is a reference source only. `DONOR/` is not a runtime dependency, is not copied wholesale into production architecture, and may be removed after the required ideas have been captured in BybitScanner-owned documents and implementation.

---

# 1. PRODUCT ROLE

The BybitScanner product uses a **Trading Diary**, not a minimal trade journal.

The Diary is the durable research and review layer for both manual trading and future AUTOPILOT. It must preserve what the system knew, why a decision was made, what was intended, what actually happened at the exchange/runtime boundary, and what the later outcome was.

Canonical information chain:

```text
MARKET / SCANNER OBSERVATION
  -> SIGNAL
  -> SETUP INSTANCE
  -> STRATEGY DECISION
  -> RISK DECISION
  -> ORDER INTENT / PLAN
  -> ORDER LIFECYCLE
  -> EXECUTION FACTS
  -> POSITION / TRADE EPISODE
  -> MANAGEMENT / PROTECTION
  -> EXIT
  -> CLOSED RESULT
  -> POST-TRADE ENRICHMENT
  -> STATISTICS / RESEARCH DATASET
```

The Diary is downstream of trading authority. It records and reconciles facts; it must not become a second execution engine or a competing source of position/order truth.

---

# 2. EXISTING BYBITSCANNER AUTHORITY THAT MUST BE PRESERVED

The integration must preserve these existing project decisions:

* Scanner signal is not a trade command.
* Geometry/pattern detection, Confirmation, Strategy, Risk and Execution remain separate layers.
* `setup_id` and `entry_mode` are mandatory research cohort keys.
* Falling Wedge, Rising Wedge and Triangle Compression remain the initial robot pattern families.
* Breakout, breakout-plus-retest and pre-breakout/corridor entries remain separate cohorts.
* Future strategy hypotheses such as H-011 through H-016 remain versioned research claims rather than production rules.
* One Working Volume remains the existing account-level WV concept; the 19-WV ROBOT ceiling is exposure, not the complete risk model.
* Future AUTOPILOT risk admission remains separate from pattern quality and must preserve idea risk and aggregate open-risk evidence.
* PAPER/LIVE execution separation, account/session fencing, single-attempt dispatch, no blind retry and `UNKNOWN -> RECONCILING` remain authoritative.
* Detection-time and decision-time facts must not be rewritten from future information.
* SKIPPED, INVALIDATED and EXPIRED eligible setups are required research observations, not disposable noise.

The Diary therefore extends the existing design; it does not replace it.

---

# 3. DONOR IDEAS ADOPTED

The following donor concepts are accepted because they strengthen the existing BybitScanner design without changing its trading authority.

## 3.1 Normalized execution facts

Adopt the donor principle of a transport-neutral execution fact at the application/domain boundary.

A future BybitScanner execution fact should normalize at least:

* exchange/environment;
* account identity;
* instrument/symbol identity;
* side;
* executed quantity;
* executed price;
* fee/cost facts when authoritative;
* execution timestamp in UTC;
* external execution ID;
* external order ID;
* BybitScanner command/client-action identity when known;
* position/trade-episode linkage when known;
* source/provenance.

The exchange/runtime observation is factual input. It is not reconstructed from UI intent when authoritative execution evidence exists.

## 3.2 Idempotent execution replay and trade reconstruction

Adopt the donor principle that repeated import/reconciliation of the same external execution must be idempotent.

The durable duplicate identity should use authoritative exchange execution identity scoped by exchange/account. Replaying an already-known execution must not duplicate quantity, fees, PnL or a trade episode.

Historical import, restart recovery and incremental synchronization must therefore be replay-safe.

## 3.3 Safe incremental synchronization

Adopt the donor pattern of:

```text
DURABLE WATERMARK
  + OVERLAP WINDOW
  + IDEMPOTENT EXTERNAL EXECUTION IDs
  + ORDERED REPLAY
```

The durable cursor must never advance beyond the first unprocessed/failed factual item. This matches BybitScanner's existing fail-closed reconciliation philosophy and avoids silently skipping fills during restart or transient failures.

Exact overlap duration and persistence location are implementation details to be chosen later.

## 3.4 Explicit data readiness

Adopt a derived readiness state for records used by general statistics:

```text
OPEN
INCOMPLETE
READY
```

General closed-trade statistics include only records that are logically CLOSED and READY for the metric being reported.

Missing data is not zero. A realized/net PnL equal to zero is a valid breakeven result and must remain distinguishable from missing PnL.

Metric-specific research may apply stricter eligibility than general trade readiness.

## 3.5 Versioned automatic factors as observations, not schema columns

Adopt the donor's registry/observation principle:

* factor definitions are metadata;
* factor observations are stored separately from the core trade row;
* each factor has stable identity, definition version, calculation version, source/provenance, capture semantics and applicability;
* adding a new research factor should normally not require adding another column to the core trade entity;
* historical observations retain their original semantics when a factor definition evolves.

This is especially important for BybitScanner because strategy research will add and kill many features over time.

## 3.6 Statistics as a read-only analysis layer

Adopt the donor separation in which the statistics engine reads immutable/derived records and does not mutate trading state.

Statistics must support cohorting/filtering by BybitScanner identities such as:

* account/environment;
* symbol/instrument;
* direction;
* timeframe;
* pattern and pattern version;
* hypothesis ID;
* strategy version;
* setup ID / setup instance;
* entry mode;
* regime;
* manual versus robot controller;
* admission/skip reason;
* management/exit policy version;
* selected automatic factors when statistically meaningful.

## 3.7 PnL and calculation provenance

Adopt explicit provenance for outcome facts.

The system must distinguish, where applicable:

* exchange-authoritative realized/fill facts;
* execution-replay reconstruction;
* terminal/runtime snapshot facts;
* derived research calculations;
* manual annotations/corrections.

A later derived number must not silently overwrite a more authoritative source. Corrections require traceable amendment/provenance.

## 3.8 Post-trade MAE/MFE and exit-quality analytics

Adopt post-trade excursion analysis as a first-class research capability.

MAE/MFE must have explicit versioned observation semantics and horizon/source rules. Future R-normalized measures must use the **initial admitted risk/stop semantics**, not a later moved stop unless the metric explicitly says otherwise.

Exit-quality metrics may be derived from MFE/MAE and actual exit, but must remain separate from entry quality and must not use future data in decision-time features.

## 3.9 Data-quality and integrity audit

Adopt explicit integrity checks for duplicate executions, broken trade linkage, missing required facts, impossible lifecycle transitions, mixed provenance, inconsistent currencies/units and historical-semantic drift.

Integrity failures must be visible and must exclude affected records from metrics that require the missing/invalid evidence.

---

# 4. DONOR IDEAS NOT COPIED AS-IS

The donor is not imported wholesale.

The following parts are deliberately **not** adopted as direct BybitScanner architecture:

* donor Telegram-bot runtime and UI flows — BybitScanner already owns its Telegram/Trading Workspace direction;
* donor Mini App frontend — the existing Trading Workspace remains the primary terminal/autopilot UI base;
* donor account/access model — BybitScanner already has account/session authority and must retain its own fencing semantics;
* donor execution client — BybitScanner already has PAPER/LIVE execution adapters and reconciliation logic;
* donor one-net-position-per-account/instrument aggregation implementation — useful as a reference policy, but BybitScanner trade/position episode rules must be defined against its actual account mode, order lifecycle and controller ownership;
* donor generic reminder/attention subsystem — may inspire later UX, but is not required for the first Diary architecture;
* donor database schema/migrations — concepts are reusable, schema is not;
* donor custom-field UX wholesale — BybitScanner should prefer automatic factors and explicit robot/research fields; manual custom fields are secondary.

---

# 5. BYBITSCANNER-OWNED DOMAIN MODEL

The Diary must keep **setup/decision lifecycle** separate from **execution/trade lifecycle**.

## 5.1 Research / setup side

Logical entities:

```text
SignalObservation
SetupInstance
StrategyDecision
RiskDecision
OrderPlan
SetupOutcome
```

A `SetupInstance` can terminate without a trade:

```text
SKIPPED
INVALIDATED
EXPIRED
CANCELLED
```

These outcomes remain part of the research denominator.

## 5.2 Execution / trade side

Logical entities:

```text
OrderIntent
OrderLifecycle
ExecutionFact
PositionEpisode / TradeEpisode
ProtectionEvent
ExitEvent
TradeOutcome
```

The exact class names and persistence names remain implementation details. The architectural rule is the separation of intent from authoritative execution fact.

## 5.3 Required linkage

Where applicable, a closed trade must be traceable backward through:

```text
trade_id / episode_id
  -> execution_id(s)
  -> external order ID(s)
  -> BybitScanner client_action_id / command identity
  -> order plan
  -> risk decision
  -> strategy decision
  -> setup_instance_id
  -> candidate/signal identity
  -> detector / pattern / strategy versions
```

A manual terminal trade may legitimately have no Scanner setup. Its origin must then be explicit, e.g. `MANUAL`, rather than populated with invented strategy data.

---

# 6. APPEND-ONLY DECISION HISTORY

Decision-time evidence is immutable after the decision event.

For every meaningful strategy/setup transition preserve:

* timestamp;
* previous state;
* next state;
* machine-readable reason code;
* responsible controller (`MANUAL`, `ROBOT`, later other explicit sources);
* strategy/hypothesis version;
* relevant decision-time feature snapshot or references;
* risk/exposure evidence when admission is involved.

Corrections do not rewrite history. They append an amendment linked to the original record with author/source, reason and time.

This prevents hindsight from contaminating the training/research dataset.

---

# 7. CORE DIARY RECORD

The durable Diary view of an executed trade should be composed from normalized facts rather than one oversized mutable row.

Required categories are:

## 7.1 Identity

* account/environment;
* symbol/instrument;
* trade/episode identity;
* controller/origin;
* setup instance when applicable;
* pattern, hypothesis, strategy and entry-mode versions when applicable.

## 7.2 Pre-trade decision

* signal/setup state;
* decision-time geometry/confirmation/context references;
* strategy admission result and reason;
* risk admission result and reason;
* intended WV/quantity;
* initial structural invalidation;
* initial stop policy/price;
* target/expected-reward reference;
* expected reward-to-risk after expected costs;
* aggregate exposure/open-risk evidence.

## 7.3 Execution

* intended orders and stable client action identities;
* acknowledgements/rejections/ambiguity;
* external order/execution IDs;
* fills and partial fills;
* actual average entry/exit;
* latency/slippage where measurable;
* fees/funding/other costs with provenance;
* reconciliation events.

## 7.4 Management

* protection state and changes;
* partial exits;
* rebuild/averaging/pyramiding legs if a tested policy permits them;
* manual intervention;
* controller handoff;
* exit intent and reason.

## 7.5 Outcome

* realized result before/after costs;
* normalized R using the frozen initial-risk definition;
* holding time;
* MAE/MFE under versioned semantics;
* exit quality metrics;
* outcome/data-quality status.

## 7.6 Human review

Human notes/tags/screenshots may be attached after the fact, but they are annotations. They must not mutate or masquerade as original decision-time machine evidence.

---

# 8. NON-TRADED SETUP RECORD

A non-traded setup is a first-class Diary/research record.

For every eligible `SKIPPED`, `INVALIDATED`, `EXPIRED` or policy-cancelled setup preserve at least:

* setup/candidate/signal identity;
* decision timestamp;
* pattern, strategy/hypothesis, timeframe and direction;
* decision-time feature/context snapshot;
* proposed entry/stop/target or economic references if the setup reached that stage;
* explicit rejection/invalidation/expiry reason;
* risk/portfolio state when relevant;
* later outcome labels used for research, stored separately from decision-time fields.

This allows the project to ask whether a filter removed bad trades or accidentally removed profitable opportunities.

---

# 9. AUTOMATIC FACTOR MODEL

The first implementation should use a small, high-value factor registry and expand only when a research question requires it.

## 9.1 P0 automatic factors

Recommended first set:

**Temporal/context**

* entry UTC/local session fields as explicitly defined;
* holding duration.

**Volatility/range**

* ATR/realized-volatility context used by the active strategy;
* current range/day-range position where useful;
* spread at decision/fill when reliably available.

**Activity/liquidity**

* volume context and RVOL under frozen semantics;
* executable/liquidity evidence already available to admission logic.

**Price context**

* distance to relevant structure/zone;
* distance to VWAP only when a strategy study explicitly uses it;
* 24h or higher-horizon change when used as regime context.

**Derivatives**

* open interest/funding/basis only when a hypothesis requires them and historical source quality is adequate.

**Execution/cost**

* entry/exit slippage;
* fees;
* funding;
* latency where measurable;
* rejected/ambiguous/reconciled execution markers.

**Post-trade**

* MAE/MFE price and percentage excursions;
* later R-normalized excursion only after initial-risk semantics are frozen;
* exit-quality measures derived from a versioned excursion definition.

## 9.2 No factor hoarding

The donor demonstrates that many automatic factors can be collected. BybitScanner should **not** collect every possible metric merely because it is available.

A factor is promoted into routine capture when it satisfies at least one of:

* it is required to reproduce a strategy/risk decision;
* it is required for execution/accounting integrity;
* it answers a predefined research question;
* it is inexpensive, stable and clearly useful as a general cohort/context field.

This keeps the Diary useful rather than turning it into uncontrolled feature accumulation.

---

# 10. STATISTICS MODEL

## 10.1 Two different denominators

The project must never confuse:

```text
TRADE STATISTICS DENOMINATOR
= executed trades eligible for the metric

SETUP RESEARCH DENOMINATOR
= all eligible setup observations, including non-traded outcomes
```

Both are required.

## 10.2 Required first metrics

For closed READY trades:

* sample size;
* net PnL and cumulative PnL;
* expectancy per trade;
* expectancy per unit initial risk where defined;
* win/loss/breakeven counts;
* win rate with breakeven policy stated;
* average win and average loss;
* profit factor;
* fees/funding/slippage contribution;
* MAE/MFE distributions;
* holding time;
* drawdown/equity-curve metrics once the sampling/accounting basis is frozen.

For setup research:

* candidate/admitted/skipped/invalidated/expired counts;
* admission rate;
* reason-code distributions;
* hypothetical/follow-up outcome metrics under a frozen observation horizon;
* filter lift versus otherwise comparable cohorts;
* coverage/missingness for every research factor used.

## 10.3 Cohort integrity

Statistics must remain separable by at least pattern, setup, entry mode, strategy version, hypothesis, direction, timeframe, regime and controller/origin.

Different versions may be combined only by an explicit analysis that declares the combination; the default is not to silently pool them.

---

# 11. READINESS AND DATA QUALITY

General trade readiness is derived, not manually toggled.

Candidate model:

```text
OPEN
CLOSED_INCOMPLETE
CLOSED_READY
```

An implementation may retain donor-style labels `OPEN / INCOMPLETE / READY`; semantics matter more than names.

Typical blockers for CLOSED_READY include missing or contradictory:

* instrument/account identity;
* direction;
* entry/fill facts;
* quantity;
* exit facts;
* realized/net outcome provenance;
* required execution linkage;
* required metric-specific data.

A record may be READY for general PnL statistics but not eligible for a metric that requires initial risk, MAE/MFE or a particular research factor. Metric coverage must therefore be reported explicitly.

---

# 12. PERSISTENCE BOUNDARIES

The future implementation should prefer explicit repositories/ports around these logical stores:

* setup/decision event store;
* order/execution fact store;
* trade/position episode store;
* automatic factor definition/observation store;
* annotation store;
* synchronization/import state;
* statistics read model/query layer.

The exact database technology and migration layout are not frozen by this document. If PostgreSQL/SQLAlchemy/Alembic are chosen later, that is a BybitScanner implementation decision, not a donor inheritance requirement.

Core trading runtime must not depend on statistics UI availability. Diary/statistics failure must not create a second order attempt or alter authoritative exchange reconciliation.

---

# 13. PAPER, LIVE AND HISTORICAL DATA

The Diary must support all three provenance modes without mixing them silently:

```text
PAPER
LIVE
HISTORICAL_REPLAY / IMPORT
```

Every record must preserve environment/source.

PAPER is valid for workflow and policy validation but is not equivalent to LIVE execution evidence. Historical replay can support strategy research but must preserve its simulator/market-data assumptions. LIVE facts remain exchange/runtime evidence and retain account/session provenance.

---

# 14. MANUAL TRADING AND AUTOPILOT

The same Diary schema should support both.

Manual trading:

```text
origin = MANUAL
setup linkage = optional
manual reason / note = allowed
execution facts = authoritative as usual
```

AUTOPILOT:

```text
origin = ROBOT
setup linkage = required for strategy-driven exposure
strategy/risk decision trail = required
version identities = required
execution facts = authoritative as usual
```

A manual action affecting a ROBOT-controlled position must be recorded as an intervention/controller event rather than silently rewritten as robot behavior.

---

# 15. UX INFORMATION ARCHITECTURE

The donor's useful information organization is adopted conceptually, but the UI belongs to BybitScanner Trading Workspace.

Recommended Diary views:

```text
DIARY
├── Trades
│   ├── Open
│   ├── Closed
│   └── Incomplete / Needs attention
├── Setups
│   ├── Admitted
│   ├── Skipped
│   ├── Invalidated
│   └── Expired
├── Trade / Setup Details
│   ├── Decision
│   ├── Risk
│   ├── Orders / Executions
│   ├── Management
│   ├── Outcome
│   ├── Automatic factors
│   └── Notes
└── Statistics / Research
    ├── Performance
    ├── Cohorts
    ├── Factors
    ├── Coverage / data quality
    └── Strategy comparison
```

Exact screen layout is deferred until implementation/UX work. The key requirement is that the same structured data powers manual review and robot research.

---

# 16. IMPLEMENTATION SEQUENCE

Implementation should be staged so the Diary does not destabilize the Trading Workspace execution path.

## Stage D0 — contracts and identity

Freeze:

* trade/position-episode identity;
* setup-to-trade linkage;
* normalized execution fact contract;
* origin/controller/provenance vocabulary;
* PnL/cost provenance;
* append-only decision event contract.

No UI dependency.

## Stage D1 — execution facts and replay-safe trade reconstruction

Build persistence/read models for authoritative execution facts and trade episodes. Integrate through observation of the existing execution/reconciliation path, not by replacing it.

Acceptance includes duplicate replay safety, restart recovery and no mutation of order-dispatch behavior.

## Stage D2 — setup and decision records

Persist Scanner/setup/strategy/risk decisions, including SKIPPED/INVALIDATED/EXPIRED records and reason codes.

This stage is essential before strategy backtesting/filter optimization because it creates the eligible-event denominator.

## Stage D3 — readiness, PnL provenance and basic statistics

Add READY/INCOMPLETE rules, basic closed-trade performance, cohort filters and data coverage.

## Stage D4 — automatic factor registry and P0 enrichment

Add versioned factor definitions/observations only for the selected P0 factors required by current research.

## Stage D5 — post-trade MAE/MFE and exit analytics

Add versioned post-trade path observations and exit-quality metrics with explicit no-look-ahead boundaries.

## Stage D6 — Diary UI

Expose trades, setups, details, attention/data-quality and statistics inside the BybitScanner product UI.

## Stage D7 — strategy-research integration

Connect the dataset to holdout/walk-forward/PAPER/SHADOW research workflows and strategy promotion gates.

No stage authorizes autonomous LIVE entry. Existing LIVE gates remain independent.

---

# 17. DONOR-TO-BYBITSCANNER MAPPING

| Donor concept | BybitScanner decision |
| --- | --- |
| `ExecutionFact` | Adopt concept; define BybitScanner-owned normalized execution fact tied to current execution identities. |
| execution replay/idempotency | Adopt; authoritative external execution identity prevents duplicates. |
| trade aggregation service | Adopt concept, not donor one-net-position implementation; reconcile with current terminal/account semantics. |
| historical import/backfill | Adopt later through replay-safe factual ingestion. |
| incremental Bybit sync | Adopt overlap + watermark + fail-closed cursor semantics where useful. |
| `OPEN/INCOMPLETE/READY` | Adopt readiness semantics. |
| dynamic/custom fields | Partially adopt; automatic/versioned factors are primary, manual custom fields secondary. |
| automatic data registry | Adopt strongly; factor definitions separate from observations/core trade schema. |
| statistics engine | Adopt read-only architecture and coverage reporting; metrics/cohorts adapted to robot research. |
| PnL provenance | Adopt strongly. |
| MAE/MFE V4 | Adopt capability, re-specify semantics for BybitScanner initial-risk and research horizons. |
| exit quality V5 | Adopt later as derived post-trade research, not as a trading rule. |
| data quality/integrity | Adopt strongly. |
| Telegram/Mini App runtime | Do not copy; use BybitScanner UI/runtime. |
| donor DB schema | Do not copy; design BybitScanner persistence from its own contracts. |

---

# 18. GOVERNANCE AND SAFETY

This document accepts architecture and integration direction only.

Before material implementation:

* resolve the applicable Task/Spec or ChangeRequest;
* inspect current Trading Workspace execution/reconciliation contracts and persistence boundaries;
* freeze the D0 identities/contracts;
* preserve existing PAPER/LIVE authority and fail-closed behavior;
* verify that Diary writes are observational and cannot cause duplicate trading mutations;
* add only objectively necessary tests for critical identity, replay, data-integrity and statistics logic.

No donor code is authoritative merely because it is mature or well tested. BybitScanner authority, existing contracts and current runtime safety win whenever semantics differ.

---

# 19. RELATION TO TRADING STRATEGY RESEARCH

`DOCUMENTS/TRADING_STRATEGY_SPEC.md` owns strategy hypotheses, entry/management research and promotion criteria.

This document owns the **Diary/data architecture needed to observe and analyze those strategies**.

`DOCUMENTS/ROBOT_STRATEGY_DESIGN.md` owns the robot decision pipeline and uses the Diary as its durable evidence/research output.

The intended relationship is:

```text
TRADING_STRATEGY_SPEC
  defines what must be tested

ROBOT_STRATEGY_DESIGN
  defines how a future robot decides

TRADING_DIARY_ARCHITECTURE
  defines how the evidence, decisions, executions and outcomes are preserved and analyzed
```

# END_OF_DOCUMENT
