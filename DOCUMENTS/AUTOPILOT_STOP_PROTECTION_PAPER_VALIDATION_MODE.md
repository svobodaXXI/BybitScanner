# AUTOPILOT STOP Protection — PAPER Validation Mode

Date: 2026-09-08
Status: ACTIVE / PAPER VALIDATION
Implementation authorization: NONE

## Decision

The first PAPER validation phase uses comparative evidence without pre-imposed hard PASS/FAIL KPI thresholds.

The purpose is to determine whether STOP protection improves the risk/return profile in practice before numerical acceptance thresholds are fixed.

## Compare

Evaluate periods/scenarios with STOP protection against the same strategy behavior without STOP protection where practical.

Primary evaluation dimensions:
- maximum drawdown;
- final/net profitability;
- depth and frequency of severe losing streaks;
- proportion of time AUTOPILOT spends under STOP-related pause or reduced-size restrictions.

## Rule

Do not define arbitrary hard numerical acceptance thresholds before sufficient PAPER evidence exists.

After the first meaningful PAPER sample is collected, use the observed trade-off between drawdown reduction and opportunity/profit loss to define explicit PASS/FAIL criteria for later validation.

## Current PAPER baseline

The current initial STOP-protection PAPER baseline uses:
- base pause `N = 6` closed candles;
- on 5-minute strategy timeframe this equals 30 minutes;
- other STOP-protection trigger, size-ladder, recovery, midnight, local/global and override semantics remain as defined in the authoritative STOP-protection specification and accepted PAPER baseline decisions.

## LIVE

No LIVE acceptance is implied by PAPER operation. LIVE enablement requires separate evidence review and explicit acceptance after PAPER validation.
