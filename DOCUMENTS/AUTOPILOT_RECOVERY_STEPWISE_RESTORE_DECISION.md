# AUTOPILOT Recovery Stepwise Restore Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

Recovery from reduced AUTOPILOT size is stepwise rather than an immediate jump back to full size.

Accepted ladder:

- 12.5% -> 25%
- 25% -> 50%
- 50% -> 100%

A completed successful recovery cycle restores exactly one level at a time.

This applies together with the previously accepted rules for STOP counters, pauses, local/global restrictions, and the 12.5% minimum recovery size floor.
