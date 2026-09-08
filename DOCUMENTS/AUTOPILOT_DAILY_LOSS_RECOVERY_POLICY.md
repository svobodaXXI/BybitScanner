# BybitScanner — AUTOPILOT Daily Loss Recovery Policy

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted behavior after the daily-loss threshold is crossed due to current account equity drawdown and later recovers within the same trading day.

## ACCEPTED DESIGN

The daily-loss blocker is **not latched until the next day**.

If the account's current daily result improves back above the configured daily-loss threshold during the same trading day, AUTOPILOT may allow new-risk admission again, provided all other risk/data/account health gates are healthy.

Conceptually:

`DAILY_RESULT <= DAILY_LOSS_THRESHOLD`
`-> BLOCK_NEW_RISK`

then later:

`DAILY_RESULT > DAILY_LOSS_THRESHOLD`
`+ ACCOUNT/RISK STATE HEALTHY`
`-> DAILY_LOSS_BLOCKER MAY CLEAR`
`-> NORMAL ADMISSION RESUMES`

Rules:

- the daily result is measured against the fixed day-start equity baseline;
- the trading-day boundary is 00:00 Moscow time (MSK, UTC+3);
- the daily result includes realized PnL, current unrealized PnL, trading fees, and funding already applied to the account;
- crossing the threshold blocks new entries and position increases while the threshold remains violated;
- risk-reducing actions, protective STOP/TAKE handling, and emergency exits remain available;
- recovery above the threshold does not bypass any other Portfolio Risk Engine constraint;
- if account state, reconciliation, or required risk data is unhealthy/unknown, normal fail-closed policy still applies even after the daily result itself has recovered;
- all threshold crossings, blocker activations, recoveries, and resumptions must be logged for PAPER research so later analysis can compare latched vs recoverable policies.

Exact numeric daily-loss threshold remains NEEDS VALIDATION from PAPER statistics.

# END_OF_DOCUMENT
