# BybitScanner — Standalone Android Terminal Competitor / UX References

Version: 1.0
Date: 2026-09-08
Status: FUTURE PROJECT RESEARCH NOTE
Implementation authorization: NONE
Related project: `DOCUMENTS/STANDALONE_ANDROID_TERMINAL_PROJECT.md`

Purpose: preserve external mobile/professional trading-terminal references worth reviewing when the future standalone Android terminal project is activated. This note is research input only and does not change the current Terminal or Robot scope.

---

# 1. REFERENCE PRODUCTS

The following products were identified as useful reference points for different parts of the future mobile terminal UX:

- **TabTrader** — mobile chart + order-book interaction; useful reference for compact mobile trading workflows and tapping order-book price levels to initiate orders.
- **Bitfinex Mobile** — useful reference for compact composition of chart, order entry, order book and position state on a phone-sized screen.
- **Altrady** — useful product-level reference for multi-exchange terminal structure, smart orders, paper trading, scanner/journal integration and mobile workflow.
- **Tiger Trade / Tiger Control** — useful reference for simplifying professional trading controls for mobile, including quick position management and stop adjustment.
- **Bookmap** — primarily a professional order-flow/DOM reference rather than a direct mobile analogue; useful for liquidity visualization, tape/prints and DOM semantics.
- **Quantower** — primarily a professional desktop reference; useful for fast DOM trading semantics, click-to-place, drag-to-amend, direct cancel and bracket STOP/TAKE workflows.
- **Bybit Mobile** — baseline exchange-native reference for mobile derivatives trading and native account/order UX.

No single reviewed product was identified as a complete analogue of the intended BybitScanner mobile terminal. The useful pattern is to study individual strengths rather than copy one product wholesale.

---

# 2. BYBITSCANNER DISTINCTIVE COMBINATION

The intended BybitScanner terminal combines capabilities that are usually split across products:

```text
Chart
+ full DOM / order book
+ prints / tape
+ fast manual order gestures
+ draggable active LIMIT orders
+ STOP/TAKE directly on chart
+ Working Volume sizing model
+ MANUAL / ROBOT ownership model
+ Scanner -> Terminal deep-link workflow
+ future Robot integration
+ Trading Diary integration
```

A particularly distinctive mobile interaction concept is:

```text
hold BUY or SELL
+ tap target chart/DOM price with second finger
-> create pending LIMIT at that price
```

This should be treated as a BybitScanner-specific UX hypothesis to validate on real devices, not as an industry-standard gesture.

---

# 3. RESEARCH USE RULE

When the standalone Android project starts:

1. review the current versions of these products again because mobile UX changes rapidly;
2. extract useful interaction patterns, not proprietary visual copies;
3. preserve BybitScanner's existing execution/state contracts and reuse-first architecture;
4. do not adopt an external UX pattern if it weakens fail-closed behavior, reconciliation, order identity, ownership or protection semantics;
5. prioritize real-phone usability and latency over visual imitation.

Reference products are inspiration for presentation and interaction only. They are not architecture authority and must not become justification for creating duplicate trading engines or duplicate state ownership.

---

# 4. FUTURE COMPARISON AREAS

If deeper research is needed later, compare at minimum:

- chart/DOM coexistence on a phone screen;
- one-handed and two-handed order placement;
- order amend/cancel gestures;
- STOP/TAKE editing;
- position and PnL visibility;
- account switching;
- reconnect/degraded-state UX;
- emergency close ergonomics;
- haptics/sound feedback;
- landscape vs portrait layouts;
- accessibility of critical controls under one-thumb operation.

# END_OF_DOCUMENT
