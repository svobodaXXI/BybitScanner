# Ikigai Box — two-impulse Fibonacci reversal (user-defined PAPER strategy)

Status: **observational geometry/opt-in Scanner WATCH implemented; Robot execution NOT implemented**.
Scope: Scanner recognition, Telegram observation charts, and later separately
authorized PAPER Robot execution. This is **not** the
ordinary horizontal-range breakout/rectangle pattern. The 2026-09-20 user screenshot and
explicit trading decisions in the current conversation take precedence over the obsolete
`DOCUMENTS/BACKLOG.md` G5 "horizontal range / breakout" text.

## 1. Source references and status

- `training/reference_patterns/HEIUSDT/post_pump_two_drop_fib_1618_1h/annotation.json`:
  first downward impulse, consolidation, second downward impulse to extension 1.618,
  LONG reversal and target 1.0. Recorded historical levels ~0.1436 (1.0) and ~0.12235
  (1.618). The source's description of *dragging* the Fibonacci tool must not replace the
  explicit numeric-level orientation below.
- `training/reference_patterns/AEONUSDT/ikigai_box_15m/annotation.json` and
  `outcome_01.json`: a bearish wedge breakdown, two-drop setup and subsequent recovery;
  price can exceed 1.618 before bottoming. Observational, not a universal trigger.
- `training/reference_patterns/VELVETUSDT/ikigai_boxes/annotation.json`: recorded
  nested examples; moderate overshoot of 1.618 alone did not invalidate the example.
- `training/reference_patterns/CHIPUSDT/multitimeframe_confluence/annotation.json`:
  recorded 5m Ikigai Box reversal and separate 1m triangle/L-shape continuation.
- The user-provided 2026-09-20 screenshot gives the *mirrored SHORT example*: impulse 1
  UP (start marked 2, peak marked 1), intervening consolidation, second UP impulse
  through the 1.618 region toward 2.618, then declining price. Do not mistake the
  2.618 price extension for the first-impulse endpoint.
- `DOCUMENTS/TRADING_STRATEGY_SPEC.md` §6/H-011 describes a **separate**
  post-impulse mirror-range research hypothesis. Its statement that 1.618 is not
  an independent trigger for that *hypothesis* must not silently override the
  user-defined Ikigai Box advance-limit entry plan. Neither constitutes evidence
  of profitability; actual PAPER fills, stop risk and execution costs require validation.

## Owner clarification: first-impulse reversal, candle colour and consolidation (2026-09-23)

For CPUSDT 5m and both directions generally, the first impulse A starts at
the **actual local reversal extreme**, not a later convenient candle. It is
an initially directional, predominantly single-colour candle sequence: green
for UP and red for DOWN. Small opposite-colour candles are allowed only while
they do not create zigzag price action or a material countertrend swing. Do
not apply an absolute "first opposite colour ends the impulse" rule. The
first substantial opposite-direction/zigzag move terminates the initial leg;
B must remain at the last valid impulse-direction candle/extremum, before the
independent consolidation. After B, consolidation may alternate colours in
any order and must never be merged into impulse 1 or used to relocate A/B.
Apply to upward and downward cases and both CONFIRMED and WATCH at initial
candidate construction, using decision-time closed candles. "Small" and
"zigzag" need reproducible source-time criteria validated against actual
reference windows before coding; do not silently invent a numeric threshold.
This rule supersedes older first-leg candle-colour/wick exceptions insofar
as they allow materially zigzag/mixed first impulses or consolidation candles
to be included in A→B. It does not change Fibonacci arithmetic, second-leg
rules, risk or Robot trading authorization. Implementation and full owner
Telegram acceptance remain queued under `DOCUMENTS/BACKLOG.md`.

## 2. Structure, anchors and Fibonacci math

**SHORT / upward mirror:**
1. Identify the beginning `A` (lowest valid origin of first UP impulse) and its
   ending peak `B` (highest valid terminal extremum before consolidation), using
   only evidence available at the detection candle. Store both exact candle indices,
   timestamps and prices; do not substitute a shelf extremum or later second-impulse high.
2. Confirm consolidation/box between impulse 1 and impulse 2. A horizontal range
   alone, without the ordered two-impulse structure, is not this pattern.
3. Detect an upward second impulse approaching the calculated 1.618 extension.
   Anticipatory SHORT entry grid is around 1.618; if the first trade is confirmed
   stopped and price continues, 2.618 is the one allowed secondary entry area.

