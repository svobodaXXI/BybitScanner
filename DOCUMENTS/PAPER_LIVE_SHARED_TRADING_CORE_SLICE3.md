# PAPER / LIVE SHARED TRADING CORE — SLICE 3

Date: 2026-09-06
Status: IMPLEMENTED ON BRANCH / VERIFICATION PENDING
Parent direction: `DOCUMENTS/PAPER_LIVE_SHARED_TRADING_CORE_RECOVERY.md`
Baseline: `8641ed1573b447670cba4f5740729a5b470d491f`

## Objective

Move existing-order Limit mutation ownership for `AMEND_LIMIT` and `CANCEL_LIMIT` behind one provider-neutral lifecycle while preserving PAPER behavior and all LIVE safety invariants.

This slice does not reopen the completed Limit create path.

## Shared lifecycle boundary

`LimitOrderMutationController<T>` owns only:

- one attempt per `(operation, order_id)` pair;
- reuse of the same in-flight/latched attempt for duplicate UI actions;
- release after definitive terminal handling;
- retention after ambiguous handling;
- explicit clearing when provider authority is invalidated.

It deliberately does not own:

- transport endpoints;
- account/session authority;
- command/request construction;
- provider response semantics;
- reconciliation;
- authoritative state/projection application;
- runtime mutation gates.

## Provider adapters

`PaperLimitOrderMutationController` retains PAPER-specific:

- `paperTradingStore.runMutation` integration;
- resulting `paper_state` application;
- PAPER refresh after transport/application failure;
- existing release-after-refresh behavior.

`LiveLimitOrderMutationController` retains LIVE-specific:

- current account/session authority capture and stale-authority preflight;
- durable `client_action_id` ownership per attempt;
- LIVE amend/cancel REST transport;
- authoritative LIVE refresh after `accepted_pending` / `completed`;
- retained ownership after `unknown`, `reconciliation_required`, stale response, transport failure, or refresh failure;
- no blind redispatch after an ambiguous outcome.

## External-reference check

Bybit V5 documents both amend and cancel acknowledgements as asynchronous request acceptance rather than final exchange state. Therefore a successful HTTP acknowledgement must remain followed by authoritative reconciliation/projection refresh, and an ambiguous transport outcome must not be treated as safe evidence for redispatch.

The retry/idempotency pattern also follows the general distributed-systems rule that retries of side-effecting operations require stable request identity and explicit idempotency/reconciliation semantics rather than issuing a new semantic request after uncertainty.

## Current branch progress

Branch: `shared-limit-existing-order-lifecycle-slice3`
Draft PR: `#2 refactor: share existing Limit mutation lifecycle`

Added:

- `terminal/frontend/src/orders/limitOrderMutation.ts`;
- `terminal/frontend/src/orders/limitOrderMutation.test.ts`;
- `terminal/frontend/src/orders/limitOrderMutationSubmission.ts`;
- `terminal/frontend/src/orders/limitOrderMutationSubmission.test.ts`.

Integrated:

- `App.tsx` no longer owns a LIVE amend/cancel attempt map;
- `App.tsx` routes PAPER amend/cancel through `PaperLimitOrderMutationController`;
- `App.tsx` routes LIVE amend/cancel through `LiveLimitOrderMutationController`;
- direct `executePaperLimitAmend`, `executePaperLimitCancel`, `executeLiveLimitAmend`, and `executeLiveLimitCancel` lifecycle ownership was removed from `App.tsx`;
- retained mutation ownership is cleared only when the effective PAPER/LIVE mutation authority key changes or becomes unavailable, rather than on an ordinary projection refresh;
- existing active-order caller contracts remain unchanged.

The implementation is intentionally not marked verified or complete yet. No local targeted tests or production build have been executed against this branch after the App integration.

## Remaining work

1. Synchronize the branch to the Windows checkout only when local verification is ready to begin.
2. Run focused shared-controller/adapter regression tests and any compile/type checks routed by the protected task workflow.
3. Run the required frontend production build through the protected local verification workflow.
4. Review the final scoped diff/PR evidence after current verification.
5. Do not perform a real LIVE amend or cancel during implementation verification.
6. Any project-driven real LIVE amend/cancel acceptance requires separate explicit user authorization and a fresh acceptance session/gate where applicable.
