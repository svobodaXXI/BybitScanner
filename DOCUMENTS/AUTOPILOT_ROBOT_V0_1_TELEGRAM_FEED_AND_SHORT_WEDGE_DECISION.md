# AUTOPILOT Robot v0.1 — Telegram feed, position navigation, and short wedges

Status: DESIGN DECISION
Date: 2026-09-08
Implementation authorization: NONE

## Main Robot surface

The main Telegram `Робот` tab is a feed of event/state posts, not an interactive chart screen.

Each important lifecycle transition creates a separate post:
- signal accepted for robot observation;
- trade opened;
- trade closed;
- explicit current-state post requested by selecting a position from `Все позиции`.

## Static chart snapshots

Charts in Robot v0.1 are static generated images, not interactive charts.

A current-state position post must include a fresh chart image with the currently authoritative trade state rendered on it, including where applicable:
- scanner pattern geometry and wedge lines;
- signal timeframe;
- current/average entry price line;
- STOP line;
- TAKE line;
- executed-trade markers (triangles) for actual entries/exits;
- current relevant price context.

The renderer must consume the stored/versioned signal/trade snapshot plus authoritative execution state. It must not create a second source of trading state or recompute scanner geometry independently.

## `Все позиции`

`Все позиции` is a separate screen.

It uses the previously accepted ranking policy:
1. the currently selected/displayed position first;
2. then larger and more promising positions;
3. remaining positions below.

Selecting a position from this screen returns to / updates the main `Робот` feed by publishing a new current-state post for that position with full information and a fresh chart snapshot.

## `Под наблюдением`

The Robot menu includes a separate `Под наблюдением` action/screen.

It shows approved robot candidates that have been handed to the robot but have not yet opened a position, including their current lifecycle state such as `WAITING_BREAKOUT` and remaining validity where available.

## Direction support in v0.1

Robot v0.1 trades both wedge directions:

- Falling Wedge -> LONG
- Rising Wedge -> SHORT

The short side is the mirror of the already accepted long policy:
- wait for the first closed 1m candle below the frozen lower Rising Wedge boundary;
- enter PAPER short automatically with the already accepted fixed `1 WV` intent;
- preferred STOP is above the breakout candle high by the technical buffer, subject to the same 2% maximum structural-stop distance rule; if the preferred structural STOP would exceed 2% from actual entry, use the fixed 2% fallback above actual entry;
- TAKE uses the existing scanner `potential_percent`, applying 90% of that potential from the actual entry price downward;
- no second user confirmation is requested before entry.

## Approval semantics

The only user approval is pressing `Робот` next to the scanner signal.

After successful handoff:
`APPROVED -> WAITING_BREAKOUT -> automatic PAPER entry -> OPEN -> managed exit -> CLOSED`.

No additional `WAITING_CONFIRMATION` state or pre-entry confirmation button exists in Robot v0.1.

## Reuse rule

Telegram presentation, position navigation, chart generation, robot lifecycle and PAPER execution must reuse authoritative project capabilities. No duplicate position store, accounting source, scanner geometry engine, potential calculator or execution lifecycle is introduced for this UI.
