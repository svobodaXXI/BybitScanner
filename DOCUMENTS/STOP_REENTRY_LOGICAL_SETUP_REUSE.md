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
- **Owner decision 29.10: attempt journal MUST reuse Trading Diary/statistics.**
  Existing `robot_trades`, `robot_candidates`, `executions`, protection
  obligations and `terminal.statistics.reader.RobotStatisticsReader` are the
  authoritative trade, fill, exit and financial data. The `terminal.diary`
  read side projects campaign -> individual attempt -> original/new pattern ->
  exit reason -> gross/fees/known-cost net, preserving attribution and missing
  cost coverage. It must not duplicate trades, fees or PnL into a second journal.
- **P0 canonical identity linkage in existing PAPER SQLite:** version 26 adds
  only `robot_reentry_campaigns` and `robot_reentry_attempts` identity and
  reservation tables. They are linkage/atomic admission metadata, **not** a
  parallel trading diary or execution ledger. `terminal.diary.reentry` reads
  them through the existing `RobotStatisticsReader`, strictly read-only and
  fail-closed on duplicate/non-STOP/overlapping lineage. The separate D2
  `.trading_diary.sqlite3` remains research-only and MUST NOT become order
  admission authority, because transactions cannot be atomic across stores.
- **Implemented in draft PR #668 (not active strategy behavior):**
  `SQLiteStore.create_robot_reentry_campaign` and
  `SQLiteStore.reserve_robot_stop_reentry` require the existing canonical
  `BEGIN IMMEDIATE` Robot admission transaction and durable READY state.
  `admit_robot_candidate(..., reentry=RobotReentryAdmissionRequest(...))`
  and the Box handoff accept an optional **internal typed** strategy proof
  so candidate and Diary linkage commit or rollback together. Without that
  argument the original behaviour is unchanged. The last STOP must be a
  closed `robot_trades` row plus resolved `paper_protection_obligations`
  with a matching immutable `executions` record. Account/symbol/direction,
  synchronized FLAT, no pending entry/protection, unique candidate/attempt
  and cumulative realized loss+fees+new reserved worst-case risk are checked.
  Unique schema constraints forbid >3 slots or restarting the same frozen
  thesis to reset its risk budget.
- **New opt-in slice:** `terminal.application.robot_reentry_adapter`
  now derives trusted admission proposals from immutable MIRROR, L-shape
  and **1m Wedge** terms: MIRROR's *next* closed confirmation candle
  (`robot_l_shape.initialize_state` verifies the kind, identity and TF),
  L-shape's completed breakout candle, or Wedge's exact 1m
  `scanner_geometry_cursor` anchor + independently validated immutable
  Robot geometry (not an envelope arrival timestamp). Wedge still waits
  for its own breakout/retest before any actual order. The adapter reserves the maximum
  non-Box permitted STOP distance (1.5%) on the existing 250-USDT Robot RO
  plus two-sided fees and conservative adverse slippage. First admission
  freezes the three-attempt risk budget; subsequent matching direction STOP
  campaign reuses the budget and obtains `previous_stop_exec_id` from the
  same canonical SQLite. No selection by symbol alone without direction,
  completed pattern and uniquely outstanding durable campaign.
  **Existing `PAPER_AUTO` calls this adapter when and only when environment
  `BYBITSCANNER_STOP_REENTRY_AUTO=1`.** OFF by default; no production rollout
  approved. A later TAKE permits a new independent frozen idea; a fourth STOP
  entry is refused. Existing unlinked Wedge/Box STOP cannot be treated as a
  first attempt in this opt-in slice: it fails closed until canonical
  backfill/adapters are built.
- **Still missing P0:** Box frozen-plan risk and closed-candle provenance;
  5m-to-1m Wedge handoff assurance; unknown-cursor/stale Wedge candidates
  remain outside this opt-in route. Generalized initial-campaign backfill
  for already stopped pre-v26 Box/Wedge trades must be proven before
  universal coverage. Exact instrument-specific loss/fees and durable
  prior-campaign linkage still require PAPER acceptance.
  The standalone double-bottom/top detector and candle recognizer (#647)
  must independently produce verified candidates; no pattern guessing.
  Wedge without the verified 1m cursor, or any Box plan, still uses its
  older normal PAPER_AUTO path, so enabling the flag **is NOT safe or
  sufficient for the owner's full universal 1+2 retry requirement**. Complete the universal
  dispatch enforcement and full PAPER replay/restart acceptance before
  enabling flag, merge or deploying to VPS.
- **Reservation is not an executed attempt.** Preserve both identities:
  queued/cancelled/no-fill candidates are Diary observations, but do not count
  as verified filled STOP losses. A retry needs an earlier executed-and-closed
  position. No-fill reservation reuse requires authoritative cancellation
  evidence and concurrency fencing, not just the absence of a trade row.
- **Formation time is not confirmation time.** An emerging double bottom may
  begin before the preceding STOP; only its *new confirming closed candle*
  must be after STOP. `robot_trades.signal_time_ms` can refer to earlier
  formation evidence. The Diary proves trade non-overlap, whereas canonical
  Admission independently proves post-STOP confirmation.
- **Diary analytics:** campaign, chronological pattern/attempt lineage,
  STOP/TAKE, realized gross/fees/known-cost net, and data coverage must be
  derived from existing statistics. Unknown funding/external costs stay
  unknown; known-cost net is not silently claimed to be complete net.

- **Missing Box, higher-TF Wedge and double-extremum adapters:** map their
  independently proven entry terms to the campaign without modifying geometry.
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

This PR now includes **pure policy, canonical PAPER identity reservations
and an optional atomic Robot Admission boundary**, plus targeted tests.
The opt-in MIRROR/L-shape PAPER_AUTO route now passes a verified request
but Wedge/Box and universal 1+2 fencing are incomplete. It is **not
production-ready automatic reentry**. The final success condition remains a
durable, end-to-end automatic PAPER reentry from an actual fresh confirmed
signal, with STOP/TAKE, correct attribution and exactly-once ledger updates.
