# Robot Statistics — development vs production baseline decision

Date: 2026-10-17  
Status: **OWNER DECISION / DESIGN-ONLY**  
Implementation authorization: **NONE**

## Owner requirement

Split Robot trading statistics into **before full operational readiness** and **after formal acceptance of the fully working Robot**. Pre-acceptance experiments must not distort the reported performance of the accepted trading system.

## Reporting periods

1. **DEVELOPMENT / TESTING** — all historical Robot/PAPER activity before the formally recorded production-baseline cutover. Includes debugging trades, intermediate builds, technical emergency closes and fees, without excluding unfavorable outcomes.
2. **PRODUCTION BASELINE** — trading activity from the explicit, recorded acceptance cutover onward. This is the main performance cohort for evaluation of a fully working robot.

Add a Statistics view filter: **Development / Production / All time**. Aggregate figures, trade lists, ranking and period views must all respect the selected cohort. **All time** remains available to reconcile full historical financial performance.

## Cutover rule

- **No production baseline has been established as of this decision.** Current and earlier trading history is DEVELOPMENT / TESTING.
- The cutover is authorized by the **owner only after verified technical acceptance**, not automatically on the first profitable trade, first PAPER_AUTO fill, or a particular date.
- When approved, record an immutable checkpoint containing effective cutover timestamp (UTC with explicit MSK display), installed release/commit identifier, acceptance evidence reference, and the owner approval.
- Never retroactively relabel historical trades as production merely because the software later becomes stable. Define boundary semantics unambiguously for a trade that spans cutover (proposal for implementation: classify by entry time and publish the rule).
- Do not delete, reset, rewrite or physically segregate historical trades or accounting ledger for this feature. This is an **analytics segmentation**, not a financial reset.

## Financial consistency

- Distinguish **gross PnL**, commissions/known costs, and **net PnL**; do not use misleading labels.
- Known open issue from UMAUSDT PAPER_AUTO acceptance (2026-10-17): non-BOX `robot_trades.fees_costs_usdt` stores only exit fee, while entry and exit fees both exist in `executions`; external acceptance monitor also labels gross as net. Fix/verify fee attribution **before trusting production performance statistics**. Do not imply this proves a ledger/daily-loss gate defect.
- Preserve the project's `Decimal`, read-only statistics, MSK trading-day boundary, and existing filter/aggregation contracts. Keep financial accounting continuous across cohorts.

## Implementation sequencing

1. P0: restore safe Robot readiness after `RECONCILIATION_REQUIRED`; complete protected PAPER_AUTO end-to-end acceptance and correct proven fee-reporting defects.
2. Only after that, implement the cohort selection / persisted acceptance marker through a separately scoped change, with tests for boundary behavior, all-time reconciliation, and complete filter propagation.
3. Establish PRODUCTION BASELINE only upon explicit owner declaration supported by acceptance evidence.

Related existing specifications:
- `DOCUMENTS/ROBOT_STATISTICS_V1_CHECKPOINT_2026-09-14.md`
- `DOCUMENTS/AUTOPILOT_JOURNAL_FILTERS_AND_PERIOD_RETURNS_DECISION.md`

This document records a **future design requirement only**: no runtime, Robot, PAPER DB, or statistics implementation changes are authorized.
