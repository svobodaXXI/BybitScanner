# Stage 8 — Production-Build Phone Acceptance

Date: 2026-09-06

Status: ACCEPTED

Authoritative code checkpoint before this acceptance record:

`2e48f8b13f356dbefaabbda99c1526f41d04b705`

## Accepted scope

Stage 8 production-build phone acceptance is complete for the current Trading Workspace scope.

The acceptance used production assets served through the existing Vite preview after a fresh successful production build. This avoids conflating HMR/dev-only behavior with terminal defects.

Accepted production-phone behavior included:

- Chart renders;
- DOM renders;
- lower trading panel renders;
- the application is not blank or crashed;
- PAPER BUY LIMITS popup creates a pending LIMIT candidate;
- the pending dashed LIMIT line exists even when its default price is initially outside the visible chart range;
- the pending dashed LIMIT line is draggable;
- popup price stays synchronized with chart drag;
- confirming the candidate creates the LIMIT order;
- LIMIT count increments;
- the own order is projected into DOM.

## Defect found during acceptance

During phone acceptance, dragging the pending LIMIT line exposed a presentation defect: the popup could display the raw JavaScript floating-point value returned by chart coordinate conversion, for example:

```text
0.09042679128725561
```

The chart line itself was already rendered from the tick-normalized draft projection, so the popup and chart could temporarily show different decimal representations.

This was a presentation-state defect, not an execution-lifecycle defect. Submission continued to normalize against authoritative tick size before dispatch.

## Corrective change

PR: #37

Title: `fix: normalize anomalous limit drag price tails`

Merge commit:

`2e48f8b13f356dbefaabbda99c1526f41d04b705`

Result:

- anomalously long binary floating-point tails are collapsed to the authoritative tick-aligned price during LIMIT draft interaction updates;
- ordinary manually typed decimal input remains preserved until normal submission-time normalization;
- PAPER/LIVE lifecycle ownership, durable action identity, authority fencing, reconciliation and no-blind-retry behavior are unchanged.

## Automated evidence

Focused regression:

```text
npm test -- --run src/orders/limitDraft.test.ts
PASS
1 test file passed
8 tests passed
```

The suite includes the observed regression value:

```text
0.09042679128725561 -> 0.09042
```

for a BUY draft with authoritative tick size `0.00001`.

## Production build evidence

Fresh build after the corrective change:

```text
npm run build
PASS
93 modules transformed
built in 456ms
```

Generated production assets included:

```text
dist/assets/index-Ch6pAuaI.css
dist/assets/index-DDr92wq2.js
```

Vite emitted only the existing non-blocking warning that the main JS chunk is larger than 500 kB after minification.

## Real-phone acceptance after correction

After refreshing the production preview on the phone:

1. PAPER BUY LIMITS was opened;
2. the pending dashed LIMIT line was dragged;
3. the linked popup price was observed.

Result: PASS.

The popup displayed the normal tick-aligned price instead of the long floating-point tail.

No real-money LIVE mutation was required for this acceptance.

## Gate conclusion

Stage 8 production-build phone acceptance is ACCEPTED for the tested Trading Workspace scope.

The previous `full production-serving terminal acceptance remains open` wording in `TRADING_WORKSPACE_MASTER_ROADMAP.md` is superseded by this acceptance record until the master roadmap status line is physically refreshed.

Future work in this area should be driven by a newly observed concrete defect, regression, or new product requirement rather than by the former open Stage 8 status alone.
