# PAPER / LIVE SHARED TRADING CORE RECOVERY — PROGRESS

Date: 2026-09-06
Parent direction: `DOCUMENTS/PAPER_LIVE_SHARED_TRADING_CORE_RECOVERY.md`
Status: SLICE 1 REAL LIVE CONFIRM ACCEPTED / COMPLETE

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

Therefore the observed no-submit state was not evidence that the chart touch-confirm handler was broken. It was consistent with the intended fail-closed LIVE capability boundary.

## Safe runtime rehearsal on 2026-09-06

The backend was restarted with authoritative build attribution:

`d05cae669c07a66d76682ca7b65091d6c28eb7e7`

and deployment identity `local-rehearsal`, while all LIVE mutation gates remained explicitly OFF.

Operator diagnostics confirmed:

- active Bybit MAINNET account: READY and writable;
- account session generation: `2`;
- durable acceptance service available: `true`;
- LIVE Market capability: `false`;
- LIVE Limit capability: `false`;
- LIVE parity capability: `false`;
- unresolved LIVE Limit actions: `0`;
- unresolved LIVE Limit operations: `0`;
- all previous acceptance sessions non-ARMED (`EXPIRED`, `EXHAUSTED`, or `REVOKED`).

The built-in safe rehearsal then ran with session id `live-limit-ong-safe-rehearsal-006`, symbol `ONGUSDT`, capability `LIVE_LIMIT_CREATE`, max create count `1`, aggregate ceiling `5.20 USDT`, and per-order ceiling `5.20 USDT`.

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

This proved the durable acceptance administration path, runtime/build/database/session attribution, ARMED diagnostics, revocation, and final fail-closed state without requesting an exchange mutation.

## Controlled real LIVE Limit chart-confirm acceptance on 2026-09-06

The user gave separate explicit authorization for exactly one real LIVE Limit create with a maximum notional of `5.20 USDT`.

The local checkout was synchronized to build:

`fa9a4d0a9242ab206b4d9bec7370e794d6e07bf9`

The backend was restarted as `local-live-limit-acceptance` with only the required authority enabled:

- `LIVE_MAINNET_AUTHORIZED=true`;
- `LIVE_LIMIT_MUTATIONS_ENABLED=true`;
- `LIVE_LIMIT_ACCEPTANCE_NOTIONAL_CEILING=5.20`;
- LIVE Market mutations remained OFF;
- LIVE parity mutations remained OFF.

Pre-arm diagnostics confirmed:

- active account `bybit-9e55e9b1839a41b4b492a54a25b26295`;
- MAINNET / READY / writable;
- account session generation `2`;
- build/database/session attribution current;
- LIVE Limit capability `true`;
- Market and parity capabilities `false`;
- unresolved actions `0`;
- unresolved operations `0`.

Acceptance session `live-limit-ong-shared-core-accept-007` was armed for:

- symbol `ONGUSDT`;
- capability `LIVE_LIMIT_CREATE`;
- max create count `1`;
- aggregate ceiling `5.20 USDT`;
- per-order ceiling `5.20 USDT`.

A final pre-dispatch inspect confirmed `state=ARMED`, `authority_matches_runtime=true`, `reserved_count=0`, `reserved_notional=0`, and no unresolved actions or operations.

The user then exercised the real Terminal path on `ONGUSDT`: created a BUY Limit draft and pressed the chart checkmark exactly once. The UI immediately showed `SUBMITTING...`; the pending dashed line then disappeared without a second press.

Post-dispatch operator diagnostics confirmed:

- `reserved_count=1`;
- `reserved_notional=5.20`;
- acceptance session state `EXHAUSTED`;
- unresolved action count `0`;
- unresolved operation count `0`.

Authoritative workspace refresh then showed the actual Bybit order:

```text
symbol = ONGUSDT
order_id = 53570b3f-f0c5-47b5-8665-1f9f29462b11
side = Buy
order_type = limit
price = 0.09247
quantity = 56
status = open
```

The exchange order notional at the accepted price/quantity is `5.17832 USDT`, below the `5.20 USDT` acceptance ceiling.

This is end-to-end acceptance evidence for the previously blocked shared path:

```text
LIVE chart checkmark
→ exact draft identity
→ App.submitLimitDraft
→ current LIVE authority
→ durable one-create acceptance admission
→ single exchange dispatch
→ authoritative Bybit open order
```

No duplicate create occurred, no UNKNOWN/reconciliation state remained, and the one-create acceptance budget was exhausted after the single authorized dispatch.

## Safety

No LIVE STOP/TAKE/full-close behavior was enabled.

No LIVE Market mutation was enabled for this acceptance.

No LIVE parity mutation was enabled for this acceptance.

No blind retry was introduced.

LIVE account/session fencing, single-attempt ownership, durable acceptance ownership, and reconciliation behavior remain unchanged.

The acceptance session is `EXHAUSTED`, so it cannot admit another create. Runtime mutation gates should be returned to their fail-closed OFF configuration after acceptance evidence is captured.

## Slice 1 result

SLICE 1 is accepted for the exercised path.

Evidence now includes:

1. shared Limit core tests PASS;
2. targeted LIVE integration tests PASS;
3. real `ChartPanel` + `PendingLimitLine` touch-confirm boundary PASS;
4. production frontend build PASS;
5. PAPER chart Limit create + confirm real UI PASS;
6. LIVE hold BUY + chart tap draft creation real UI PASS;
7. controlled real LIVE chart checkmark create PASS;
8. exactly one durable acceptance reservation consumed;
9. actual Bybit `ONGUSDT` BUY Limit observed open;
10. no unresolved LIVE action/operation after dispatch.

The previously open `LIVE dashed chart Limit checkmark confirmation` blocker is closed for this accepted path.

## Next step

Return the local runtime to fail-closed LIVE mutation gates OFF after the acceptance evidence is captured.

Then proceed with the next shared PAPER/LIVE trading-core slice rather than reopening the resolved hold/tap or chart-confirm path unless new evidence shows a regression.
