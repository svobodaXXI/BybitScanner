# BybitScanner — Trading Diary D0 Contracts

Version: 1.0

Date: 2026-09-08

Status: ACCEPTED DESIGN / D0 FROZEN / NO RUNTIME IMPLEMENTATION AUTHORIZATION

Purpose: freeze the Stage D0 identity, linkage, normalized execution-fact, provenance and append-only event contracts required before Trading Diary implementation.

Authoritative parents:

* `DOCUMENTS/TRADING_DIARY_ARCHITECTURE.md`;
* `DOCUMENTS/ROBOT_STRATEGY_DESIGN.md`;
* `DOCUMENTS/TRADING_STRATEGY_SPEC.md`;
* current Terminal domain, execution, reconciliation and persistence contracts.

This document defines BybitScanner-owned contracts. Donor code remains reference material only.

---

# 1. D0 SCOPE

Stage D0 freezes six things only:

1. trade/position-episode identity;
2. setup-to-trade linkage;
3. normalized execution-fact identity and factual payload;
4. origin/controller/provenance vocabulary;
5. PnL/cost provenance;
6. append-only decision-event history.

D0 does not select a database, create migrations, add UI, alter PAPER/LIVE order flow, change reconciliation, authorize AUTOPILOT entry or implement strategy admission.

---

# 2. EXISTING TERMINAL IDENTITIES THAT REMAIN AUTHORITATIVE

D0 reuses, rather than replaces, the current Terminal identity model.

Current operational identities include:

```text
TradingAccountId
PositionKey = account + category + symbol + position_idx
CommandId
order_link_id
client_action_id where the current mutation path exposes it
OrderId
ExecutionId
ExecutionDedupKey = account + category + ExecutionId
```

For the current Linear One-Way terminal baseline, `position_idx = 0` remains part of `PositionKey`. Diary design must not invent a different account/symbol position key.

Identity roles are distinct:

* `CommandId` — durable internal identity of one trading command;
* `order_link_id` — exchange correlation identity used by current Bybit command submission;
* `client_action_id` — client/request mutation identity where current Market/Limit paths own one;
* `OrderId` — exchange order identity;
* `ExecutionId` — exchange execution/fill identity;
* `ExecutionDedupKey` — replay/idempotency identity for one authoritative execution within account/category scope.

No Diary identity may substitute for these execution identities.

---

# 3. TRADE EPISODE IDENTITY

## 3.1 Canonical concept

The Diary uses a BybitScanner-owned logical identity:

```text
TradeEpisodeId
```

A `TradeEpisode` is one continuous directional exposure episode for one authoritative `PositionKey`.

It is a research/accounting aggregate over execution facts. It is not exchange position authority and is not used to dispatch orders.

## 3.2 Episode start

For the current One-Way baseline, a new episode begins only when authoritative/reconciled execution evidence changes a `PositionKey` from:

```text
FLAT -> LONG
```

or

```text
FLAT -> SHORT
```

The opening execution allocation belongs to the new `TradeEpisodeId`.

A submitted command, acknowledged order or frontend preview does not open an episode.

## 3.3 Episode continuation

The same `TradeEpisodeId` continues through:

* additional fills in the same position direction;
* averaging or pyramiding that is permitted by the active policy;
* partial reductions;
* STOP/TAKE creation, amendment or removal;
* management-state changes;
* controller handoff/intervention;
* order cancellation/replacement;
* temporary execution ambiguity while authoritative position remains non-FLAT.

A change in average entry does not create a new episode.

## 3.4 Episode close

An episode closes only when authoritative reconciliation/factual replay establishes that its `PositionKey` is FLAT after applying the relevant executions.

The episode close reason is a separate classified fact such as:

```text
MANUAL_CLOSE
STOP_LOSS
TAKE_PROFIT
STRATEGY_EXIT
STRUCTURAL_INVALIDATION
EXTERNAL_CLOSE
LIQUIDATION_OR_ADL
UNKNOWN_RECONCILED_CLOSE
```

Exact operational cause mapping may be refined at implementation time, but the close timestamp and quantity/PnL facts must derive from execution/reconciliation evidence, not from intended exit reason alone.

## 3.5 Reversal split

If one execution crosses the position through zero and leaves exposure in the opposite direction, it must be represented as two episode allocations without duplicating the execution fact:

```text
ONE ExecutionFact
  -> allocation A closes remaining quantity of old TradeEpisode
  -> allocation B opens residual quantity of new opposite TradeEpisode
```

The old episode closes at the zero-crossing allocation and the new episode receives a new `TradeEpisodeId`.

This rule prevents a LONG and subsequent SHORT from being merged into one trade merely because the exchange reports one crossing execution.

## 3.6 Episode immutability

