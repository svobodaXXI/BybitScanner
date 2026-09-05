# PAPER / LIVE SHARED TRADING CORE RECOVERY

Status: ACTIVE ENGINEERING DIRECTION
Date: 2026-09-05
Baseline for investigation: `f1d45f7a4963e027bbe1021a6d21095a779722b7`
Relevant pre-LIVE-Limit PAPER baseline: `2bb7fa3c77f0f9413e1aa95a787e4afbcb8efb89`

## 1. Purpose

Recover a single trading workflow shared by PAPER and LIVE accounts.

The intended architecture is not two independently evolving trading frontends. PAPER defines and exercises the trading UX/domain semantics; LIVE reuses the same gesture, draft, validation, confirmation, editing and order-intent flow, while replacing only the execution-specific boundary.

The immediate trigger for this recovery is a confirmed regression cluster:

- LIVE hold BUY/SELL + chart tap no longer creates a Limit draft in the real-phone flow;
- PAPER chart Limit confirmation has also regressed;
- a sequence of LIVE-specific frontend fixes has accumulated around shared UI paths;
- automated tests have passed while real shared behavior remained broken.

This document supersedes the working assumption that the problem is only a narrow LIVE hold/tap defect.

## 2. Core architectural invariant

PAPER and LIVE must share the same trading interaction and domain pipeline:

```text
USER GESTURE
    -> COMMON TRADING INTENT
    -> COMMON DRAFT / VALIDATION / UI / CONFIRMATION
    -> COMMON ORDER COMMAND
    -> EXECUTION ADAPTER
        -> PAPER adapter
        -> LIVE Bybit adapter
```

PAPER and LIVE may differ only where the execution environment actually differs.

### Shared by PAPER and LIVE

The following semantics are one system and must not fork by account type:

- BUY/SELL short tap versus hold behavior;
- selected side volume semantics;
- default 1 WV volume semantics;
- fast Limit hold + chart tap;
- Limit draft identity and lifecycle;
- Limit line creation, selection, drag and price editing;
- popup and chart representation of the same draft;
- individual confirm/dismiss controls;
- global confirm-all/dismiss-all behavior;
- common price normalization and validation semantics;
- confirmation eligibility derived from the same draft/domain state;
- UI feedback for invalid inputs;
- common order intent produced after confirmation.

### Execution-specific by design

Only these concerns should remain provider-specific:

- transport endpoint / exchange adapter;
- LIVE account and session authority fencing;
- LIVE idempotency and durable command identity;
- LIVE single-attempt dispatch ownership;
- LIVE ambiguous/UNKNOWN handling;
- LIVE REST-only reconciliation;
- LIVE exchange projection refresh;
- PAPER state application / simulation mechanics;
- capability and runtime gates controlling whether execution is allowed.

Provider-specific concerns must not redefine the trading gesture or draft semantics.

## 3. Investigation findings

### 3.1 PAPER was previously a coherent reference implementation

Before capability-gated LIVE Limit frontend integration, the PAPER path had a coherent sequence around shared selected volume, fast Limit draft creation, draft confirmation and the PAPER submit controller.

The relevant reference point is commit:

`2bb7fa3c77f0f9413e1aa95a787e4afbcb8efb89`

This commit is not automatically a rollback target. It is the behavioral/reference baseline for reconstructing the invariants that must still hold.

### 3.2 LIVE Limit integration introduced branching inside the shared workflow

Commit:

`b34082f0898db3da9a081e8e9e8ed54c29bfcae7` (`feat: add capability-gated live limit frontend`)

added LIVE-specific branching directly inside `App.tsx` for create/amend/cancel, authority checks, attempt ownership and live order projection.

The documentation for that slice stated that PAPER behavior remained unchanged, but subsequent real behavior shows that this invariant was not sufficiently protected by tests.

### 3.3 A repair chain formed around shared UI behavior

After LIVE Limit frontend activation, multiple commits were required to repair surrounding behavior, including volume input, popup inputs, chart confirm rendering, live order projection, refresh after cancel, linked confirmations and later draft interaction hardening.

The pattern indicates that LIVE was being incrementally patched around shared UI paths instead of being cleanly attached behind a stable common trading-core boundary.

### 3.4 Current fast-Limit volume ownership is inconsistent

`ModePanel` captures a hold intent containing both side and an effective volume, including fallback to 1 WV:

```text
selected side volume || oneWvUsdt
```

But `App.createFastLimitDraft()` later recomputes the volume from mutable `selectedVolumes[side]` rather than using the volume already captured in the intent.

This creates two sources of truth for one user gesture and can reject a valid hold intent when the visible/default volume is not represented as a non-empty selected-volume value.

The exact one-line repair is not the architectural goal; the finding is evidence that gesture intent and later draft creation no longer share one authoritative state object.

### 3.5 Current Limit confirmation is also overly coupled to mutable UI state

`submitLimitDraft()` retrieves the draft, then re-reads selected volume from external UI state before deciding whether confirmation is valid and before branching into PAPER or LIVE execution.

That means the confirmed draft is not fully self-contained. A draft can visually exist with one semantic volume while confirmation eligibility depends on another mutable source.

