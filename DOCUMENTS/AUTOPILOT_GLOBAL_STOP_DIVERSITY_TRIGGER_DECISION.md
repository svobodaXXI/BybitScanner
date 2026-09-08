# BybitScanner — AUTOPILOT Global STOP Diversity Trigger Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

A single instrument must not be able to trigger the global AUTOPILOT STOP-series protection by itself.

Global STOP statistics still include qualifying STOP events from all instruments, including instruments that are already under local protection.

However, the global protection becomes eligible only when the qualifying STOP activity is distributed across multiple distinct instruments.

Therefore:

- a bad streak confined to one instrument remains a local-protection event;
- broad deterioration across multiple instruments may trigger the global protection;
- the exact minimum number of distinct instruments required for the global trigger remains a separate design decision;
- local and global protections remain independent, and when both apply to an instrument, the stricter size restriction wins.

This supersedes any interpretation under which one instrument alone can activate the global STOP-series protection merely by accumulating enough qualifying STOP events.

# END_OF_DOCUMENT
