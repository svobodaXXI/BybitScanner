# AUTOPILOT Global Recovery Ladder Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

Global STOP-protection recovery uses the same size ladder and progress requirements as local recovery.

Recovery ladder:
- 12.5% -> 25%
- 25% -> 50%
- 50% -> 100%

Each upward step requires exactly 5 recovery-progress units.

This keeps local and global recovery semantics aligned unless a later explicit decision changes them.
