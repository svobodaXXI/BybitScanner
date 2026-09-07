# BybitScanner — AUTOPILOT Stop-Loss Streak Cooldown + Reduced-Size Recovery

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

AUTOPILOT uses a two-stage protection after an abnormal concentration of STOP exits within a short research-defined window.

Flow:

`STOP-LOSS STREAK / CLUSTER OF STOPS`
`-> COOLING-OFF PAUSE`
`-> REDUCED-SIZE RECOVERY MODE`
`-> NORMAL SIZE ONLY AFTER RECOVERY CONDITIONS`

Rules:

- when the stop-loss streak condition is met, new entries are temporarily blocked;
- existing positions continue to be managed by their already-authorized STOP / TAKE / exit / risk-reduction logic;
- after the pause expires, AUTOPILOT does not immediately return to full requested size;
- new entries initially pass through a reduced-size recovery state;
- all ordinary Portfolio Risk Engine rules still apply during reduced-size recovery;
- strategy revalidation remains mandatory for any reduced admitted size;
- exact stop-count threshold, observation window, cooldown duration, reduced-size factor and conditions for returning to normal size remain `NEEDS VALIDATION` and should be selected from PAPER data;
- diary/research telemetry must record every trigger, blocked opportunity, recovery-mode admission, recovery-mode rejection and later outcome;
- this protection is distinct from the daily-loss blocker and from simultaneous portfolio STOP-risk limits.

## DESIGN INTENT

The purpose is to react to evidence that the current strategy/market interaction may temporarily be unfavorable without permanently shutting AUTOPILOT down for the day.

A hard temporary pause reduces immediate repeated losses. A subsequent reduced-size phase allows the system to test whether conditions have normalized while limiting the cost of a false recovery.

# END_OF_DOCUMENT