**LONG / downward mirror:** `A` is the beginning HIGH of the first DOWN impulse
and `B` is its ending LOW before consolidation; the second impulse is DOWN, and
the entries near 1.618/2.618 are LONG. The first impulse and second impulse have
the **same** direction. Do not reinterpret the first leg as a preceding opposite
trend or replace the two-impulse sequence with a generic rectangle.

**First DOWN impulse / box boundary (FLOCK 5m acceptance, 2026-09-20):**
A and B are the wick extremes of the first impulse; each may belong to an
adjacent green boundary candle, provided all candle bodies strictly between
A and B form one uninterrupted bearish (red) run. A green or doji candle
*inside* that red core splits the run. A/B are frozen independently of later
box wicks or the second impulse; this narrower red-core rule currently applies
to DOWN impulses only, without silently changing the established UP detector.

A consolidation box may briefly wick **past B** before the second impulse
(for LONG, below B; for SHORT, above B). That wick does not redefine B.
The ordinary full box range remains limited to 55% of the A/B impulse span.
As a bounded alternative when full range exceeds 55%, retracement measured
*from B in the opposite direction* must remain <=55% of the span, and the
overshoot past B in the impulse direction must remain <=12% of the span,
subject to the existing impulse-specific retracement gates. This is a
geometry/WATCH allowance only, **not** proof of a valid entry or permission
to place an order. FLOCK's observed 5m example had 54.89% retracement and
5.33% overshoot; no threshold was increased to accommodate it.

**Numerical convention, independent of the charting tool's click/drag direction:**

`F(r) = A_price + r * (B_price - A_price)`.

`F(0)=A_price` (first-impulse origin), `F(1)=B_price` (first-impulse terminal
extremum), `F(1.618)` and `F(2.618)` extend **beyond B in the same direction as
impulse 1**. For SHORT, `F(2.618) > F(1.618) > F(1)`; for LONG, inequalities
reverse. Freeze the two original anchors once the setup is emitted: no hindsight
re-anchoring from impulse 2 or later reversal candles.

The Telegram signal chart must show the entire first impulse, consolidation,
second impulse so far, exact A/B markers, Fibonacci 0/1/1.618/2.618 price lines,
both candidate entry zones and the tentative 1.0 target. Plot only information
known at signal time; label entry/STOP/TP as planned rather than filled or
guaranteed. This is a *different* Fibonacci convention and trading lifecycle from
the separate L-shape impulse-retracement preview.

## 3. Entry and position management — user-approved intent, NOT wired to Robot

- **Attempt 1:** four approximately equally spaced price LIMITs in the zone of
  `F(1.618)`, each of size **1/4 РО** (user-defined working order volume),
  together limited to one total РО. The furthest limit extends *past* 1.618
  in the second impulse's direction: **above** 1.618 for SHORT, **below** for
  LONG. The grid is placed *before* the intended reversal; a reversal candle
  is desirable for structural STOP selection but is **not a prerequisite** for
  placing the advance grid when the fallback STOP is available. Exact spacing,
  zone width and anchoring are **not yet specified**; never hard-code a price
  distance or assume all four orders are filled.
- **STOP:** prefer the confirmed suitable reversal candlestick's protective
  extreme: SHORT above the bearish engulfing/shooting-star high; LONG below the
  bullish engulfing/hammer low. The extreme must produce a valid protective
  level for the actual fill, with normal tick/fee/technical safety constraints.
  If no suitable *confirmed* candle is available, or no valid structural STOP
  can be constructed, fallback is **-1.5% from actual quantity-weighted entry**:
  LONG `average_entry * 0.985`; SHORT `average_entry * 1.015`, subject to
  proper tick rounding in the protective direction. All actually filled
  exposure needs protection immediately, including partial-grid fills.
  Do not leave a filled position unprotected awaiting candlestick confirmation.
  Exact additional buffer beyond an extreme remains **unspecified**.
- **Attempt 2 (only after stopped attempt 1):** after a **confirmed STOP close**
  of the first trade, **verified FLAT position**, no unresolved exit/protection
  obligation, and cancellation/terminal state of *all* unfilled limits from
  the first grid, wait for the second impulse's continuation toward `F(2.618)`.
  Only then allow a **new** four-limit grid, each **1/4 РО**, around 2.618,
  with the furthest limit beyond 2.618 in impulse direction. Use the same STOP,
  early partial exit and 1.0-target policy. An ambiguous STOP reason, unresolved
  partial position, uncertain ownership or still-active earlier LIMIT blocks
  attempt 2. **At most two sequential attempts per frozen formation**, no
  overlapping grids, doubling, martingale, or averaging the stopped trade.
