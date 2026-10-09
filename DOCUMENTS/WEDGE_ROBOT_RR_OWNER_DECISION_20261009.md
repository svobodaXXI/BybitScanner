# Wedge Robot entry RR — owner decision (2026-10-09)

**Current authoritative rule:** for Falling Wedge (LONG) and Rising Wedge (SHORT), the minimum executable Robot entry reward/risk ratio remains **1.5:1**. Do not impose a hard 2:1 floor on Wedge. The owner explicitly rejected that change on 2026-10-09.

- Apply the existing Wedge entry RR admission calculation to the actual proposed LIMIT entry price, including reprice checks. With the default `ROBOT_MIN_ENTRY_RR=1.5`, a computable RR of 1.5 or more is eligible; below the configured threshold, or when RR cannot be computed, entry remains blocked. Do not relax other safety, STOP/TAKE, protection, ownership or reconciliation gates.
- `ROBOT_MIN_ENTRY_RR` remains configurable under its existing validation rules; this owner decision restores the **default Wedge minimum** of 1.5 and rejects the proposed hard 2.0 floor. No changes to LIVE trading are authorised.
- This decision is **Wedge-only**: it does not change the distinct Ikigai Box and L-shape strategy/admission contracts or their RR thresholds.
- The historical BBUSDT / issue #419 claim that RR ~1.54 must be rejected for being under 2.0 is **superseded** by this owner decision. A signal with RR ~1.54 cannot be disqualified solely by an invented 2.0 Wedge floor; other actual risk gates still apply.
- PR #440 (`fix/wedge-rr-floor-419`) was **closed unmerged**, because it enforced 2.0 and its CI failed. Its source/test edits are not part of `stable/adfb50b-forward`. Do not revive/merge this change without a new explicit owner decision.

This file is the current decision addendum to historical architecture, backlog, Robot trading strategy, signal/Robot integration and acceptance documentation wherever older notes suggest Wedge RR must be 2:1. Historical records remain historical; they do not override this newer owner instruction.
