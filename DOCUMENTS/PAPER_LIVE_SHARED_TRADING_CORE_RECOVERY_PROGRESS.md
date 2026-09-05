# PAPER / LIVE SHARED TRADING CORE RECOVERY — PROGRESS

Date: 2026-09-05
Parent direction: `DOCUMENTS/PAPER_LIVE_SHARED_TRADING_CORE_RECOVERY.md`
Status: SLICE 1 PARTIALLY ACCEPTED / LIVE CHART CONFIRM BLOCKED

## Slice 1 objective

Restore one authoritative Limit interaction state before further LIVE-only fixes.

The slice intentionally does not redesign transport or relax LIVE safety. PAPER and LIVE still keep their existing execution-specific paths, but the user interaction leading to a Limit draft now carries stable domain values into confirmation instead of recomputing them from mutable UI state.

## Implemented changes

### Shared Limit interaction core

Added `terminal/frontend/src/orders/limitInteractionCore.ts`.

It defines and tests provider-independent semantics for:

- captured side + effective volume + origin;
- explicit side-volume override;
- fallback to valid 1 WV;
- draft-owned USDT volume;
- common confirmation eligibility;
- fail-closed same-side draft volume validation.

### Draft volume is authoritative

`LimitDraft` remains the shared PAPER/LIVE draft contract. Its reducer now supports `update-volume` and refuses volume changes while a draft is `submitting` or `ambiguous`.

Confirmation no longer needs to re-read the current side-volume control. The volume captured in the draft is the volume being confirmed.

### Fast Limit intent is captured once

`App.tsx` now keeps `fastLimitIntent` as a full shared interaction intent containing side, captured volume and origin.

Chart-fast and PAPER DOM Limit creation consume the captured intent volume instead of recomputing `selectedVolumes[side]` later.

This removes the previously observed two-sources-of-truth defect.

### Common 1 WV initialization across account providers

Selected BUY/SELL volumes are initialized from the active account projection `one_wv_usdt` for both PAPER and LIVE workspaces, with the PAPER state value retained as fallback.

The initialization key includes account id, session generation and symbol so account switching does not inherit another workspace's side-volume state.

### Popup volume edits update the shared draft

When the Limit popup is active, changing its side volume updates both the side control and that popup draft's `volume` field. A later chart or popup confirmation therefore addresses the same draft identity and volume.

### Confirmation uses the draft

PAPER and LIVE Limit create confirmation now validate and execute using the shared draft's captured volume.

Provider-specific execution remains behind the existing PAPER submit controller or LIVE authority/idempotency/reconciliation path.

## Regression protection added

Added `terminal/frontend/src/orders/limitInteractionCore.test.ts` covering:

- explicit side volume;
- 1 WV fallback;
- invalid fallback rejection;
- draft-owned confirmation volume;
- popup draft volume updates;
- submitting draft volume lock;
- fail-closed same-side candidate validation.

The existing LIVE integration test harness was updated so test-driven volume changes update the draft itself instead of relying on the old mutable-selected-volume assumption.

## Automated verification

Local verification after pull:

- `src/orders/limitInteractionCore.test.ts`: 7/7 PASS;
- `src/app/App.liveLimitConfirm.test.tsx`: 16/16 PASS;
- targeted total: 23/23 PASS;
- production `tsc -b && vite build`: PASS;
- built assets included `dist/assets/index-BCQ3MsJ9.js`.

The first targeted run exposed 7 stale LIVE integration tests because their mocks changed only `selectedVolumes`; that harness was corrected to update draft-owned volume. The repeated targeted run then passed 23/23.

## Real UI acceptance on 2026-09-05

### PAPER

PASS:

- real PAPER Limit flow was exercised in the current preview;
- pending Limit line appeared on chart;
- chart checkmark confirmation succeeded.

This confirms the previously reported PAPER chart-confirm regression is recovered for the exercised flow.

### LIVE draft-only

PASS:

- on the LIVE account, hold BUY + second touch on chart created the pending dashed Limit line;
- no LIVE exchange confirmation was intentionally required for this draft-creation acceptance.

This confirms the previously reported LIVE hold + chart tap draft-creation regression is recovered.

### LIVE chart confirmation

FAIL / OPEN BLOCKER:

- the dashed LIVE pending Limit line does not confirm when the chart checkmark is pressed in the real UI;
- therefore Slice 1 is NOT fully accepted and the shared recovery is NOT complete;
- automated LIVE integration tests passing do not override this real-UI failure.

The next investigation must start after draft creation, along the real path:

```text
PendingLimitLine chart checkmark
    -> onPendingLimitConfirm(draftId)
    -> App.submitLimitDraft(draftId)
    -> common draft confirmation eligibility
    -> LIVE capability / current authority gate
    -> executeLiveLimitCreate
```

Do not start the next session by changing the hold/tap gesture again: that part is now real-UI PASS.

## Safety

No LIVE gate was relaxed.

No LIVE STOP/TAKE/full-close behavior was enabled.

No blind retry was introduced.

LIVE account/session fencing, single-attempt ownership and reconciliation behavior remain unchanged.

The user should not repeatedly press the LIVE chart checkmark while the blocker is unresolved; diagnose the non-confirming path before any further real mutation acceptance.

## Next session

Resume from the current GitHub `main` and treat these facts as authoritative:

1. shared Limit core tests PASS;
2. existing targeted LIVE Limit integration tests PASS;
3. production frontend build PASS;
4. PAPER chart Limit create + confirm real UI PASS;
5. LIVE hold BUY + chart tap draft creation real UI PASS;
6. LIVE dashed chart Limit checkmark confirmation real UI FAIL — current blocker.

Investigate the chart-confirm path end-to-end and add a test that reproduces the real interaction boundary before changing execution behavior. Preserve PAPER/LIVE common semantics and keep provider-specific differences behind the execution/safety boundary.
