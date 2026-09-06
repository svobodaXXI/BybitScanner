# POST-RECOVERY AUDIT CHECKPOINT

Date: 2026-09-06
Scope: BybitScanner / Trading Workspace shared PAPER/LIVE trading-core recovery follow-up
Status: COMPLETE

## Purpose

Record the post-recovery architectural audit performed after shared trading-core Slices 1-8 were completed. This checkpoint does not introduce Slice 9. It records only the cleanup work required to remove remaining lifecycle/authority bypasses found after recovery.

Authoritative code checkpoint before this documentation update:

`7634506d792e18f23dc8cea0d1d083d7c200a492`

At that checkpoint:

- Slices 1-8 are COMPLETE;
- post-recovery Cleanup #1-#8 are COMPLETE and merged;
- single PAPER inventory Full Close is routed through the shared Full Close lifecycle;
- `/api/close-all` remains a separate bulk contract and was intentionally not migrated by Cleanup #8;
- no new Slice 9 is declared.

## Post-recovery cleanup ledger

### Cleanup #1 — LIVE MARKET authority / dead legacy

PR: #18

Title: `refactor: tighten LIVE market authority boundary`

Merge commit:

`cd07fb19d4a535c0325db078477fab32c33d2015`

Result:

- revalidated LIVE MARKET capability/account/session at confirmation and response time;
- cleared stale unsubmitted confirmation state when capability changed;
- removed unreachable legacy direct PAPER Limit amend code from `ModePanel`;
- preserved existing backend/runtime gates and fail-closed behavior.

### Cleanup #2 — LIVE Limit bulk-cancel authority latch

PR: #19

Title: `fix: scope LIVE bulk cancel latch to authority`

Merge commit:

`c25dcd540ad9c811d1b01b429ba154b005d7349d`

Result:

- scoped unresolved bulk-cancel ownership by account/session authority plus per-attempt token;
- prevented a stale session-N pending latch from blocking session N+1;
- prevented late completion from clearing replacement ownership.

### Cleanup #3 — LIVE stale-response authority ref fencing

PR: #20

Title: `fix: fence LIVE responses with current authority`

Merge commit:

`0f901f92e8fc4c865c51b4db3a15365413f7019d`

Result:

- replaced stale render-closure authority reads with current mutable authority snapshots for LIVE Limit and protection post-response checks;
- preserved Full Close's existing ref-based authority boundary;
- preserved durable action identity, reconciliation, and no-blind-retry semantics.

### Cleanup #4 — PAPER STOP/TAKE duplicate lifecycle owner

PR: #21

Title: `refactor: keep one PAPER protection lifecycle owner`

Merge commit:

`9ba85319e94db2eeb65056d57c6e66666d53e52e`

Result:

- removed the redundant lower-level `ProtectionCommandLifecycleController` from PAPER STOP/TAKE transport;
- kept `PaperProtectionMutationController` as the sole semantic attempt owner;
- retained controller-level dedupe, durable id, `runMutation`, fetch, clear, and replacement semantics.

### Cleanup #5 — PAPER MARKET stale authoritative-state acceptance

PR: #22

Title: `fix: fence PAPER market authoritative state`

Merge commit:

`a41dbdfa5a095903d2b9ad5f6a2fcee61fd29944`

Result:

- completed PAPER MARKET results now fail closed when `applyPaperState` rejects returned state for the current PAPER account/session;
- false success after a stale session handoff is prevented.

Accidental neutralized main history during this cleanup:

- accidental test commit: `7cda7cd226abaffc0b020a5a3d110d700c2f2614`;
- neutralizing deletion: `ac3c0e01a3576008734f6298de8bf0ac6a12bff8`.

The history is intentionally preserved. It must not be rewritten merely to hide the neutralized mistake.

### Cleanup #6 — PAPER Full Close stale authoritative-state acceptance

PR: #23

Title: `fix: fence PAPER full close authoritative state`

Merge commit:

