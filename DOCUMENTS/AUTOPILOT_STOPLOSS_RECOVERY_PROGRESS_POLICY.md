# BybitScanner — AUTOPILOT Stop-Loss Recovery Progress Policy

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted recovery-progress rule after a stop-loss streak has triggered the AUTOPILOT cooling-off / reduced-size protection.

## ACCEPTED DESIGN

Let `N` be the number of STOP-loss trades in the triggering losing streak.

After the cooling-off phase, AUTOPILOT trades in reduced-size recovery mode.

Recovery progress is tracked as a bounded score:

- each profitable completed trade: `progress += 1`;
- each losing completed trade: `progress -= 1`;
- progress must not fall below `0`;
- when `progress >= N`, normal position-size eligibility may be restored, subject to all other risk gates still passing.

Example for a triggering streak of `N = 4` STOP losses:

`0 -> WIN -> 1 -> WIN -> 2 -> LOSS -> 1 -> WIN -> 2 -> WIN -> 3 -> WIN -> 4 -> recovery complete`.

Thus profitable trades do not need to be strictly consecutive, but losses erase one unit of recovery progress rather than being ignored or resetting the entire recovery process.

This rule is separate from the daily-loss blocker, market-regime limits, correlation limits, per-asset cap, aggregate exposure cap and stop-risk budget.

Exact definitions of what qualifies as a profitable/losing recovery trade and how break-even trades are treated remain separate design questions.

# END_OF_DOCUMENT
