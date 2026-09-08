# Handoff — STOP/TAKE popup/line sync and PAPER side bulk-cancel

Date: 2026-09-07
Updated: 2026-09-08

## Branch / PR

- PR #47: `fix: sync STOP popup with pending line`
- Branch: `fix/stop-popup-line-sync`
- Last validated code head: `7be62dcf259c3d85136046f716064a97b19b3c29`
- PAPER side bulk-cancel blocker is now RESOLVED and accepted on the real phone.
- `main` advanced during the session. Re-sync branch with latest `main` and verify mergeability/CI before merge.

## Implemented behavior in PR #47

### STOP
- Short tap opens STOP popup and dashed STOP draft simultaneously.
- Dashed STOP draft is immediately draggable.
- Dragging the STOP line updates popup Price and Percent.
- Editing popup Price/Percent moves the same STOP draft.
- Popup uses `Тек. цена` instead of `Reference`.
- Current-price formatting follows authoritative tick precision.
- Percent presentation uses one decimal place.
- Popup controls are `✓` / `×` instead of Apply / Close.
- `×` dismisses popup and pending draft without mutation.
- `✓` uses the existing protection mutation lifecycle.
- After confirmation, active solid STOP remains selected and shows edit/delete controls.
- Tap outside hides active STOP controls.
- Tap active STOP line reveals controls again.

### TAKE
- STOP behavior above is mirrored for TAKE.
- Short tap opens TAKE popup and dashed TAKE draft simultaneously.
- Popup/line synchronization, current-price label, tick formatting, one-decimal Percent, `✓`/`×`, selected-active lifecycle and outside-tap behavior are symmetric with STOP.

### Safety preserved
- No LIVE mutation bypass was added.
- Existing shared protection controllers remain authoritative.
- UNKNOWN/reconciliation remains fail-closed.
- No blind retry behavior was introduced.

## PAPER side bulk-cancel diagnosis and resolution

### Real-runtime failure that was reproduced
Expected:
- with several PAPER Buy Limit orders, tap the side-level `×` beside `BUY LIMITS`, confirm once, and all side orders disappear.

Observed before the final fix:
- one cancellation reached the backend and succeeded;
- the frontend then threw `PAPER LIMIT cancellation failed` and stopped the sequential side loop;
- authoritative state showed only one order removed per confirmation.

### Diagnostic evidence
1. PAPER `state_revision` was stable without mutations (`411 → 411`), so a spontaneous revision race was ruled out.
2. Two direct sequential POST `/api/limit/cancel` calls with distinct action IDs both succeeded (`411 → 412 → 413`), proving the backend/runtime can process sequential cancels correctly.
3. The earlier same-millisecond `client_action_id` collision hypothesis was fixed defensively with order-specific PAPER cancel IDs, but real-phone acceptance still failed, proving that was not the whole root cause.
4. The remaining frontend defect was a stale PAPER session-fence callback: `applyPaperStateForSession` had been captured before the active PAPER session was installed and then retained by `cancelPaperLimit` through an incomplete `useCallback` dependency set. The first backend cancel completed, but the returned authoritative PAPER state was rejected by the stale callback, causing the side loop to abort.

### Final fix
- `App.cancelPaperLimit` now refreshes its closure when the session-scoped `applyPaperStateForSession` callback changes, so each PAPER cancel response is validated against the current session fence.
- Integration regression added: `src/app/App.paperLimitSessionFence.test.tsx`.
- Existing order-specific PAPER cancel action-ID regression remains in `src/orders/limitOrderMutationSubmission.test.ts`.
- Existing one-confirm side bulk-cancel component regression remains in `src/components/ModePanel.paperBulkCancel.test.tsx`.

## Validation completed

### Latest targeted validation at code head `7be62dc`
Command:

```powershell
npm test -- --run src\app\App.paperLimitSessionFence.test.tsx src\orders\limitOrderMutationSubmission.test.ts src\components\ModePanel.paperBulkCancel.test.tsx
```

Result:
- `App.paperLimitSessionFence.test.tsx` — 1/1 PASS
- `limitOrderMutationSubmission.test.ts` — 7/7 PASS
- `ModePanel.paperBulkCancel.test.tsx` — 1/1 PASS
- total 9/9 PASS

### Production build
`npm run build` PASS at `7be62dc`.

Vite emitted only the existing chunk-size warning (~509 kB main JS chunk). This is a non-blocking optimization warning, not a build failure.

### Real-phone PAPER acceptance — PASS
Production preview:
`http://192.168.100.8:4173/`

STOP:
- popup + dashed line simultaneous: PASS
- `Тек. цена`: PASS
- Percent one decimal: PASS
- dashed-line drag updates popup Price/%: PASS
- after `✓`, active line remains selected with edit/delete controls: PASS
- outside tap hides controls: PASS
- tap active line shows controls: PASS

TAKE:
- same mirrored checks: PASS

PAPER side Buy bulk-cancel after final fix:
- UI showed 3 active Buy limits before the acceptance action;
- user tapped the side-level `×` once and confirmed once;
- all Buy limits disappeared in the UI;
- authoritative backend check returned `state_revision: 420` and `active_limit_orders: []`;
- no second cancellation attempt was required.

This closes the real-runtime PAPER Buy bulk-cancel blocker.

## Remaining pre-merge work

1. Re-sync PR branch with latest `main`.
2. Resolve any conflicts without touching unrelated/user-owned files.
3. Re-run targeted validation and `npm run build` after the re-sync if the branch changes materially.
4. Verify PR mergeability and CI/status checks.
5. Keep PR draft until those checks are complete.
6. Only then merge.

Sell-side bulk cancel uses the same shared PAPER side loop and order-cancel path; no side-specific code path was identified during diagnosis. A separate real-phone Sell acceptance is not required unless re-sync or subsequent evidence introduces a side-specific difference.

## User-owned files
Do not touch:
- `New Chat.txt`
- `Terminal_almost.zip`
- `test_100.txt`
- `test_compare_falling_candidates.py`
- `Инструкция по запуску на новом компьютере.txt`
- `пароль от VPS.txt`

## LIVE safety
No new LIVE acceptance was performed in this session. Do not reuse old LIVE authorization without re-checking authorization freshness/session binding. External/user-owned ONG SELL remains out of scope and must not be touched without explicit permission.
