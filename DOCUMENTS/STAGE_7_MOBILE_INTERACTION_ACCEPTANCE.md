# Stage 7 — Mobile Interaction State Machines Acceptance

Date: 2026-09-06

Status: ACCEPTED

Authoritative code checkpoint before this acceptance record:

`61dd48f1adca2861806b05b0ed8fd083a541368c`

## Accepted scope

Stage 7 mobile interaction handling is accepted for the current Trading Workspace scope:

- long-press trading controls use an explicit pointer lifecycle with pointer capture;
- BUY/SELL fast-limit hold mode activates only after the configured hold threshold;
- hold release and pointer cancellation clear fast-limit intent;
- a second touch pointer on the Chart while BUY/SELL remains held creates exactly one fast-Limit price-selection intent;
- compatibility touch/click events do not duplicate the fast-Limit intent;
- DOM fast-limit price/size row activation remains covered by its existing pointer tests;
- Chart multi-pointer gesture ownership remains explicit and separate from fast-Limit interception.

## Automated evidence

Focused Stage 7 suite on merged main before the added regression:

```text
src/interactions/useTradingControlActivation.test.tsx   3 passed
src/components/ChartPanel.fastLimit.test.tsx           4 passed
src/components/DomPanel.test.tsx                       6 passed
src/app/App.liveLimitConfirm.test.tsx                  16 passed
TOTAL                                                  29 passed
```

A dedicated two-finger regression was then added in PR #35:

```text
uses a second touch pointer on the chart while the first touch holds BUY
```

After that addition:

```text
src/components/ChartPanel.fastLimit.test.tsx           5 passed
```

The added regression is test-only; production code was unchanged.

## Real-phone acceptance

Real-phone PAPER acceptance passed for the intended two-finger gesture:

1. hold BUY;
2. wait for fast-limit activation;
3. while BUY remains held, tap the Chart once with a second finger;
4. release BUY.

Observed result:

- exactly one pending BUY LIMIT appeared at the selected Chart price;
- no MARKET trade was executed.

No real-money LIVE mutation was required for this acceptance.

## Production build evidence

Fresh production build after the real-phone acceptance:

```text
npm run build
PASS
93 modules transformed
built in 469ms
```

Vite emitted only the existing non-blocking warning that the main JS chunk is larger than 500 kB after minification.

## Gate conclusion

Stage 7 mobile interaction state machines are ACCEPTED for the tested scope.

The previous `NOT FINALIZED` wording in `TRADING_WORKSPACE_MASTER_ROADMAP.md` is superseded by this acceptance record until the master roadmap status line is physically refreshed.

Future work on these interactions should be driven by a newly observed concrete defect, regression, or new UX requirement rather than by the former open Stage 7 status alone.
