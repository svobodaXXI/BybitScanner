# AUTOPILOT Local Recovery: directional counters after full recovery

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

When a symbol fully recovers back to 100% size, its temporary symbol-wide recovery state ends and separate LONG/SHORT local STOP counters become authoritative again.

This means:
- during normal operation, each symbol has independent LONG and SHORT STOP counters;
- once one side reaches the local trigger threshold, the entire symbol enters symbol-wide recovery;
- while symbol-wide recovery is active, STOPs from either side contribute to further deterioration;
- after the symbol earns full recovery back to 100%, the symbol-wide recovery state ends;
- from that point onward, LONG and SHORT are monitored separately again.

The exact retained/reset values of the newly reactivated directional counters after full recovery are a separate decision and are not specified here.
