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

Accepted progress:
- resting BUY/SELL + DOM placement uses the shared canonical `PaperLimitCreateController` and `/api/limit` path;
- stable per-intent identity, definitive release, ambiguity lock and 300-ms anti-bounce passed on the real phone;
- PRICE and SIZE on one DOM row select the same level, while own-order dots remain cancel-only.

Still open:
- marketable/aggressive DOM LIMIT explicit confirmation; current behavior remains fail-closed.

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

Current status: PARTIAL. The resting DOM-create projection path is real-phone accepted; the complete Stage 6 gate
remains open until all lifecycle/restart/fill acceptance items are complete.

## 8. Stage 7 — Mobile interaction state machines

Use explicit pointer-state machines with pointer capture for:
- long press;
- BUY/SELL fast-limit hold mode;
- two-finger interactions.

Current status: NOT FINALIZED.

## 9. Stage 8 — Production-build phone acceptance

Vite remains for development.

Final phone acceptance should use production assets so HMR/dev behavior is not confused with terminal defects.

Binding workflow gate: follow `ASSISTANT_PROTOCOL.md` section
`VITE PREVIEW BUILD-BEFORE-ACCEPTANCE`; acceptance evidence under
`vite preview` is valid only after a fresh successful build and page reload.

Current status:
- `npm run build` currently PASSES;
- the production build passed real-phone acceptance for resting DOM LIMIT placement;
- full production-serving terminal acceptance remains open.

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
5. Create via DOM → immediately appears in chart + inventory. **PASS — resting BUY/SELL DOM placement.**
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

Accepted current checkpoint:

```text
WORKSPACE SYMBOL SWITCHING + PHONE REFINEMENT — IMPLEMENTED / AUTOMATED PASS
```

Open next work item:

```text
REAL-PHONE WORKSPACE SYMBOL SWITCHING ACCEPTANCE
```

Open Positions real-phone acceptance is `PASS`. Symbol switching plus its bounded phone-review refinement are
implemented: ticker/timeframe are inside Chart, account switching is beside BUY/SELL LIMITS, removed header height
belongs to the common market row, and clipped authoritative DOM own-order dots are corrected. On the real phone,
verify case-insensitive autocomplete; BTCUSDT and ONGUSDT Chart/DOM/Tape authority; full-symbol internal identity;
card confirmation/Cancel and close-`×` isolation; same-symbol return; selected-symbol PAPER projection; visible
one-per-order concrete-cancel DOM dots including same-price orders; and the refined layout/price-axis readability.
Manual/real-phone acceptance remains `PENDING`. Aggressive DOM Limit confirmation and Done/Enter focus progression
remain separately deferred.

## 15. Engineering completion criterion

Not merely green tests.

Completion means:
No known defects remain in scope, critical invariants pass, and real acceptance scenarios are stable on the actual phone.

## 16. Future track — Autonomous Android Manual Trading Terminal

Checkpoint: `AUTONOMOUS ANDROID MANUAL TRADING TERMINAL — FUTURE DIRECTION RECORDED / IMPLEMENTATION NOT AUTHORIZED`.

Status: `FUTURE / PLANNING ONLY / NOT_IMPLEMENTATION_AUTHORIZED`.

This is a separate future track after the current terminal completion and acceptance path. It does not replace the
desktop/web or Telegram Mini App prototype, does not start Android implementation, and does not change section 14's
immediate next step: `REAL-PHONE WORKSPACE SYMBOL SWITCHING ACCEPTANCE`.

### 16.1 Product intent and autonomy

The future Android version is primarily a manual Bybit trading terminal that can operate independently of
`C:\BybitScanner`, the home Windows PC and its Python backend, VPS, Scanner runtime, and the future Trading Robot.

```text
ANDROID TRADING WORKSPACE
        │
        ├── Chart / DOM / Smart Tape / controls
        ├── local market-data/trading core
        ├── secure credential boundary
        ▼
   BYBIT PUBLIC + PRIVATE API
```

The intended manual-trading route is `PHONE → BYBIT`, not `PHONE → PC/VPS → BYBIT`. Robot integration is not an
Android requirement; the future Robot remains separate and must not depend on a running Android application.

### 16.2 Reuse and preliminary architecture direction

Android does not automatically require a rewrite. Prefer maximum reuse of the existing React/TypeScript UI and its
Chart, DOM, Smart Tape, BUY/SELL, LIMITS, Open Positions, future completed STOP/TAKE, Working Volume, symbol
switching, Drawing Tools, layout, and phone-interaction contracts. Keep UI/business boundaries capable of binding
later either to the current backend transport or to an Android-local bridge without duplicating trading semantics.

