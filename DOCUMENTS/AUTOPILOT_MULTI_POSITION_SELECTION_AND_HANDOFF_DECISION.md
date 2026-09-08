# AUTOPILOT Multi-Position Selection and Handoff Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

When AUTOPILOT has multiple open positions:

- the main AUTOPILOT screen displays one selected current trade at a time;
- `Все открытые сделки` opens the list of all robot-controlled open positions;
- selecting a position from that list switches the AUTOPILOT chart, order book and current-trade card to that position's ticker;
- `Подробности сделки` always refers to the currently selected position;
- `Взять управление текущей сделкой` transfers only the currently selected position to the user;
- all other AUTOPILOT positions remain under robot control;
- after transfer, the selected ticker remains blocked for AUTOPILOT re-entry until the user fully closes the transferred position;
- once that transferred position is fully closed, the ticker becomes eligible again under the normal strategy and Portfolio Risk Engine rules.

## Rationale

This keeps the main screen focused, preserves the existing chart/order-book interaction model, avoids clutter from multiple simultaneous trade cards, and makes control ownership explicit per position.
