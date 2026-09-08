# BybitScanner Trading Diary — D6 UI Scope

Status: ACCEPTED SCOPE / IMPLEMENTATION NOT YET AUTHORIZED

Date: 2026-09-08

## Purpose

Define the first Trading Diary user-interface scope inside BybitScanner without changing Scanner, strategy, risk, execution, PAPER/LIVE authority, reconciliation, or AUTOPILOT trading behavior.

D6 is a downstream presentation layer over the already-defined Diary/read-model work from D1-D5.

## Product placement

The Diary belongs inside the existing Trading Workspace product UI.

Current implementation target:

```text
Trading Diary data / read models
        -> Diary UI
             -> Terminal access
             -> AUTOPILOT access
```

Deferred future access:

```text
Trading Diary data / read models
        -> Telegram / Scanner-bot entry point
```

Telegram integration is intentionally deferred. When implemented later, it must consume the same Diary/statistics read layer and cohort semantics rather than creating a second statistics implementation.

## Entry points

D6 must support access from the Trading Workspace and AUTOPILOT UI.

At minimum AUTOPILOT must provide:

- `Статистика` — opens Diary statistics/research views;
- `Подробности сделки` — opens details for the currently selected/robot-controlled trade episode when linkage exists.

The Diary UI must not become a trading authority or issue order mutations.

## D6 slices

### D6.1 — Diary shell + Trades list

Add the Diary shell inside Trading Workspace with primary sections:

- Trades;
- Setups;
- Statistics.

Trades must support at least:

- Open;
- Closed;
- Incomplete / Needs attention.

Trade-list rows should expose only read-model facts, including where available:

- symbol;
- LONG/SHORT;
- environment (PAPER/LIVE/HISTORICAL_REPLAY when applicable);
- controller/origin;
- opened/closed time;
- entry / average entry;
- exit or current state;
- PnL when READY for that metric;
- holding duration;
- readiness/data-quality state.

Missing values must remain missing and must never be displayed as numeric zero by default.

### D6.2 — Trade Details

Expose one structured trade-detail view composed from existing Diary entities/read models.

Sections:

- Identity;
- Decision;
- Risk;
- Orders / Executions;
- Management;
- Outcome;
- Automatic factors;
- Notes / annotations.

Manual trades must not fabricate setup/strategy metadata. Robot-origin trades may show setup/strategy/risk linkage only when actually present.

### D6.3 — Setups + Attention / Data Quality

Expose setup observations independently of whether a trade occurred.

Setup states/views:

- Admitted;
- Skipped;
- Invalidated;
- Expired;
- other already-authorized terminal outcomes when represented by the read model.

Expose:

- setup/candidate identity;
- pattern;
- timeframe;
- direction;
- entry mode when defined;
- decision/reason code;
- linkage to a trade episode when one exists.

Attention/Data Quality must explain metric eligibility and incomplete records, including missing evidence rather than coercing missingness to zero.

A trade may be READY for PnL while remaining ineligible for MAE/MFE or another factor. UI coverage must make this distinction visible.

### D6.4 — Statistics / Cohorts / Factors

Expose read-only statistics over existing Diary analytics.

Initial statistics surface should include where already supported/eligible:

- sample size;
- net PnL;
- average/expectancy per trade when available;
- win/loss/breakeven counts;
- win rate;
- average win/loss when available;
- profit factor when available;
- holding time;
- MAE/MFE;
- factor coverage / missingness.

The D6 statistics target is extended with the following high-value metrics/presentations, derived from BybitScanner requirements plus retained external product references:

**Priority additions**

