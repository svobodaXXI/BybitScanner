# BybitScanner — AUTOPILOT Strategy Addendum Errata

Date: 2026-09-07
Status: ACTIVE / DESIGN CORRECTION
Applies to: `DOCUMENTS/AUTOPILOT_STRATEGY_ACCUMULATED_DESIGN.md` v1.1
Implementation authorization: NONE

This errata corrects one over-constrained interpretation in addendum v1.1.

## Corrected MVP scope

The initial AUTOPILOT scope is:

- one selected trading account is controlled by AUTOPILOT at first;
- development/acceptance may begin with one selected trading pair as the initial test instrument;
- this does **not** impose a strategy or architecture rule that only one position or only one symbol may be active at a time;
- when the scanner universe is later expanded beyond the initial test pair, AUTOPILOT may manage multiple simultaneous positions on that same account, subject to the account-level risk/exposure policy;
- the allowed simultaneous-position count is owned by risk/exposure policy, not by a hard-coded `1 active symbol` rule;
- the existing robot aggregate exposure ceiling of `19 WV` remains a separate account-level constraint; exact concurrent-position, correlation and portfolio-heat limits remain to be defined and validated.

## Architecture invariant retained

The correction does not change these requirements:

- strategy logic remains account-neutral;
- explicit `account_id`, `symbol`, `setup_instance_id` and `account_trade_id` are retained;
- PAPER and LIVE must not become separate strategy implementations;
- execution adapters, authority fencing, authoritative fills and reconciliation semantics remain shared architectural seams;
- multi-account operation remains a future extension.

## Superseded statements

Any statement in addendum v1.1 that says or implies:

- `exactly one selected trading pair/symbol is actively traded at a time`;
- `one active setup/trade lifecycle` as a hard MVP execution limit;
- `single-account and single-pair in runtime scope`;
- multi-symbol operation is necessarily deferred until after single-pair stabilization;

is superseded by this errata.

The intended meaning is: **one account initially, one pair as the first test scope, but no architectural one-position/one-symbol ceiling.**

# END_OF_DOCUMENT
