# AUTOPILOT STOP-streak scope policy

Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

STOP-streak protection operates on two levels simultaneously:

1. Global AUTOPILOT scope
   - one STOP counter across the whole AUTOPILOT portfolio;
   - when the global threshold is reached, the recovery restriction applies to the whole AUTOPILOT.

2. Per-instrument scope
   - each trading instrument/symbol has its own STOP counter;
   - when the local threshold is reached, the recovery restriction applies only to that instrument.

Current shared threshold:
- STOP trigger threshold = 5;
- qualifying protective STOP = +1;
- profitable fully closed trade after actual costs = -1;
- counters cannot go below 0.

The current recovery ladder is:
- first triggered level: pause N candles, then 50% of normal requested size;
- second triggered level: pause 2N candles, then 25%;
- third and further triggered levels: pause kN candles for level k, while size is halved each level but never below the accepted floor of 12.5%;
- at 00:00 MSK the restriction state relaxes by exactly one level, subject to stricter active portfolio-risk gates.

The stricter applicable restriction wins when both global and per-instrument protection are active.
