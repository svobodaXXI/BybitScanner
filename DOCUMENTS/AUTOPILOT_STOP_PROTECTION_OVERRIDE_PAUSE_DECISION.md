# AUTOPILOT STOP Protection Emergency Override — Pause Semantics

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

Emergency override removes both:

- the active STOP-protection pause (`N`, `2N`, `3N`, ...), and
- active STOP-protection size restrictions.

While override is active, AUTOPILOT returns to ordinary trading permissions and ordinary allowed size, subject to all independent risk controls that are outside this STOP-series protection mechanism.

The internal STOP/recovery state is not erased by the override and continues to evolve under the previously accepted rules.

The override remains temporary and ends according to the separately accepted override termination rules, including a new protection trigger or completion of internal recovery to 100%.
