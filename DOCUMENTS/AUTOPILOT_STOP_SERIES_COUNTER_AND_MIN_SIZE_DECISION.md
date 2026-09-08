# AUTOPILOT STOP-series counter and minimum recovery size

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decisions

1. STOP-series trigger threshold is 5 qualifying STOPs.
2. A profitable closed trade does not fully reset the STOP counter; it partially reduces it.
3. The exact decrement per profitable trade is not fixed yet and remains NEEDS VALIDATION on PAPER unless separately decided.
4. Recovery-size floor is 12.5% of the strategy-requested size.
5. The recovery ladder therefore does not reduce below 12.5%.

Current ladder:
- first qualifying STOP-series trigger -> pause N -> 50% size;
- second trigger while recovering -> pause 2N -> 25% size;
- third trigger while recovering -> pause 3N -> 12.5% size;
- further triggers at the floor may extend/escalate pause according to the same recovery logic, but size remains at 12.5% unless another rule is explicitly adopted.

Trading-day rollover remains one recovery level softer than the level at the end of the previous day, subject to all stricter active portfolio-risk gates.

A profitable trade is counted only after the position is fully closed and net result after actual fees/funding is > 0, per the existing recovery-profitability decision.
