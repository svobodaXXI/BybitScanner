# AUTOPILOT Local Recovery Aggregation

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

Local STOP monitoring starts direction-aware per instrument: LONG and SHORT STOP counters are tracked separately for detecting the first local failure.

When either direction reaches the local STOP-series trigger of 5 protective STOP losses, the whole instrument enters local recovery.

From that point onward, local recovery for that instrument is aggregated across both directions:
- STOPs from either LONG or SHORT contribute to the instrument's local recovery deterioration;
- profitable closed trades on the instrument reduce the local recovery STOP count by 1, but not below zero;
- further local recovery steps apply to the whole instrument, not only the direction that caused the first trigger;
- the instrument follows the accepted recovery ladder: pause N -> 50%, then 2N -> 25%, then 3N -> 12.5%, with 12.5% as the minimum size floor;
- additional STOP-series triggers at the 12.5% floor increase pause length to 4N, 5N, 6N, ... while size remains 12.5%.

The global AUTOPILOT STOP counter continues independently and includes all qualifying STOPs from all instruments.

If local and global size restrictions are active simultaneously, the stricter restriction applies.
