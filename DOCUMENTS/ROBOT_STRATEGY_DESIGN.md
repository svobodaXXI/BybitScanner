# BybitScanner — Robot Strategy Design

Version: 0.1

Date: 2026-09-05

Status: RESEARCH DESIGN / NO IMPLEMENTATION AUTHORIZATION

Purpose: preserve the current robot-strategy design decisions and research direction without changing Scanner, Strategy, Risk, Execution, PAPER or LIVE behavior.

---

# 1. CORE ARCHITECTURE

The robot must separate detection, strategic admission, risk admission and execution.

```text
SCANNER SIGNAL
  -> SETUP CANDIDATE
  -> SETUP VALIDATED
  -> ENTRY OPPORTUNITY
  -> RISK APPROVED
  -> ORDER PLAN
  -> ORDER / FILL
  -> POSITION
  -> EXIT
```

A Scanner signal is not a buy/sell command. Scanner identifies potentially relevant structure. Strategy decides whether the setup is tradable under the current regime, entry model and expected economics. Risk independently admits or rejects exposure. Execution determines whether the admitted intent can be safely sent and reconciled.

The robot must be allowed to skip the market. No detector score, pattern identity or discretionary narrative is sufficient by itself to authorize exposure.

---

# 2. INITIAL ROBOT SCOPE

The first research robot should intentionally remain simple.

Primary pattern families:

* Falling Wedge;
* Rising Wedge;
* Triangle Compression.

Later pattern families such as Flag, Head & Shoulders / Inverse H&S, Double Top / Bottom and candlestick formations remain separate future research candidates until the baseline robot is measurable and stable.

The first entry strategies are independent cohorts:

* `S1_BREAKOUT`;
* `S2_RETEST`;
* `S3_PRE_BREAKOUT`.

Their statistics must not be silently pooled. The purpose is to learn which entry mechanism actually contributes edge rather than hiding differences inside one aggregate strategy.

Initial management should also remain simple enough to attribute results:

```text
ENTRY
  -> STRUCTURAL STOP / HARD INVALIDATION
  -> FIXED-R OR STRUCTURAL/PATTERN TARGET
  -> EXIT
```

Break-even, trailing, adaptive partials, smart exits and averaging are not assumed to improve expectancy. They are later policy variants that must be tested against a frozen simple baseline.

---

# 3. ROBOT DECISION MODEL V1

For every detected candidate, the robot evaluates the following stages in order.

## 3.1 Market eligibility

Determine whether the exact instrument is currently eligible for autonomous exposure increase. Exchange/data degradation, delisting/shutdown evidence, stale state or inability to establish required authoritative evidence is an execution/admission veto according to existing safety contracts.

## 3.2 Regime classification

Record the market regime available at decision time, including at least:

* trend / higher-timeframe context;
* volatility state;
* compression / expansion state;
* volume context;
* swing / structural context;
* liquidity and spread;
* BTC / broad-market context when available and validated;
* abnormal or event-like volatility.

Regime features are context and possible filters, not assumed edge until validated out of sample.

## 3.3 Setup detection and identity

A setup must receive a stable, versioned identity. The robot must distinguish a new setup from another observation of the same setup and from a materially new formation after invalidation.

The setup record must preserve the exact information available at decision time. Future candles must never rewrite historical setup features.

## 3.4 Setup validation

The robot determines whether the candidate satisfies the versioned setup definition. Validation may include geometry, touch quality, structural integrity, breakout evidence, retest evidence, volatility, volume and economic tradability, depending on the entry model.

## 3.5 Entry-model selection

Breakout, retest and pre-breakout/corridor entry are separate strategies. A setup may become eligible for one model while remaining ineligible for another.

The robot must never collapse these into a generic "good signal" decision.

## 3.6 Entry quality and vetoes

Before risk admission, the robot must determine whether enough potential remains after realistic costs and execution uncertainty.

Candidate vetoes include:

* expected reward too small relative to stop/invalidation distance;
* post-cost reward insufficient;
* spread/slippage/liquidity unacceptable;
* setup too old or expired;
* chase distance too large;
* regime incompatibility under the selected strategy version;
* portfolio or idea-risk limit reached;
* overlapping/correlated exposure limit reached;
* degraded/unknown/reconciling execution state.

Exact thresholds are research parameters until statistically validated.

## 3.7 Risk admission

Risk admission is separate from pattern quality.

The robot must distinguish:

```text
POSITION EXPOSURE
= capital/notional currently committed

OPEN RISK
= estimated loss if admitted stops / hard invalidations execute under defined assumptions
```

The existing 19-WV robot exposure ceiling remains an operational exposure cap, not a sufficient risk model.

Before entry, every idea must have a pre-defined risk budget. Position building, ladder accumulation, pyramiding or averaging may consume that same budget but may not enlarge it because price moves against the position.

Research must determine:

* maximum loss per idea;
* maximum aggregate open risk / portfolio heat;
* correlated-alt exposure policy;
* daily/session loss constraints;
* drawdown-level kill/reduction rules;
* liquidation-distance constraints;
* whether sizing should be normalized by structural stop distance.

## 3.8 Order plan

Only after strategy and risk approval does the robot create an order plan.

The plan must define, before submission where applicable:

* side;
* intended entry model;
* order type;
* intended price or trigger;
* quantity / WV;
* structural invalidation;
* stop policy;
* target / exit policy;
* TTL / expiry or cancellation conditions;
* ladder legs if the tested model uses them;
* maximum admitted risk under expected and worst admissible fills.

Order planning does not bypass the existing fail-closed execution layer, account/session fencing, single-attempt dispatch, UNKNOWN handling or reconciliation requirements.

