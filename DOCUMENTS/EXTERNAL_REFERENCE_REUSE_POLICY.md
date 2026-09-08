# BybitScanner — External Reference Reuse Policy

Status: ACTIVE DEVELOPMENT PRINCIPLE

Date: 2026-09-08

## Purpose

Define a durable project-wide rule for using strong external products, documentation, papers, repositories, and public implementation references as **design accelerators** without importing their authority, code, assumptions, or unsafe behavior into BybitScanner.

The goal is to avoid repeatedly rediscovering mature product/reporting/UX patterns from scratch. When an external source materially informs a BybitScanner design decision, the project should preserve enough provenance to revisit that source later during implementation, review, extension, or redesign.

## Universal principle

For any non-trivial product, UX, analytics, research, workflow, or architecture feature:

1. Inspect the strongest relevant external examples when doing so can materially improve the design or reduce implementation time.
2. Prefer primary/official product documentation, technical documentation, public specifications, and original repositories over secondary summaries.
3. Record the external source, the useful pattern extracted from it, and the BybitScanner-specific adaptation.
4. Never treat the external source as project authority. BybitScanner contracts, safety boundaries, data semantics, and current runtime architecture remain authoritative.
5. Reuse **concepts, information architecture, metric definitions, workflow patterns, and implementation ideas**; do not copy proprietary code or silently inherit incompatible assumptions.
6. Before implementing a referenced pattern, re-check the current source when practical because external products and documentation change over time.
7. If a metric or pattern is adopted, freeze BybitScanner-owned semantics/versioning rather than depending on an external product's mutable definition.

This principle is especially useful when building:

- statistics/reporting dashboards;
- Trading Diary views;
- research/cohort analysis;
- execution/reconciliation observability;
- terminal/mobile UX;
- alerts and attention workflows;
- developer workflow/harness improvements.

## Reference-record format

When an external reference materially informs a design, record at least:

- source/product name;
- source URL or repository;
- access/review date when useful;
- exact pattern, metric, or workflow used as inspiration;
- BybitScanner decision: ADOPT / ADAPT / DEFER / REJECT;
- local owning document or component;
- semantic differences or safety constraints.

The record may live in the owning spec/architecture document when narrow, or in a dedicated reference section when multiple external sources are reused.

## Safety and authority boundary

External references must never bypass:

- PAPER/LIVE separation;
- account/session fencing;
- no-blind-retry and UNKNOWN/RECONCILING behavior;
- strategy/risk/execution layer separation;
- current ChangeRequest/Task/Spec approval gates;
- data provenance/readiness rules;
- repository licensing/copyright restrictions.

An external product displaying a metric does not prove that its exact formula, sampling window, price source, fill semantics, or risk definition is correct for BybitScanner. The project must define its own versioned semantics.

## Trading analytics reference set — initial seed

The following sources are retained as reusable examples for Trading Diary / statistics design.

### TradeZella

Official/product documentation reviewed 2026-09-08:

- https://www.tradezella.com/blog/trading-dashboard
- https://www.tradezella.com/blog/trading-expectancy
- https://www.tradezella.com/blog/analyze-trading-performance
- https://help.tradezella.com/en/articles/11391581-reports-day-time
- https://help.tradezella.com/en/articles/7118437-understanding-dashboard-widgets-and-stats

Useful patterns retained:

- win rate by setup rather than only global win rate;
- profit factor;
- expectancy per trade and R-normalized expectancy;
- average win versus average loss / payoff ratio;
- current and maximum drawdown;
- rolling rather than lifetime-only health metrics;
- performance by time of day, day of week, setup, ticker, and holding time;
- planned versus realized R-multiple;
- streaks and largest win/loss;
- compact dashboard hierarchy: headline health -> pattern/cohort breakdown -> process quality;
- compare LIVE results with backtest/research baselines instead of viewing LIVE in isolation.

BybitScanner adaptation:

- all metrics remain cohort-safe by pattern/setup/entry_mode/version/environment/controller;
- R-normalized metrics are DEFERRED until initial admitted-risk semantics are frozen and represented durably;
- Telegram will later consume the same statistics/read layer, not reimplement formulas;
- rolling degradation indicators are a desired AUTOPILOT research/monitoring capability, not an autonomous LIVE trading authorization.

### Tradervue

Official documentation reviewed 2026-09-08:

- https://www.tradervue.com/help/reports/trade_stats
- https://www.tradervue.com/help/reports/reports_advanced
- https://www.tradervue.com/help/reports

Useful patterns retained:

- separate position MFE/MAE and price MFE/MAE semantics;
- best-exit PnL as a post-trade benchmark;
- exit efficiency / captured-potential concept;
- time-to-MFE and time-to-MAE;
- advanced breakdowns by instrument, time, price/volume, market behavior, liquidity, expectation, and risk.

BybitScanner adaptation:

- D5 already owns versioned trade-lifetime MAE/MFE and exit-capture/giveback semantics;
- future time-to-MFE / time-to-MAE are candidate additions once the market-path producer is implemented reliably;
- any "best exit" metric must be explicitly versioned and must not contaminate decision-time features with future information.

## Implementation-use rule

When future work touches a domain listed in this document, agents should inspect the relevant retained sources before inventing a new presentation or metric scheme, **only when the source remains relevant to the concrete task**. Reuse the pattern, not the vendor implementation.

If the external source has changed, record the new interpretation in the owning document rather than silently changing an existing BybitScanner metric definition.

## Anti-patterns

Do not:

- copy a competitor dashboard wholesale;
- copy proprietary source code;
- adopt vendor benchmarks as risk policy without BybitScanner validation;
- add every metric a reference product exposes;
- conflate attractive UI with correct statistics semantics;
- silently pool strategy/setup/version cohorts because an external dashboard does;
- let future-data analytics leak into strategy decision-time factors.
