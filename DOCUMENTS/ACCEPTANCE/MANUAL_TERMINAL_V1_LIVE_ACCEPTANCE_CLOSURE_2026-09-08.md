# Manual Terminal v1 — LIVE acceptance closure

Date: 2026-09-08

Status: ACCEPTED

Authoritative code baseline before this closure record:

- `394cb8c2334d2d7a05a0008971b8d4abf1c58749` — merge of PR #61, `fix: refresh stale LIVE market book via REST fallback`.

## Scope

This checkpoint records the final real-account acceptance evidence required for Manual Terminal v1 LIVE execution closure. It does not authorize Trading Robot/AUTOPILOT runtime implementation and does not grant standing LIVE mutation authority.

## LIVE Market acceptance

Instrument: `NILUSDT`.

Preflight:

- active Bybit MAINNET account was `READY`;
- workspace symbol was `NILUSDT`, session generation `2`;
- workspace and upstream market-data state were `READY` / `SUBSCRIBED`;
- `NILUSDT` was FLAT and had no open NILUSDT orders;
- runtime enabled only the explicitly authorized LIVE Market acceptance gate with a 10 USDT ceiling and single-flight guard.

Mutation:

- client action: `accept-nilusdt-market-buy-20260908-03`;
- requested side: BUY;
- requested notional: 10 USDT;
- result: `completed` / `filled`;
- command id: `cmd_da3fc664020e4cf394f7f77a7bd5ec38`;
- order link id: `tw_da3fc664020e4cf394f7f77a7bd5ec382`;
- reconciliation required: `false`.

Authoritative account refresh after execution showed:

- `NILUSDT` Long;
- size `195`;
- average entry `0.05121`;
- effective notional approximately 9.99 USDT;
- no STOP, TAKE or trailing protection was created implicitly.

This closes the real-money LIVE Market acceptance gate for Manual Terminal v1.

## Stale-book defect and fix

Before the successful acceptance, LIVE Market could fail closed with `live_market_context_unavailable` on a low-churn symbol even while workspace readiness remained `READY`. Root cause: a READY websocket order book could be older than the one-second LIVE Market freshness gate, while the existing REST order-book fallback was used only when no current websocket book existed.

PR #61 changed LIVE Market price acquisition so that:

- a fresh READY websocket book remains authoritative;
- if the websocket book is stale, the existing REST order-book provider is reused;
- the same READY and freshness checks are applied to the fallback result;
- fallback absence, exception or stale REST evidence remains fail-closed.

Focused regression test result on the branch before merge:

- `tests/test_live_market_stale_book_fallback.py` — `5 passed`.

## LIVE Full Close acceptance

The test Long created by the accepted LIVE Market execution was then closed under a separate explicit one-shot authorization.

Pre-close authoritative position:

- `NILUSDT` Long;
- size `195`;
- average entry `0.05121`;
- no STOP, TAKE or trailing protection.

Mutation:

- client action: `accept-nilusdt-full-close-20260908-02`;
- command id: `cmd_8c99e3f322204af7884af29e61ea5f45`;
- immediate result: `accepted_pending`;
- message: request pending authoritative exchange confirmation;
- reconciliation required: `false`.

The command was not repeated.

A subsequent explicit read-only account refresh advanced refresh generation to `1353` and returned no `NILUSDT` position, proving authoritative exchange-side `FLAT`.

This confirms the Full Close path without blind retry.

## Prior LIVE protection acceptance incorporated into closure

The Manual Terminal v1 closure also relies on already completed real-account protection acceptance from the same acceptance campaign:

- LIVE STOP acceptance on ONGUSDT was completed and reconciled;
- LIVE TAKE acceptance on NILUSDT completed with command `cmd_9d931555c1e45bc19686452577c71072`, normalized TAKE `0.05490`, and confirmed-active authoritative protection projection;
- the historical flat/protection reconciliation defects discovered during those acceptances were fixed and regression-tested before this final Market acceptance.

No consumed authorization may be reused.

## LIVE Limit acceptance incorporated into closure

LIVE Limit create/cancel acceptance had already been recorded and merged before this checkpoint. No repeat real-money Limit mutation was required for this closure.

## External/user-owned state

The acceptance campaign did not take ownership of unrelated user/external positions or orders. In particular, the external MetaScalp ONGUSDT SELL order

- order id `23d839cd-b768-4a27-b415-a7baec8be0ab`

remained open and untouched through the final account refresh.

## Safety conclusion

Manual Terminal v1 LIVE acceptance is complete for the required mutation families:

- Market — ACCEPTED;
- Limit — ACCEPTED;
- STOP — ACCEPTED;
- TAKE — ACCEPTED;
- Full Close — ACCEPTED.

The runtime remains default-off for LIVE mutations. Each future real-money mutation still requires its own applicable authorization boundary; this closure checkpoint is not standing authorization.

Trading Robot/AUTOPILOT runtime implementation remains outside this acceptance and is not authorized by this record.
