# BybitScanner — AUTOPILOT Daily-Loss Recovery Hysteresis

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted recovery behavior for the AUTOPILOT daily-loss blocker.

## ACCEPTED DESIGN

When the daily-loss blocker has activated, AUTOPILOT may resume new-risk admission within the same trading day only after the account has recovered above a separate safer recovery threshold.

This means the block threshold and recovery threshold are intentionally different.

Example concept only:

- blocker threshold: `-9%` from the fixed day-start capital baseline;
- recovery threshold: a materially safer level such as `-8%`.

The exact numerical recovery gap remains `NEEDS VALIDATION` and must be selected from PAPER / virtual-account data.

## RULES

- reaching the blocker threshold disables new entries and position increases;
- risk-reducing actions, STOP/TAKE handling and exits remain allowed;
- a tiny move back above the blocker threshold is not enough to resume trading;
- new-risk admission resumes only after the account reaches the separate recovery threshold and other account/risk-health checks are healthy;
- the system should log blocker activation, recovery-threshold crossing, and any same-day reactivation;
- PAPER research should preserve the full sequence so alternative hysteresis gaps can be evaluated later.

The daily-loss metric itself remains based on actual account-capital change from the fixed day-start baseline, including realized PnL, unrealized PnL, trading fees and funding, with the trading-day boundary at 00:00 MSK.

# END_OF_DOCUMENT
