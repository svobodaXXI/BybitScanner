# AUTOPILOT — Open Positions Ranking Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted UX rule

The `Все открытые сделки` view must rank currently open AUTOPILOT positions.

### Fixed first row

The position currently selected on the AUTOPILOT main screen and displayed on the chart is always pinned to the first row of the open-positions list.

### Ranking of all remaining positions

All other open positions are ordered by a robot-derived ranking that prioritizes larger and more promising positions above lower-priority positions.

The ranking should consider, at minimum:
- current position size / engaged working volume;
- current signal / trade quality and remaining opportunity;
- current trade state and whether the original thesis remains valid;
- current risk / reward context;
- current unrealized PnL only as one input, not as the sole ranking criterion.

The exact weighting/formula is an implementation/tuning detail and should remain adjustable during PAPER validation without changing this UX contract.

### Selection behavior

Selecting another position in `Все открытые сделки` makes it the active AUTOPILOT view:
- its ticker is shown on the chart;
- its order book is shown;
- its signal geometry/context is shown;
- `Подробности сделки` refers to it;
- `Взять управление текущей сделкой` refers to it;
- on the next opening of the positions list, this selected position is pinned to row 1.

## Rationale

The operator should always be able to find the position currently visible on the main screen immediately, while the rest of the list should surface the positions that deserve the most attention rather than being ordered arbitrarily or only chronologically.
