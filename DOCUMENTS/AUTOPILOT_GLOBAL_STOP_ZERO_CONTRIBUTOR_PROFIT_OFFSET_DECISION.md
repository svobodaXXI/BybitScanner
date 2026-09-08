# AUTOPILOT Global STOP Zero-Contributor Profit Offset Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

If an instrument currently has global STOP contribution `0`, but a profitable completed AUTOPILOT trade on that instrument previously reduced the aggregate global STOP score by `0.5`, the next qualifying protective STOP on that same instrument is still processed normally.

Rules:
- instrument global STOP contribution: `0 -> 1`;
- aggregate global STOP score: `+1` from its current value;
- there is no separate debt, credit, or offset ledger attached to that instrument for the prior `0.5` aggregate reduction;
- the `0.5` reduction affects only the aggregate global STOP score at the time it is earned;
- subsequent qualifying STOP events remain ordinary `+1` events.

Example:
- before profit: BTC=3, ETH=2, SOL=0, global=5;
- profitable SOL trade: global `5 -> 4.5`, SOL contribution stays `0`;
- next qualifying SOL STOP: SOL `0 -> 1`, global `4.5 -> 5.5`.

This decision keeps instrument STOP contributions simple and prevents creation of hidden per-instrument fractional debt state.
