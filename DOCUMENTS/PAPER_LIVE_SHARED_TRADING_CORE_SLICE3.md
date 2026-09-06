# PAPER / LIVE SHARED TRADING CORE — SLICE 3

Date: 2026-09-06
Status: VERIFIED / READY FOR MERGE
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
PR: `#2 refactor: share existing Limit mutation lifecycle`

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
- a reviewed clear/late-completion race was fixed so a stale completion cannot release replacement ownership;
- existing active-order caller contracts remain unchanged.

## Verification evidence

Windows checkout verification against the current Slice 3 code completed on 2026-09-06 before the subsequent documentation-only robot-architecture decision commit.

Focused suite:

```text
src/orders/liveLimitCommand.test.ts                    3 passed
src/orders/limitOrderMutation.test.ts                  7 passed
src/orders/limitOrderMutationSubmission.test.ts        6 passed
src/app/App.liveLimitConfirm.test.tsx                 16 passed
TOTAL                                                 32 passed
```

Production build:

```text
npm run build
= tsc -b && vite build
PASS
82 modules transformed
```

The later documentation-only commit does not change executable code, tests, build configuration, or runtime behavior, so the code verification evidence remains applicable to the current PR scope.

Final scoped review was performed after the race fix. No material defects remain in the reviewed Slice 3 execution/order-lifecycle scope.

No real LIVE amend or cancel was performed or authorized for implementation verification.

## Remaining merge boundary

1. Merge PR #2 after final repository/PR state is confirmed mergeable.
2. Synchronize Windows `main` to the resulting merge commit and record the new authoritative checkpoint.
3. Any future project-driven real LIVE amend/cancel acceptance requires separate explicit user authorization and a fresh acceptance session/gate where applicable.
