# Slice 5 — Shared Protection Lifecycle Checkpoint

Status: COMPLETE FOR PAPER / LIVE NOT ACTIVATED
Date: 2026-09-06
Authoritative implementation checkpoint: `7a80d1e3e3829886d8148e4a494a6fa2415ab6ff`

## Scope

Slice 5 converged PAPER STOP/TAKE mutation submission onto the shared lifecycle architecture without activating LIVE STOP/TAKE execution.

Covered operations:

- STOP create;
- STOP amend;
- STOP delete;
- TAKE create;
- TAKE amend;
- TAKE delete.

## Final architecture

PAPER protection mutations now follow:

```text
UI protection intent
    -> PaperProtectionMutationController
    -> ProtectionCommandLifecycleController
    -> paperTradingStore.runMutation
    -> PAPER protection command transport
    -> authoritative PAPER state application
```

`App.tsx` no longer owns protection `client_action_id` allocation, provider-specific transport selection, or direct `runMutation` orchestration for STOP/TAKE create, amend, or delete.

## Lifecycle ownership

`PaperProtectionMutationController` owns semantic attempt identity across STOP/TAKE operations.

Semantic ownership keys are separated by:

- protection leg: STOP vs TAKE;
- operation: CREATE / AMEND / DELETE;
- symbol;
- trigger price for CREATE / AMEND.

A duplicate semantic attempt shares the same in-flight Promise and therefore preserves:

- one durable `client_action_id` allocation;
- one `runMutation` ownership instance;
- one transport dispatch.

PAPER completed results release ownership. PAPER errors release ownership.

## Account/session reset boundary

The controller is cleared when the mutation authority key changes across account/session context.

`PaperProtectionMutationController.clear()` also clears the nested PAPER protection transport lifecycle introduced during Slice 5 phase 1. This preserves replacement-attempt ownership after authority reset while late completion cleanup remains identity-checked and cannot delete a newer owner.

This nested lifecycle arrangement is a transitional internal detail. It must not be interpreted as permission to add additional parallel protection lifecycles.

## Safety and behavior preserved

The Slice 5 refactor did not change protection UI semantics.

Preserved invariants include:

- authoritative PAPER state application remains session-fenced;
- no blind retry behavior was introduced;
- duplicate submission ownership is deterministic;
- late completion after `clear()` cannot evict a replacement attempt;
- STOP and TAKE ownership remain independent;
- failure paths still restore the draft/editing state and refresh PAPER state where the existing UI required it.

## LIVE boundary

LIVE STOP/TAKE remains outside this Slice.

Slice 5 does **not**:

- enable LIVE STOP;
- enable LIVE TAKE PROFIT;
- add LIVE protection endpoints;
- weaken LIVE authority fencing;
- add LIVE mutation retries;
- claim LIVE protection acceptance.

Any future LIVE protection work must reuse the same common protection domain/lifecycle semantics and add only the LIVE execution adapter, authority fencing, durable command identity, ambiguity handling, and reconciliation behavior required by the LIVE environment.

## Verification

Phase 2a targeted verification:

- `src/orders/protectionCommandLifecycle.test.ts` — 3 tests;
- `src/orders/paperStopCommand.test.ts` — 4 tests;
- `src/orders/paperProtectionMutationSubmission.test.ts` — 3 tests;
- total: 10/10 PASS.

Phase 2b targeted regression verification:

- `src/orders/protectionCommandLifecycle.test.ts` — 3 tests;
- `src/orders/paperStopCommand.test.ts` — 4 tests;
- `src/orders/paperProtectionMutationSubmission.test.ts` — 3 tests;
- `src/app/App.liveLimitConfirm.test.tsx` — 16 tests;
- total: 26/26 PASS.

Frontend production build after phase 2b:

```text
npm run build
-> tsc -b PASS
-> vite build PASS
```

## Merge history

Phase 1:

- PR #6;
- merge commit `d8816252b2acc278fcdad13d6c77ab9a49a31f48`.

Phase 2a:

- PR #7;
- merge commit `776e6dc35aa7980103d6afca8830d85abfad6874`.

Phase 2b:

- PR #8;
- merge commit `7a80d1e3e3829886d8148e4a494a6fa2415ab6ff`.

## Completion decision

Slice 5 is COMPLETE for the PAPER-side shared protection mutation lifecycle.

This closes the residual `App.tsx` ownership for PAPER STOP/TAKE mutation submission and aligns protection lifecycle ownership with the broader shared trading-core direction established for Limit and Market operations.

This checkpoint does not close the broader PAPER/LIVE shared-core recovery as a whole, and it does not activate LIVE STOP/TAKE.

## Next architectural step

The next protection-specific step, when separately scheduled, is LIVE STOP/TAKE adapter work behind the existing common protection semantics and LIVE fail-closed safety boundary.

Before that work begins, the shared trading-core roadmap should continue to be treated as authoritative: provider-specific code belongs at the execution boundary, not in common UI/domain interaction logic.
