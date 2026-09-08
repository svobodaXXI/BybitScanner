# AUTOPILOT Global STOP Contribution Profit Decrement Decision

Version: 1.0  
Date: 2026-09-08  
Status: ACTIVE / DESIGN-ONLY  
Implementation authorization: NONE

## Decision

When a completed AUTOPILOT trade is profitable, the global STOP contribution is decremented for the same instrument on which that profitable trade occurred.

Example:
- BTC global STOP contribution = 3
- ETH global STOP contribution = 2
- global STOP total = 5
- a profitable BTC trade completes

Result:
- BTC contribution: 3 -> 2
- ETH contribution: 2
- global STOP total: 5 -> 4

The per-instrument contribution ledger and global total must remain consistent. A profit on instrument X does not decrement another instrument's contribution.

Floor for every per-instrument contribution is 0.
