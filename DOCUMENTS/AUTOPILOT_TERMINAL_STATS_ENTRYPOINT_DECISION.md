# AUTOPILOT Terminal Statistics Entrypoint Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The robot trading diary / statistics dashboard must be accessible directly from the Trading Workspace AUTOPILOT page.

Navigation flow:

`Trading Terminal -> AUTOPILOT button -> AUTOPILOT page -> Statistics / Diary button`

The statistics interface is part of the terminal product experience and must not require leaving the terminal for a separate external application or standalone analytics interface.

## Scope

The Statistics / Diary page opened from AUTOPILOT must expose the previously accepted analytics, including:
- profitability in USDT and percent over selectable periods;
- daily financial result;
- per-day ticker breakdown with traded tickers, trade count, and ticker PnL;
- average trade return;
- average holding time;
- win rate;
- profitable-to-losing trade ratio;
- time-of-day ranking in MSK;
- signal ranking;
- ticker ranking;
- STOP-protection and daily-drawdown block counts;
- completed trade count;
- accepted filters and drill-downs;
- factual vs counterfactual views needed for protection validation.

## UX principle

AUTOPILOT remains the operational control page. Statistics / Diary is reached from it through a dedicated button and opens as a terminal-integrated page/view with a clear route back to AUTOPILOT.

The exact visual layout and button label may be finalized later without changing this navigation decision.
