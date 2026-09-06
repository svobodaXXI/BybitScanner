# PAPER / LIVE SHARED TRADING CORE RECOVERY — PROGRESS

Date: 2026-09-06
Parent direction: `DOCUMENTS/PAPER_LIVE_SHARED_TRADING_CORE_RECOVERY.md`
Status: SLICE 1 DIAGNOSED / REAL LIVE CONFIRM ACCEPTANCE PENDING EXPLICIT AUTHORIZATION

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

A later diagnostic boundary test exercised the real `ChartPanel` + `PendingLimitLine` touch-confirm routing and, together with the existing targeted suite, produced 33/33 PASS. This narrowed the real-phone failure away from gesture capture and exact draft-id routing.

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

### LIVE chart confirmation — diagnosis

The real-phone symptom was initially recorded as a chart-confirm failure. Subsequent end-to-end inspection and runtime diagnostics established that the tested runtime was fail-closed at the LIVE authority boundary rather than blocked at touch handling or `ChartPanel` routing.

The relevant frontend path is:

```text
PendingLimitLine chart checkmark
    -> onPendingLimitConfirm(draftId)
    -> App.submitLimitDraft(draftId)
    -> common draft confirmation eligibility
    -> LIVE capability / current authority gate
    -> executeLiveLimitCreate
```

`App.submitLimitDraft` requires current LIVE Limit authority. The workspace projection reports that authority through `capabilities.limit`. The diagnosed local runtime had `capabilities.limit=false` because LIVE mutation gates were OFF and, before restart with explicit build attribution, the durable acceptance service was unavailable.

Therefore the observed no-submit state is not evidence that the chart touch-confirm handler is broken. It is consistent with the intended fail-closed LIVE capability boundary.

## Safe runtime rehearsal on 2026-09-06

The backend was restarted with authoritative build attribution:

`d05cae669c07a66d76682ca7b65091d6c28eb7e7`

and deployment identity `local-rehearsal`, while all LIVE mutation gates remained explicitly OFF.

Operator diagnostics then confirmed:

- active Bybit MAINNET account: READY and writable;
- account session generation: `2`;
- durable acceptance service available: `true`;
- LIVE Market capability: `false`;
- LIVE Limit capability: `false`;
- LIVE parity capability: `false`;
- unresolved LIVE Limit actions: `0`;
- unresolved LIVE Limit operations: `0`;
- all previous acceptance sessions non-ARMED (`EXPIRED`, `EXHAUSTED`, or `REVOKED`).

The built-in safe rehearsal was then run with session id `live-limit-ong-safe-rehearsal-006`, symbol `ONGUSDT`, capability `LIVE_LIMIT_CREATE`, max create count `1`, aggregate ceiling `5.20 USDT`, and per-order ceiling `5.20 USDT`.

Result:

```text
status = PASS
exchange_mutation = NOT_REQUESTED
live_gates = OFF
workflow =
  INSPECTED_GATES_OFF
  ARM_REQUEST_VALIDATED
  ARMED_DIAGNOSTICS_CONFIRMED
  REVOKED
  FINAL_DIAGNOSTICS_CONFIRMED
```

This proves the durable acceptance administration path, runtime/build/database/session attribution, ARMED diagnostics, revocation, and final fail-closed state without requesting an exchange mutation.

## Safety

No LIVE gate was relaxed during diagnosis or rehearsal.

No LIVE STOP/TAKE/full-close behavior was enabled.

No blind retry was introduced.

LIVE account/session fencing, single-attempt ownership and reconciliation behavior remain unchanged.

A real LIVE Limit create is still separately authorization-gated. Safe rehearsal PASS does not authorize an exchange mutation.

## Next step

Do not change the hold/tap gesture or bypass the acceptance boundary.

The next meaningful acceptance is one deliberately bounded real LIVE Limit create only after separate explicit user authorization. Before that acceptance, runtime authority must be started with the exact authorized build/database/session identity and the dedicated LIVE Limit gates/ceiling, then one ARMED acceptance session must be created with the previously established one-create / 5.20-USDT budget.

Until that explicit authorization is given, keep all LIVE mutation gates OFF.