- **TP:** the common principal target is **F(1.0)**. Start partial profit taking
  *before* that level, then move the remaining position's STOP to fee-aware
  breakeven. Exact partial-exit fraction, trigger price/offset and breakeven
  buffer are **user decisions still pending**: not an execution-ready policy.
  No position size, STOP or TAKE may be fabricated from these placeholders.
- **Potential (planning metric):** measured on the frozen first-impulse
  Fibonacci from the entry reference `F(1.618)` to the common target `F(1.0)`.
  Rising first impulse (SHORT setup): from `F(1.618)` down to `F(1.0)`. Falling
  first impulse (LONG setup): from `F(1.618)` up to `F(1.0)`. Percentage
  potential = `abs(F(1.0) - F(1.618)) / F(1.618) * 100`, reported as a
  magnitude. It is measured from the level, not from actual fills or the
  average entry, and is before fees/slippage. Example: FLOCKUSDT LONG
  `0.062549 -> 0.06533` = approximately +4.45%. It is a display/planning
  figure only and changes no STOP, TAKE, sizing or execution rule.

## 4. Minimal implementation boundary / non-goals

1. Read-only structure detector first: frozen A/B, impulse/box/second-impulse
   index ranges, directional Fibonacci levels, detection-time provenance;
   explicit UNKNOWN for ambiguous anchors. Reject standalone ranges and
   after-the-fact second-impulse rebasing. Conservative named, tunable pattern
   thresholds require focused offline validation against the reference cases.
2. Scanner/Telegram signal integration after deterministic detection and a
   visually checked example, reusing the same frozen geometry. **Do not** label
   a planned limit as placed or pass Box through the Wedge apex-based Robot
   lifecycle or its existing pattern-direction allowlist.
3. PAPER-only four-order entry and two-attempt Robot lifecycle require a
   separate, focused, test-verified implementation and explicit resolution of
   grid placement, available collateral/risk cap, partial fills and multiple
   protective/TP orders, early partial close/BE levels, STOP selection timing,
   restart persistence and fail-closed ownership. No LIVE execution authority.
4. This document records design intent and examples; it does **not** assert
   positive expectancy, completed implementation, actual exchange-side
   protective orders, or readiness to run against the working PAPER database.

## 5. Chart/card trade overlay — presentation only (implemented)

`geometry/ikigai_box_overlay.py` + `geometry/ikigai_box_chart.py` draw a PLANNED
trade overlay on the Ikigai Box chart. Detection, Scanner, Telegram, Robot
admission, order placement and candidate creation are untouched.

- **Fibonacci grid = the terminal tool.** The signal PNG mirrors
  `terminal/frontend/src/chart/drawingModel.ts` and `DrawingOverlay.tsx`:
  levels `0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236`,
  price `first + (second - first) * level` with first = A, second = B (equal to
  the frozen `fibonacci_price`), a translucent band between every ADJACENT pair
  of levels, the terminal's five-colour palette cycled by band index, the
  terminal line colour and `level  price` labels. Only the fill opacity is lifted
  for a white PNG; off-screen levels are clipped as in the terminal.
- Stage label: `BOX_READY` / `BOX_BREAK_OBSERVED` / `CONFIRMED`, plus whether
  `F(1.618)` has been touched by a closed candle after B (through `as_of` only).
- `F(1.618)` not reached: observation only, **no** entry zone, grid or STOP.
- `F(1.618)` reached: four LIMITs, each 1/4 РО, equally spaced. Most of the grid
  (3 of 4) sits on the APPROACH side of 1.618 — it fills before price reaches the
  level — and only the furthest LIMIT is beyond it (for LONG: three above 1.618,
  one below; SHORT is the mirror). This distribution is the user's instruction:
  the terminal Fibonacci tool defines NO limit-order placement rule, so nothing
  about spacing or the split was copied from it.
- STOP: extreme of the latest closed reversal candle (bearish engulfing /
  shooting star for SHORT; bullish engulfing / hammer for LONG) when it
  protects the planned entry; otherwise fallback -1.5% from the planned equal-
  weight average entry (LONG below, SHORT above).
- Target: `F(1.0)`, with only a text note that partial profit-taking starts
  before it.

Still **not** decided or implemented: the real grid spacing (the drawn step is a
visualisation placeholder, `GRID_STEP_FRACTION`), partial-take trigger/fraction,
fee-aware breakeven stop, attempt 2 at `F(2.618)`, any order execution, and the
Scanner caption text. `build_entry_grid(anchor_level=...)` is reusable for the
2.618 grid but no second-attempt logic exists.
