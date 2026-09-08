# BybitScanner — AUTOPILOT Global STOP Diversity Distribution Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

Global STOP protection is not eligible to trigger from one instrument alone.

The global STOP trigger threshold remains 5 qualifying STOP-loss events, but the five events must show meaningful cross-instrument breadth:

- qualifying STOP events must come from at least 2 distinct instruments;
- the second contributing instrument must contribute at least 2 qualifying STOP events;
- therefore the narrowest eligible 5-STOP distribution is `3 + 2` across two instruments;
- a `4 + 1` distribution is NOT sufficient for global protection;
- a `5 + 0` distribution is local-only and is NOT sufficient for global protection.

This rule preserves the distinction between local instrument failure and genuinely broader AUTOPILOT stress.

Local STOP protection remains independent and continues to apply to the affected instrument according to the accepted local recovery ladder.

# END_OF_DOCUMENT
