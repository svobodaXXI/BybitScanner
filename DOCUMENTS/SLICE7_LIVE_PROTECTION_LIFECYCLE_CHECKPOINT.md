# Slice 7 — LIVE STOP/TAKE Lifecycle Checkpoint

Status: IMPLEMENTATION COMPLETE / REAL LIVE ACCEPTANCE NOT EXECUTED
Date: 2026-09-06
Authoritative implementation checkpoint: `74da1a01c4e262481767a112a41de7d838e67346`

## Scope

Slice 7 adds LIVE STOP/TAKE execution behind the shared protection lifecycle while preserving the existing PAPER path and LIVE fail-closed invariants.

Covered LIVE protection operations:

- STOP create;
- STOP amend;
- STOP delete;
- TAKE create;
- TAKE amend;
- TAKE delete.

LIVE Full Close is not part of Slice 7.

## Final architecture

LIVE protection now follows:

```text
STOP/TAKE UI gesture
    -> common protection draft/edit semantics
    -> LiveProtectionMutationController
    -> ProtectionCommandLifecycleController
    -> LIVE protection command adapter
    -> /api/live/stop|take[/amend|delete]
    -> backend live_execute account/session fencing
    -> Bybit protection mutation
    -> authoritative LIVE account refresh
    -> LIVE position protection projection
    -> STOP/TAKE UI projection
```

PAPER continues to use `PaperProtectionMutationController` over the same provider-neutral `ProtectionCommandLifecycleController`.

The UI no longer needs provider-specific lifecycle ownership for STOP/TAKE attempts.

## Phase 1 — LIVE protection lifecycle foundation

Phase 1 added:

- `terminal/frontend/src/orders/liveProtectionCommand.ts`;
- `terminal/frontend/src/orders/liveProtectionCommand.test.ts`;
- `terminal/frontend/src/orders/liveProtectionMutationSubmission.ts`;
- `terminal/frontend/src/orders/liveProtectionMutationSubmission.test.ts`.

The LIVE command adapter maps semantic protection operations to the already-existing backend routes:

```text
STOP CREATE  -> /api/live/stop
STOP AMEND   -> /api/live/stop/amend
STOP DELETE  -> /api/live/stop/delete
TAKE CREATE  -> /api/live/take
TAKE AMEND   -> /api/live/take/amend
TAKE DELETE  -> /api/live/take/delete
```

Changing one protection leg preserves the authoritative sibling leg because the Bybit protection mutation operates on combined TP/SL state.

The LIVE submission controller:

- captures LIVE account/session authority before dispatch;
- allocates `client_action_id` only inside owned lifecycle attempt creation;
- refreshes authoritative LIVE account state after accepted/completed results;
- retains ownership on `unknown` or `reconciliation_required` results;
- retains ownership on rejected transport promises because dispatch certainty is ambiguous;
- returns stale-authority responses as fail-closed rather than applying them;
- performs no blind retry.

## Phase 2a — authoritative LIVE protection projection

The existing Bybit `PositionEvent` already contained protection evidence, but LIVE account reconciliation discarded it.

Phase 2a extended the read-only LIVE position projection with:

- `take_profit`;
- `stop_loss`;
- `trailing_stop`.

Frontend helper `projectLiveProtectionPosition()` projects the active open BYBIT position for the selected symbol and fails closed for:

- missing position evidence;
- flat/zero-size positions;
- non-BYBIT projections;
- invalid/non-positive protection prices.

This closes the authoritative-state loop required before LIVE STOP/TAKE UI activation.

## Phase 2b — shared UI wiring

`App.tsx` now derives protection state from one provider-appropriate authoritative source:

- PAPER: authoritative PAPER state;
- LIVE: authoritative BYBIT account projection.

The shared STOP/TAKE draft, edit, drag, settings, confirmation, and delete UI now routes to:

- `PaperProtectionMutationController` for PAPER;
- `LiveProtectionMutationController` for LIVE.

LIVE STOP/TAKE controls are enabled only when all LIVE protection authority conditions hold:

- active provider is BYBIT;
- environment is MAINNET;
- account status is READY;
- projection is writable (`read_only === false`);
- STOP capability is true;
- TAKE capability is true;
- workspace is not switching.