This is a likely contributor to PAPER and LIVE divergence.

### 3.6 Passing tests do not currently prove the real shared interaction

Recent LIVE tests explicitly enter a non-empty amount such as `5` before exercising hold/draft creation. This bypasses the default-volume path that is important in the real UI.

Other tests often invoke child callbacks directly rather than exercising the complete real pointer/gesture -> intent -> draft -> chart confirm path.

Therefore current tests are necessary but insufficient as regression protection for PAPER/LIVE parity.

## 4. Engineering direction

Do not continue with isolated LIVE-only UI patches unless required for immediate safety.

The next development phase is a scoped recovery/refactor of the trading vertical so that PAPER and LIVE become two execution adapters behind one common workflow.

### Phase A — Recover behavioral invariants

Compare the current implementation against the pre-LIVE-Limit PAPER baseline and explicitly record the intended behavior for:

1. BUY hold activation and release;
2. second-finger chart tap while hold remains active;
3. default 1 WV and explicit side-volume override;
4. Limit draft creation;
5. draft line drag/edit;
6. popup/chart shared draft identity;
7. chart `✓` confirmation;
8. popup confirmation;
9. individual `×` dismissal;
10. global `✓` / `×` actions;
11. active order projection and editing after accepted execution.

The baseline is used to recover semantics, not to blindly restore old source files.

### Phase B — Define one common trading intent/draft contract

The hold gesture must produce one captured intent containing all data that should remain stable for that gesture, at minimum:

- side;
- effective volume;
- symbol/account workspace generation context only where needed for invalidation;
- origin.

Limit draft creation must consume that captured intent rather than recomputing its business meaning from unrelated mutable UI state.

A Limit draft must carry the authoritative values necessary for later common validation and confirmation.

### Phase C — Isolate execution adapters

The common confirmation pipeline should resolve to an execution abstraction conceptually equivalent to:

```text
executeLimit(command, executionContext)
```

with PAPER and LIVE implementations.

`App.tsx`, `ModePanel.tsx` and `ChartPanel.tsx` should not each grow independent PAPER/LIVE business branches for the same action.

The LIVE adapter retains fail-closed safety, authority fencing, stable command identity, no blind retry, UNKNOWN -> reconciliation and REST-only refresh.

### Phase D — Shared behavioral tests

Create a provider-agnostic behavioral suite that is executed against both PAPER and mocked LIVE execution contexts.

At minimum it must prove:

- empty side-volume control with valid 1 WV default can create a draft;
- explicit side volume overrides 1 WV;
- hold BUY and hold SELL both create the correct chart draft;
- creating a draft performs no execution POST;
- chart and popup confirmation target the same draft identity;
- chart `✓` works on PAPER;
- chart `✓` reaches LIVE adapter only when LIVE authority/capability is valid;
- invalid or stale authority blocks execution without changing common draft semantics;
- submitting/ambiguous LIVE drafts remain locked without weakening PAPER behavior;
- global controls operate on the same candidate set in both modes.

Prefer tests that exercise the real interaction boundary rather than directly invoking internal callbacks when practical.

### Phase E — Real acceptance sequence

After automated parity tests pass:

1. verify PAPER on the real UI first;
2. verify LIVE draft-only gestures with no confirmation / no exchange mutation;
3. only then perform separately authorized LIVE mutation acceptance.

A LIVE test must not be used as a substitute for proving PAPER remains correct.

## 5. Non-goals for this recovery

- no redesign of the trading UI;
- no removal of LIVE safety gates;
- no relaxation of account/session fencing;
- no blind retries;
- no private WebSocket requirement;
- no activation of unrelated LIVE STOP/TAKE/full-close scope;
- no broad rewrite of the terminal unrelated to the shared trading vertical.

## 6. Completion criteria

This recovery is complete only when all of the following are true:

- PAPER and LIVE use one common gesture/draft/validation/confirmation pipeline;
- account type selection happens at an execution boundary rather than throughout shared UI/domain code;
- PAPER chart Limit creation and confirmation are restored;
- LIVE hold + chart tap creates the same class of draft without submitting anything;
- default 1 WV and explicit side-volume semantics are identical across providers;
- common behavioral tests run against PAPER and mocked LIVE contexts;
- real-phone PAPER acceptance passes;
- real-phone LIVE draft-only acceptance passes;
- LIVE execution safety semantics remain fail-closed.

## 7. Immediate next task

The next implementation task should be framed as:

> Recover the shared PAPER-derived Limit interaction core before further LIVE-only feature work. Compare current behavior with `2bb7fa3c77f0f9413e1aa95a787e4afbcb8efb89`, formalize common invariants, then make the smallest structural changes needed so PAPER and LIVE share one gesture/draft/confirmation pipeline and differ only at the execution adapter/safety boundary.

Do not start by patching only the observed LIVE hold/tap symptom.

## 8. Decision

From this checkpoint forward, PAPER remains the behavioral reference implementation for manual trading semantics, while LIVE is an execution environment using the same trading core.

Any future manual-trading feature intended for both account types should be implemented once in the common core and proven with parity tests before provider-specific execution wiring is considered complete.
