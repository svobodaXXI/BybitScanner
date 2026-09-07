# BybitScanner — AUTOPILOT Stop-Loss Series Trigger Policy

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

The stop-loss protection trigger uses a combined rule.

Protection may activate through either of two paths:

1. consecutive-stop path — a configured number of qualifying protective STOP losses occur consecutively;
2. rolling-window path — a configured number of qualifying protective STOP losses occur within a bounded recent time/candle window, even if isolated profitable trades occur between them.

Only qualifying protective STOP events defined by the accepted stop-event policy count toward these triggers.

When either path reaches its configured threshold, AUTOPILOT enters the previously accepted two-stage protection flow:

`STOP SERIES TRIGGER`
`-> COOLING-OFF PAUSE`
`-> REDUCED-SIZE RECOVERY MODE`
`-> RECOVERY PROGRESS`
`-> NORMAL SIZE`

The exact consecutive-stop threshold, rolling-window stop threshold, and rolling-window duration/candle count remain `NEEDS VALIDATION` and should be selected from PAPER/virtual-account data rather than fixed by design assumption.

The diary/research dataset should preserve which trigger path fired and the decision-time counts/window state so both mechanisms can be evaluated independently.

# END_OF_DOCUMENT
