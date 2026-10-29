# ROBOT STOP-reentry: logical next setup and mature-engine reuse

Status: **bounded PAPER_AUTO linkage merged by PR #668; feature OFF by default
and eligible for owner-approved PAPER activation only with the fail-closed
limits below. It is not universal pattern support.**
Owner priority: operate only the accepted bounded retry path and keep every
unproved pattern/context on the canonical WAIT path. **PAPER only. LIVE
prohibited.**

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
  `BYBITSCANNER_STOP_REENTRY_AUTO=1`.** OFF by default. A later authoritative
  TAKE permits a new independent frozen idea; a fourth STOP
  entry is refused. Existing unlinked Wedge/Box STOP cannot be treated as a
  first attempt in this opt-in slice: it fails closed until canonical
  backfill/adapters are built.
- **Added in this draft:** immutable Box plan `decision_time_ms` +
  completed source candle and worst-case frozen grid `net_stop_loss` /
  `partial_fill_loss_upper_bound` + conservative quantity-weighted
  slippage are now used for the attempt's budget (NOT a flat 250-USDT
  non-Box risk). The original `BOX_PLAN_ONLY` row is hash-verified,
  Robot-created child is recorded as the actual admitted attempt, and
  source plan/child are never mistaken for two separate entries.
  Wedge 5m uses its already-frozen affine 1m `robot_geometry` and
  `scanner_geometry_cursor`, rechecked by canonical Wedge state machine.
  A malformed/historical unsupported snapshot does not invent a candle,
  stop or strategy. Both source types share the same PAPER_AUTO →
  canonical Robot Admission → Diary linkage.
- **Universal fail-closed dispatch:** when
  `BYBITSCANNER_STOP_REENTRY_AUTO=1`, an unsupported or unproven
  Scanner/Box candidate cannot silently fall through to the normal
  untracked Robot admission. The flag is still OFF by default.
- **Implemented conservative matching boundary:** `robot_reentry_thesis`
  derives a frozen directional price corridor from the actual immutable
  previous candidate (MIRROR, L-shape, Wedge or Box), fetched and hash-
  verified by canonical Robot Admission, and from the new independently
  confirmed candidate. The new reference must remain within the previous
  STOP-to-TAKE structure; price corridors must overlap. Symbol/direction
  by themselves never qualify. Any explicit `reentry_parent` signal hint
  is validated against that exact candidate ID and SHA; it cannot override
  the canonical DB or price proof. The Robot may establish the parent
  automatically in its transaction, so Scanner candidates need no manual
  lineage annotation. Failure records auditable PAPER_AUTO
  `WAIT:REENTRY_THESIS_UNPROVEN` and no candidate/order reservation.
  The definition is intentionally conservative: distant continuation
  formations, older incompatible snapshots and unlinked historical STOPs
  remain WAIT until a more specific strategy-context bridge exists.
  Pre-v26/unlinked terminal trades also fail closed unless the last canonical
  exit is TAKE: STOP, MANUAL, TAKEOVER and emergency/unknown lineage cannot
  mint a fresh three-attempt budget.