---

# 4. STRATEGY STATE MACHINE

The strategy-layer lifecycle should be explicit and machine-auditable.

```text
DETECTED
  -> OBSERVING
  -> VALID
  -> ARMED
  -> ENTRY_PENDING
  -> ENTERED
  -> PROTECTED
  -> MANAGING
  -> EXITING
  -> CLOSED
```

Terminal side states include:

```text
INVALIDATED
EXPIRED
SKIPPED
CANCELLED
UNKNOWN / RECONCILING
```

Each transition must carry a machine-readable reason. Examples:

```text
VALID -> ARMED
reason = BREAKOUT_CONFIRMED

ARMED -> SKIPPED
reason = EXPECTED_RR_TOO_LOW

ARMED -> SKIPPED
reason = PORTFOLIO_RISK_LIMIT

ENTERED -> EXITING
reason = STRUCTURAL_INVALIDATION

ENTERED -> EXITING
reason = TARGET_REACHED
```

The exact state vocabulary must later be reconciled with domain execution states. Strategy must not infer a fill from an order attempt, and execution ambiguity must reduce autonomy rather than cause blind retry.

---

# 5. ROBOT DECISION RECORD

The system must preserve not only completed trades but also decision-time observations and rejected opportunities.

At minimum, record:

* signal / candidate / setup identity;
* strategy version and hypothesis ID;
* symbol, timeframe and side;
* pattern and geometry features;
* regime features;
* selected entry model;
* setup state transitions;
* intended entry, actual fill and execution quality;
* structural invalidation, stop and target;
* intended and admitted WV;
* idea risk and aggregate open risk at admission;
* amendments, partial fills, protection and management transitions;
* exit reason and actual exit;
* fees, funding, slippage and net outcome;
* R, MAE, MFE, bars/time held;
* execution anomalies, stale state and reconciliation events;
* explicit skip/rejection reason for opportunities not traded.

Skipped and invalidated setups are required research data. Without them the system cannot measure whether a filter improves expectancy or merely removes profitable opportunities.

---

# 6. TRADING DIARY INSTEAD OF A SIMPLE JOURNAL

The project should use a Trading Diary rather than a minimal trade journal.

The Diary is intended to become a richer research and review layer containing the full decision context, not merely fills and PnL.

Conceptual chain:

```text
MARKET CONTEXT
  -> SIGNAL
  -> SETUP
  -> DECISION
  -> ORDER PLAN
  -> FILLS
  -> MANAGEMENT
  -> EXIT
  -> RESULT
  -> POST-TRADE ANALYTICS
```

The future AUTOPILOT should populate as much of the Diary automatically as possible. The Diary should support both machine-generated structured fields and human-readable review/annotation.

The user intends to obtain a friend's existing trading-diary structure and use it as the main UX/information-architecture reference. The BybitScanner Diary should reproduce that useful structure closely where appropriate while adapting fields, automation and analytics to the project's robot, Scanner, risk and execution model.

Until that reference is supplied, no final Diary schema, layout or implementation contract is frozen.

The Diary must be able to include both executed trades and non-traded setup outcomes (`SKIPPED`, `INVALIDATED`, `EXPIRED`) so strategy research can compare admitted and rejected opportunities.

---

# 7. RESEARCH PRIORITY

The recommended sequence is:

1. Define the deterministic Robot Decision Model for the existing Falling Wedge, Rising Wedge and Triangle Compression baseline.
2. Freeze machine-readable definitions for setup identity, validation, invalidation and expiry.
3. Define and compare `S1_BREAKOUT`, `S2_RETEST` and `S3_PRE_BREAKOUT` independently.
4. Freeze a simple initial management baseline: structural invalidation plus fixed-R or structural target.
5. Define risk admission beyond the 19-WV exposure cap, including idea risk and portfolio open risk.
6. Build the event/decision dataset and Trading Diary schema.
7. Replay/backtest with realistic costs, untouched holdout and walk-forward validation.
8. Add regime filters only when they show incremental out-of-sample value.
9. Add more complex management only against the frozen simple baseline.
10. Add new pattern families only after the core pipeline is measurable.
11. Progress through PAPER -> SHADOW -> tightly gated MICRO LIVE only after research and safety gates pass.

---

# 8. OPEN DESIGN QUESTIONS

The next design pass should resolve, one by one:

* exact machine definition of Falling/Rising Wedge and Triangle setup validity at the strategy layer;
* exact breakout definition;
* false-breakout definition;
* exact retest definition and expiry window;
* pre-breakout corridor eligibility and invalidation;
* minimum expected post-cost reward / R:R admission rule;
* structural stop derivation and tolerance;
* target calculation per setup family;
* risk per idea;
* maximum aggregate open risk;
* correlated-position policy;
* simultaneous-candidate ranking when many setups compete for limited risk budget;
* setup expiry and cooldown/re-entry rules;
* manual-close suppression so AUTOPILOT does not immediately re-enter;
* which Diary fields are generated automatically and which may be manually annotated;
* final Diary structure after the friend's reference is supplied.

---

# 9. AUTHORITY / SAFETY NOTE

This document is a research and architecture checkpoint. It does not claim profitability, promote any hypothesis to production strategy, authorize autonomous LIVE trading, or weaken existing Trading Workspace safety invariants.

Existing fail-closed LIVE gates, account/session fencing, single-attempt dispatch, no blind retry, UNKNOWN -> reconciliation behavior, PAPER/LIVE separation and execution-source-of-truth rules remain authoritative.

# END_OF_DOCUMENT
