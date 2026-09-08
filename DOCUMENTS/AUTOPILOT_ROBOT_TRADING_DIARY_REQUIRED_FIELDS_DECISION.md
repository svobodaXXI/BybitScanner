# AUTOPILOT Robot Trading Diary — Required Fields Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

The robot trading diary must record, at minimum, the following data for each fully completed AUTOPILOT position lifecycle:

- instrument and direction;
- entry time and full-close time;
- entry reason / signal / pattern;
- planned size and actual size;
- average entry price;
- all partial closes;
- final exit reason: STOP / TAKE / strategy / manual / emergency;
- final net PnL including actual fees and funding;
- result in percent, USDT, and R;
- maximum favorable excursion and maximum adverse excursion before full close;
- whether local/global STOP protection was active at entry;
- effective STOP-protection size level: 100% / 50% / 25% / 12.5%;
- whether emergency STOP override was active;
- global STOP-score and relevant local STOP state at entry and exit;
- market regime and correlation / Portfolio Risk Engine state;
- a counterfactual record of what would have happened without STOP protection whenever STOP protection changed trade size or blocked an entry.

## Rationale

The counterfactual record is mandatory because the PAPER validation must determine not only the realized result under protection, but also whether the protection reduced drawdown at an acceptable opportunity cost. Without tracking blocked or reduced trades, the system cannot reliably distinguish useful protection from over-restriction.

## Scope

This is the mandatory minimum dataset. Additional implementation-level telemetry, identifiers, timestamps, audit fields, and persistence metadata may be added without further user confirmation as long as they do not alter trading behavior or risk policy.
