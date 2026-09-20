# Backlog (working queue, priorities, rules)

Status: WORKING BACKLOG (living document)
Last updated: 2026-09-19
Owner: user. When a task starts, Claude Code registers it as a ChangeRequest per the project rules; this file is the
single place where new ideas are parked until then.

## 0. Rules to avoid loose ends

1. WIP limit: one active task plus at most one background task that is only waiting (CI, review, deploy, live check).
2. A task is DONE only when: merged; deployed where relevant; verified live by a named check; run log / spec updated;
   the local branch is deleted; follow-ups are written here.
3. New ideas go into this file first, never into a running task.
4. Backend restart only with no open positions or with the robot PAUSED.
5. Until PR #153 (candle cache) runs on the machine that trades and is verified: do not press Pause, Stop, Close-all and do not
   call reconcile while positions are open (owner-thread REST stall, see run log section 9).
6. A second agent (Codex) works only in a separate `git worktree` on its own branch.
7. Commits are staged by explicit file list, never `git add -u` while unrelated edits sit in the tree.
8. At most 2 commands per message to the user; no manual file placement (ASSISTANT_PROTOCOL 2.2.2 and 8.11, DECISION-010).
   Repo and runtime routine goes to Claude Code prompts.

## 1. State snapshot (2026-09-19 late)

- `main` contains PRs #148-#153: emoji labels, position card + chart, lifecycle posts, unsupported-pattern fix, owner-queue
  diagnostics, light candidate reads, signal-timeframe chart, owner-thread candle cache.
- The live run is on the PC (PAPER backend + Telegram listener; no scanner running). PC robot state: `RECONCILIATION_REQUIRED`
  (`ingress_overflow`, CFXUSDT, 2026-09-19 21:15), open STGUSDT LONG, 3 APPROVED candidates. Next: restart the PC processes onto `main`
  (running processes keep old code), reconcile, resume. One Telegram poller only (the PC).