`8effd8a5c94eb701c90968621a450ffc44b374bd`

Result:

- completed PAPER Full Close fails closed when returned PAPER state is rejected for the current authoritative account/session;
- callers cannot treat rejected stale state as a successful Full Close.

### Cleanup #7 — PAPER LIMIT CREATE/AMEND/CANCEL authoritative-state fencing

PR: #24

Title: `fix: fence PAPER limit authoritative state`

Merge commit:

`b484c86bf5e830efe34224d4c28e881c88eb0bfa`

Result:

- PAPER Limit CREATE fails closed on rejected authoritative state and remains ambiguous/owned until reconciliation through the existing draft lifecycle;
- PAPER Limit AMEND/CANCEL reject and refresh authoritative PAPER state when application fails;
- false completed-state acceptance is removed across all three PAPER Limit mutation paths.

## Read-only `applyPaperState` audit after Cleanup #7

A read-only audit of PAPER state-application ownership identified one remaining architectural bypass:

`terminal/frontend/src/components/OpenPositionsOverlay.tsx`

Its single-position PAPER Full Close path still directly owned:

- `/api/full-close` transport;
- `client_action_id` allocation;
- pending/ambiguous latch;
- repeat blocking;
- reconciliation;
- direct `applyPaperState`.

The existing shared controller was already available:

`PaperFullCloseSubmissionController`

The overlay's `/api/close-all` path was classified separately as a bulk contract and explicitly excluded from this cleanup.

### Cleanup #8 — PAPER inventory single Full Close lifecycle bypass

PR: #25

Title: `fix: route PAPER inventory full close through shared lifecycle`

Merge commit:

`7634506d792e18f23dc8cea0d1d083d7c200a492`

Result:

- single PAPER Full Close in `OpenPositionsOverlay` now routes through `PaperFullCloseSubmissionController`;
- direct overlay-owned `/api/full-close` transport was removed;
- direct overlay-owned `applyPaperState(result.paper_state)` was removed;
- existing inventory/UI reconciliation behavior was preserved;
- completed + position still present remains locked as `Позиция ещё открыта`;
- completed + authoritative inventory FLAT clears row/latch/action id;
- UNKNOWN/reconciliation/error paths refresh inventory and block blind retry unless FLAT is proven;
- `/api/close-all` remains unchanged as a separate bulk contract.

Verification for Cleanup #8 after pulling the branch to Windows:

- focused lifecycle boundary test: 1/1 PASS;
- `OpenPositionsOverlay.test.tsx` + lifecycle boundary test: 10/10 PASS;
- production `npm run build`: PASS;
- tracked tree clean and local diff empty before merge.

## Audit conclusion

The post-recovery audit/cleanup sequence is COMPLETE for the identified scope.

The resulting execution architecture remains:

```text
USER GESTURE
  -> COMMON TRADING INTENT
  -> COMMON DRAFT / VALIDATION / UI / CONFIRMATION
  -> COMMON ORDER COMMAND
  -> EXECUTION ADAPTER
      -> PAPER adapter
      -> LIVE Bybit adapter
```

Required invariants remain intact:

- provider-neutral lifecycle ownership where semantics are shared;
- provider-specific transport behind adapters;
- stable durable command identity;
- single-attempt ownership;
- current account/session authority fencing;
- fail-closed authoritative-state application;
- UNKNOWN / reconciliation remains fail-closed;
- no blind retry after ambiguous mutation outcome;
- unrelated user-owned files remain outside project commits.

## Deferred / intentionally separate

- `/api/close-all` is a separate PAPER bulk contract and was not folded into single Full Close lifecycle ownership;
- no new shared-core slice is created by this checkpoint;
- any future cleanup requires a newly identified concrete defect or architectural bypass, not continuation by numbering alone.

## Recovery pointer

For future continuation, recover from repository authority first. Treat this document as the completion checkpoint for the post-recovery cleanup sequence following shared-core Slices 1-8.
