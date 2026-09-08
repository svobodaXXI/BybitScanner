# AUTOPILOT Local STOP Direction Policy

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

Local STOP accounting for each instrument is tracked separately by direction (LONG and SHORT), but a local protection trigger on either side applies to the entire instrument.

Rules:
- each instrument maintains separate local LONG and SHORT STOP counters;
- the accepted STOP-series threshold remains 5;
- if either the LONG or SHORT local counter for an instrument reaches the trigger threshold, that instrument enters its local protection state for both directions;
- while the local pause is active, no new LONG or SHORT risk is opened or increased for that instrument;
- other instruments remain governed by their own local state and the global AUTOPILOT state;
- all qualifying STOP events still contribute to the global AUTOPILOT STOP counter;
- the effective position-size limit remains the strictest active limit among local and global controls.

This allows diagnosis by direction while preventing the opposite side of the same instrument from immediately bypassing a demonstrated local failure state.
