# LIVE acceptance standing authorization

Date: 2026-09-08

Status: ACTIVE

## Purpose

This document records the OWNER's standing authorization for small real-money LIVE acceptance trades used only to verify BybitScanner / Trading Workspace terminal behavior.

It supersedes any earlier acceptance note that required a new per-mutation confirmation for the bounded acceptance scope below. It does not make LIVE mutations generally enabled; runtime gates remain default-off and must be intentionally enabled only for the acceptance being executed.

## Standing authorization

For Terminal / Trading Workspace engineering, validation, reconciliation, regression acceptance, and closure work, the assistant may execute objectively necessary LIVE acceptance mutations without asking for a new confirmation each time when all of the following are true:

- each newly opened test position has intended notional between 6 and 10 USDT inclusive;
- by default, no more than one assistant-created LIVE acceptance position is open at a time;
- opening, protection, Limit, cancellation, and Full Close actions are scoped to the assistant-created acceptance position/order under test;
- resulting test exposure is closed when the acceptance workflow requires closure;
- account/session authority, symbol, quantity/notional, and exchange state are reconciled before mutation;
- UNKNOWN / RECONCILING / ambiguous transport remains fail-closed and never triggers blind retry;
- external or user-owned positions, orders, protection, and unrelated symbols are not mutated;
- existing exchange state is never re-labelled as assistant-owned merely because it is visible in Terminal.

This standing authorization includes small acceptance actions needed to exercise the terminal's Market, Limit, STOP, TAKE, cancellation, and Full Close paths within the bounded test exposure above.

## Actions still requiring a new OWNER decision

A separate explicit OWNER decision is required before:

- intentionally opening a test position above 10 USDT notional;
- intentionally maintaining multiple assistant-created LIVE test positions concurrently;
- mutating or cancelling an existing user-owned or external position, order, or protection;
- using LIVE acceptance execution as a trading strategy or profit-seeking operation rather than bounded product validation;
- materially expanding risk, leverage, exposure, or symbol scope beyond what is objectively necessary for the current acceptance;
- any destructive recovery whose financial consequence is not already bounded by this authorization.

## Runtime safety boundary

Standing authorization is an authorization boundary, not an always-on runtime configuration.

LIVE mutation capabilities remain default-off. Before each acceptance, enable only the minimum required capability/gate; after the acceptance and authoritative reconciliation, disable or stop that mutation-enabled runtime when no further authorized acceptance mutation is immediately required.

Durable idempotency, single-attempt ownership, account/session fencing, no-blind-retry behavior, REST/exchange reconciliation, and fail-closed UNKNOWN handling remain mandatory.

## Relationship to Manual Terminal v1 closure

`MANUAL_TERMINAL_V1_LIVE_ACCEPTANCE_CLOSURE_2026-09-08.md` recorded the acceptance campaign as it stood before this standing authorization was granted. Its statement that future real-money mutations require separate authorization is superseded only for the bounded acceptance scope defined here.

This document does not authorize Trading Robot / AUTOPILOT runtime implementation and does not alter Robot strategy, sizing, risk, STOP/TAKE, ownership, or recovery policy.