`TradeEpisodeId` never changes after creation. A later correction changes linkage or derived views through an amendment, not by recycling the identity.

---

# 4. SETUP-TO-TRADE LINKAGE

## 4.1 SetupInstance identity

Strategy research uses a stable:

```text
SetupInstanceId
```

A setup instance is the versioned, decision-time identity of one concrete detected setup lifecycle. Re-observation of the same setup does not create a new ID unless the setup was invalidated/expired and a materially new formation cycle is established under the versioned setup rules.

## 4.2 Robot-origin requirement

For strategy-driven ROBOT exposure:

```text
TradeEpisode -> primary SetupInstanceId REQUIRED
```

The primary setup link must also preserve:

* strategy version;
* hypothesis ID where applicable;
* setup ID;
* entry mode;
* decision/admission event identity;
* order-plan identity.

A robot trade may not be retroactively assigned a setup from outcome knowledge.

## 4.3 Manual-origin rule

For terminal manual trading:

```text
origin = TERMINAL_MANUAL
primary SetupInstanceId = OPTIONAL
```

If no setup existed, the field remains absent. The system must never fabricate strategy metadata simply to make a manual trade look complete.

A manual trade may later receive human tags/notes or an explicit retrospective classification, but that classification is annotation provenance and not original decision-time evidence.

## 4.4 One setup, multiple episodes

One `SetupInstanceId` may legitimately lead to zero, one or multiple `TradeEpisodeId` values.

Examples include:

* setup skipped -> zero episodes;
* one entry/one close -> one episode;
* policy-defined close followed by a separately admitted retest rebuild from the same still-valid setup -> more than one episode.

Every later episode requires its own strategy/risk admission event. The existence of the original setup does not authorize automatic re-entry.

## 4.5 One episode, one primary setup

A ROBOT `TradeEpisode` has exactly one primary setup origin.

Other overlapping structures or hypotheses may be attached as contextual/contributing references, but they do not become additional primary origins. This keeps cohort attribution deterministic.

---

# 5. ORDER PLAN AND CORRELATION CHAIN

The canonical traceability chain is:

```text
SetupInstanceId
  -> StrategyDecisionEvent
  -> RiskDecisionEvent
  -> OrderPlanId
  -> CommandId / client_action_id
  -> order_link_id
  -> OrderId
  -> ExecutionId(s)
  -> TradeEpisodeId
```

Not every node exists for every manual/external event, so absent linkage is explicit rather than guessed.

`OrderPlanId` identifies the strategy/risk-approved execution plan before dispatch. Amend/cancel actions remain separate commands/actions correlated to the same plan or parent order where applicable.

The Diary observes this chain. It does not own order dispatch.

---

# 6. NORMALIZED EXECUTION FACT CONTRACT

## 6.1 Contract role

The Diary owns a normalized factual representation conceptually named:

```text
ExecutionFact
```

The implementation may adapt the existing `terminal.domain.models.Execution` / `terminal.exchange.events.ExecutionEvent` rather than creating duplicate semantics. D0 freezes the information contract, not the Python class name.

## 6.2 Required immutable factual fields

A LIVE execution fact must preserve at least:

```text
trading_account_id
category
symbol
execution_id
order_id
order_link_id?         # exchange evidence if present
side
execution_price
execution_quantity
execution_fee
execution_value?
is_maker?
executed_at_ms
exchange_sequence?
environment = LIVE
source_kind
observed_at_ms
raw/source schema version
```

For PAPER, an analogous simulated execution identity and the explicit `environment = PAPER` provenance are required.

Historical import/replay must retain `environment/source_mode = HISTORICAL_REPLAY` or equivalent explicit provenance rather than masquerading as current LIVE evidence.

## 6.3 Deduplication identity

For LIVE Bybit execution facts the replay key remains compatible with the current Terminal model:

```text
ExecutionDedupKey
= trading_account_id + category + execution_id
```

A repeated fact with the same dedup key and identical economic evidence is a duplicate replay and must not be applied twice.

If the same dedup key arrives with conflicting immutable economic evidence, the result is an integrity conflict, not a second fill and not a silent overwrite.

## 6.4 Attribution is separate from the fact

Correlation that may become known later must not require mutating the original factual execution payload.

Use a separate logical linkage/amendment concept for:

* `CommandId`;
* `client_action_id`;
* `OrderPlanId`;
* `SetupInstanceId`;
* `TradeEpisodeId` or episode allocation;
* controller/origin attribution.

This matters for external orders, restart recovery and historical imports where an execution may be known before all internal correlation is reconstructed.

## 6.5 Fact conflict rule

Facts are append-only/immutable by identity. If a source later corrects an exchange field, preserve the original observation and append a versioned correction/amendment with explicit source and reason. Do not edit history in place without provenance.

