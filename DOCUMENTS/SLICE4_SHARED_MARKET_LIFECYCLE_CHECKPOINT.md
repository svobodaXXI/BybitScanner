# Slice 4 — Shared MARKET Lifecycle Checkpoint

Status: COMPLETE
Date: 2026-09-06
Authoritative code checkpoint before this documentation commit: `456f2b1add304cf08cf70fa7d6174be478c6309c`

## Scope

Slice 4 converged PAPER and LIVE Market command-attempt ownership behind a provider-neutral lifecycle without activating any new LIVE capability.

## Completed implementation

- Added `MarketCommandLifecycleController<T>` as provider-neutral single-attempt ownership keyed by durable `client_action_id`.
- PAPER Market execution now routes through the shared lifecycle.
- LIVE Market execution now routes through the shared lifecycle.
- Duplicate submissions for the same `client_action_id` reuse the owned attempt rather than dispatching again.
- LIVE `unknown`, reconciliation-required, `accepted_pending`, stale-authority responses, and transport errors retain attempt ownership so blind redispatch remains blocked.
- Definitive PAPER outcomes and configured PAPER errors release ownership.
- `clear()` is race-safe: a late completion from a cleared attempt cannot release replacement ownership.
- Retained LIVE Market ownership is fenced by account/session authority and is cleared when authority changes, allowing a reused action id only after the authority generation changes.
- `ModePanel` confirmation UI remains presentation/debounce state; command-attempt authority is owned by the shared Market lifecycle.

## Preserved safety invariants

- durable/stable `client_action_id`;
- single-attempt dispatch ownership;
- no blind retry;
- UNKNOWN / reconciliation remains fail-closed;
- LIVE account/session authority fencing;
- no private-WS dependency added;
- no real LIVE Market mutation performed during this slice.

## Explicitly out of scope

- Full Close;
- STOP / TAKE;
- Limit lifecycle changes;
- new LIVE capability activation;
- real LIVE mutation acceptance.

## Verification evidence

Phase 1 targeted frontend verification on Windows:

- `liveMarketCommand.test.ts`
- `marketCommandLifecycle.test.ts`
- `paperMarketCommand.test.ts`
- result: 9/9 tests PASS
- `npm run build`: PASS

Authority-fencing follow-up verification on Windows:

- `liveMarketCommand.test.ts`
- `marketCommandLifecycle.test.ts`
- result: 6/6 tests PASS
- `npm run build`: PASS

## Merge checkpoints

- Shared Market lifecycle merge: `52d1871522f47e72a125ffa68d93e7209ddfdbb6`
- Authority-fencing follow-up merge / authoritative Slice 4 code checkpoint: `456f2b1add304cf08cf70fa7d6174be478c6309c`

## Next architectural step

Continue provider convergence with the next trading vertical while preserving the same boundary:

```text
COMMON TRADING INTENT / COMMAND
        -> COMMON LIFECYCLE
        -> EXECUTION ADAPTER
            -> PAPER
            -> LIVE
```

Do not merge Full Close, STOP/TAKE, or new LIVE capability activation into the completed Market slice. The next slice should be separately scoped and verified before any real LIVE mutation is authorized.
