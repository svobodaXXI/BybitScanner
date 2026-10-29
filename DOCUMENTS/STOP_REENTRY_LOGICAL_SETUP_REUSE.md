# ROBOT STOP-reentry: logical next setup and mature-engine reuse

Status: **contract + pure policy under PR #668, NOT connected to PAPER_AUTO**.
Owner priority: complete cross-pattern STOP retries, then deploy to VPS after
targeted CI and PAPER acceptance; Codex is used only for authorized VPS/SSH
operations, not software development. **PAPER only. LIVE prohibited.**

## Research: reuse architecture, not engines

- [Hummingbot V2 controllers](https://hummingbot.org/strategies/v2-strategies/controllers/):
  a strategy/controller emits a proposal; the executor owns position lifecycle.
  **Reuse in BybitScanner:** Scanner detectors emit immutable candidates and
  canonical Robot owns execution/protection; do not import Hummingbot executors.
- [QuantConnect LEAN order events](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-events):
  trade state advances from actual order/fill events, including partial fills.
  **Reuse:** authoritative durable STOP execution + position reconciliation,
  not candle-touch assumptions; do not open a new order directly from a fill
  callback.
- [Freqtrade confirmation callbacks](https://docs.freqtrade.io/en/latest/strategy-callbacks/):
  independent entry confirmation is enforced at the latest order boundary.
  **Reuse:** canonical Robot Admission checks facts again at decision time.
  **Do not reuse** `adjust_trade_position()`: that can increase an open
  position, whereas owner requests a new entry ONLY after the old one is flat.
- [Freqtrade protections](https://www.freqtrade.io/en/stable/plugins/):
  cooldown, stoploss guard and drawdown checks are separate from strategy
  signal generation. **Reuse:** campaign-level cumulative risk and daily
  limits; do not introduce an automatic cooldown that suppresses owner-
  approved fresh patterns unless risk/backtesting supports it.

## Semantic distinction: trade idea, attempt, confirmation, position

A **campaign** freezes the symbol, direction, original structural thesis,
invalidation condition and initial risk budget. An **attempt** is one
independently executed, protected position arising from a uniquely identified,
fresh candidate. A **new setup** may be a different strategy pattern
(engulfing -> double bottom -> L-shape or MIRROR -> Wedge), but must be
structurally compatible with the same frozen thesis and direction.

1. Initial confirmed entry is counted as attempt 1. After **verified filled
   STOP**, not a wick touching the stop, campaign enters WAIT_NEW_SETUP.
2. Scanner keeps detecting all supported patterns and applicable timeframes.
   STOP does not automatically open or submit anything. A completed *new*
   formation, confirmed **after the last STOP close timestamp**, with a
   distinct immutable source identity may propose an entry.
3. **Double bottom:** bullish second low and neckline are frozen by its own
   detector. LONG only after a subsequent *closed* confirmation candle
   **above** neckline, not just a wick or an in-progress candle. Double top
   is symmetric SHORT after closed confirmation **below** neckline. Neither
   detector is currently proven Robot-capable; #647/new structural adapter
   must be supplied before such signals trade.
4. **L-shape after STOP:** use the already-implemented L-shape strategy's
   complete frozen geometry, retest and entry-ready contract; new setup must
   be confirmed after STOP. No unconditional breakout chase. A prior failed
   reversal does not invalidate a subsequently established *continuation*
   setup unless the frozen campaign thesis/direction is broken.
5. **MIRROR:** retain the existing standalone next-closed-candle confirmation
   beyond reversal candle body and its 1m/5m constraints; do not make a
   neutral doji an automatic trade. Wedge and Box keep their own confirmed
   break/retest entry rules, Net RR and structural limits. #647 is the shared
   candle recognition contract, not permission for new automatic trades.
6. Only if prior attempt is proven closed, account/Robot/symbol is FLAT,
   no active ENTRY_PENDING / order / unresolved protection, the candidate is
   fresh and owner runtime ready, and the total **spent + worst-case current
   and proposed** exposure stays within the original frozen campaign risk:
   reserve candidate atomically and pass it to **existing**
   Scanner -> candidate persistence -> PAPER_AUTO -> Robot Admission ->
   PAPER LIMIT -> fills -> STOP/TAKE.
7. At most **1 original + 2 post-STOP attempts**; attempt count is per durable
   campaign, not per pattern. TAKE, invalidated structure, owner STOP, exhausted
   budget or conflicting ownership terminate / block. A pattern in opposite
   direction cannot be smuggled in as a retry; it is a separate setup which
   still needs its own normal gates.

## Minimal implementation — owner state only once

- Keep `stop_reentry_policy.py` (proof of STOP, no open/pending, Robot ready,
  quota and risk availability); `stop_reentry_setup.py` (pure fresh logical
  setup / closed-candle / neckline test); `stop_reentry_campaign.py` (pure
  risk-limited attempt proposal). These three may later be consolidated,
  but **no second execution engine** is introduced.
- **Missing P0 durable wiring:** add the minimal SQLite single-writer
  `reentry_campaign` + `reentry_attempt` records or extend existing durable
  Robot state if it already provides identity/revision proof. Unique constraints
  on campaign/attempt/candidate and source fingerprint; compare-and-set revision
  to prevent dual Scanner callbacks / process restarts from doubling entries.
  Fill & STOP proof comes from authoritative Robot executions/trades.
- **Missing adapter wiring:** map immutable existing Wedge/Box/MIRROR/L-shape
  snapshots to the campaign without modifying their detector geometry.
  Create #647 candle and double-bottom/top recognition only when verified;
  never infer a double-bottom from a STOP alone. For a new confirmed setup
  whose original structural thesis is no longer valid, create a separately
  admissible campaign instead of bypassing risk/attempt cap.
- **Missing risk wiring:** model cumulative realized STOP costs, all fees,
  slippage and reserved worst-case pending/live losses without double
  counting. Treat unknown/ambiguous numbers as WAIT. Do not reset the
  frozen initial budget at every pattern transition.
- **Acceptance:** deterministic event tests (STOP -> engulfing ->
  double-bottom neckline -> L-shape continuation; STOP -> MIRROR -> Wedge);
  no pre-STOP, same-candle, wick-only, still-forming, duplicate, TAKE,
  pending, OPEN, owner-paused, changed-thesis, wrong direction, stale TF,
  4th entry, unknown cost, restart/crash partial fill. Prove candidate id,
  trade id, protection, charged risk and event attribution on isolated PAPER
  DB. Historical backtests must avoid look-ahead and include fees/slippage.
  No real VPS runtime start without separate owner approval.

## Boundary of PR #668

This PR currently provides **only side-effect-free policy primitives and
tests**. It is not production reentry. The final success condition remains a
durable, end-to-end automatic PAPER reentry from an actual fresh confirmed
signal, with STOP/TAKE, correct attribution and exactly-once ledger updates.
