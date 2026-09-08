# BybitScanner — Reuse-First / Single Authoritative Capability Principle

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Scope: PROJECT-WIDE

Purpose: establish a universal project principle that minimizes duplicated data sources, duplicated computation, duplicated state and duplicated lifecycle ownership while preserving or improving runtime performance.

---

# 1. CORE PRINCIPLE

BybitScanner follows **Reuse Before Build** and **Single Authoritative Capability**.

Before creating any new module, service, data source, calculation, state store, renderer, execution path, subscription, cache, adapter or lifecycle owner, the implementation must first identify whether the required capability already exists in the project.

A new component is justified only when it introduces a genuinely new responsibility or provides an objectively necessary performance/isolation boundary that cannot be supplied by the existing capability without violating its contract.

A new consumer is not by itself justification for a new implementation of an existing capability.

---

# 2. SINGLE AUTHORITATIVE SOURCE / COMPUTATION / STATE

For one semantic fact or capability there should normally be one authoritative producer/owner.

Examples include:

- market data acquisition;
- scanner observations and pattern geometry;
- pattern potential calculation;
- breakout/confirmation evidence;
- account and position state;
- working-volume calculation;
- order lifecycle;
- STOP/TAKE lifecycle;
- fee/funding/PnL accounting;
- chart data and reusable chart rendering primitives;
- Telegram delivery infrastructure.

Multiple consumers may read, subscribe to or adapt the same authoritative output. They must not independently reproduce the same business calculation or maintain competing versions of the same state unless a documented architecture/performance requirement explicitly demands it.

---

# 3. PERFORMANCE-FIRST REUSE

Reuse is required to improve total system efficiency, not to force every workload through an unsuitable abstraction.

Therefore:

1. do not duplicate expensive acquisition or business computation merely to simplify a consumer;
2. share immutable/versioned results whenever possible;
3. prefer event/subscription delivery over repeated polling or recalculation when the source already produces the event;
4. permit local read caches, projections, indexes, materialized views or thin adapters when they measurably reduce latency/load;
5. such optimizations must remain derived from one authoritative source and must not become a second business authority;
6. hot-path specialization is allowed when required for performance, but it must preserve the same semantic contract and must not fork strategy/risk/execution truth;
7. remove or avoid redundant network calls, market-data subscriptions, serialization cycles and repeated geometry/indicator calculations when the same current result can be reused safely.

The optimization target is not minimum code size. The target is **maximum useful throughput and minimum duplicated work/state while preserving correctness and maintainability**.

---

# 4. UNIVERSAL TOOLING PRINCIPLE

Project nodes should be designed as reusable capabilities with narrow contracts rather than feature-specific copies.

Preferred model:

```text
AUTHORITATIVE PRODUCER / CAPABILITY
        ↓
stable contract / event / query
        ↓
multiple consumers
   ├─ Scanner
   ├─ Terminal
   ├─ PAPER Robot
   ├─ future AUTOPILOT
   ├─ LIVE execution
   ├─ Telegram
   └─ Trading Diary / analytics
```

A consumer-specific adapter may translate shape, timing or presentation, but should not re-own the underlying calculation or lifecycle.

---

# 5. ROBOT APPLICATION

The PAPER Robot must preferentially consume existing BybitScanner capabilities rather than reimplement them.

For the first wedge prototype this means, subject to current contracts and implementation availability:

- wedge identity and geometry come from the existing Scanner/Wedge pipeline;
- pattern potential comes from the existing potential calculation;
- candles/market data come from the existing authoritative market-data path;
- breakout evidence reuses the existing confirmation/breakout capability where its semantics match the prototype contract;
- working volume and quantity calculation reuse the existing account/terminal model;
- entry, STOP, TAKE and close commands reuse the common trading intent/order lifecycle and PAPER execution adapter;
- position/order truth comes back from the execution/runtime authority rather than being guessed by Robot state;
- chart rendering should reuse existing chart data/primitives and add Robot overlays as derived presentation;
- Telegram Robot messages use the existing bot/delivery infrastructure;
- PnL, fees and funding should be sourced from authoritative execution/accounting data and then recorded into Robot/Diary telemetry.

The Robot owns only its genuinely new responsibility: candidate admission/approval, strategy-policy state, trade orchestration and Robot-specific event/history projection.

---

# 6. DUPLICATION GATE

Before adding a new capability, implementation must answer:

1. Does an equivalent authoritative capability already exist?
2. Can the new consumer use it directly?
3. If not, can a thin adapter/projection solve the mismatch?
4. Would a new implementation duplicate acquisition, computation, state or lifecycle ownership?
5. If duplication is proposed for performance, is the performance need real and measurable?
6. Can the optimization remain derived from the authoritative source instead of becoming another source of truth?

If these questions do not justify a new owner, reuse is mandatory.

---

# 7. NON-GOALS

This principle does not require:

- one giant universal module;
- excessive abstraction before a second real consumer exists;
- routing latency-sensitive code through slow generic layers;
- sharing mutable state without ownership boundaries;
- premature microservices or distributed infrastructure;
- eliminating caches, indexes or optimized projections.

Universal capability means reusable semantics and ownership, not universal implementation shape.

---

# 8. DESIGN INTENT

Informal project shorthand:

**Compactness, low waste, reusable nodes, no duplicated work, performance first.**

The project should evolve so that each mature node becomes a general-purpose internal capability that can serve new features without being copied, while feature-specific orchestration remains thin.

# END_OF_DOCUMENT
