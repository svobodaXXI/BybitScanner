# Backlog (working queue, priorities, rules)

Status: WORKING BACKLOG (living document)
Last updated: 2026-09-22 (Scanner acceptance queue; older entries retain their own dates)
Owner: user. When a task starts, Claude Code registers it as a ChangeRequest per the project rules; this file is the
single place where new ideas are parked until then.

## HAEDALUSDT 5m — Box early-grid/slice TP/re-arm strategy feedback (2026-09-23)

Queued **only in the existing later Ikigai Box PAPER Robot lifecycle stage**;
not a Scanner acceptance blocker and not executable trading authorization.
The owner requires the first 1/4 РО advance LIMIT at F(1.0) + 0.75 ×
(F(1.618) − F(1.0)), three further equally spaced 1/4 РО LIMITs in the
second-impulse direction, and the furthest beyond F(1.618). A confirmed
partial fill requires immediate protection and a matching-quantity opposite
TAKE LIMIT slightly before F(1.0); after proven profitable closure, restore
only freed quantity to its first-grid level if the same frozen formation is
still eligible. No doubled exposure, duplicate orders or re-arming completed/
STOP-terminated setups. The screenshot alone cannot establish same-candle
fill/TP or profitable realized execution. The precise fourth grid price,
TAKE offset/net-fee rule, partial-fill/STOP coordination and re-arm lifecycle
remain open financial decisions; do not invent defaults or enable trading.
Owning detailed specification: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`,
"Owner strategy amendment — advance 75% entry, slice TP and re-arm".
Current acceptance → 5m/1m → source geometry → Box construction/lifecycle →
L-shape → Telegram control → separately authorized PAPER Robot order remains
unchanged. No additional full scan is triggered by this documentation alone.

## Telegram Scanner menu: owner-controlled discovery, pause/resume and safe start — QUEUED (2026-09-23)

Owner request after stopping an incomplete 302/777 pass: make the existing
Telegram Scanner menu button the **manual owner control** for the Scanner,
regardless of whether its worker is running on the PC or VPS. On owner tap,
discover the actual live owner/host and current pass state instead of assuming
a host from stale DB state. If running, pause the current pass durably at a
safe symbol boundary, without killing Telegram pollers, Robot, backend, or
open positions; on the next tap resume the **same** pass from its persisted
cursor, without rescanning already completed symbols or duplicating sent
signals. If no Scanner worker is running, the owner tap requests a safe start
of the required components from an **available, verified host**, equivalent
to the owner's existing batch-file workflow, but only after tracing which
components the batch file actually starts and checking live host reachability,
process/poller ownership and Robot/position safety. Do NOT infer that a
Telegram callback can wake a powered-off PC; if no existing reachable and
authorized remote launcher is available, report the specific unavailable
host/dependency rather than pretending to start it. Never spawn a duplicate
poller or Scanner, enable Robot/trading, restart unsafe infrastructure, or
silently switch PC/VPS runtime and account. Ambiguous ownership or missing
reachable host => fail closed and show status, not a blind launch.

Manual owner menu taps (unlike autonomous agent action) satisfy the manual-
start-only rule. Codex must not run the Scanner or stay active to supervise
it. Distinguish PAUSED vs STOPPED: a paused pass retains its frozen eligible
universe/cursor; a stopped/interrupted 302/777 pass is not complete acceptance
and must never be reported as 777/777. The first actual implementation slice
must inspect existing Telegram callback, ScannerControlRuntime, host control
surface and batch-file dependency/side-effect chain; reuse them instead of
building an additional remote process manager. Reconcile the button's
availability, auth and deployment before enabling start. Implement only at
the authorized turn in the established task sequence; no runtime start or
process termination is authorized by this backlog entry. Owner visual
acceptance for Scanner changes remains a complete real eligible-universe
Telegram pass, not a partial/selected preview.

## Owner manual Scanner run; agent quota protection — BINDING (2026-09-23)

The owner, not Codex/Claude Code/ChatGPT, manually launches each real Scanner
pass through a verified Scanner-only entrypoint. Agents must not start,
restart, resume, supervise, poll or wait through a full Scanner/Telegram
acceptance run: doing so wastes the owner's agent quotas. A bounded read-only
host-state/preflight task must exit immediately after its concise report;
subsequent manual Scanner execution does not require an active agent session.
Before any instruction to stop a possibly running process, distinguish Codex
job, Scanner worker, Telegram poller, Robot/backend and positions; never blindly
stop trading infrastructure. The full eligible-universe Telegram acceptance
requirement remains unchanged; an interrupted run remains unaccepted.

## CPUSDT 5m Ikigai Box: first-impulse construction correction — QUEUED (2026-09-23)

Owner's visual feedback: first impulse must begin at the actual local reversal
extremum, not an arbitrary later candle, and terminate at the last candle of
the initial directional move **before** subsequent consolidation/sideways
movement. Predominantly same-colour candles: UP predominantly green, DOWN
predominantly red. Only small opposite-colour candles that do not produce a
zigzag/meaningful countertrend swing may occur inside that first impulse.
Do not mechanically terminate on the first tiny opposite-colour candle, nor
include later sideways candles in the first impulse or move frozen A/B to fit
later prices. The first substantial opposite-direction candle/zigzag marks the
end of the directional leg; use the source-time candles to determine its exact
boundary and ensure terminal B is a candle of the impulse's own direction.
For UP use reversal LOW→terminal HIGH; DOWN mirror HIGH→terminal LOW. Keep
subsequent consolidation independent, regardless of its candle colours.
At implementation, establish reproducible pattern-specific evidence for
"small" and "non-zigzag" (no arbitrary one-example thresholds), repair the
first-leg candidate construction rather than a chart/score/Telegram reject,
and keep both CONFIRMED and WATCH consistent. This supersedes earlier
opposite-colour-core/wick-path exceptions wherever they conflict; defer any
financial Robot change. Preserve existing task order: manual full current-
Scanner pass, 5m→1m integration/full acceptance, then authorized geometry
fixes. No isolated screenshot/card visual acceptance.

## Permanent owner-only visual acceptance protocol — FULL PASS OR NO ACCEPTANCE (2026-09-23)

For any Scanner change whatsoever, including a chart-only/caption/button
change, **owner visual review happens only from the normal Telegram signal
feed produced by one COMPLETE real Scanner pass over EVERY available eligible
ticker and ALL integrated patterns**. Do not offer a separate "updated Box
card", one-off chart, selected symbol, local PNG, offline replay, partial
302/777 run, or short demonstration *before or instead of* the full pass.
Agent and Codex prompts must request the full pass as the ONLY visual-review
route, after minimal necessary developer-side technical verification. The
owner judges the resulting live Telegram charts, not developer-generated
examples. An interrupted or unsafe run leaves acceptance **PENDING**.

**Anti-regression check for every next-step prompt:** (1) Is this a request
for owner visual inspection? If yes, prescribe exactly the complete
real eligible-universe Scanner pass with ordinary Telegram delivery of every
integrated pattern; never a single-chart preview. (2) Is a complete safe pass
currently possible? Check the actual launcher, process/poller ownership and
Robot/position fail-closed conditions; if blocked, name the concrete blocker
and do not offer a smaller substitute. (3) Did the pass complete? Report
eligible/included/error counts, signal delivery and actual Telegram charts;
otherwise do not mark visual acceptance complete. When the future 5m→1m
per-symbol implementation is complete, include both intervals in the
full pass; before it, do not claim they were scanned.

**Current queue correction:** PR #204 (L-shape Telegram) and PR #205 (Box
card and 40% narrower chart) are both MERGED, but no complete owner-visible
full pass for the current implementations is confirmed. The next visual
acceptance action is ONE complete safe full pass displaying both patterns
through ordinary Telegram delivery, not an isolated Box card review. After
that proceed to the queued 5m→1m per-symbol Scanner integration and the
geometry corrections. No Robot/PAPER/LIVE activation is authorized.

## Permanent Scanner scan cadence and current task placement — OWNER RULE (2026-09-23)

**Every symbol: 5m first → immediately 1m → next symbol.** Evaluate all
integrated patterns independently on both intervals; send their real charts
to Telegram with the correct interval and pattern. Preserve separate
(symbol, timeframe, pattern, formation) anchors, candle data, identity,
state, deduplication and chart paths; a failure on one interval does not
block or falsify the other. Do not replace this with a full-universe 5m
pass followed by a full-universe 1m pass, or silently leave 1m patterns
unwired. Do not automatically extend Robot/PAPER/LIVE trading to 1m.

**Execution queue update:** the L-shape Telegram integration is merged
(PR #204), but full user-visible acceptance has not been reported. The
owner has explicitly moved the full scan later. First finish the ongoing
Ikigai Box Telegram/chart simplification, including **candles about 40%
narrower** (presentation only), without interrupting it. **Next** implement
the universal per-symbol 5m→1m Scanner/Telegram path; **then** tackle the
existing geometry-construction cases APTUSDT, B3USDT, DASHUSDT, ATHUSDT
(with B2USDT Box positive control). For each completed Scanner correction,
follow the owner's mandatory full eligible-universe Telegram visual
acceptance rule when the owner authorizes the actual run. The user judges
the charts visually; developer verification stays limited to necessary
technical checks, not extra test campaigns.

## Binding owner execution order — 2026-09-23 (LATEST OWNER OVERRIDE; READ FIRST)

The owner explicitly changed the priority to **former tasks 5 → 4 → 2 → 6;
all remaining tasks afterwards**. This section supersedes the previous
numbered order and any contrary "next/immediate" wording elsewhere in this
backlog or geometry index. Preserve task content, but execute in this order:

1. **Former #5 — L-shaped geometry and Telegram card.** Implement the B2USDT
   5m owner definition and the METISUSDT 5m possible missed independent
   L-shape alongside a delivered Box: local HIGH → trough → HIGH breakout, without a
   mandatory shelf; source-time upper edge of trough candles determines
   depth. Draw only rightward breakout HIGH ray and horizontal target with
   potential measured from HIGH; minimal ticker/timeframe/direction-arrow-
   before-pattern/potential caption. Remove diagonal, START, shelf box/text,
   green formula and other annotations. Do not activate L-shape Robot.
2. **Former #4 — Ikigai Box first-impulse and missed-pattern geometry.** Apply
   the CPUSDT 5m reversal-origin, predominantly single-colour non-zigzag
   first-impulse rule; freeze first-leg A/B before the independent sideways
   consolidation, for CONFIRMED and WATCH. Diagnose INTUUSDT 5m possible
   missed downward Box independently of the L-shape, using historical
   decision-time candles and the detector's decision/rejection path. Preserve
   historical completion vs actionable setup vs actual Robot execution;
   never fabricate a Box just because its screenshot looks plausible.
3. **Former #2 — Per-symbol Scanner 5m → immediately 1m**, all integrated
   patterns and ordinary separate Telegram notifications; independent
   candles, anchor/formation identities, state and dedup per timeframe.
   Robot/PAPER/LIVE stays on its separately authorized trading scope.
4. **Former #6 — Telegram Scanner-menu owner control.** Discover actual
   reachable host/worker, safe symbol-boundary pause, durable resume of the
   same pass and manual owner-tap start through the verified existing
   launcher/control mechanism. No autonomous Codex run, duplicate workers/
   Telegram pollers, blind PC wakeup/VPS switch, Robot enablement or unsafe
   backend restart. Fail closed on unavailable host/ambiguous ownership.
5. **Only afterwards — former #1, #3, #7 and all other queued work.** Resolve
   outstanding acceptance of the earlier #204/#205 changes and any newly
   implemented Scanner changes using the owner's mandatory ONE COMPLETE
   eligible-universe, ALL-pattern, ordinary-Telegram visual pass; the earlier
   interrupted 302/777 pass is not accepted. Then resume APTUSDT/B3USDT/
   DASHUSDT/ATHUSDT source-geometry defects (B2USDT Box positive control),
   remaining Ikigai setup lifecycle and separately authorized PAPER Robot
   work according to dependencies. Record existing valid complete-pass
   evidence, if recovered, instead of commissioning a redundant pass.

**Acceptance scheduling:** focused developer checks during each implementation
are permitted, but the owner never reviews selected cards, local PNGs or
partial scans. Do not insert a new full runtime pass ahead of the owner’s
newly prioritized development tasks merely to satisfy the OLD ordering.
Before claiming visual acceptance of any delivered Scanner changes, require
one complete real pass under the then-current implementation with all
integrated patterns and ordinary Telegram delivery, started **manually by
the owner**. An interrupted/unsafe pass remains unaccepted. Agents never
launch or supervise Scanner runtime and do not wait/poll in Codex.

**Implementation boundaries:** handle one dependent micro-slice at a time;
preserve dirty user-owned local work and use an isolated worktree for local
edits. No Robot/financial/risk activation, LIVE trading, or service/process
mutation is authorized by this plan. Existing detailed task specifications
in this backlog and `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md` remain in force
except for their now-superseded scheduling claims. The HAEDALUSDT 75%-entry/
partial-TP/re-arm proposal remains in the later, separately authorized PAPER
Robot stage; the B2USDT L-shape is distinct from the B2USDT Ikigai Box.

## METISUSDT 5m — missing independent L-shaped signal (owner feedback, 2026-09-23)

During owner Telegram review a real Ikigai Box signal was delivered for
METISUSDT 5m. The owner also identifies an apparent L-shaped structure on
the same candles and expects a **separate normal Telegram L-shape signal**
when its independently evaluated geometry is valid. The Box notification
must not consume a per-symbol slot or otherwise suppress the L-shape, and
vice versa. This is a candidate missed-pattern reference for the **current
first-priority L-shaped geometry task**, not proof of a confirmed detection
from a screenshot alone.

At the task's implementation stage, recover the source-time closed candles,
actual L-shape detector candidate/rejection and Scanner notification path
for METISUSDT 5m. Distinguish absence of a structurally valid candidate from
signal-memory/dedup/delivery suppression; fix the first demonstrated cause
at its owning stage. Assess alongside B2USDT's HIGH→trough→breakout owner
rule; do not force a positive by coin-specific exceptions, relaxing gates,
retroactive anchors or chart-only adjustments. Valid coexisting Box/L-shape
must each have distinct (symbol,timeframe,pattern,formation) identities,
real charts and ordinary owner buttons; no L-shape Robot admission.

No isolated chart/selected-ticker owner review. After the scheduled changes,
acceptance remains one complete manually started eligible-universe Scanner
pass with all integrated patterns and ordinary Telegram delivery, per the
latest binding execution order. No extra scan now just for this observation.

**Investigation result (2026-09-23, source-time Bybit 5m candles).** The Box
and L-shape paths are independent in `main.py` and use distinct memory keys
(`ikigai_box:*` vs `l_shape:*`), so no slot/dedup/delivery suppression was
involved. The earliest cause was the detector: the old shelf model returned
no candidate for METISUSDT at any bar (and only evaluated a shelf ending on
the latest closed candle). With the HIGH → trough → breakout detector and
latest-breakout reporting, the closed candles up to the scan (13:45 MSK)
yield LONG HIGH 12:25 (3.613) → trough 12:30–12:50 → breakout 12:55, U =
3.611 (12:40 body top), target +0.06%.

**Owner decision applied (PR #208):** the impulse origin is the nearest
structurally valid reversal LOW before the HIGH (the `pivots.find_pivots`
rule: strictly below 3 candles on each side, confirmed by the HIGH, and
still the lowest low up to it), never the 30-candle window minimum; no
fallback, unchanged impulse gates, no minimum target. METISUSDT now yields
12:40 LOW (3.593) → 13:05 HIGH (3.647) → trough 13:10–13:35 → 13:40
breakout, U 3.630 (13:20), T 3.664, +0.47% (3.7 ATR, 0.62 ATR/bar). The
earlier 11:50 → 12:25 → 12:55 structure still qualifies independently.
The Scanner sends only the most recent formation per pass, so a single
pass at 13:45 sends the 13:40 one; the 12:55 one only on a pass before
13:40. B2USDT is unchanged (origin 11:10, +8.05%).

## L-shaped formation: owner correction from B2USDT 5m chart — IMPLEMENTED, ACCEPTANCE PENDING (2026-09-23)

**Implementation (2026-09-23):** `geometry/l_shape.py` now detects impulse →
local HIGH → trough → first closed candle whose high exceeds H (SHORT is the
mirror). No shelf condition remains. Owner decision on U: body top
max(open, close) of the trough candle with the lowest low (earliest on a
tie); T = H + (H − U). Scanner reports the most recent breakout in the
closed candles, deduplicated by HIGH + breakout candle times. B2USDT 5m
reproduces H 0.5168 (11:30), U 0.4752 (11:35), breakout 12:25, T 0.5584,
+8.05%. Chart/caption: `B2USDT · 5м · ↑ Г-образная · +8.05%`, breakout ray and
`Цель` level only. Owner visual acceptance remains pending on the next
complete owner-started Scanner pass.

**Original status: specification feedback only.**
The owner rejects the current mandatory post-impulse narrow "shelf" model and
its shelf box/labels for this example. The intended search structure is a
local HIGH, a subsequent trough/pullback ("впадина"), then a breakout of
that local HIGH. Construct the correct local episode, HIGH and trough from
closed decision-time candles at the detector/candidate stage; do not merely
redraw a shelf-based or otherwise invalid candidate. The owner measures
trough depth from the local HIGH **to the upper edge of the trough candles**
(as indicated by the owner's black arrow), not automatically to the trough's
lowest wick. Before coding, resolve the exact reproducible candle/price
selection for that upper edge from source-time evidence; do not silently
reuse the previous `shelf_low` as this price or invent a numeric threshold.

For this HIGH-breakout / LONG example, draw a horizontal rightward signal
ray at the local HIGH breakout level H. Let U be the agreed upper-edge price
of the trough candles and D = H - U; project D upwards from H to obtain the
target T = H + D, with potential 100*(T/H - 1)% from the **breakout level**.
Draw one horizontal target level labelled `Цель` and its potential percentage.
Chart/card caption: only ticker, timeframe, upward direction arrow directly
before the pattern name, and potential to target. Remove the blue diagonal
impulse ray and its labels, the shelf outline and caption, green `T = 2H-L`
text, START and other nonessential annotations. No shelf condition or shelf
terminology is to be retained in the intended detector or owner-facing card.
This screenshot's B2USDT **L-shape** example is distinct from the B2USDT
**Ikigai Box** positive control elsewhere in this backlog.

**Execution order unchanged:** first complete the currently queued safe full
real Scanner/Telegram pass, then per-symbol 5m→1m integration and its full
pass, then the queued APT/B3/DASH/ATH geometry work. Take this L-shape
correction only at its authorized turn; do not modify the current running
Scanner or Robot in response to this documentation. After implementation,
owner visual acceptance is ONLY one complete real pass over every eligible
ticker and all integrated patterns via ordinary Telegram notifications;
no isolated image/card or shortened-pass substitute. L-shape Robot trading
remains unauthorized.

## Box presentation implementation — 2026-09-23

The Box chart header and Telegram caption share only ticker, formatted timeframe,
pattern name and the first-impulse A→B arrow (not the opposite trade direction).
No A/B/START, status, zone/STOP captions or planned limit-grid overlay appear.
Frozen Fibonacci prices/bands and source-time candle/anchor selection remain unchanged.
The canvas width is 7.2 inches instead of 12 at the same 125 DPI and height:
candle bodies and horizontal spacing are 60% of their previous pixel width.
Use the shared TradingView keyboard with review buttons for the owner only;
no Robot button or candidate is supported. This minimal identity and applicable
safe shared buttons are the presentation reference for future new patterns.
The implementation has been merged as PR #205; full Scanner/Telegram
visual acceptance is pending. Do not offer a single Box card for owner review:
the owner inspects this and all other Scanner changes only during the
complete real eligible-universe Scanner pass above.

## IMMEDIATE owner-visible milestone — L-shape Telegram (2026-09-23)

**Owner correction, superseding the older queue's deferral of L-shape delivery:**
All newly developed Scanner patterns must appear as **normal Telegram chart
signals with the common caption and applicable existing safe buttons during
their initial integration**. The owner evaluates the real delivered charts
visually. A local-only detector/observer or private `charts/` PNG is developer
diagnosis, **not** completed integration, user-visible acceptance, or a valid
substitute for Telegram delivery. Do not send the owner into a local filesystem
to review a new pattern and do not silently disable configured notifications.

**Implementation update:** L-shape Telegram delivery merged as PR #204,
and Ikigai Box card simplification merged as PR #205. The remaining
user-visible step is ONE complete real eligible-universe Scanner pass with
ordinary Telegram notification delivery for ALL integrated patterns. Owner
visual acceptance is pending; no isolated L-shape/Box chart inspection,
short run or local-PNG substitute. Robot admission/orders stay OFF for
L-shape until independently authorized.

**Workflow for every future new pattern:** implement valid pattern-specific
candidate construction and its ordinary Telegram visualization/delivery
together as the initial user-visible Scanner milestone. Focused offline
tests help coding only; a hidden observer is never offered as the final
visual acceptance path. A full-pass acceptance must display actual charts
to the owner in Telegram. Scanner signal presentation does NOT authorize
PAPER/LIVE orders or bypass independent Robot safeguards. See `AGENTS.md`
"Telegram-first visual development" and its full-pass rule.

## ACTIVE owner-feedback action plan — 2026-09-23 (read this first)

**Outcome, not downstream suppression:** each pattern's search/generation stage
must construct only geometry consistent with the owner's pattern definition.
Never generate malformed geometry and conceal it later through scoring,
Telegram delivery or Robot admission. Preserve original source-time candles
and candidate identity when diagnosing examples. This plan supersedes older
queue ordering when tasks conflict; it does **not** claim that the defects are
already fixed or that a screenshot proves the exact code-level cause.

**P0 — source-time geometry construction (one dependent fix at a time).**
- **Wedge/Triangle:** use the owner's APTUSDT 5m wedge, B3USDT 5m
  triangle and **DASHUSDT 5m falling-wedge** charts as reported
  false-geometry cases. DASHUSDT has two same-period visual references:
  the Scanner's selected wedge (START and both boundaries around the later
  local segment) and the owner's TradingView drawing showing a different,
  broader descending channel/wedge with boundaries starting from earlier
  local extremes. Treat the owner drawing as the intended geometry to test,
  **not** as proof that the broader figure already meets every confirmed
  pivot, A/B/C or source-time rule. Recover the matching closed-candle
  decision cutoff and candidate provenance; trace impulse episode,
  chronological A/B/C, START, candidate generation, boundary selection
  and display to the *first* divergence from the pattern contract.
  Compare the selected Scanner geometry to the owner's drawing using the
  same source-time candles. Fix generation/anchor selection, **not** score,
  chart window or Telegram filtering. For wedges retain the owner's
  universal A/B/C rule; triangle constraints are pattern-specific. If an
  original frozen snapshot is absent, state the missing provenance and
  collect a reproducible source-time case from the next complete pass
  rather than assert a guessed cause.
- **Ikigai Box:** ATHUSDT 5m: the owner rejects an opposite-colour candle
  within the *core* of the first impulse. Resolve the precise directional/
  boundary-candle rule in `IKIGAI_BOX_STRATEGY_SPEC.md` before editing the
  shared construction gate; the existing red-body-core exception applies only
  to DOWN impulses, and the UP path still admits mixed colour. Enforce the
  approved rule at first-leg construction for CONFIRMED and WATCH, not with a
  downstream reject. Preserve B2USDT 5m as a visually valid LONG control
  showing a move from the 2.618 area back toward/through 1.0.
- **Scope:** these cases are distinct; address one causative defect at a
  time. Do not convert a single chart observation into a universal numeric
  threshold, retrofit wedge rules onto Box, or merge all patterns into one
  large unverified rewrite.

**P1 — market setup lifecycle, independently of trade execution.**
- ATHUSDT is the owner's example of price reaching the first 1.618 entry
  region and then returning to the frozen 1.0 target: the original Box setup
  must become completed/historical and must not be reconstructed or offered
  again as an actionable entry for the same frozen A/B episode. Determine
  the exact closed-candle touch/return sequence from saved evidence; retain
  distinct attempted-entry and completion status and source-time provenance.
- The B2USDT move around 2.618 is a reference for evaluating the *second
  attempt*, not permission to open it merely because price reached 2.618.
  The strategy permits attempt two only after a verified STOP closure of
  attempt one, verified FLAT and no unresolved limits/protection obligation.

**P2 — reliable PAPER lifecycle, separately authorized.**
Implement only after the geometry and setup lifecycle are credible: approved
Box entry grid, partial fills, immediate protection, confirmed STOP/TAKE,
fee-aware profit-taking/flat closure, cancellation, durable restart-safe
ownership. Resolve still-unspecified grid spacing and partial-exit/BE policy
with the owner before placing orders. Historical chart price action cannot
prove an executed profitable trade; do not enable LIVE or alter risk.

**P3 — consistent Telegram presentation for every new pattern.**
For Box and then new patterns reuse the common notification/card button
model. The chart and caption show only ticker, timeframe, pattern name and
impulse-direction arrow; remove service-status/limit-grid/Fibo labels,
A/B/START, planned STOP/zone and other unwanted overlay text from the
user-facing Box presentation without changing frozen source geometry or
entry policy. Existing Box sender presently uses a separate photo/caption
path and does not give every normal owner button; this is pending.

**P0 immediate delivery gap — L-shape is NOT a Telegram signal yet.**
PR #197 added only an opt-in local observer. In `main.py`, the flag
`BYBITSCANNER_L_SHAPE_OBSERVATIONS=1` calls `observe_l_shape`; that function
logs candidates and saves local PNGs to `charts/l_shape` only. It never calls
Telegram/photo delivery, `signal_memory` or Robot admission. No flag can
turn the current observer into a Telegram sender. **Finish normal Telegram
chart delivery now, before any further owner-facing full-pass acceptance**
and without waiting for all older wedge/Box geometry tasks to finish.
Reuse the common caption/applicable safe buttons, dedup and retries; do not
activate Robot for L-shapes. Do not describe missing Telegram notifications
as detector failure or guess the host's current flag/deployment state.

**Mandatory acceptance for each changed Scanner pattern/geometry path:**
focused proof during implementation, then **one complete real Scanner pass
through every available eligible instrument**, with ordinary configured
delivery and the intended pattern integration enabled. Return all candidate
charts and a full pass count/error summary for the owner's visual acceptance.
Do not replace it with short/sampled/offline-only runs; do not start Robot,
LIVE, deploy or restart multi-service launchers without separate safety checks
and authorization. See `AGENTS.md` for the binding rule.

**Next dependent task (owner override 2026-09-23):** first deliver
L-shape candidate charts in the ordinary Telegram signal feed, without Robot
execution; then perform one complete real Scanner pass and obtain owner visual
feedback from its Telegram posts. After that, resume the geometry-construction
queue using APTUSDT/B3USDT source-time evidence. Keep ATH/B2 Box and PAPER
work as later scoped tasks, not parallel implementation campaigns.

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

## 1a. CURRENT queue: Scanner acceptance follow-ups (2026-09-22)

**Evidence:** one full 5m pass 2026-09-21 23:15–2026-09-22 00:30, 774 symbols, 156 Telegram deliveries (85 Wedge/Triangle, 71 Ikigai Box), zero Telegram errors. 9 symbols had market-data errors; 47 lacked pivots. Only ONE pass was authorized and executed. The analysis of B2/AZTEC/HIMS/FWDI used reconstructed matching-as-of windows; the Scanner does not persist its candle windows. No new implementation was committed after PR #180; current checked-out main was `a4ef2ff` at acceptance. This section supersedes outdated Scanner/PC-runtime assertions elsewhere in this backlog **only where verified below**; older Robot, VPS, financial and risk work is NOT resolved by this scan.

**Priority rule:** minimize user time to verified, reliable Scanner/PAPER Robot results, with process safety first; one active coding task, reuse recorded evidence, no repeated 774-symbol scans to diagnose one case. Findings are a queue, not authority to change strategy/risk or to launch Scanner/Robot. Do not create separate projects/PRs for each symbol.

| Priority | Task / existing evidence | Next bounded outcome and gate |
|---|---|---|
| **P0 — before next launcher start** | Resolve **pre-existing duplicate local processes**: 2 PAPER backends and 2 Telegram Monitoring workers were observed **before** the scan, sharing backend port 127.0.0.1:8765 and risking Telegram long-polling contention. One-shot `main.py` completed; Robot state `ROBOT_RUNNING/READY` was unchanged, 0 APPROVED candidates, 27 trades in DB; this does **not** prove that the runtime is safe to restart or that no positions are open. | Read-only identify process owners, bound ports, worker ownership, actual Robot/position state and existing lifecycle constraints. Keep one authorized owner per service, only through a safe, specifically approved stop/start plan; do NOT kill all Python processes or restart a backend with uncertain positions. No new infrastructure. |
| **P1 — next geometry task** | Restore **credible formation selection / envelope fit** with AZTEC (U70/L109; 17 upper-body prefix breaches outside common_start), HIMS (19 lower-body breaches and no confirmed outside pivot), QQQ (56/80 breaches), CHIP (0.42 breach ratio) as counterexamples. PR #180's confirmed-pivot+same-body gate catches AAVE/POL but intentionally cannot detect body-only dislocation or earlier-prefix evidence. An own-anchor extension already rejected the AEVO reference and moved INJ/WLD; a generic hard body-containment reject is NOT authorized by the owning decision. | ONE evidence-led geometry task on saved or matching-as-of examples: distinguish boundary support, prefix affiliation, structurally unsupported lines, and later legitimate breakout. Propose a **general, contract-compatible** minimal fix or report the exact required contract decision; include AEVO, INJ, WLD, XRP, PONS regressions and altered winner shape. No global `min_line_span`/coin-specific threshold/blanket score gate, no refitting references to force PASS, no broad scan during diagnosis. If evidence cannot justify a safe fix, stop rather than multiply diagnostic rounds. |
| **P1 — same geometry acceptance, not separate campaign** | **Quality-score interpretation:** 40 of the 74 examined wedge/triangle signals show 100/100 despite malformed envelopes; QQQ 95/100 at 56/80 breaches, HIMS 100/100 at 19 lower-body breaches. Existing quality/containment evaluator remains disabled by contract. | In the geometry task, separate structural scoring from containment validity; verify where 100/100 is computed and whether presentation should identify score scope rather than imply proof of boundary quality. Do not silently enable disabled penalties or add a new hard threshold; if a new policy is necessary, request a narrow explicit decision **after** geometry evidence. |
| **P2 — Ikigai, independent from wedge geometry** | **FWDIUSDT SHORT first impulse:** candidate A176/B189 failed ordinary first-leg close-progress and green-bar share; entered via existing wick alternative, despite larger earlier advance and ~0.59-span intraleg pullback. Opposite-color candles alone do not invalidate an impulse. `CONFIRMED` means completed geometry, **not** that 1.618 was reached or that a trade is authorized. | One scoped Ikigai task, after geometry priority: verify existing wick-path intent against the owning strategy spec and saved FWDI example, then correct the *general* first-impulse eligibility/anchor choice if evidenced and authorized. Preserve WATCH cold-start and no Robot admission/order behavior; do not tune thresholds to one ticker or mix with wedge PR. |
| **P2 — presentation quick fixes (batch together)** | B2: START dot is drawn at `common_start` although model START=88; 7 upper-body breaches at 193–199 are **after END=187**, i.e. acceptable breakout. Ikigai chart's `CONFIRMED` caption can be confused with trade/1.618 confirmation. | Small presentation-only batch: draw actual formation START (and make earliest line anchor intelligible); explicitly label Ikigai `CONFIRMED STRUCTURE / observation; 1.618 not reached` when appropriate. Verify graphs using existing artifacts; do not change geometry/entry/score. User-owned dirty `geometry/ikigai_box_chart.py`: never overwrite; delegate safe review to local agent and preserve edits. |
| **P2 — reliability, scoped** | Bybit rate-limit 10006 and SOCKS timeout/SSL led to 9/774 symbol fetch failures (DUSK, DYDX, DYM, EBAY, EDEN, EDGE, EDU, EGLD, EIGEN). | First reuse logs and existing fetch policy; only if justified add bounded, rate-limit-aware retry/backoff within existing API path, focused network-failure tests; no extra full scan or retry storms. |
| **P3 — later acceptance** | One complete run confirmed Falling/Rising Wedge, Triangle and Ikigai Box SIGNALS wiring; WATCH flag on but 0 cards on **cold start by design**. `structures/` and root `scanner.py` are unused legacy prototypes, not ready patterns. 85 Wedge/Triangle + 71 Box notifications; 239 approved patterns include 154 STABLE/WEAKENING not re-sent. | After fixes, ONE user-approved full production Scanner acceptance with real Telegram; check one controlled continuous WATCH transition **only if specifically relevant**. Do not treat zero WATCH on the initial one-shot run as a defect, promise a further run, or enable Robot autonomously. No blanket connection of unfinished L-shape/flags/HS/Double Top/Bottom prototypes until separately implemented and accepted. |
| **P3 — cleanup / deferred** | Two old worktrees `C:\\BybitScanner-pr178` and `C:\\BybitScanner-bv` plus other historical worktrees remain; root `analyzer.py` is shadowed by live `analyzer/core.py` and can mislead reviews. Scanner doesn't persist exact candle snapshots. | Do not delete user worktrees or refactor imports just for hygiene. On the next *relevant* scoped task, consider reproducible capture of the single signal-time OHLC snapshot **only if** it measurably saves more user-time than it costs; no new ingestion infrastructure. Cleanup requires separate verification of ownership and explicit authorization. |

**P1 decision/result update — 2026-09-22:** The owner now permits evidence-backed
revision of defective references; isolated excursions must not automatically
reject. The earlier P1 prohibition above is superseded only by the bounded rule
in `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`: seven consecutive body breaches
beyond existing ATR tolerance on each boundary's own-anchor..END interval,
replacing #180's single pivot/body veto; selection counts use the same intervals.
Eleven historical cases and cutoff sensitivity 4..8 are verified. AEVO/HIMS/QQQ/
CHIP/POL have no admissible pair; INJ's lower anchor changes 68->77; WLD changes
to supported U129/L61 triangle; AZTEC keeps only stale U106/L102 END148; XRP,
PONS and AAVE's stale diagnostic selection are unchanged. Evidence and tests:
`CR-SCANNER-GEOMETRY-FORMATION-FIT-001`. Next: protected final verification and
one PR review/integration; no runtime acceptance is claimed. Score 100/100
remains structural-plus-confirmation, not an envelope guarantee. Other queue
items and all runtime/risk authorization boundaries are unchanged.

**Sequencing:** P0 runtime ownership/safety before any next multi-service launcher; P1 one geometry correction and score interpretation; P2 Ikigai and a combined display batch; P2 data resilience when it blocks acceptance; P3 one authorized full rerun only after material fixes. These are distinct issues, not a license to open them all simultaneously. The older Robot/v0.1 financial-risk backlog retains its own authorization/safety gates.

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
Findings so far:
- Anchor groundwork exists: `DOCUMENTS/ROADMAP.md` FUTURE_MISSION_ANCHOR_QUALITY_LEARNING (several anchor candidates kept
  with immutable detection-time geometry, ranking evidence), `FUTURE_FEATURES.md` ANCHOR_GEOMETRY_INTEGRATION, the
  Anchor/START button in scanner posts.
- Triangle Compression is detected by the scanner (`ARCHITECTURE.md`) but Robot v0.1 rejects it (only Falling/Rising Wedge are in
  `robot_state_machine._PATTERN_DIRECTION`; button and admission now refuse it).
- L-shaped continuation: only in `AUTOPILOT_STRATEGY_ACCUMULATED_DESIGN.md` ("L-shaped post-impulse consolidation"); the exact
  structure definition is an open item there (item 7). No code.
- Ikigai Box is NOT a generic rectangle/breakout. Existing archived cases are in `training/reference_patterns/HEIUSDT/post_pump_two_drop_fib_1618_1h/`, `AEONUSDT/ikigai_box_15m/`, and `VELVETUSDT/ikigai_boxes/`; authoritative design: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`. The older generic-range wording in this backlog was incorrect.
- Geometry code lives in `wedge/` (detector, classifier, integrity, potential) and `structures/`.
To do: a short survey of mature open-source pattern-detection approaches (anchor/pivot selection, scaling), written to a doc,
with concrete ideas to borrow. Output: `DOCUMENTS/GEOMETRY_RESEARCH_<date>.md`.

