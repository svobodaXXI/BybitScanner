## Problem
SHADOW kept 19/19 virtual RO reserved with zero open positions, so every new candidate got `WAIT PORTFOLIO_AGGREGATE_CAP`. Only the Wedge `EXPIRED_AT_APEX_NO_RETEST` rule could release a virtual reservation. Two cases could never release:
- a Wedge that was retested;
- any Ikigai Box, because no producer existed for Box plans.

## Change (one file + tests + contract note)
`terminal/application/wedge_source_terminal_producer.py` now proves two more terminals from closed 1m candles, using only existing pattern rules. It appends the same immutable sidecar event with status `EXPIRED` and its own `rule` plus evidence `outcome`:

| Rule | Proven when |
|---|---|
| `WEDGE_RETEST_TAKE_REACHED_AFTER_APEX` v1 | BREAKOUT → RETEST before the apex, then a candle **strictly after the apex candle** reaches the Robot's frozen TAKE (`frozen_take_90`, which does not depend on the fill price). The retest LIMIT is cancelled at the apex, so every branch is over: never filled, filled and TAKE, or filled and an earlier STOP. |
| `IKIGAI_BOX_FIRST_GRID_EXIT_REACHED` v1 | The frozen plan's P1 is touched, then a **strictly later** candle reaches its common TAKE (#416 completion) or its shared STOP beyond the full grid. A candle that touches P1 and an exit at once is ambiguous and never counts as the exit. |

**Opportunity over vs. position closed.** The event says only that the observed opportunity is over. It never claims a position closed. A linked Robot candidate going `CLOSED` stays the only release for a closed position, and no fill or closure is simulated.

**Gates unchanged:**
- exact identity (snapshot SHA, symbol, `BOX_PLAN_ONLY` source);
- no physical obligation on the symbol;
- idempotent append (repeats and restarts return `ALREADY_TERMINAL` without refetching);
- gap-free closed candles; the newest row is ignored;
- bounded windows: post-apex ≤ 2000 min, Box ≤ 3000 min after the decision minute;
- same fetch budget and rotation.

Unchanged: the 19 RO cap, PAPER_AUTO, admission, orders, LIVE, and the sidecar schema.

## Still BLOCKED (kept reserved, no proof)
- **Retest then STOP** without a later TAKE: the STOP depends on the actual fill price, which closed candles cannot prove.
- **Scanner-side Wedge invalidation:** no durable producer exists.
- **20-candle breakout timeout:** accepted design, never implemented.
- **Box never entered:** there is no age-based expiry.
- **Anything beyond the bounded windows.**

## Evidence
- `tools.dev.task finish`: **PASS** (task-delta, inverse proof, compile, focused tests, isolated scope, diff check).
- Focused tests: `test_wedge_source_terminal_producer.py` 44 passed (new cases: Wedge retest TAKE, pre-apex-only TAKE, forming row, SHORT symmetry, Box TAKE/STOP, ambiguous bar, no entry, gap, historical window, repeat + restart without double release, identity mismatch, physical obligation). Adjacent worker, sidecar and portfolio tests: 86 passed.
- **Dry run on a copy** of the live PAPER DB with public 1m klines (the real DB and sidecar were not touched): occupied RO **19 → 8**. Released: all 6 Box (3 TAKE, 3 STOP) and 5 retested Wedges (TAKE after the apex). The remaining 8 are all retested Wedges whose TAKE was not reached within 2000 minutes after the apex, which is the BLOCKED scenario above.

No merge. The live runtime keeps the old producer until the owner restarts on the merged code.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
