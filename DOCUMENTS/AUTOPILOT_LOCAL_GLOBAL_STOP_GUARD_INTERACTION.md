# AUTOPILOT local/global STOP-guard interaction

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

AUTOPILOT maintains both:
- a global STOP-series protection level for the whole portfolio;
- a local STOP-series protection level for each instrument.

When both are active for the same instrument, the stricter active restriction wins.

Conceptually:

`EFFECTIVE_RECOVERY_SIZE(symbol) = min(GLOBAL_RECOVERY_SIZE, LOCAL_RECOVERY_SIZE(symbol))`

Examples:
- global 50%, BTC local 25% -> BTC trades at 25%; other instruments may trade at 50% if they have no stricter local restriction;
- global 12.5%, BTC local 50% -> BTC trades at 12.5%;
- local 12.5% and global 100% -> that instrument remains at 12.5% while others can remain unrestricted.

The same strictest-gate principle applies to pauses and new-risk admission: a stricter active global or local protection cannot be overridden by a weaker protection at the other scope.

Existing STOP-series rules remain in force:
- trigger threshold: 5 STOPs;
- each negative protective STOP adds +1;
- each profitable closed trade after actual costs subtracts 1 from both the local counter for that instrument and the global counter, floor 0;
- recovery size ladder: 100% -> 50% -> 25% -> 12.5%, with 12.5% as the lower bound;
- pause ladder: N -> 2N -> 3N for successive restriction levels, with exact base N to be validated on PAPER;
- at the new trading day boundary (00:00 MSK), active restriction level steps back by exactly one level, subject to other stricter risk gates.
