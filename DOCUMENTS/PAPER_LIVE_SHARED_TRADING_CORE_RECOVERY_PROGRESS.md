# PAPER / LIVE SHARED TRADING CORE RECOVERY — PROGRESS

Date: 2026-09-05
Parent direction: `DOCUMENTS/PAPER_LIVE_SHARED_TRADING_CORE_RECOVERY.md`
Status: SLICE 1 IMPLEMENTED ON GITHUB / LOCAL VERIFICATION PENDING

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

## Safety

No LIVE gate was relaxed.

No LIVE STOP/TAKE/full-close behavior was enabled.

No blind retry was introduced.

LIVE account/session fencing, single-attempt ownership and reconciliation behavior remain unchanged.

## Verification still required after pull

This GitHub-direct slice has not yet been compiled or executed in the user's local runtime. After pulling, required evidence is:

1. focused frontend tests including `limitInteractionCore.test.ts`;
2. existing Limit/PAPER/LIVE regression tests;
3. production frontend build;
4. real UI PAPER Limit create + chart confirm;
5. LIVE hold BUY/SELL + chart tap draft-only acceptance with no confirmation / no exchange mutation.

If any automated verification fails, treat this slice as unaccepted and repair it before real acceptance.