### G1 — Chart window from pattern start (small, do first)
Window must cover the whole figure: from the earlier of pattern start and entry, minus a left margin, to the current candles.
Data: frozen `robot_geometry` lines carry `anchor_index` in 1m index space; time = `scanner_geometry_cursor.source_candle_time_ms`
minus (`geometry_index` - `anchor_index`) x 60 000 ms. Margin: max(10 candles, 8% of the span). Cap 1000 candles; if the start is
still earlier, caption "Начало паттерна раньше окна графика". Acceptance: on real signals the START point of both boundaries is
visible with margin on both 5m and 1m cards.

### G2 — Adequate anchor detection
Depends on G0 and G1. Inputs from the user: 3-5 chart examples where anchors were wrong (Anchor/START feedback already exists in
the Telegram posts). Output: spec (which pivots are candidates, ranking, tolerance), then implementation behind a flag with
side-by-side comparison on saved signals.

### G3 — Two wedge categories
Inputs from the user (blocking): definition of the two categories with one example each. Robot already handles Falling -> LONG and
Rising -> SHORT; new categories need their own direction and entry rules.

### G4 — Triangle in the robot
Scanner detects Triangle Compression. Needs the trading rule decision: symmetric, ascending, descending or all three; direction of
the breakout trade; stop/take source; whether `_PATTERN_DIRECTION` becomes per-variant. Depends on G2 (anchors).

