# BybitScanner — AUTOPILOT Manual Position After Approval Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

Decision:

For Robot v0.1, if a manual PAPER position appears for a symbol after the robot candidate was approved but before robot entry, the robot candidate is immediately terminated with status `BLOCKED_BY_MANUAL_POSITION`.

The candidate must not resume or reactivate automatically after the manual position is later closed. A new scanner signal and a new user approval are required for any future robot trade on that symbol.

Rationale:

- preserve one unambiguous controller/owner per symbol position;
- prevent stale approved signals from silently reactivating;
- avoid mixing manual and robot STOP/TAKE/PnL lifecycle;
- keep Robot v0.1 deterministic and compact;
- reuse existing authoritative PAPER position state rather than maintaining a duplicate robot-side position truth.

# END_OF_DOCUMENT