---

# 7. EXECUTION-TO-EPISODE ALLOCATION CONTRACT

One execution fact may contribute to one or, only for zero-crossing reversal, two episode allocations.

Logical allocation fields:

```text
allocation_id
execution_dedup_key
trade_episode_id
allocation_role = OPEN | INCREASE | REDUCE | CLOSE | REVERSAL_OPEN
quantity
signed_effect
occurred_at_ms
allocation_version
```

Allocation quantity across all allocations of one execution must equal the execution quantity exactly.

This allocation layer allows replay-safe trade reconstruction without changing the immutable exchange fact.

---

# 8. ORIGIN AND CONTROLLER VOCABULARY

D0 preserves the current Terminal concepts and makes their Diary meaning explicit.

## 8.1 Origin

`Origin` answers: **where did this action/exposure originate?**

Accepted baseline values:

```text
TERMINAL_MANUAL
ROBOT
EXTERNAL
```

Persistence strings may continue using the current lowercase enum values.

Future origins require an explicit contract change; they are not inferred from missing metadata.

## 8.2 Controller

`Controller` answers: **who currently owns strategy/management control of the position/action?**

Accepted baseline values:

```text
MANUAL
ROBOT
EXTERNAL
NONE
```

Origin and controller are not the same field. Example: a ROBOT-origin episode may later receive a MANUAL intervention. The original origin remains ROBOT while controller history records the handoff/intervention.

## 8.3 Environment

Every Diary fact also carries an orthogonal environment/source mode:

```text
PAPER
LIVE
HISTORICAL_REPLAY
```

Environment must never be inferred from account label or missing exchange IDs.

---

# 9. PROVENANCE CONTRACT

## 9.1 Provenance classes

Every stored fact/derived observation must be attributable to one of these authority classes:

```text
EXCHANGE_AUTHORITATIVE
PAPER_SIMULATED
TERMINAL_PERSISTED
DERIVED
MANUAL_ANNOTATION
AMENDMENT
```

The exact source channel is a separate field, for example:

```text
BYBIT_PRIVATE_STREAM
BYBIT_REST_EXECUTION_HISTORY
BYBIT_REST_POSITION
TERMINAL_RECONCILIATION
PAPER_ENGINE
HISTORICAL_IMPORT
MARKET_DATA_PROVIDER
STATISTICS_DERIVATION
USER_NOTE
```

## 9.2 Provenance precedence

More authoritative evidence must not be silently replaced by a weaker source.

For LIVE execution quantities/prices/IDs, exchange execution evidence controls over UI intent or a local estimate.

For reconstructed trade aggregates, the result is `DERIVED_FROM_EXECUTIONS` and must retain the execution identities used.

A manual correction may coexist as an amendment, but the system must preserve that it is manual and must not relabel it as exchange-authoritative.

---

# 10. PNL AND COST PROVENANCE

PnL is not one unqualified mutable number.

The Diary must preserve components and sources where available:

```text
realized_price_pnl
execution_fees
funding
other_exchange_costs
manual_external_costs?    # only with explicit annotation provenance
net_pnl
```

## 10.1 LIVE

LIVE fee/fill facts use exchange-authoritative execution/transaction evidence where available.

Trade-level realized/net PnL may be reconstructed from authoritative executions/cost components. Such a number must be marked as derived/replayed, including the exact component identities/version used.

If Bybit supplies an authoritative closed-PnL/transaction fact with compatible semantics, it may be stored alongside the reconstruction and used for integrity comparison; semantic mismatch is not silently averaged away.

## 10.2 PAPER

PAPER PnL remains simulated and must preserve simulator/version assumptions, including fee/slippage/funding behavior actually modeled.

## 10.3 Missing versus zero

Missing cost/PnL is `NULL/UNKNOWN`, not zero.

A true amount of `0` is a valid observed/calculated breakeven component.

## 10.4 Net PnL definition

Any published `net_pnl` metric must name or version the formula/components used. Strategy research promotion uses after-cost results when required by `TRADING_STRATEGY_SPEC.md`.

---

# 11. APPEND-ONLY DECISION EVENT CONTRACT

## 11.1 Role

Strategy/setup/risk history is represented as append-only events, not by repeatedly rewriting a final-state row and losing prior evidence.

Logical identity:

```text
DecisionEventId
```

## 11.2 Required event fields

Every decision/state event must preserve:

```text
decision_event_id
aggregate_type
aggregate_id
occurred_at_ms
previous_state?
next_state
reason_code
origin
controller
strategy_version?
hypothesis_id?
setup_id?
setup_instance_id?
entry_mode?
feature_snapshot_ref or immutable payload reference
risk_snapshot_ref?
order_plan_id?
actor/source
schema_version
```

