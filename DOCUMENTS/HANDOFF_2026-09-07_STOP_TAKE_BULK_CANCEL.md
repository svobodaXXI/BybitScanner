# Handoff — STOP/TAKE popup/line sync and PAPER side bulk-cancel

Date: 2026-09-07

## Branch / PR

- PR #47: `fix: sync STOP popup with pending line`
- Branch: `fix/stop-popup-line-sync`
- Last validated code head before this handoff: `fa4ef67d2641010f0f29f3d7e82444b6ff568f4a`
- PR remains OPEN and MUST NOT be merged yet because real-phone PAPER bulk-cancel acceptance failed.
- `main` advanced during the session; PR metadata reported mergeable=false before this handoff. Re-sync branch with latest `main` before merge work resumes.

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

## Validation completed

### Targeted tests at branch head `fa4ef67`
Passed:
- `src/components/StopSettings.test.tsx` — 2/2
- `src/chart/StopLine.test.tsx` — 5/5
- `src/components/ModePanel.paperBulkCancel.test.tsx` — 1/1
- `src/components/ModePanel.liveBulkCancel.test.tsx` — 1/1
- `src/components/ModePanel.stop.test.tsx` — 6/6
- `src/app/App.test.tsx` — 4/4

The focused PAPER bulk-cancel mock regression specifically passed for five Buy limits after one side confirmation.

Two existing tests in `ModePanel.test.tsx` still failed:
- PAPER Market success-status test
- PAPER Full Close success-status test

Those two failures are outside the STOP/TAKE change and remained present after restoring `ModePanel.test.tsx` from current main.

### Production build
`npm run build` PASS.

Vite emitted only the existing chunk-size warning (~509 kB main JS chunk). This is a non-blocking optimization warning, not a build failure.

### Real-phone PAPER acceptance — PASS
On production preview `http://192.168.100.8:4173/`:

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

## BLOCKER — PAPER side bulk-cancel real runtime

Expected:
- with 5 PAPER Buy Limit orders, tap the side-level `×` beside `BUY LIMITS`, confirm once, and all five orders disappear.

Actual real-phone behavior:
- only one order disappears per confirmation attempt;
- the UI shows `PAPER LIMIT cancellation failed` above the LIMIT controls;
- screenshot at end of session showed `BUY LIMITS 3`, `SELL LIMITS 0` and the failure message;
- therefore real runtime acceptance is FAIL even though the isolated 5-order component mock test passes.

This proves the defect is below or beyond the isolated `ModePanel` loop test. Do not mark bulk-cancel fixed from the mock regression alone.

## Current implementation path relevant to blocker

`ModePanel.cancelLimits()` loops through the captured side-order snapshot and awaits `onLimitCancel(order_id)` sequentially.

In App, `onLimitCancel` is `cancelPaperLimit`.

PAPER cancel path:
`ModePanel.cancelLimits`
→ `App.cancelPaperLimit`
→ `PaperLimitOrderMutationController.cancel`
→ nested `paperTradingStore.runMutation(CANCEL_LIMIT:<orderId>)`
→ `executePaperLimitCancel`
→ POST `/api/limit/cancel`
→ `applyPaperStateForSession`.

The outer side operation itself is also wrapped in `paperTradingStore.runMutation(CANCEL_SIDE:<side>)`.

Observed `PAPER LIMIT cancellation failed` comes from the catch path in `ModePanel.cancelLimits()`, so one of the later sequential cancellations is throwing/rejecting after at least one earlier cancellation has succeeded.

## First diagnostic for next session

Do not change code first. Reproduce in PAPER with several Buy limits and inspect the backend/runtime evidence for each sequential `/api/limit/cancel` request.

First read-only state check if limits still exist:

```powershell
Invoke-RestMethod "http://localhost:8765/api/paper-state?symbol=BTCUSDT" | ConvertTo-Json -Depth 8
```

Then determine exactly why the second/subsequent cancellation rejects. Candidate areas to verify, not assume:
- returned `paper_state.state_revision` progression for each cancellation;
- whether `applyPaperStateForSession` rejects a subsequent response as stale/mismatched;
- nested `runMutation` ownership between `CANCEL_SIDE:<side>` and `CANCEL_LIMIT:<orderId>`;
- backend/idempotency/client_action_id behavior across rapid sequential cancellation requests;
- whether controller/application refresh changes the authoritative order snapshot during the loop in a way that invalidates the next request.

No blind retry. Diagnose the first rejected cancellation from evidence.

## Acceptance required before merge

1. Fix root cause of PAPER side bulk-cancel runtime failure.
2. Add a regression at the correct integration/controller level, not only a mocked `ModePanel` loop test.
3. Targeted tests PASS.
4. `npm run build` PASS.
5. Fresh production preview.
6. Real-phone PAPER test: create 5 Buy limits → one side `×` → one confirmation → all 5 disappear → count 0 → no failure status.
7. Mirror/verify Sell side if code path differs or evidence indicates need.
8. Update PR #47 validation notes.
9. Re-sync PR branch with latest main and verify mergeability/CI.
10. Only then merge.

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
