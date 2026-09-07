# LIVE LIMIT CANCEL ACCEPTANCE CHECKPOINT

Date: 2026-09-07
Status: ACCEPTED
Scope: BybitScanner / Trading Workspace / real-phone LIVE Limit cancel acceptance

## Authoritative code checkpoint before this documentation update

`2010debeae485ac231e78ed7928e97abee7074e6`

At this checkpoint:

- shared PAPER/LIVE trading-core Slices 1-8 are COMPLETE;
- post-recovery Cleanup #1-#8 are COMPLETE;
- Stage 8 production-build phone acceptance is ACCEPTED;
- PR #43 (`fix: make LIMITS inventory dismissible`) is merged;
- the previously open REAL-PHONE LIVE LIMIT CANCEL ACCEPTANCE is now ACCEPTED.

## Acceptance envelope

Acceptance session:

`live-limit-ong-cancel-accept-011`

Authorized scope was exactly:

- account: `bybit-9e55e9b1839a41b4b492a54a25b26295`;
- environment: MAINNET;
- symbol: ONGUSDT;
- one LIVE LIMIT CREATE;
- maximum per-order and aggregate notional: 5.20 USDT;
- cancel the exact test Limit created by that acceptance;
- no MARKET, STOP, TAKE or full-close mutation;
- no bulk cancel;
- external/user-owned MetaScalp SELL excluded from the authorized scope.

The one-time authorization was consumed by this acceptance and must not be reused.

## Accepted LIVE order and cancel result

Test order created during the accepted envelope:

- order_id: `75609e45-c4f1-4ad2-828b-18185c8d5853`;
- side: Buy;
- price: 0.09225;
- quantity: 56 ONG;
- notional: 5.166 USDT.

Real-phone cancel result:

- cancel of the exact test BUY Limit succeeded at Bybit;
- MetaScalp removed the test order immediately;
- the Trading Workspace projection remained stale briefly, then removed the order after refresh latency;
- resulting visible side counters were BUY 0 / SELL 1;
- the remaining SELL was the pre-existing external/user-owned order and was not touched.

External/user-owned order intentionally preserved:

- order_id: `23d839cd-b768-4a27-b415-a7baec8be0ab`;
- side: Sell;
- price: 0.14684;
- quantity: 71 ONG.

Acceptance session 011 ended EXHAUSTED with one reserved successful create and no unresolved action/operation ownership. No additional CREATE is permitted under that session.

## Post-cancel UI defect and correction

During the accepted cancel flow a separate UI-only defect was observed:

- active LIMITS inventory did not close on outside tap;
- the inventory header `×` was wired as a cancel-all action rather than a pure close action.

PR #43 corrected this without changing exchange mutation semantics:

- outside `pointerdown` closes the open LIMITS inventory;
- header `×` closes the inventory only;
- header close does not call `onLimitCancel`;
- the separate side cancel-all control remains unchanged.

Verification on branch before merge:

- focused regression test: 2/2 PASS;
- production `npm run build`: PASS;
- Vite transformed 94 modules;
- >500 kB chunk warning remains informational and unrelated to this fix.

Real-phone post-fix verification:

- hold BUY LIMITS -> inventory opens;
- tap outside -> inventory closes: PASS;
- reopen inventory -> header `×` closes it without affecting orders: PASS.

PR #43 merge commit:

`2010debeae485ac231e78ed7928e97abee7074e6`

## Runtime safety after acceptance

The LIVE acceptance backend used for the real-money acceptance was stopped after the accepted cancel.

A later UI-only verification runtime was launched with LIVE mutation gates disabled:

- `LIVE_MAINNET_AUTHORIZED=false`;
- `LIVE_LIMIT_MUTATIONS_ENABLED=false`;
- `LIVE_MARKET_MUTATIONS_ENABLED=false`;
- `LIVE_PARITY_MUTATIONS_ENABLED=false`.

No new real-money authorization is carried forward from this checkpoint. Any future LIVE mutation requires a new explicit authorization and must preserve single-attempt ownership, authority fencing, fail-closed UNKNOWN/reconciliation behavior and no blind retry.

## Result

REAL-PHONE LIVE LIMIT CANCEL ACCEPTANCE: **ACCEPTED**.

The accepted mutation result is not invalidated by the observed frontend refresh delay: Bybit/MetaScalp confirmed removal first, and the Terminal projection converged afterward. The refresh latency is a presentation/reconciliation UX observation, not a failed cancel mutation.

The LIMITS inventory dismissal defect discovered during acceptance is also closed and real-phone verified.

## Next step

Do not repeat the consumed LIVE Limit acceptance session.

Recover from repository authority at the documentation merge checkpoint, then choose the next still-open Trading Workspace item from the authoritative roadmap/state documents. Any new real-money test must receive a new bounded explicit authorization before mutation.