- **Actual protected retry E2E now demonstrated (isolated DB):**
  `tests/test_stop_reentry_paper_e2e.py` reuses the production
  `MirrorStandaloneHarness`. The real MIRROR Scanner candidate receives a
  canonical PAPER LIMIT/fill and STOP, then the **real**
  `l_shape_scanner.observe_l_shape` detects a fresh latest-closed 5m
  breakout from synthetic market candles, freezes its genuine geometry,
  and the canonical PAPER_AUTO reentry routes that signal through the
  existing Robot retest monitor. A *different* PAPER LIMIT fills and
  closes by TAKE. No artificial hand-authored L-shape terms are used.
  Both closures have STOP/TAKE protection executions, and existing Trading
  Diary calculates 2 filled attempts with individual and aggregate gross,
  fees and known-cost net. The test restarts the exact same SQLite runtime
  after closure and proves no duplicate order/execution.
  The E2E is included in `robot-paper-acceptance-ci.yml`, not the thin
  unit-only policy workflow. A second test
  `tests/test_stop_reentry_scanner_lshape.py` exercises the **actual**
  `l_shape_scanner.observe_l_shape` detector on a fresh latest CLOSED
  breakout and its immutable `_robot_signal_snapshot` to the canonical
  previous STOP campaign. It separately proves that the same old breakout
  is no longer emitted if a subsequent candle closes without a new signal.
  The formerly separate tests now also pass as ONE uninterrupted
  real Scanner-detection → Admission → PAPER matcher lifecycle in
  [GitHub Actions #40865975980](https://github.com/svobodaXXI/BybitScanner/actions/runs/40865975980)
  (3/3 workflows PASS). The E2E independently proves per-trade fees and
  Diary aggregate net equal actual fills, then restart no-duplicate.
- **Actual execution blocker fixed, not bypassed:** the L-shape Scanner
  ratio STOP fallback previously had gross RR exactly 2:1; the Robot
  correctly rejected it after two-tick entry adjustment and round-trip
  fees for failing the owner's Net RR >= 2:1. The fallback uses a
  conservative gross 3:1 stop distance for fee/slippage headroom,
  while retaining the original structural STOP whenever appropriate.
  This intentionally tightens fallback STOP placement; original geometry,
  instrument tick normalization, fee-inclusive Robot RR gate and
  protective fail-closed rules are unchanged.
- **2026-10-29 resolved: ONE spawned-child-to-protected-fill PAPER E2E PASS.**
  `tests/test_stop_reentry_paper_e2e.py` now proves in one uninterrupted
  disposable PAPER DB: actual MIRROR Scanner signal → first Robot LIMIT fill
  → canonical protected STOP → genuine L-shape detector running in spawned
  Scanner child on synthetic, aligned, latest-closed 5m OHLC → immutable
  candidate-ID relay through production `scanner_process` IPC →
  `PaperRuntime._dispatch_autopilot_shadow_scanner_candidate` →
  canonical PAPER_AUTO and **attempt_index=2** after the verified STOP →
  normal Robot closed-candle retest monitor → separate LIMIT/fill → TAKE
  → existing Diary reconciles attempts, gross/fees/known-cost net →
  restart against same SQLite without duplicate executions.
  PASS: [Robot PAPER acceptance #40875335919](https://github.com/svobodaXXI/BybitScanner/actions/runs/40875335919)
  (`1 passed` full E2E); all three workflows success at code commit
  `6fa5e28`. Independent spawned-IPC and freshness tests also remain PASS.
  No direct order call or disabled admission gate; no network or VPS.
- **Root cause of earlier combined E2E monitor stall:** after a real STOP,
  the deterministic test fabricated a just-closed future 5m candle and
  advanced only PAPER_AUTO's admission clock. The newly created candidate
  was timestamped in the simulated future; the real-time Robot monitor
  attempted to update it with an earlier wall-clock timestamp.
  `SQLiteStore.save_robot_candidate_state` correctly rejects that with
  `ConcurrentUpdate` (fail-closed monotonic timestamps); the monitor
  swallowed the expected CAS conflict. The isolated **test now patches
  the wall-clock for the whole post-STOP PAPER replay**, including
  Scanner admission, Robot monitor, matching and restart. It does NOT
  loosen SQLite CAS, protection, admission or RR. Keep 5m kline opening
  times aligned to 300000ms and never treat a forming candle as confirmed.
- **2026-10-29 #592 double-extremum increment:** new closed-candle
  `geometry/double_extremum.py` independently detects Double Top/Bottom
  only after the latest fully closed 1m/5m candle BODY crosses the neck.
  It rejects wick-only, stale or mismatched pivot geometry, and generates
  immutable `neckline_entry` STOP beyond the confirming candle extreme
  with measured target only when planned fee-aware Net RR >= 2:1.
  Existing `robot_l_shape` immediate confirmed LIMIT, Robot Admission,
  protected STOP/TAKE, PAPER_AUTO campaign lineage and risk are reused;
  `main.py` emits deduplicated Scanner candidates only when STOP-reentry
  feature is opted in. Focused detector/lineage policy and standard PAPER
  suites passed at commit `452fcb9`. This demonstrates executable parsing and
  integration, NOT an accepted automatic retry path. Double Top/Bottom now
  deliberately return no trusted reentry proposal, so opt-in PAPER_AUTO
  records `WAIT:REENTRY_THESIS_UNPROVEN` instead of reserving or ordering.
- **Bounded activation status (issue #592):** partial-fill plus
  crash/restart while retry #2 is OPEN and STOP/TAKE-armed passed in the
  protected PAPER acceptance workflow
  [#40892336459](https://github.com/svobodaXXI/BybitScanner/actions/runs/40892336459).
  Pre-v26/unlinked STOP and every non-TAKE terminal reason are now explicitly
  fail-closed and cannot reset risk. Remaining work is for broader support,
  not a prerequisite for this bounded activation: independent protected
  Double Top and Double Bottom retry E2E, continuation beyond the frozen
  corridor, and an explicit new-thesis transition after structural
  invalidation. Until those are implemented, each stays WAIT; do not claim
  universal support.
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

- **Outstanding structural context and double-extremum adapters:**
  frozen-corridor overlap is the currently tested conservative rule, but
  broader continuation beyond the previous TAKE requires a separately
  verified context/leg-of-trend model. Never infer a double bottom from
  an executed STOP. Build #647 neckline-close candidates independently
  and test both 1m and 5m confirmation. A genuinely new thesis after
  prior structural invalidation must have an explicit terminal transition,
  not a silent risk-budget reset.
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

## Bounded PAPER activation boundary after PR #668

This PR includes **canonical PAPER campaign identity/reservations,
atomic Robot Admission, bounded Box/Wedge/MIRROR/L-shape entry proofs and a
passing single-run spawned Scanner→actual runtime dispatcher→protected
post-STOP L-shape LIMIT fill→TAKE→Diary→restart E2E**. The same test exercises
the production-shaped IPC and monitoring route on synthetic market inputs.
Independent double-extremum neckline retries and continued-trend structural
context remain outside the accepted boundary and fail closed. Partial-fill /
crash recovery is accepted by Actions `40892336459`; unlinked non-TAKE exits
cannot create a campaign or reset risk. This remains **bounded PAPER reentry,
not universal reentry**. Enable the opt-in flag only for an owner-approved
PAPER runtime after integration and preflight; LIVE remains prohibited.