Both protection capabilities are required because each Bybit mutation preserves and submits the sibling protection leg.

## Authority and reset boundaries

LIVE protection lifecycle ownership has its own authority boundary rather than depending on LIVE Limit capability.

The controller is cleared when relevant protection authority changes across:

- account id;
- session generation;
- provider/PAPER-vs-LIVE mutation authority;
- LIVE protection capability availability.

Drafts and settings are also cleared fail-closed when protection authority disappears or authoritative position evidence is no longer available.

A stale late response cannot be treated as current authority.

## Ambiguity and reconciliation semantics

The following remain fail-closed:

- `status === "unknown"`;
- `reconciliation_required === true`;
- rejected transport Promise after dispatch may have occurred;
- stale account/session authority;
- missing authoritative LIVE position evidence.

For ambiguous LIVE attempts, ownership is retained and blind re-dispatch is forbidden.

Accepted/completed LIVE results trigger authoritative account refresh. The UI clears a submitting draft only after refreshed authoritative projection proves the requested protection price.

## PAPER behavior preserved

Slice 7 does not replace or weaken PAPER protection semantics.

Preserved PAPER behavior includes:

- shared `ProtectionCommandLifecycleController` ownership;
- authoritative PAPER state application;
- PAPER mutation runner ownership;
- existing STOP improvement rule;
- existing STOP/TAKE preset/settings UX;
- existing signal TAKE proposal behavior remains PAPER-only in this Slice.

## Verification

Phase 1 targeted verification after test typing correction:

- `src/orders/liveProtectionCommand.test.ts` — 2 tests;
- `src/orders/liveProtectionMutationSubmission.test.ts` — 4 tests;
- total: 6/6 PASS;
- frontend production build PASS.

Phase 2a verification:

- `tests/test_live_protection_projection.py` — 1/1 PASS;
- `src/orders/liveProtectionProjection.test.ts` — 2/2 PASS;
- frontend production build PASS.

Phase 2b targeted verification:

- `src/components/ModePanel.stop.test.tsx`;
- `src/orders/liveProtectionProjection.test.ts`;
- `src/orders/liveProtectionMutationSubmission.test.ts`;
- total: 12/12 PASS.

Phase 2b frontend production build:

```text
npm run build
-> tsc -b PASS
-> vite build PASS
```

Vite emitted a non-failing chunk-size warning after minification; this is not a Slice 7 correctness failure.

## Merge history

Phase 1 — LIVE protection lifecycle foundation:

- PR #13;
- merge commit `d7b8ec7dc8baf8cb4c478fe73ca4a576e44112e4`.

Phase 2a — authoritative LIVE protection projection:

- PR #14;
- merge commit `29d34cea0da8a75f48404cf8ed1e54e1bf517832`.

Phase 2b — shared LIVE protection UI wiring:

- PR #15;
- merge commit `74da1a01c4e262481767a112a41de7d838e67346`.

## Real LIVE boundary

No real-money STOP/TAKE mutation was executed as part of Slice 7 implementation or verification.

Therefore this checkpoint does **not** claim real LIVE acceptance.

Real LIVE acceptance must remain a separate explicitly authorized activity with minimal mutation count and must verify, at minimum:

- correct account/session authority;
- one and only one mutation per authorized action;
- authoritative Bybit projection after mutation;
- sibling protection preservation;
- no duplicate dispatch after ambiguous outcome;
- fail-closed behavior when reconciliation is required.

## Completion decision

Slice 7 is IMPLEMENTATION COMPLETE for LIVE STOP/TAKE shared lifecycle integration.

The shared protection architecture now spans PAPER and LIVE through a provider-neutral lifecycle, provider-specific execution adapters, and authoritative provider state projection.

This does not close the broader PAPER/LIVE recovery as a whole because LIVE Full Close remains unactivated.

## Next architectural step

The next planned shared-core step is LIVE Full Close execution behind the existing `FullCloseCommandLifecycleController`.

That work must preserve:

- explicit LIVE account/session authority fencing;
- durable command identity;
- single-attempt ownership;
- no blind retry;
- UNKNOWN/reconciliation fail-closed behavior;
- reduce-only/close-to-FLAT semantics;
- authoritative LIVE reconciliation before considering the action complete.
