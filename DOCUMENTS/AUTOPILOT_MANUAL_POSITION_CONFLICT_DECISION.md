# BybitScanner — AUTOPILOT Manual Position Conflict Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

Decision:

For Robot v0.1, if a manual PAPER position already exists on a symbol, the robot must not open a robot-controlled position on that symbol.

The robot candidate is marked:

`BLOCKED_BY_MANUAL_POSITION`

Rationale:

- preserve one unambiguous controller/owner per symbol position;
- avoid mixing manual and robot STOP/TAKE ownership;
- keep PnL/accounting attribution deterministic;
- preserve simple future handoff semantics;
- reuse the existing authoritative PAPER position state instead of creating a parallel robot position view.

This decision applies to Robot v0.1 and does not yet define behavior when a manual position appears after robot approval but before breakout.

# END_OF_DOCUMENT