- payoff ratio = average win / absolute average loss;
- expectancy in currency per trade;
- expectancy in R per trade once initial admitted-risk semantics are frozen and durably represented;
- average and median R once R semantics are frozen;
- maximum drawdown;
- current drawdown;
- equity curve;
- maximum consecutive wins and losses;
- largest win and largest loss;
- rolling profit factor;
- rolling expectancy;
- performance by setup/pattern;
- performance by entry mode;
- performance by timeframe;
- LONG versus SHORT performance;
- performance by hour/session and weekday where timestamps/source coverage are reliable;
- performance by holding-duration buckets;
- fees/funding/slippage contribution relative to gross PnL;
- entry and exit slippage when reliable execution evidence exists;
- MAE/MFE distributions;
- MFE capture / exit giveback from D5;
- setup admission rate;
- reason-code distributions for skipped/rejected setups;
- skip/filter effectiveness when later-outcome semantics are frozen;
- metric/factor coverage and missingness.

**Desired health/degradation presentation**

Statistics should support lifetime plus rolling windows when enough eligible observations exist, for example:

```text
Profit Factor
All time      1.72
Last 100      1.61
Last 50       1.28
Last 20       0.83
```

Rolling values are observational/research indicators only. They do not authorize automatic strategy disabling, LIVE entry, or risk-policy mutation.

**Desired setup-level summary**

A primary research view should be able to summarize one cohort such as:

```text
FALLING WEDGE / PRE-BREAKOUT
sample size
win rate
profit factor
expectancy
average win / average loss
MAE / MFE distribution
MFE capture
holding time
cost contribution
drawdown
skipped setups / reason codes
coverage
```

The exact layout remains a D6 implementation decision, but the cohort definition and metric semantics must remain explicit and version-safe.

Cohort filters should preserve the architecture's separation rules and support only fields already represented reliably in the read layer, such as:

- environment;
- symbol;
- direction;
- pattern;
- setup/setup instance;
- entry mode;
- strategy/hypothesis version when present;
- controller/origin.

Different versions and entry modes must not be silently pooled.

External references retained for this statistics design are recorded in `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md`. TradeZella is used as a reference for expectancy, profit factor, setup/time breakdowns, drawdown, R-multiples, streaks, rolling health and dashboard hierarchy. Tradervue is used as a reference for MAE/MFE, best-exit/exit-efficiency concepts, time-to-MFE/time-to-MAE and advanced report breakdowns. These are design references only; BybitScanner owns all metric definitions and safety semantics.

### D6.5 — AUTOPILOT integration

Integrate Diary navigation into the AUTOPILOT mode without changing trading control semantics.

Required behavior:

- `Статистика` opens the shared Diary statistics view;
- `Подробности сделки` opens Trade Details for the currently displayed trade when a Diary episode link exists;
- returning from Diary preserves the user's prior Trading Workspace/AUTOPILOT context where practical;
- Diary navigation must not transfer controller ownership, issue orders, retry mutations, or alter PAPER/LIVE authority.

## Explicitly out of scope for D6

D6 does not implement:

- new execution-fact ingestion;
- new trade reconstruction semantics;
- new Scanner admission logic;
- strategy/risk/order-plan producers;
- AUTOPILOT decision logic;
- autonomous LIVE entry;
- PAPER/LIVE mutation paths;
- reconciliation changes;
- backtesting;
- holdout/walk-forward/PAPER/SHADOW promotion workflows;
- D7 research integration;
- Telegram menu or Mini App integration;
- a separate Telegram-specific statistics engine.

## Telegram future requirement

Future Scanner Telegram Bot navigation should be able to enter the same Trading Diary / Statistics product surface or a thin Telegram-compatible presentation over the same read APIs.

The future Telegram integration must reuse:

- the same trade/setup identities;
- the same readiness semantics;
- the same statistics/cohort definitions;
- the same factor coverage/missingness semantics.

Telegram must not calculate competing PnL, MAE/MFE, readiness, or cohort statistics independently.

## Safety boundary

D6 is read-only with respect to trading authority.

A Diary/UI failure must not:

- trigger an order;
- retry an ambiguous mutation;
- change account/session authority;
- alter position reconciliation;
- transfer MANUAL/ROBOT control;
- change protection state.

No part of this scope authorizes autonomous LIVE trading.

## Implementation authorization

This document freezes D6 scope only.

Implementation remains unauthorized until the user explicitly authorizes D6 implementation or an individual D6 slice.
