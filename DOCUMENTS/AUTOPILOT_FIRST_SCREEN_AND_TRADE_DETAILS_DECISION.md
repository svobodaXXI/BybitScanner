# AUTOPILOT First Screen and Trade Details — Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted first-screen AUTOPILOT summary

The AUTOPILOT page inside the trading terminal must show a concise operational summary directly on the first screen.

Required first-screen information includes:
- current-day PnL;
- number of completed trades for the current day;
- current STOP-series protection/block status;
- current daily-drawdown block status;
- currently effective STOP-protection size level when applicable;
- current AUTOPILOT operational state.

## Current trade card

For the currently focused/open AUTOPILOT trade, the first screen must show a compact trade card with:
- instrument/ticker;
- LONG/SHORT direction;
- basis/reason for entry;
- current reason for continuing to hold the position;
- current live PnL;
- current open position size;
- current STOP;
- current TAKE PROFIT;
- button/action: `Подробности сделки`.

The compact first-screen card should remain concise. Detailed explanatory text must not overload the main AUTOPILOT screen.

## Trade details view

`Подробности сделки` opens a dedicated details surface/window for the selected current trade.

It should contain the fuller trade-state explanation, including as available:
- full entry thesis / signal basis;
- confirmation conditions that were satisfied at entry;
- why the position is still being held now;
- what would invalidate the trade thesis;
- current STOP and TAKE logic;
- current PnL and position size;
- relevant risk-engine / STOP-protection constraints affecting the trade;
- material state changes since entry.

This view is explanatory/read-only unless a separately authorized trading control is explicitly included elsewhere in the product design.

## Open positions access

The AUTOPILOT page must include access to all currently open positions.

Use the existing trading-terminal interaction pattern where practical, preferably keeping the `open positions` control in the same or analogous location so the user does not need to relearn navigation.

The all-open-positions view should support selecting a position and opening that position's `Подробности сделки` view.

## UX principle

The AUTOPILOT first screen must answer two questions immediately:
1. `Что робот сейчас делает?`
2. `Почему он держит текущую позицию?`

Deep analytics remain available through `Статистика / Дневник`; deep trade reasoning remains available through `Подробности сделки`.
