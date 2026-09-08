# AUTOPILOT STOP Protection — Emergency Override Full-Size Decision

Version: 1.0  
Date: 2026-09-08  
Status: ACTIVE / DESIGN-ONLY  
Implementation authorization: NONE

## Accepted decision

While an emergency STOP-protection override is active, new AUTOPILOT entries use the normal full allowed size (`100%`) even if the internal recovery level is lower (for example `25%`).

The override therefore bypasses active local and global STOP-series size restrictions for execution sizing while it is active.

This does not erase or freeze the underlying STOP counters or recovery state. Internal recovery accounting continues under the previously accepted rules, and the override ends under its separately defined termination conditions.
