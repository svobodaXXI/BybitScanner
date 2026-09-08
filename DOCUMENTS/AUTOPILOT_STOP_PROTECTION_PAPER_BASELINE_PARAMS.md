# AUTOPILOT STOP Protection — PAPER Baseline Parameters

Date: 2026-09-08
Status: ACTIVE / PAPER BASELINE
Implementation authorization: PAPER ONLY

## Accepted PAPER baseline

For the first PAPER validation run, use:

- base STOP-protection pause `N = 6` closed candles;
- with the current 5-minute strategy working timeframe, `N = 30 minutes`;
- pause ladder: `N -> 2N -> 3N -> 4N -> ...`, therefore `30m -> 60m -> 90m -> 120m -> ...` on 5m;
- local trigger threshold remains `5` qualifying STOP units;
- global trigger remains aggregate global STOP-score `>= 5` plus valid diversity/distribution, with minimum threshold distribution `3 + 2`;
- size restriction ladder remains `100% -> 50% -> 25% -> 12.5%`;
- upward recovery remains `12.5% -> 25% -> 50% -> 100%`;
- each upward recovery step requires exactly `5` recovery-progress units;
- midnight rule remains `00:00 MSK` with one size-level relaxation when applicable, recovery-progress reset for that relaxation, pause reset to base `N`, and the accepted global-score midnight decay semantics;
- this parameter set is for PAPER validation only;
- LIVE enablement is not authorized by this document.

## Validation intent

`N = 6` is a baseline tuning choice, not a permanently fixed production constant. PAPER evidence should determine whether the 30-minute base pause is too short, too long, or appropriate relative to drawdown suppression and opportunity cost.

The rest of the STOP-protection architecture remains governed by `DOCUMENTS/AUTOPILOT_STOP_PROTECTION_AUTHORITATIVE_SPEC.md`.
