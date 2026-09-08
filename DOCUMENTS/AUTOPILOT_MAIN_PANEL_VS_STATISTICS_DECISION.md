# AUTOPILOT Main Panel vs Statistics — Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The AUTOPILOT main panel is a live trading/control surface, not a statistics dashboard.

Move these metrics out of the AUTOPILOT main panel and into the separate Statistics / Trading Journal window:
- day PnL;
- number of trades;
- STOP-protection block counts / current STOP-protection level;
- daily-drawdown block information;
- other aggregate historical/session analytics.

The AUTOPILOT main panel keeps current live trading context only.

## Main AUTOPILOT surface

The main AUTOPILOT surface includes:
- the shared live chart;
- the live DOM/order book;
- visible working/open orders and their execution on both chart and DOM where applicable;
- current/open position information;
- concise current-trade context such as entry basis, current hold rationale, current PnL, open position size, STOP and TAKE;
- access to `Подробности сделки` for expanded reasoning/status;
- access to the list of all open positions using the same familiar terminal interaction/location pattern where practical.

## Statistics / Trading Journal

Aggregate and historical analytics belong to the separate Statistics / Trading Journal page opened from AUTOPILOT.

This separation is intentional:
- main AUTOPILOT = what the robot is doing now and how the live trade is being managed;
- Statistics / Journal = what the robot has done historically, performance, protection activity, rankings, daily results and filtered analytics.

## Live visibility invariant

The chart and DOM are first-class live observability surfaces. The user must be able to watch orders being placed, amended/cancelled where applicable, and executed in real time through those surfaces, consistent with the shared terminal trading UI.
