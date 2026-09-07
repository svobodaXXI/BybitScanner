# AUTOPILOT Local Recovery: direction reset after full recovery

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

After a symbol completes local recovery and returns to 100% size, its temporary symbol-wide local recovery state ends and the symbol returns to separate directional STOP counters for LONG and SHORT.

Normal-state behavior:
- LONG and SHORT STOP counters are tracked separately for each symbol;
- if one directional counter reaches the local trigger threshold, the whole symbol enters local recovery;
- while local recovery is active, subsequent STOPs from either direction contribute to the symbol-wide recovery deterioration path;
- after full recovery to 100%, the symbol-wide recovery state is cleared and directional tracking resumes.

This restores the distinction between a direction-specific problem and a whole-symbol problem after the symbol has demonstrated full recovery.