```text
Existing React / TypeScript Trading Workspace UI
                    │
             internal bridge
                    │
        Android-native trading core
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
Bybit Public WS/REST       Bybit Private API
```

Capacitor or a comparable native-shell approach is a candidate, not a selected stack. `Capacitor vs alternative
hybrid/native approach` remains a future research decision. A full Kotlin or React Native rewrite is not required
and may be considered only if measured performance, security, or Android UX evidence justifies it.

### 16.3 Security and command boundary

For real-money manual trading, the Bybit API Secret must never enter ordinary React/JavaScript/WebView state or be
available to frontend code as a string.

```text
React UI
   │ intent only
   ▼
Android native trading boundary
   │
   ├── credentials
   ├── request signing
   ├── private API
   └── reconciliation
```

The UI sends intents such as `placeLimit`, `cancelOrder`, `amendOrder`, `marketBuy`, and `fullClose`; native code
owns credentials, signing, private API access, and reconciliation. Research Android Keystore and hardware-backed
storage where available. A dedicated Android-terminal key must have only necessary read/trade permissions, no
withdrawal permission, minimum privileges, and a rotation/removal workflow. No secret may be hardcoded in the APK,
repository, or frontend bundle. Exact design requires a separate security research gate before real-money work.

### 16.4 Exchange authority and lifecycle

The manual app need not run continuously. Successfully created exchange entities—active Limits, exchange-native
Stop/Take where applicable, and open positions—remain at Bybit. Local UI state is never exchange truth.

```text
APP START / RESUME / RECONNECT
        ↓
authenticate
        ↓
restore public market data
        ↓
fetch/reconcile private authoritative state
        ↓
only then enable unsafe trading actions
```

The core must retain stable/unique command identity where required, no blind resend after ambiguity,
reconciliation before retry, reconnect duplicate prevention, fail-closed ambiguous private state, authoritative
position/order recovery, Full Close that cannot flip through zero, and exchange-authoritative protection lifecycle.

### 16.5 Market-data authority

The app must independently support Bybit public order-book WebSocket data, public trades, candles, normalized state,
reconnect/resynchronization, sequence/integrity checks, and freshness/health.

```text
one authoritative normalized market-data owner
        ↓
Chart + DOM + Tape + liquidity-dependent manual trading
```

Chart, DOM, and Tape must not create independent subscriptions. Symbol/session switching requires explicit
authority, generation identity, candidate readiness before swap, stale-consumer isolation, and fail-closed behavior.

### 16.6 Research gates before implementation

1. Packaging/runtime: native-shell alternatives, WebView capability/performance, and bridge API design.
2. Market-data performance: sustained WS/DOM/Tape rates, battery, CPU, memory, and foreground/background transitions.
3. Lifecycle: pause/resume, process death, connectivity changes, Wi-Fi/cellular switching, lock, and background restrictions.
4. Security: Keystore/hardware backing, signing, root/device threats, redaction, backup/export, rotation, and revocation.
5. Bybit integration: then-current WS/REST requirements, rate limits, reconciliation, metadata, clock, and recv-window.
6. Distribution: private sideload versus store, updates, signing/release keys, and migration.
7. Observability: connection/stream health, freshness, reconciliation, and pending/ambiguous command state.

This checkpoint resolves none of these decisions.

### 16.7 Preliminary future phases

- **Android A0 — Architecture/security research:** no implementation; choose packaging, bridge, credentials, and lifecycle.
- **Android A1 — UI packaging prototype:** installable current UI; no real-money private API.
- **Android A2 — Autonomous public market data:** direct Bybit Chart/DOM/Tape without PC/VPS.
- **Android A3 — Secure private read-only account connection:** credentials and authoritative reconciliation; no mutations.
- **Android A4 — Manual PAPER trading:** validate command/session/lifecycle behavior without real-money mutations where useful.
- **Android A5 — Restricted live manual trading:** progressively add Market/Limit/Cancel/Amend/Full Close under safety contracts.
- **Android A6 — Protection/recovery hardening:** STOP/TAKE, reconnect, process death, ambiguity, network switching, and resume.
- **Android A7 — Real-device acceptance/performance:** sustained load, battery, thermals, latency, unreliable network, and phone UX.

The sequence is preliminary and may change after research.

### 16.8 Non-goals

- Android implementation is not started or authorized.
- The future Robot is not coupled to Android, and autonomous manual Android mode does not require VPS.
- Existing desktop/web architecture is not removed; React is not rewritten; Android dependencies are not introduced.
- Secrets are not stored in JS/frontend, and real-money trading is not enabled by this checkpoint.

This document is the canonical roadmap unless a proven defect requires a narrowly scoped deviation.