- The VPS has only the backend service (code `c363008`, without #153): robot `RECONCILIATION_REQUIRED`, open AAVEUSDT and LUNA2USDT,
  no listener and no scanner, so no Telegram posts. Leave it until they close, then stop the service.
- Scanner timeframe: VPS `TIMEFRAME = "5"` (decision: keep); the PC config still has "1" (see P3-9).
- Times: VPS is CEST, the user's Telegram and the PC are MSK (+1 h).

## 2. Prioritized queue

### P0 — stability of the live run
| # | Task | Status / next step |
|---|---|---|
| P0-1 | Owner-thread candle cache (PR #153): MERGED. Remaining: sync the PC, restart PC backend+listener (Claude Code prompt), reconcile, resume | Then a 30-minute load check on the PC (`protection-health`: `high_watermark`, `candle_cache_misses_owner`; backend window for `Slow PAPER owner task`). The PC also hit `ingress_overflow` on 2026-09-19 21:15 (CFXUSDT), so the fix is needed there |
| P0-2 | Conditional: only if overflow persists after P0-1, on whichever machine runs the robot (currently the PC) | Reconcile recovery-policy geometry index (`load_candles` per APPROVED candidate), admission catch-up loader; then a disk fsync benchmark (`synchronous=FULL`) on that machine |

### P1 — money-relevant, small
| # | Task | Status / next step |
|---|---|---|
| P1-1 | Analysis of PC closed trades (fees entry+exit) | DONE 2026-09-19: 25 trades, clean sample 10 (3 TAKE / 7 STOP, net -1.63 USDT), see section 6 |
| P1-2 | Minimum stop distance 0.7% (`structural_stop` floor) | Spec written, not started. Decide after the back-test A-3 |
| P1-3 | Chart window from pattern start (left margin, current candles right) | Small Telegram-side task; spec in section 3 (G1) |
| P1-4 | Reward/risk filter (skip entry if take distance < k x stop distance) | APPROVED by the user 2026-09-19: configurable `MIN_TAKE_TO_STOP_RATIO`, start value 1.5, tune later; next backend task after the PC restart |

### P2 — features that need a spec first
| # | Task | Status / next step |
|---|---|---|
| P2-1 | Geometry and patterns program | Section 3 (G0-G7) |
| P2-2 | Fee attribution in the DB (`realized_pnl_pct` lacks entry fee, `realized_pnl_usdt` is gross) | Posts already compute entry+exit from executions; DB fix is separate |
| P2-3 | Distinguish exit reasons: feed-gap emergency exit vs operator "Close all" (both `EMERGENCY_CLOSE` today) | Analytics quality; small |

### P3 — hygiene
| # | Task | Notes |
|---|---|---|
| P3-1 | Buttons "Под наблюдением" and "Обновить" have no handlers | Every lifecycle post carries only "Все позиции" until fixed |
| P3-2 | Listener and Scanner as systemd services on the VPS (paused: the live run is on the PC now) | Resume when the run moves back to the VPS |
| P3-3 | CI for the Telegram side (workflow paths cover only trading backend and dev tooling) | Add `telegram_*.py`, `robot_position_*.py`, `robot_telegram_feed.py`, `tests/test_telegram_*.py` |
| P3-4 | Stop/Pause semantics: Stop left WAITING_* candidates alive (CSOPSAMSUNG2LUSDT, 5 more on 2026-09-19) although the decision doc says zero-exposure pending candidates are terminalized | Decide: fix behaviour or correct the doc |
| P3-5 | Old manual-test residue: CELOUSDT dust position (sync_state reconciliation_required), 5 commands stuck in `submitting` (OGUSDT x2, CELOUSDT x3) | Keeps the `/positions` warning permanently on; needs a proper task, no manual journal edits |
| P3-6 | Chart axis: date labels for windows longer than 24 h | Small |
| P3-7 | Flaky test `test_dispatch_fails_closed_on_replacement_lifecycle_with_same_quantity` (failed once under load) | Re-run first; investigate only if it recurs |
| P3-8 | Stale GitHub state: open PRs #143, #144, #63, #66, #121; merged local branches; 5 stashes; local-only branches | Clean only after review, nothing was deleted so far |
| P3-9 | PC config: set `TIMEFRAME = "5"` before the PC scanner is used again | One line; PC and VPS trades stay separate in statistics |
| P3-10 | Run log: add section 10 (2026-09-19 incidents 2 and 3, owner-thread REST finding, PRs #151-#153) and DECISION_LOG entries | Do together with P0-1 |
| P3-11 | Pre-existing failing tests: `tests/test_task_context.py`, `tests/test_task_harness.py` (10 of 11 fail on `main` without any change) | Cause not investigated |

## 3. Epic: Geometry and patterns (queued, one item at a time)

User request (2026-09-19, from the ChatGPT conversation): rework wedge and triangle geometry; add two wedge categories;
add triangle, box and L-shaped patterns for robot trading. First fix scaling so a pattern start never falls off the left
edge of the chart, then move to adequate anchor detection. Work through Codex/Claude Code, light and fast, edit through
GitHub with timely synchronization. Also: check earlier groundwork and borrow proven solutions from mature projects.

### G0 — Research and groundwork (docs first)
Status: existing-code and reference review recorded in `DOCUMENTS/GEOMETRY_RESEARCH_2026-09-20.md` (PR #156; pending integration). Newly confirmed strategy need: show the **price impulse before the pattern** to distinguish corrective wedges from same-direction deceleration. A display window is not sufficient evidence for automatic classification; G3 owns that separate task.
Findings so far:
- Anchor groundwork exists: `DOCUMENTS/ROADMAP.md` FUTURE_MISSION_ANCHOR_QUALITY_LEARNING (several anchor candidates kept
  with immutable detection-time geometry, ranking evidence), `FUTURE_FEATURES.md` ANCHOR_GEOMETRY_INTEGRATION, the
  Anchor/START button in scanner posts.
- Triangle Compression is detected by the scanner (`ARCHITECTURE.md`) but Robot v0.1 rejects it (only Falling/Rising Wedge are in
  `robot_state_machine._PATTERN_DIRECTION`; button and admission now refuse it).
- L-shaped continuation: only in `AUTOPILOT_STRATEGY_ACCUMULATED_DESIGN.md` ("L-shaped post-impulse consolidation"); the exact
  structure definition is an open item there (item 7). No code.
- Box/rectangle: no design found; closest code is `structures/channel.py`.
- Geometry code lives in `wedge/` (detector, classifier, integrity, potential) and `structures/`.
- Impulse groundwork already exists: `geometry.pre_pattern.detect_pre_pattern_impulse` is called by
  `geometry/evaluation.py` and stored as `pair_metrics["pre_pattern_impulse"]` for each geometry candidate.
  Its current 20-bar endpoint-close direction is preliminary evidence only (any nonzero change yields UP/DOWN);
  G3 must reuse/validate this existing path rather than implement a second impulse detector. See the research note.
To do: a short survey of mature open-source pattern-detection approaches (anchor/pivot selection, scaling), written to a doc,
with concrete ideas to borrow. Output: `DOCUMENTS/GEOMETRY_RESEARCH_<date>.md`.

### G1 — Chart window showing both the pattern and its preceding impulse (small, do first)
Purpose: expose the movement immediately **before** the first pattern anchor, not merely the full wedge. That history is necessary
for visual review and for collecting labeled examples for G3; chart history does NOT by itself change detector/Robot decisions.
The existing frozen START may be an unsuitable choice for a subtype not yet distinguished by the detector.
G1 displays that recorded START and enough preceding bars to inspect alternative terminal/local extrema;
it must not silently relocate existing line anchors based on a retrospective subtype guess.
Window: request enough historical candles for the earlier of both frozen line anchors and the entry, plus a **pre-pattern context**
target of one pattern-formation span (earliest anchor to frozen Scanner detection time), in the source chart timeframe; keep the
current candles on the right. This is a display-only lookback target, NOT an algorithmic definition of a qualifying impulse.
Minimum left margin: max(10 candles, 8% of the pattern-to-current span). Preserve the existing 1m/5m minimums and 1000-candle
request cap. Convert Scanner-source `anchor_index` through existing `robot_position_chart._line_start_index` into the
frozen 1m cursor coordinate before computing timestamp; do not treat 5m source bars as 1m bars.
Under the 1000-candle cap, preserve pattern-start visibility before spending the available history budget on pre-pattern
context. If the pattern start itself no longer fits, show "Начало паттерна раньше окна графика"; if the start fits but the
desired impulse-context history is truncated, show "Предшествующий импульс показан не полностью". Keep any entry-window
warning independent and derive warnings from the actual candles returned, not only from the requested limit.
Acceptance: on representative 1m and 5m signal/position cards, both START anchors have left-side room, earlier price movement
is visible when available, and capped/missing history is marked rather than invented. No DB writes, frozen-geometry revisions,
trading-rule changes, or VPS/runtime operations in this task.

### G2 — Adequate, context-dependent anchor detection
**Priority correction from local SOLUSDT 5m acceptance (2026-09-20): REJECT the example as a wedge,
not as a chart-history or START-repair sample.** In a one-pass, 200-bar local scan the
fitted upper and lower first anchors were indices 19 and 124: **105 x 5m = 525 minutes,
8 h 45 m apart**. Despite a CANONICAL Falling Wedge / 95 quality display, the owner
sees no coherent local wedge formation; extending the chart or shifting the START
cannot make that fitted pair legitimate. Do NOT use this case to select a historical
START, subtype, G3P four-point candidate or corridor-trade geometry.

**G2-P0 structural-coherence gate BEFORE further START/window/subtype work:** inspect why
this pair survived rather than treating its high quality score as evidence of a wedge.
`geometry/engine.py` currently evaluates a Cartesian product of separately generated
upper and lower lines. `geometry/pair_metrics.py` already enforces that the lower first
anchor of a falling pair equals the **next LOW in the supplied filtered list** after
its upper first anchor (and mirrors this for a rising pair). The SOL case proves
that “next surviving opposite pivot” is **insufficient**: `pivots.py::filter_pivots`
filters highs and lows independently using same-side price change, potentially leaving
a large temporal gap even when its adjacency check passes. Investigate the actual
pivot sequence and any omitted local extremes; do not assume adjacency was absent
or that a magic score/tolerance fixes it.

Owner requirement: a candidate pattern begins with **neighboring, meaningful,
opposite-side structural pivots in one local formation episode**, not two anchors
gathered from distant, unrelated swings. **Do not impose one fixed initial order
solely from wedge orientation:** a falling *correction* after an UP impulse may
begin at a terminal HIGH then a nearby LOW, whereas a falling *deceleration*
after a DOWN impulse may begin at its terminal transition LOW then a nearby
rebound HIGH. Rising contexts require the corresponding context-dependent
analysis; confirm actual source-pivot availability before adopting any rule. Verify a coherent alternating sequence and a bounded first-opposite-pivot
bar/time separation **relative to the formation's timeframe and observed local
swings**, including the raw versus filtered pivot-gap distinction. Numeric duration
and pivot-significance limits are NOT approved; calibrate on locally captured
accepted/rejected 1m/5m examples, including this negative control. If coherent
local formation evidence is missing or ambiguous, REJECT the pair **before ranking
or presentation as a confirmed wedge**, rather than hiding its mismatch by drawing
more history, changing chart START, globally lowering confirmations, or trusting
95/100. A correct pair may retain distinct genuine HIGH/LOW start anchors, but
its opening opposite swing must be structurally adjacent, not hours apart.

**CRCLUSDT 5m positive user annotation (2026-09-20):** the original Scanner PNG
shows a steeply descending lower line fitted from a later point and a misplaced
START. On a separate annotated TradingView chart, the owner draws the local
falling *deceleration* wedge immediately after a sharp DOWN impulse: first
structural LOW at the post-collapse trough (historical episode START), the
nearby rebound HIGH as the first upper-boundary anchor, a comparatively shallow
lower support from the transition LOW, and descending upper resistance through
subsequent reaction highs. **The visually labeled order is LOW -> HIGH**, not
HIGH -> LOW. Its actual pivot indices/times, confirmation candles, line fit,
and retention by Scanner filtering have not yet been verified; map this case to
the saved original signal-time OHLC/pivots before any quantitative selection.
Treat the annotated chart as owner-provided positive research target, not a
proven automatic detection, entry signal or authorization to trade.

**Next micro-slice:** read-only trace on the rejected SOL example (raw and filtered
pivots, anchor order/confirmation, gap in bars, existing anchor_sequence validity,
why the geometry and quality gates admitted it) and a small positive local control.
Then specify and test the minimal fail-closed *wedge-only* pair-coherence gate
before wiring any production behavior. Keep current Scanner/Robot execution,
prior frozen signals, live PAPER/VPS and unrelated patterns unchanged; do not
rerun the dismissed SOL extended-window demonstration. G2a/G2b0 remain
research-only tools for subsequently verified coherent formations.

Depends on G0 and G1. Inputs from the user: 3–5 chart examples where anchors were wrong (Anchor/START feedback already exists in
the Telegram posts). Output: spec (which pivots are candidates, ranking, tolerance), then implementation behind a flag with
side-by-side comparison on saved signals.
**Corrected user definition, 2026-09-20 — subtype-specific historical START:**
- **Falling CORRECTION after a sharp UP impulse:** START is the **upper extreme / terminal pivot (swing high) ending that preceding bullish impulse**. The downward wedge begins as a countertrend local correction from that high; the previously recorded “lowest local-structure extremum” was a misunderstanding and is explicitly SUPERSEDED.
- **Rising CORRECTION after a sharp DOWN impulse:** mirrored confirmed rule: START is the **lower extreme / terminal pivot (swing low) ending the preceding bearish impulse**. The rising wedge is the countertrend rebound from that low.
- **Falling DECELERATION after a DOWN impulse:** retain the user's earlier formulation: START candidate is the **first impulse-terminal pivot at the falling impulse → slowing wedge transition** (the transition low in the working interpretation; confirmation/local-pivot criteria remain to be specified). It need not be the final lowest low of the whole wedge.
- **Rising DECELERATION after an UP impulse:** mirrored **proposal** for review: transition high terminating the preceding bullish impulse; unlike rising correction, its exact rule was not separately specified by the user.

START is the historical beginning/impulse-to-pattern transition of the *overall pattern*, not a demand that both boundary lines pass through the same high/low. Upper/lower lines retain their own authentic pivot anchors. Keep alternative transition pivots available for G2/G3, with closed-candle confirmation time and immutable detection-time evidence; select no historical START from future candles. The correction/slowdown subtype and its appropriate START must be validated jointly instead of forcing an arbitrary common anchor heuristic. G1 only displays pre-pattern candles and the currently frozen geometry; it must not retrospectively relocate historical START or refit boundaries.
**Remaining specification work:** impulse start/strength and transition-pivot confirmation thresholds, valid local windows, false pivot handling, and what to do when a transition pivot is not yet confirmed at signal time. Collect user-labeled 1m/5m examples for all four variants before altering production detection.
### G3 — Context subtype classification for BOTH wedge orientations (before G4 Triangle)
**User intent (2026-09-20):** classify each wedge using the preceding impulse. These are two *context subtypes per geometric
orientation*, not four new unrelated geometry detectors, and the current Falling -> LONG / Rising -> SHORT breakout directions
remain unchanged until a separate strategy decision.
- Falling Wedge after UP impulse: `FALLING_CORRECTION_AFTER_UP` — downward countertrend pullback, candidate bullish
  continuation LONG cohort.
- Falling Wedge after DOWN impulse: `FALLING_DECELERATION_AFTER_DOWN` — downward move losing pace inside a descending
  contraction, candidate bullish exhaustion/reversal LONG cohort.
- Rising Wedge after DOWN impulse: `RISING_CORRECTION_AFTER_DOWN` — upward countertrend rebound, candidate bearish
  continuation SHORT cohort.
- Rising Wedge after UP impulse: `RISING_DECELERATION_AFTER_UP` — upward move losing pace inside an ascending
  contraction, candidate bearish exhaustion/reversal SHORT cohort.
- `PREPATTERN_CONTEXT_UNKNOWN` for missing/ambiguous prior history; do not force a subtype from wedge slope alone.
**Subtype-specific historical START (corrected):** falling *correction* begins at the terminal
**HIGH** of its preceding UP impulse; rising *correction* begins at the terminal **LOW** of its preceding
DOWN impulse. Falling *deceleration* begins at the first impulse-terminal pivot at the preceding DOWN
impulse → slowing wedge transition. The rising *deceleration* mirror remains to be validated.
These rules affect G2/G3 geometry semantics, not merely a post/chart label. Evaluate a bounded
set of alternative START candidates against provisional prior-impulse evidence, then resolve context
and validate the corresponding START and both boundary lines using only available closed candles.
Avoid circular logic: do not require a final subtype to generate all anchor candidates and do not
claim a final subtype merely because one candidate fits. If evidence is insufficient, retain UNKNOWN,
rather than silently substituting an anchor rule from another subtype.
**Signal and chart presentation (user requirement, 2026-09-20):** after G3 classification is implemented and tested,
show the *same immutable signal-time subtype* on each wedge signal in BOTH presentation surfaces:
- Scanner Telegram signal **text post** (`notification.py::format_signal`): one standalone line, for example
  `Контекст: Замедление после падения`, `Контекст: Коррекция после роста`,
  `Контекст: Замедление после роста`, `Контекст: Коррекция после падения`, or
  `Контекст: Не определён` for missing/ambiguous prior history. Keep the geometric
  `Паттерн: Нисходящий/Восходящий клин` line separate; do not imply a measured advantage in the label.
- The **Scanner signal PNG title/header** (`chart_clean.py::build_chart_title`, reached through
  `analyzer/charts.py`): add one clearly readable standalone `Контекст: …` line directly below the pattern/
  timeframe heading, without covering candles, boundaries, or the preceding impulse. `chart.py` is a separate
  chart renderer: inspect actual call sites and cover it only if it produces a user-facing signal.
- Robot **position/lifecycle chart and caption** (`robot_position_chart.py`,
  `robot_position_view.py::format_position_card`, `telegram_monitoring.py`): where a wedge signal snapshot
  exists, show the same context line in the chart header and text/photo caption, not a newly inferred
  context from subsequent candles. For legacy snapshots without subtype, use `Контекст: Не определён`.
The presentation reads one validated, versioned context value from the frozen signal/snapshot; no independent
classification in notification, chart renderer, or bot. A label is descriptive, not a Robot admission/
position-sizing instruction. For non-wedge patterns, keep the existing presentation unchanged.
Acceptance tests: all four subtype IDs + UNKNOWN appear consistently in the Scanner text and PNG header, and
in the Robot position/lifecycle caption and chart where applicable, on 1m and 5m; missing history does not produce
a fabricated impulse/context label. Respect Telegram photo-caption length and distinguish chart unavailable from
context unknown. Existing signal delivery/Robot ownership/STOP/TAKE are unchanged.
**Sequencing:** G1 must first make pre-pattern candles visible; G3 classification and the context UI are one
separate observable feature before G4 Triangle. Do not show a specific subtype in production until G3 has
validated signal-time evidence; until then keep UI unchanged or show only an explicitly unknown label.

**Desired trading-workflow priority:** investigate giving deceleration/exhaustion cohorts higher priority for Robot candidate
selection than corrective cohorts. This is a user-requested strategy hypothesis, NOT a validated edge or permission to
increase size, relax RR/STOP/TAKE, bypass ownership/admission, or activate preferential orders now.
Prerequisites: G1 preceding-impulse chart; G2 alternative START candidates and anchor adequacy; user-labeled examples of each orientation/context (at least
one each, ideally 3–5 uncertain examples). G3 sequence: (a) choose bounded pre-pattern horizon and reproducible impulse
direction/strength, distinguish deceleration from a sharp continuation and from noisy/sideways context; (b) freeze a
signal-time-only subtype and evidence version, with `UNKNOWN` fallback; (c) classify existing wedge detections without
changing geometry or execution; (d) compare subtype cohorts using fees, drawdown, failure rate, false positives and
1m/5m separation; (e) only after dedicated strategy/risk approval, define safe same-symbol Robot priority/admission policy
while retaining existing gates and one-owner invariants. Do not infer a statistical edge from appearance alone.
Existing groundwork: `TRADING_STRATEGY_SPEC.md` §3.2 already separates reversal/exhaustion from correction/continuation;
`AUTOPILOT_STRATEGY_ACCUMULATED_DESIGN.md` §7 records post-impulse `Rising Wedge` exhaustion for management, not
this complete four-cohort entry classifier. See the G3 research note in
`DOCUMENTS/GEOMETRY_RESEARCH_2026-09-20.md` for the source-model distinction.

### G3P — Four-point early wedge: provisional boundaries and evolving candidate (BEFORE G4 Triangle)
**User request (2026-09-20):** detect a still-forming wedge as soon as the first **four suitable confirmed structural pivot points**
(two HIGH and two LOW, enough to fit two tentative boundaries) exist, instead of waiting for a mature pattern. Project both
boundary lines forward **as estimates**, clearly separating the observed anchor-to-anchor segments from their dashed/projected
future portions; display a readable `Формируется / предварительная геометрия` state and the actual number of confirmed
pivots/touches. Do not fabricate future candles, a future fourth point or later confirmation. Distinguish source-timeframe
pivot occurrence from its closed-candle confirmation; do not let a final historical pivot list leak lookahead into an earlier
four-point event. Accept that four points can describe false wedges, wide channels or transitory noise: compare bounded
confirmed alternatives, containment/convergence, line crossing and whether a usable corridor remains before apex/expiry.
Derive a stable *formation identity* from symbol, source timeframe and signal-time structural evidence so later Scanner
observations update the **same formation** rather than replacing it with unrelated/stale four-point candidates. Preserve
the initial immutable event/signal snapshot alongside current observations and explicit version/revision; if anchors change,
mark the previous hypothesis superseded rather than silently moving a frozen line. UNKNOWN subtype or insufficient
pre-pattern history is an explicit state, not a reason to manufacture an impulse or a definitive wedge label.

**First delivery is observation and chart only:** inspect the current detector's candidate/touch gates and use existing
`pivots.py`, `geometry/candidate.py`, `geometry/engine.py`, `chart_clean.py`, signal snapshot/identity contracts and
Scanner chart/Telegram paths before specifying a bounded preliminary candidate model. Do not relax existing canonical
admission/ranking or change Robot orders to surface provisional formations. Verify both wedge orientations, 1m/5m,
four exactly confirmed pivots versus three/pending fourth, alternative anchor hypotheses, crossing/non-converging
lines, short remaining corridor, missing history, new fifth/sixth pivot, breakout/invalidated/expired states, repeated
scans and restart recovery; benchmark bounded cost against current Scanner hot path. Record provenance at each observation.

### G3R — Telegram `Освежить` for an evolving Scanner formation (AFTER G3P, BEFORE G4 Triangle)
**User request (2026-09-20):** add an inline **Освежить** button below Scanner signals for still-forming patterns,
including previously posted four-point candidates. A click requests a new **bounded current** Scanner evaluation of
the referenced formation (symbol + source timeframe + stable formation ID) and sends a **new current signal/chart post**
showing confirmed pivots, current/provisional line revisions, context/status and current price. Do not simply resend the
old PNG/snapshot or silently rewrite a frozen Robot trade. Keep old posts and their signal-time evidence immutable; show
the current revision and, when useful, its relationship to the earlier post. For insufficient history, failed fetch,
expired/invalidated/replaced formation, and missing/ambiguous identity, return an explicit status rather than a stale
or fabricated signal. Do not resurrect a stale approved candidate.

**Implementation gate:** inspect the existing Telegram callback routing, signal keyboard, scanner-on-demand path,
candidate identity and authorization before coding. Manual refresh must work when the periodic Scanner is PAUSED if
the authorized current-snapshot fetch path permits it; it must **not unpause Scanner, restart the Robot, or order
a trade**. Reject unauthorized callbacks; bound per-user/formation rate, deduplicate repeated taps, avoid blocking
the bot polling loop and preserve callback payload size. Validate callback after restart, legacy posts if sufficient
identity is present (otherwise explain unavailable), 1m/5m, and whether the new post's chart and caption refer to
the *same* current evaluation.

### G3C — Robot trade inside a forming wedge: boundary-to-boundary PAPER research (AFTER G3P/G3R, BEFORE G4 Triangle)
**User strategy intent (2026-09-20):** explore a **separate intrapattern/corridor trade mode** for provisional
four-point wedges. Falling wedge example: tentative LONG entry near the lower boundary, exit near the upper boundary
while both boundaries are still forming; Rising wedge counterpart needs a separately specified direction/entry
rule. Neither a four-point detection nor an `Освежить` button grants automatic entry permission.

**Strategy/risk decision required before execution:** define confirmed-pivot minimums, admissible geometry confidence,
proximity/price tolerance to a projected boundary, LIMIT versus MARKET entry, position ownership and re-entry,
STOP placement beyond the invalidation boundary, TAKE/exit inside the opposite boundary (including fees/slippage,
shrinking corridor and minimum net RR), expiration/apex and breakout behavior, resizing of protection on fills,
what happens after line re-anchoring or a new fifth/sixth pivot, cancel/close behavior if a formation invalidates,
and fail-closed feed/recovery/risk gates. Keep current VW/volume caps, protected order lifecycle, one-owner-per-symbol,
no martingale and PAPER-first constraints. A forming pattern's projected line is an *estimate*, not a promised future
execution price. Do not retrofit existing Robot breakout/retest admission or silently mutate frozen geometry to add
corridor trading.

**Delivery:** (1) replay/side-by-side diagnostics on four-point signals, including rejected/no-trade cases;
(2) separately approved isolated PAPER strategy with deterministic tests for lower-entry/upper-exit, late/early
fill, fees/RR, stops, line revision, breakthrough and restart; (3) manual acceptance on real forming-signal
cards; only then discuss any LIVE authority as a new explicit decision. Keep these stages separate from G2a
lookahead correction and from the G3 context-label feature.

**Queue order:** G2a remove future-pivot membership leak → G2b observational START alternatives →
G3 verified context and signal/chart labels → **G3P provisional four-point visualization** →
**G3R manual `Освежить`** → **G3C corridor-trading research and separately approved PAPER rollout** →
G4 Triangle. G1 remaining chart-history / Robot chart display work remains a prerequisite wherever needed.

### G4 — Triangle in the robot
Scanner detects Triangle Compression. Needs the trading rule decision: symmetric, ascending, descending or all three; direction of
the breakout trade; stop/take source; whether `_PATTERN_DIRECTION` becomes per-variant. Depends on G2 (anchors).

### G5 — Box (horizontal range)
Definition and detector needed (support/resistance band, minimum touches, containment tolerance); entry on breakout of either
side with retest; stop inside the box vs beyond. Input from the user: example chart and the desired entry rule.

### G6 — L-shaped continuation
Definition is an open design item (impulse, then compression at the top). Input from the user: example chart; then the exact
structure definition, detection, entry rule.

### G7 — Dual-timeframe scanner (5m + 1m per ticker) — REQUIRED (user 2026-09-19)
Constraints found in code: (1) `TIMEFRAME` is a global constant read by `analyzer/core.py`, `analyzer.py`, `main.py`,
`notification.py`; (2) `signal_memory.py` keys state by `symbol` only (needs symbol + timeframe); (3) the robot allows one active
candidate owner per symbol (a second one escalates DUPLICATE_ROBOT_OWNER to RECONCILIATION_REQUIRED), so a rule is needed for
5m and 1m signals on one ticker; (4) scan time roughly doubles (about 20 to 40 minutes). Needs a spec and a decision on priority.

Order (user 2026-09-19, refined 2026-09-20): G0/G1 (pre-pattern impulse visible) -> G2 (anchors)
-> G3 (two contextual types for Falling **and** Rising Wedge; study proposed deceleration priority)
-> G4 Triangle -> G6 L-shaped -> G5 Box. G7 dual timeframe follows G2 only after its separate ownership/priority spec.
G3 definitions are recorded above; implementation needs representative labeled charts, decision-time evidence criteria,
and separate approval of any Robot candidate-priority or execution-policy change.
Every pattern follows the same path: definition with examples -> spec -> detection -> signal/post -> robot rules -> tests ->
live verification -> record.

## 4. Decisions waiting for the user
1. Reward/risk filter: RESOLVED, yes, configurable, start 1.5, tune later.
2. Minimum stop 0.7%: confirm after the back-test A-3.
3. Pattern order RESOLVED: G3 (both wedge orientations split into correction vs deceleration) before Triangle G4, then
   L-shaped G6, Box G5. G3 context definitions recorded 2026-09-20; still open: representative example charts, precise
   signal-time classifier thresholds and whether/when a measured deceleration-priority policy may be enabled in Robot.
4. Dual timeframe: RESOLVED, required. Still open: how to resolve two signals (5m and 1m) on one ticker (which one the robot takes).

## 5. Facts to keep in mind when reading results
- PC trades before 2026-09-19 evening came from 1-minute signals, VPS trades from 5-minute ones; do not merge them in statistics.
- `EMERGENCY_CLOSE` is not a strategy exit (feed-gap fail-safe or operator close); exclude it from stop/take statistics.
- `realized_pnl_usdt` is gross and `realized_pnl_pct` includes only the exit fee; the posts compute entry+exit fees from executions.
- Cleaning candidates without SQL: "Stop" (only with no open position) does not touch WAITING_* candidates; the guarded cleanup script
  writes through `SQLiteStore` with a DB backup first.

## 6. Findings from the PC database (25 closed trades) and related queue items

| # | Priority | Task | Notes |
|---|---|---|---|
| A-1 | done | Single Telegram poller | Checked 2026-09-19: only the PC runs a listener; the VPS has none |
| A-2 | P1 | Investigate outliers MINAUSDT (-22.9% in 0 min with a 2% stop) and AAOIUSDT (stop 0.00%, 0 min) from 2026-09-14 | Bug of the early version vs thin-book slippage; read the trade row, exit price vs stop, executions |
| A-3 | P1 | Back-test on real 1m paths: 0.7% minimum stop and reward/risk filter on the clean sample (about 10 trades) | Script sent to the user, awaiting output; decides P1-2 and the first tuning of P1-4 |
| A-4 | P2 | Mark trades closed at the first check after downtime (robot/backend off for hours or days) with a distinct flag/exit reason and exclude them from strategy statistics | Five trades (BR, COTI, H, AEHR, 1000TAG) made +178.6 USDT this way; AKT/CL/MINA distort the other direction |
| A-5 | live prerequisite | Protective orders on the exchange side (software stops only work while the backend runs) | Not needed for PAPER; must be designed before any live use |

Clean sample definition (for statistics): holding time < 24 h, size >= 100 USDT, not `EMERGENCY_CLOSE`, not a 0-minute
artifact. PC result: 10 trades, 3 TAKE / 7 STOP, net -1.63 USDT (fees entry+exit included), hit rate 30%. VPS 5m: 0 TAKE / 5 STOP
so far (small sample). The raw database total (+99.76 USDT over 25 trades) is not meaningful: it is dominated by downtime gap exits and one outlier.