### G5 — Ikigai Box (two-impulse Fibonacci reversal; NOT a range breakout)
Authoritative definition and historical references: `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`.
First impulse and second impulse are in the SAME direction, separated by consolidation. Freeze first-impulse A/B;
F(0)=origin, F(1)=first-impulse terminal, F(1.618) and F(2.618) extend along that impulse.
SHORT on second UP impulse near 1.618; mirrored LONG on second DOWN impulse. Four advance LIMITs of 1/4 РО,
outermost beyond extension. Confirmed reversal candle's extremum for STOP if valid; otherwise -1.5% from actual
average entry. Following a confirmed first STOP, verified flat/cancelled, one sequential second grid at 2.618;
main target F(1.0), partial profit-taking before target and then fee-aware breakeven. Exact grid spacing,
partial-TP and breakeven triggers remain undefined, so no Robot order execution is authorized by this description.
Priority after user-requested L-shape work: detector + visual Scanner/Telegram signal, then separate PAPER Robot lifecycle.

### G6 — L-shaped continuation
Offline detector and preview published to `main` in
[PR #195](https://github.com/svobodaXXI/BybitScanner/pull/195): impulse, then a
narrow shelf near the extreme; HIGH-first (LONG) preview draws only the
impulse-HIGH ray and target `T = 2*H - L`, no Fibonacci. Current status,
what remains unimplemented (preceding-impulse-vs-ordinary-swing proof) and
the exact next step are recorded in
`SCANNER_GEOMETRY_CURRENT_COURSE.md` ("Active development priority —
L-shaped formation, not wedge S1"); not duplicated here. Entry rule and
Robot wiring are still open design items, unchanged from before.

### G7 — Dual-timeframe scanner (5m + 1m per ticker) — REQUIRED (user 2026-09-19)
Constraints found in code: (1) `TIMEFRAME` is a global constant read by `analyzer/core.py`, `analyzer.py`, `main.py`,
`notification.py`; (2) `signal_memory.py` keys state by `symbol` only (needs symbol + timeframe); (3) the robot allows one active
candidate owner per symbol (a second one escalates DUPLICATE_ROBOT_OWNER to RECONCILIATION_REQUIRED), so a rule is needed for
5m and 1m signals on one ticker; (4) scan time roughly doubles (about 20 to 40 minutes). Needs a spec and a decision on priority.

Latest user priority (2026-09-20): finish L-shaped (G6) visualization and its signal path first; then Ikigai Box (G5)
with the correct two-impulse Fibonacci design, ahead of triangle and additional wedge taxonomy. Earlier ordering
was superseded. Draft PR #156 and the unpublished local L-shape worktree remain separate; neither is a prerequisite
for the Box's offline detector. G7 (dual timeframe) is deferred.
Blocking input for G3: description of the two wedge categories with one example chart each.
Every pattern follows the same path: definition with examples -> spec -> detection -> signal/post -> robot rules -> tests ->
live verification -> record.

## 4. Decisions waiting for the user
1. Reward/risk filter: RESOLVED, yes, configurable, start 1.5, tune later.
2. Minimum stop 0.7%: confirm after the back-test A-3.
3. Pattern order RESOLVED (2026-09-20): L-shaped first, Ikigai Box second, others later. Box reference examples and
   primary/secondary entry, fallback STOP and principal target are in `IKIGAI_BOX_STRATEGY_SPEC.md`; exact grid spacing,
   early TP split/price and breakeven trigger still require user approval before executable PAPER Robot integration.
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
