# AUTOPILOT Emergency Override Recovery Accounting Decision

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Accepted decision

While an emergency override is active, the STOP/recovery accounting mechanism continues to operate normally.

- A qualifying profitable completed trade improves recovery progress by +1.
- A losing completed trade worsens recovery progress by -1, floor 0.
- A qualifying protective STOP is processed by the normal STOP-counter and recovery rules.
- Break-even remains neutral.

The emergency override only bypasses the currently applied risk-size restriction. It does not freeze, suspend, or erase diagnostic risk accounting.

This preserves the previously accepted rule that the override is temporary and does not delete STOP counters or recovery state.
