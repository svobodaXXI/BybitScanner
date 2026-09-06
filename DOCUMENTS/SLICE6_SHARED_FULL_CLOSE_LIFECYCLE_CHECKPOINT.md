# Slice 6 — Shared Full Close Lifecycle Checkpoint

Status: COMPLETE FOR PAPER / LIVE NOT ACTIVATED
Date: 2026-09-06
Authoritative implementation checkpoint: `ab937a996e71015b25985978fbd0dd7e4480e84f`

## Scope

Slice 6 converged PAPER Full Close submission onto the shared lifecycle architecture without activating LIVE Full Close execution.

Covered operation:

- PAPER Full Close.

## Final architecture

PAPER Full Close now follows:

```text
UI Full Close confirmation
    -> PaperFullCloseSubmissionController
    -> FullCloseCommandLifecycleController
    -> paperTradingStore.runMutation("FULL_CLOSE")
    -> PAPER Full Close command transport
    -> authoritative PAPER state application
```

`ModePanel.tsx` no longer owns Full Close transport dispatch, request construction, or `client_action_id` allocation.

The UI still owns presentation behavior:

- confirmation modal open/close;
- success/cancellation status text;
- refresh-on-transport-error behavior.

## Lifecycle ownership

`PaperFullCloseSubmissionController` owns semantic Full Close attempt identity by symbol.

A duplicate semantic attempt shares the same in-flight Promise and therefore preserves:

- one durable `client_action_id` allocation;
- one `runMutation("FULL_CLOSE")` ownership instance;
- one transport dispatch.

PAPER completed or rejected results release ownership. Transport errors release ownership.

The default PAPER Full Close action id remains compatible with the existing contract:

```text
paper-full-close-<timestamp>
```

Tests may inject a deterministic `createClientActionId` factory.

## Account/session reset boundary

The `PaperFullCloseSubmissionController` instance is retained by `ModePanel` and cleared when relevant mutation authority changes across:

- account id;
- provider;
- session generation;
- PAPER mutation permission state.

The underlying lifecycle performs identity-checked cleanup, so a late completion after `clear()` cannot evict a replacement attempt.

## Safety and behavior preserved

Slice 6 preserves the existing Full Close UX and PAPER command semantics.

Preserved invariants include:

- durable `client_action_id` per owned attempt;
- semantic duplicate dedupe;
- single-attempt transport ownership;
- no blind retry behavior introduced;
- authoritative PAPER state application remains delegated to the command adapter;
- transport failure still fails closed in the UI and refreshes PAPER state;
- the existing pending action key remains exactly `FULL_CLOSE`;
- confirmation behavior remains unchanged.

## LIVE boundary

LIVE Full Close remains outside this Slice.

Slice 6 does **not**:

- enable LIVE Full Close;
- add or activate LIVE Full Close transport;
- weaken LIVE account/session authority fencing;
- add LIVE mutation retries;
- claim LIVE Full Close acceptance.

Any future LIVE Full Close work must reuse the same common lifecycle/domain semantics and add only the LIVE execution adapter, authority fencing, durable command identity, ambiguity handling, reconciliation, and reduce-only/FLAT guarantees required by the LIVE environment.

## Verification

Phase 1 targeted verification:

- `src/orders/fullCloseCommandLifecycle.test.ts` — 3 tests;
- `src/orders/paperFullCloseSubmission.test.ts` — 3 tests;
- total: 6/6 PASS.

Phase 2 integration regression:

- `src/components/ModePanel.test.tsx` — 25/25 PASS after preserving the existing `paper-full-close-<timestamp>` action-id contract.

Frontend production build after Phase 2:

```text
npm run build
-> tsc -b PASS
-> vite build PASS
```

A broader `ModePanel*.test.tsx` regression run produced 44/50 PASS before the Full Close compatibility fix. The one Slice-6-related failure was the action-id format expectation and was fixed. The remaining five failures were pre-existing structural/accessibility assertions unrelated to the Slice 6 diff and were not modified as part of this Slice.

## Merge history

Phase 1:

- PR #10;
- merge commit `d01ed4805749729c51495562c68af64472c41aef`.

Phase 2:

- PR #11;
- merge commit `ab937a996e71015b25985978fbd0dd7e4480e84f`.

## Completion decision

Slice 6 is COMPLETE for the PAPER-side shared Full Close lifecycle.

This removes the remaining direct PAPER Full Close transport/request ownership from `ModePanel` and aligns Full Close with the shared lifecycle direction already established for Limit, Market, and protection mutations.

This checkpoint does not close the broader PAPER/LIVE shared-core recovery as a whole, and it does not activate LIVE Full Close.

## Next architectural step

The next planned shared-core step is LIVE STOP/TAKE execution adapter work behind the common protection semantics and existing LIVE fail-closed boundary.

After that, LIVE Full Close execution should be added behind the shared Full Close lifecycle without reintroducing provider-specific lifecycle logic into the UI.
