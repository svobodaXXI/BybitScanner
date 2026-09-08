# BybitScanner — AUTOPILOT Stop-Series Recovery Size

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

After stop-series protection is triggered and its cooling-off pause has completed, AUTOPILOT enters a recovery mode in which newly admitted strategy size is reduced to 50% of the normal requested size.

Conceptually:

`NORMAL_REQUESTED_SIZE -> STOP-SERIES PROTECTION -> PAUSE -> RECOVERY_SIZE = 0.5 * NORMAL_REQUESTED_SIZE`

Example:

- strategy requests `1.0 WV`;
- stop-series recovery mode is active;
- maximum recovery-mode request before other Portfolio Risk Engine constraints = `0.5 WV`.

This 50% recovery-size rule is an accepted design parameter.

All existing higher-priority risk constraints still apply. The 50% factor does not bypass:

- per-asset exposure cap;
- aggregate AUTOPILOT exposure cap;
- portfolio/cluster stop-risk limits;
- directional heat limits;
- market-regime restrictions;
- degraded/fail-closed data-health rules;
- reduced-size strategy revalidation.

The recovery mode ends according to the separately accepted stop-series recovery-progress rules.

# END_OF_DOCUMENT
