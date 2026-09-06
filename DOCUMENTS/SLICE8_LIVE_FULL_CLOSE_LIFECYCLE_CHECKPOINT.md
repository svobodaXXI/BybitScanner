# Slice 8 — LIVE Full Close Lifecycle Checkpoint

Status: IMPLEMENTATION COMPLETE / REAL LIVE ACCEPTANCE NOT EXECUTED
Date: 2026-09-06
Authoritative implementation checkpoint: `473e1dca56a5e64359146f661d125e38e9d62107`

## Scope

Slice 8 completed the final planned step in the PAPER/LIVE shared trading-core recovery by wiring LIVE Full Close behind the existing provider-neutral Full Close lifecycle.

Covered operation:

- LIVE Full Close.

No real-money LIVE Full Close command was executed during implementation or verification.

## Final architecture

Full Close now follows the shared lifecycle direction:

```text
USER CONFIRMATION
    -> COMMON FULL CLOSE INTENT
    -> FullCloseCommandLifecycleController
    -> EXECUTION ADAPTER
        -> PaperFullCloseSubmissionController
        -> LiveFullCloseSubmissionController
            -> POST /api/live/full-close
            -> authoritative LIVE refresh / reconciliation
```

The shared lifecycle owns semantic attempt identity and duplicate-attempt dedupe. Provider-specific transport, authority fencing, authoritative refresh, and ambiguity classification stay in the execution adapter.

## Phase 1 — LIVE adapter foundation

Phase 1 added:

- `terminal/frontend/src/orders/liveFullCloseCommand.ts`;
- `terminal/frontend/src/orders/liveFullCloseCommand.test.ts`;
- `terminal/frontend/src/orders/liveFullCloseSubmission.ts`;
- `terminal/frontend/src/orders/liveFullCloseSubmission.test.ts`.

`LiveFullCloseSubmissionController` reuses `FullCloseCommandLifecycleController<T>`.

Preserved invariants:

- one durable `client_action_id` per owned semantic attempt;
- semantic duplicate attempts reuse the same in-flight Promise;
- no blind retry;
- authority captured from active LIVE account/session;
- stale authority response is discarded;
- accepted/completed outcomes trigger authoritative LIVE refresh;
- `UNKNOWN` or `reconciliation_required` retain ownership;
- transport uncertainty retains ownership;
- explicit `clear()` remains the authority-reset boundary.

Phase 1 verification:

- `liveFullCloseCommand.test.ts` — 2 tests PASS;
- `liveFullCloseSubmission.test.ts` — 3 tests PASS;
- total: 5/5 PASS;
- frontend production build PASS.

Phase 1 PR:

- PR #16;
- head `24c28118f2e9be7381d0e11353b169a70c066d13`;
- merge commit `14f7e8f302464224c6d6a3bd6286c243ec27565b`.

## Phase 2 — UI wiring

Phase 2 wired the existing close-position confirmation path to LIVE Full Close without changing backend/runtime mutation gates.

Key changes:

- `ModePanel` owns both PAPER and LIVE Full Close submission controllers;
- authoritative LIVE position projection is used for the displayed open position when PAPER state is absent;
- the existing close-position button is shown for authoritative LIVE Long/Short positions;
- LIVE Full Close is admitted only when the active LIVE projection is MAINNET, READY, writable, and `capabilities.full_close === true`;
- the controller is cleared and confirmation dismissed across relevant authority/capability transitions;
- the current account/session authority is revalidated at submit time;
- success/accepted/ambiguous/transport-uncertain UI statuses do not create an automatic resend path;
- PAPER Full Close behavior remains available through the existing PAPER controller.

The LIVE close control is fail-closed when the common LIVE mutation authority envelope is unavailable, even if a stale-looking projection still contains Full Close capability.

Phase 2 verification:

- `ModePanel.liveFullClose.test.tsx` — 2 tests PASS;
- `liveFullCloseSubmission.test.ts` — 3 tests PASS;
- `liveFullCloseCommand.test.ts` — 2 tests PASS;
- total targeted verification: 7/7 PASS;
- frontend production build PASS (`tsc -b` and Vite build; 93 modules transformed).

An initial regression run had one test failure because the mocked controller call count leaked from the first test into the second. The production fail-closed button assertion already passed. Test isolation was fixed with per-test mock reset; the subsequent full targeted run passed 7/7.

Phase 2 PR:

- PR #17;
- final head `4bda9486a5817cd4d0492ee6f5e95829c63f163e`;
- merge commit `473e1dca56a5e64359146f661d125e38e9d62107`.

## Backend safety contract reused

The existing backend Full Close path was already sufficient for this Slice.

`TerminalCommandApi.full_close()`:

- resolves the authoritative server-side pretrade context;
- returns COMPLETED when already flat;
- chooses the opposite side of the current position;
- submits MARKET using the exact confirmed position quantity;
- relies on the application/pretrade safety boundary;
- converts ambiguous outcomes to `UNKNOWN` with `reconciliation_required=true`;
- does not expose a frontend quantity that could reverse the position.

No backend behavior change was required in Slice 8.

## Runtime gates

Slice 8 did **not** loosen or redesign runtime gates.

LIVE Full Close remains dependent on the existing account workspace capability projection and LIVE authorization gates. Defaults remain fail-closed.

No real LIVE mutation was executed merely because the frontend path is now wired.

## Real LIVE acceptance boundary

This checkpoint does **not** claim:

- a real Bybit Full Close was submitted;
- a real position was closed;
- slippage or exchange fill behavior was accepted on mainnet;
- real-money STOP/TAKE or Full Close acceptance is complete.

Any real LIVE acceptance requires a separate explicit authorization and a deliberately bounded acceptance procedure.

## Completion decision

Slice 8 is IMPLEMENTATION COMPLETE.

With Slice 8 complete, the planned eight-slice PAPER/LIVE shared trading-core recovery is implementation-complete:

1. Shared Limit interaction core;
2. Shared Limit CREATE lifecycle;
3. Shared existing Limit mutation lifecycle;
4. Shared MARKET lifecycle;
5. Shared STOP/TAKE lifecycle;
6. Shared Full Close lifecycle for PAPER;
7. LIVE STOP/TAKE execution adapter and UI lifecycle;
8. LIVE Full Close execution adapter and UI lifecycle.

The architectural target is now represented across the manual trading command paths:

```text
USER GESTURE
  -> COMMON TRADING INTENT
  -> COMMON DRAFT / VALIDATION / UI / CONFIRMATION
  -> COMMON ORDER COMMAND / LIFECYCLE
  -> EXECUTION ADAPTER
      -> PAPER adapter
      -> LIVE Bybit adapter
```

## Recovery completion boundary

The eight-slice recovery is complete at the implementation level, not at real-money acceptance level.

Preserved cross-cutting invariants include:

- stable/durable client action identity;
- single-attempt ownership;
- semantic duplicate dedupe;
- no blind retry;
- account/session authority fencing;
- fail-closed UNKNOWN/reconciliation behavior;
- authoritative refresh/state projection;
- provider-specific transport below shared lifecycle semantics.

## Recommended next step

Before starting another architectural slice, perform a focused shared-core completion audit and update the master recovery/roadmap status from the eight Slice checkpoint documents.

Real LIVE STOP/TAKE/Full Close acceptance should remain a separate, explicitly authorized activity rather than being implied by implementation completion.
