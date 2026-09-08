# BybitScanner — AUTOPILOT Daily-Loss Day Boundary Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted trading-day boundary for the AUTOPILOT daily-loss blocker.

## ACCEPTED DESIGN

The AUTOPILOT trading day used by the daily-loss blocker starts at:

`00:00 MSK`

Moscow Standard Time is treated as a fixed `UTC+3` boundary.

Rules:

- at `00:00 MSK`, capture the new fixed day-start capital baseline;
- reset the daily-loss measurement window for the new trading day;
- if a prior-day daily-loss blocker was active, normal new-risk admission may resume only after the new-day reset and only if account/session/risk state is otherwise healthy;
- no daylight-saving-time adjustment is applied to this boundary;
- the day-start baseline remains fixed for the whole trading day and is not raised when intraday equity reaches a new high;
- the daily-loss metric uses current account equity relative to this fixed day-start baseline, so both realized and current unrealized PnL are reflected in the drawdown measure;
- exact blocker threshold remains `NEEDS VALIDATION` in the previously accepted approximately `8%–10%` research range.

This decision refines the unresolved timezone/reset item in `DOCUMENTS/AUTOPILOT_RISK_ADMISSION_REFINEMENTS.md`.

# END_OF_DOCUMENT
