# BybitScanner / Trading Workspace
# MASTER ARCHITECTURE & EXTERNAL-REFERENCE ROADMAP

**Status:** ACTIVE MASTER PLAN

## 1. Core architectural conclusion

The terminal must have one authoritative trading state.

```text
             BACKEND
                │
                ▼
        AUTHORITATIVE STATE
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
     CHART     DOM      PANEL
       │        │        │
       └────────┴────────┘
            ALWAYS
         SAME STATE
```

External references behind this direction:
- Hummingbot: centralized order lifecycle / in-flight order tracking.
- OpenAlgo / OpenAlgo Charts: central trade-controller / single source of truth.
- Lightweight Charts: native price-line primitives for fixed-price active order projections.

## 2. Stage 1 — Authoritative PAPER state

Use one frontend `PaperTradingStore` owning:
- PAPER account state;
- position;
- active LIMIT orders;
- state revision;
- mutation/pending operation state;
- reconciliation state.

Use operation-scoped actions instead of UI-wide locks.

Current status: IMPLEMENTED IN CODE, NOT PHONE-ACCEPTED.

Already implemented:
- `PaperTradingStore`;
- operation-scoped mutation tracking;
- mutation result → authoritative state application;
- refresh coalescing;
- revision ordering;
- account + symbol revision scope;
- durable SQLite revision;
- clean frontend build.

Important current fact:
After restart with the latest implementation, real phone test showed:
LIMIT currently does not create and does not cancel from the phone.

Therefore Stage 1 remains OPEN.

## 3. Stage 2 — No dropped refresh / monotonic ordering

Required:
- refresh requested during refresh is marked pending;
- exactly one follow-up refresh runs;
- lower revision never overwrites higher;
- wrong account/symbol state never applies;
- stale poll cannot overwrite newer mutation state.

Current status: IMPLEMENTED, pending real phone acceptance.

## 4. Stage 3 — Mutation returns resulting authoritative state

Target:

```text
SerializedPaperRuntime
   ├─ execute mutation
   ├─ read resulting PAPER state
   └─ return mutation result + state
```

Polling is only reconciliation fallback.

Current status: IMPLEMENTED for:
- LIMIT create;
- LIMIT cancel;
- LIMIT amend;
- Market;
- Full Close.

## 5. Stage 4 — Real batch commands

Future target:

```text
POST /api/limits/batch-create
POST /api/limits/cancel-side
```

Return per-item results + one final authoritative state.

Do this only after single-order phone mutation path works.

## 6. Stage 5 — One order lifecycle for every entry path

These must not have separate business logic:

```text
BUY LIMITS
SELL LIMITS
BUY/SELL + Chart
BUY/SELL + DOM
```

Canonical pipeline:

```text
USER INTENT
    ↓
normalize tick
    ↓
validate
    ↓
stable client_action_id
    ↓
command
    ↓
backend
    ↓
authoritative state/revision
    ↓
PaperTradingStore
    ↓
Chart + DOM + Panel
```

Current status: PARTIAL.

## 7. Stage 6 — Chart and DOM become projections

Chart:
- active LIMITs derive from `PaperTradingStore.activeLimitOrders`;
- preferred fixed-price rendering: native Lightweight Charts `PriceLine`;
- pending draggable drafts may stay overlays.

DOM:
- PAPER own-order rendering must use the same active PAPER orders as Chart and Panel;
- remove separate local PAPER reality.

Invariant:

```text
BUY/SELL LIMITS count
DOM order dots
Chart active lines
Backend active orders
```

must always describe the same order set.

Current status: NOT YET IMPLEMENTED.

## 8. Stage 7 — Mobile interaction state machines

Use explicit pointer-state machines with pointer capture for:
- long press;
- BUY/SELL fast-limit hold mode;
- two-finger interactions.

Current status: NOT FINALIZED.

## 9. Stage 8 — Production-build phone acceptance

Vite remains for development.

Final phone acceptance should use production assets so HMR/dev behavior is not confused with terminal defects.

Current status:
- `npm run build` currently PASSES;
- production-serving phone acceptance still needs to be established.

## 10. Stage 9 — Transport consolidation only if measured

Do not rewrite transport prematurely.

If phone measurements confirm connection pressure, target one multiplexed transport:

```text
one WebSocket
  ├─ orderbook
  ├─ trades
  ├─ candles
  ├─ PAPER order updates
  └─ position/account updates
```

REST remains command path.

Current status: DEFERRED.

## 11. Stage 10 — Real verification

Backend lifecycle tests:
- create → active → partial fill → amend → cancel → absent;
- two simultaneous LIMITs;
- duplicate `client_action_id`;
- restart/persistence;
- batch flows when implemented.

State-controller tests:
- no lost refresh;
- stale revision rejected;
- stale account/symbol rejected;
- simultaneous mutations ordered correctly;
- pending actions release on success/failure.

Browser E2E:
- current runtime symbol;
- current BUY LIMITS / SELL LIMITS UX;
- real PAPER backend + real frontend.

Final acceptance surface:
- real phone.

## 12. LIMIT acceptance gate

Do not close LIMIT until, without reload:

1. Create 2 BUY drafts → CONFIRM ALL → exactly 2 everywhere.
2. Cancel one → exactly 1 everywhere.
3. Cancel all → exactly 0 everywhere.
4. Repeat SELL.
5. Create via DOM → immediately appears in chart + inventory.
6. Amend → same order moves, no duplicate.
7. Market fill → leaves active orders and updates position.
8. Restart frontend/backend → no duplicates, cancelled orders do not return.
9. Bad/ambiguous network → no duplicate order creation.

## 13. After LIMIT — full terminal audit

Then audit:
- MARKET BUY / SELL;
- FULL CLOSE;
- position / PnL;
- working volume;
- STOP;
- TAKE;
- DOM;
- CENTER;
- Smart Tape;
- Chart;
- timeframes;
- connection loss;
- backend restart;
- browser reload;
- PAPER persistence.

## 14. Current immediate next step

Do not jump ahead.

Current runtime:
- backend restarted on `127.0.0.1:8765`;
- Vite frontend restarted on `0.0.0.0:5173`;
- phone opened current frontend;
- user reported LIMIT does not create and does not delete at all.

Next work item:

```text
PHONE LIMIT MUTATION PATH DIAGNOSTIC
```

Trace:

```text
phone interaction
→ React handler
→ fetch POST
→ Vite proxy
→ Python HTTP handler
→ SerializedPaperRuntime
→ SQLite
→ mutation response
→ PaperTradingStore
→ UI
```

Find the first layer where the request/state stops.

Do not guess. Do not rewrite unrelated subsystems.

## 15. Engineering completion criterion

Not merely green tests.

Completion means:
No known defects remain in scope, critical invariants pass, and real acceptance scenarios are stable on the actual phone.

This document is the canonical roadmap unless a proven defect requires a narrowly scoped deviation.