For equal timestamps, persistence must preserve deterministic insertion/sequence ordering.

## 11.3 Event immutability

Once written, an event is immutable.

A correction creates:

```text
AmendmentEvent
  -> target DecisionEventId
  -> reason
  -> author/source
  -> occurred_at_ms
  -> corrected payload/version
```

Research queries may choose the corrected interpretation while retaining the original evidence chain.

## 11.4 Reason-code requirement

Every strategic transition that changes eligibility/admission must have a machine-readable reason code.

Examples:

```text
BREAKOUT_CONFIRMED
RETEST_CONFIRMED
EXPECTED_RR_TOO_LOW
STRUCTURAL_STOP_TOO_WIDE
PORTFOLIO_RISK_LIMIT
SETUP_EXPIRED
SETUP_INVALIDATED
MANUAL_INTERVENTION
EXECUTION_STATE_UNTRUSTED
```

Human notes may supplement but never replace the reason code.

---

# 12. SETUP OUTCOME CONTRACT

A setup can end without execution.

Required terminal outcomes include:

```text
SKIPPED
INVALIDATED
EXPIRED
CANCELLED
```

For each such setup, the Diary preserves the decision-time snapshot and reason plus a later, separately stored research follow-up outcome where the study requires one.

Future outcome data must never mutate the original skip/invalidation decision.

This contract creates the denominator required to measure filter lift and rejected-opportunity cost.

---

# 13. DATA READINESS CONTRACT

D0 freezes semantic readiness, not implementation labels.

General states:

```text
OPEN
INCOMPLETE
READY
```

A trade episode becomes `READY` for general closed-trade statistics only when required identity, execution, closure and PnL provenance facts are internally consistent.

Metric-specific readiness is stricter and independent. Example: an episode can be READY for net-PnL statistics while unavailable for R-normalized MAE because initial-risk semantics are missing.

Readiness is derived; it is never manually toggled to hide incomplete data.

---

# 14. INTEGRITY INVARIANTS

The future D1/D2 implementation must enforce at least these invariants:

1. one LIVE execution dedup key is economically applied at most once;
2. conflicting immutable evidence for one execution identity is an error state;
3. allocation quantity exactly equals execution quantity;
4. a TradeEpisode cannot be both LONG and SHORT simultaneously;
5. a reversal closes one episode and creates a new opposite episode;
6. ROBOT exposure-increasing episode origin requires a primary setup/admission trail;
7. manual/external trades do not receive fabricated setup metadata;
8. decision-time fields are immutable except through amendments;
9. missing facts never become numeric zero by default;
10. environment/provenance is explicit;
11. statistics never mutate execution or trading state;
12. Diary failure may not cause a retry or duplicate trading mutation.

---

# 15. IMPLEMENTATION MAPPING TO CURRENT CODE

D0 intentionally aligns with current BybitScanner rather than introducing a parallel trading model.

Current reusable foundations include:

* `terminal.domain.models.PositionKey`;
* `terminal.domain.models.CommandId`;
* `terminal.domain.models.OrderId`;
* `terminal.domain.models.ExecutionId`;
* `terminal.domain.models.ExecutionDedupKey`;
* `terminal.domain.models.Origin`;
* `terminal.domain.models.Controller`;
* `terminal.exchange.events.ExecutionEvent`;
* `terminal.exchange.events.OrderEvent`;
* `terminal.exchange.events.PositionEvent`;
* existing command records/order-link identities;
* existing `client_action_id` action records where applicable;
* existing reconciliation and immutable-execution conflict behavior.

D1 should therefore add observational/persistence capability around these facts instead of replacing the current execution engine.

---

# 16. D0 ACCEPTANCE RESULT

Stage D0 is complete when this document is merged together with the parent Diary architecture update declaring these contracts frozen.

Frozen D0 decisions:

```text
TradeEpisode = continuous non-FLAT directional episode per PositionKey
FLAT -> direction opens episode
direction -> FLAT closes episode
zero-cross reversal splits one ExecutionFact into close/open allocations
ROBOT episode requires one primary SetupInstance
manual episode may have no setup
one SetupInstance may produce multiple separately admitted episodes
ExecutionDedupKey remains account + category + execution_id
execution facts are immutable; later attribution is separate
Origin, Controller and Environment are orthogonal
PnL/cost facts preserve source provenance
strategy/risk transitions are append-only DecisionEvents
missing != zero
Diary remains observational and cannot dispatch/retry orders
```

Next implementation stage after explicit authorization:

```text
D1 — execution facts and replay-safe TradeEpisode reconstruction
```

D1 must integrate as an observer/read-model path around existing execution/reconciliation authority and must not replace it.

# END_OF_DOCUMENT
