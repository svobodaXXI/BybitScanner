# BybitScanner — AUTOPILOT Global STOP Diversity Threshold Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

Global STOP protection must not be eligible to trigger from only one instrument.

A global STOP trigger requires:

- the global STOP counter to reach its trigger threshold of 5 qualifying STOPs; and
- those qualifying STOPs to include activity from at least 2 distinct instruments.

Therefore, five qualifying STOPs from a single instrument can trigger that instrument's local protection, but cannot by themselves trigger the global AUTOPILOT protection.

Once at least two distinct instruments are represented among the qualifying STOP activity, the global protection may trigger when the global counter reaches 5, subject to all other accepted global STOP rules.

This preserves the distinction between local strategy/instrument failure and broader portfolio-wide deterioration.

# END_OF_DOCUMENT
