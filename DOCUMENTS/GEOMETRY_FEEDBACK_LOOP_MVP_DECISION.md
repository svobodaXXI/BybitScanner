# GEOMETRY FEEDBACK LOOP — priority decision and MVP contract

Date: 2026-10-20. **Owner priority: ahead of further AUTOPILOT screen expansion.**
Status: owner-approved direction; **design only**, not implementation authority for shared Scanner/Robot/API.

## Goal / first measurable outcome

The owner sees a real Scanner signal on the **existing** Trading Workspace `ChartPanel`, adjusts its geometry using the **existing** `DrawingOverlay` editing mechanics, and presses **«Передать исправление»**. A persisted review record contains the original scanner geometry, edited geometry, reproducible candle/signal identity and outcome label. A comparison reports geometric deviations and can generate a reviewed detector improvement proposal.

Work in the existing TERMINAL/AUTOPILOT chart, **no second chart or drawing engine**. AUTOPILOT remains a navigation mode, not an execution trigger.

## Verified existing components / essential missing pieces

- `terminal/frontend/src/chart/drawingModel.ts`: `DrawingObject`, `DrawingAnchor { logical, price }`, `moveAnchor`, `moveDrawing`, `DrawingHistory` exist.
- `terminal/frontend/src/chart/DrawingOverlay.tsx`: chart-coordinate conversion, selection, pointer editing and `onCommit` exist.
- `terminal/frontend/src/app/App.tsx`: mounts shared `ChartPanel`, `DomPanel`, `TapePanel`; does not require separate AUTOPILOT visualization.
- `terminal/frontend/src/orders/signalTakeProposal.ts`: `readScannerSignalContext` currently carries **signalId, symbol, targetPrice only**. It does **not** provide timeframe, immutable candle snapshot, geometry, pivot identity, detector version, or authoritative feedback identity.
- `DOCUMENTS/AUTOPILOT_REUSE_TERMINAL_CHART_AND_SIGNAL_OVERLAY_DECISION.md` forbids initial AUTOPILOT drawing tools and has design-only status. For the **new owner-prioritized correction workflow**, enable editing **only within an explicit review mode**, not manual trading mode by default. The source signal overlay stays immutable.

## MVP flow (no online learning on submit)

1. Open a saved Scanner candidate/signal with authoritative identity, timeframe, detector version, candle-window provenance and original pivot/boundary geometry. Treat missing provenance as **cannot submit**, not inferred coordinates.
2. Render **original immutable Scanner overlay** alongside an **editable review copy** using the existing chart-coordinate and drawing mechanics. Ensure the editing tool can adjust pivots/boundaries and shows before/after; do not overwrite unrelated user drawings.
3. Operator selects **«Верный сигнал»**, **«Исправлена геометрия»**, **«Ложный сигнал»** or **«Неоднозначно»**, with optional explanation, then clicks **«Передать исправление»**.
4. Persist an **append-only** review record: schema version, immutable signal ID, symbol, timeframe, detector/build version, bar snapshot provenance (UTC open times, OHLCV, source and content hash), original and corrected pivots/lines anchored to **bar UTC timestamps or candle stable IDs + price**, label, owner review metadata, creation time. A `logical` chart index alone is not durable: visible range and candle loading change its meaning.
5. Reject stale/inconsistent signal revisions, out-of-range pivot times, non-finite prices, partial geometry, duplicate submit tokens and account/environment mismatch. No changes to robot orders or active signal evaluation on submit.
6. Read-only comparison: exact match/deviation by pivot and line, positive/false-positive grouping, replayable fixture export for the Geometry Engine with train/validation/test partition by **signal family and time window** to avoid leakage.

## Retrospective corrections — OWNER AUTHORITY (2026-11-07)

The owner may correct an existing Telegram signal **using candles that closed only
after the Telegram signal was sent**, or use those later candles to propose a
new pattern. This is a legitimate and potentially essential feedback example.

Keep **both time boundaries**. The immutable signal snapshot and `source_revision`
describe what Scanner knew at the original signal timestamp. An optional
server-verified, contiguous, **closed-candle** continuation with `as_of_ms` and
content SHA defines the owner's review-time evidence. Preserve the original
source unchanged; revised anchors may refer to this verified continuation.
A source-only review remains valid and backward compatible. Reopening a saved
retrospective correction must restore its exact appended candles and UTC anchors.

The offline export must distinguish `SOURCE_TIME_ONLY` from
`RETROSPECTIVE_CLOSED_BARS`. Never train/test the original historical decision
using candles that were unavailable then, and never label a future-confirmed
pattern as an original-time detectable signal. Later bars can be used to
generate *hypotheses* about earlier recognition, but acceptance requires a
strict chronological replay / time-separated holdout with no look-ahead.

Reuse the existing Editor chart, immutable source archive, feedback store, and
Scanner geometry validators. A user-originated proposed signal is only
non-executable evaluation evidence until the canonical trusted Scanner strategy
adapter can establish full entry, STOP, TAKE, freshness and Robot admission.
No direct browser-to-Robot trading, no automatic promotion, no LIVE.

Current bounded continuation fetch is one REST page (up to 1000 closed bars,
and total review window up to 2000). Incomplete or older unavailable history
must **fail explicitly**, not interpolate or silently invent candles. This is a
known scope limit, not permission to discard or mislabel old corrections.

## Hybrid learning / approvals (later)

- **Parameter tuning:** generate candidate settings from owner-reviewed examples; compare against held-out history and Gold negative/positive fixtures.
- **Algorithmic changes:** where pivot topology/first-wave rules need source edits, prepare a human-reviewed developer/AI-agent proposal and tests; do **not** let model output write production detector parameters directly.
- Compare false positives, recall, geometric error, latency and regressions to baseline on an independent corpus and the mandated complete Scanner acceptance run. Surface improvements **and** regressions before owner approves a promotion.
- No hot-swap of running PAPER_AUTO, DB mutation, LIVE action or automatic promotion on one owner correction. Explicit gated release and rollback.

## Coordination and implementation order

**Gate A (read-only contract):** agree with Scanner/Robot owner on versioned signal geometry snapshot+provenance and append-only feedback storage/API; existing `signalTakeProposal` URL fields are insufficient. No backend/API changes before agreement.

**Gate B (frontend vertical slice):** display Scanner original overlay, clone to editable review drawing, label and build validated submission payload without any POST to trading API.

**Gate C (persistence):** approved isolated append-only endpoint/fixture store with dedupe, audit and acknowledgement; no alteration of trading signals at submission.

**Gate D (evaluation):** one complete real-signal round-trip, fixture export, isolated detector comparison, then approval workflow.

Owner priority supersedes further new AUTOPILOT screens; completed UI-1..12 is preserved, stacked draft PRs remain unmerged pending integration. MIRROR RETEST is owned elsewhere. PAPER_AUTO/Scanner/Robot untouched.
