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

## 10. MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM — ARCHITECTURE CORRECTION

Human-approved architecture correction. Current status:
`M8 COMPLETE / REAL-PHONE + TUNNEL ACCEPTANCE PASS`.

Backend symbol authority and generation isolation pass automated tests. Live ONG backend probes reached READY with
a 1000×1000 book plus trades and 5-minute klines, and local UI ONG→BTC→ONG passed. The real phone nevertheless
rendered blank Chart, DOM and Smart Tape. The proven failure boundary is therefore after backend authority, in the
backend→proxy/tunnel→mobile distribution path. Observed payloads were approximately 65 KB for book, 58 KB for
trades and 96 KB for klines, with book traffic approximately 2 MB per six seconds. Transport overload is a supported
root-cause candidate, not a proven exact cause.

Target architecture:

```text
BYBIT
→ one long-lived public linear MarketDataHub
→ InstrumentRegistry + SubscriptionRegistry
→ per-symbol SymbolContext
   - authoritative full L2
   - trades
   - candles
   - health
   - sequence/subscription state
→ WorkspaceController
   - requested_symbol
   - active_symbol
   - generation
   - readiness barrier
→ one multiplexed workspace client stream
→ Chart + DOM + Smart Tape
```

Binding contracts:

1. An ordinary Workspace symbol switch must not recreate the exchange-facing engine.
2. UI consumers must not own Bybit subscriptions.
3. Symbol contexts have explicit active and bounded-warm lifecycle states.
4. Switch success requires Workspace readiness: a fresh sequenced book, healthy trades or a recent bootstrap, and
   healthy candle history/live state.
5. The previous Workspace remains visible and working until `WORKSPACE_READY` for the candidate generation.
6. Candidate failure preserves the previous Workspace and active authority.
7. The backend owns authoritative full L2; the frontend receives a bounded snapshot followed by sequenced deltas.
8. Trades bootstrap once and then deliver only new trades in bounded batches.
9. Candle history is delivered once and followed by live candle updates.
10. The former deferred transport consolidation is promoted to one multiplexed Workspace WebSocket, replacing
    separate Workspace market-data SSE streams. REST remains the command path.
11. Every event carries symbol, generation, kind, source/event timestamps, and state; sequence/version is mandatory
    where the source supplies it.
12. Chart, DOM and Smart Tape consume one generation and cannot maintain independent active-symbol authority.
13. The previous symbol remains warm for a bounded grace period so A→B→A does not require avoidable cold startup.
14. Health exposes `NOT_READY`, `SYNCING`, `READY`, `STALE`, and `DEGRADED`, plus timestamps, sequence,
    reconnect/subscription state and the latest error.
15. Components are isolated: kline failure must not destroy healthy book/trades, and a quiet Tape must not make DOM
    unavailable.
16. Existing explicit switch authority, stale-generation rejection, generation identity, candidate preparation,
    previous-Workspace preservation and fail-closed behavior remain mandatory.

`InstrumentRegistry` must admit only instruments that the Workspace transports can serve: linear, `Trading`,
LinearPerpetual-compatible, `quoteCoin=USDT`, complete tick/quantity/precision/minimum constraints, and correct
pagination. Autocomplete must expose only this supported Workspace universe.

An ambiguous, stale or unsequenced book is not current liquidity truth. The UI may retain a last-known view only
when visibly marked `STALE` or `DEGRADED`; uncertainty must not silently become a blank or READY Workspace.

Future deterministic and chaos coverage must include stale/out-of-order book deltas, sequence gaps and resnapshot,
duplicate trades, slow/quiet trades, kline-only failure, one-component reconnect, candidate timeout/failure,
rapid A→B→A switching, late prior-generation events, warm-context expiry, client reconnect/resume, proxy/tunnel
backpressure, bounded queues and slow-client eviction.

Migration sequence:

- M0 — COMPLETE: preserve current authority invariants and record the measured distribution-boundary baseline and
  target projection/readiness/health contracts below.
- M1 — COMPLETE: one backend-owned `InstrumentRegistry` atomically publishes the fully paginated,
  transport-compatible Decimal-safe linear instrument universe; `/api/instruments`, Workspace switching and PAPER
  instrument lookup consume that same snapshot.
- M2 — COMPLETE: one long-lived public linear `MarketDataHub` owns orderbook/publicTrade subscribe,
  dispatch, reconnect and resubscribe across reusable per-symbol contexts while the existing HTTP/PAPER boundary is
  preserved by the compatibility manager.
- M3 — COMPLETE: `WorkspaceController` owns requested/active authority, generation, pending candidate, composite
  readiness and bounded active/warm context lifecycle over the M2 `SymbolContext` registry.
- M4 — COMPLETE: one backend-owned `ClientMarketProjection` emits bounded book bootstrap/deltas, bounded trade
  bootstrap/new batches and one-time candle bootstrap/changed-candle updates from authoritative Hub contexts.
- M5 — COMPLETE: one generation-scoped multiplexed Workspace WebSocket carries an atomic bounded bootstrap and
  sequenced book/trade/candle/health updates with bounded replay, resnapshot and slow-client eviction contracts.
- M6 — COMPLETE: one frontend store consumes the M5 multiplexed WebSocket and atomically projects one symbol,
  generation and event sequence across Chart, DOM and Smart Tape; legacy SSE remains backend-compatible.
- M7 — COMPLETE: deterministic bounded chaos/regression coverage proves authority isolation, sequence/resnapshot,
  replay/backpressure, reconnect, mixed projection churn and M3–M6 compatibility invariants.
- M8 — COMPLETE: rebuilt production assets passed desktop and real-phone Chrome acceptance through the active
  tunnel, including ONGUSDT 5m→1m→5m with stable Chart/DOM, visible candles and live DOM/Smart Tape.

### 10.1 M0 current implementation inventory and measured baseline

Measurement date: 2026-08-30. Method: an isolated local PAPER runtime on port 8876 with temporary persistence,
followed by simultaneous direct reads of the three current SSE routes for 15 seconds per symbol. Counts are JSON
payload bytes after the SSE `data:` prefix and exclude HTTP/TLS/tunnel overhead. Results characterize these bounded
windows only; they do not prove tunnel or mobile overload and do not establish peak rates.

Current backend ownership is per active-symbol `MarketDataSession`, recreated on a successful symbol switch:

- one Bybit public linear WebSocket worker for `orderbook.1000.<symbol>`, reconstructing and retaining the
  authoritative 1000-level-per-side L2 book;
- one separate Bybit public linear WebSocket worker for `publicTrade.<symbol>`, retaining at most 500 aggregated
  Tape items and also feeding the derived 15-second candle buffer;
- five independent REST polling workers for native klines `1`, `5`, `15`, `60`, and `D`, each polling once per
  second and retaining/sending up to 1000 candles; `15s` has no worker and is derived from public trades.

The browser owns exactly three concurrent market-data `EventSource` instances for the selected symbol/timeframe:

- `/api/public-orderbook/stream?symbol=<symbol>`;
- `/api/public-trades/stream?symbol=<symbol>`;
- `/api/public-klines/stream?symbol=<symbol>&interval=<interval>`.

Symbol change closes and recreates all three. Timeframe change closes/recreates only klines. Each `onerror` closes
its source and schedules a one-second reconnect. Native browser EventSource retry may occur before the explicit
close handler runs, but the store itself owns the one-second retry. Source-object, selected-symbol and timeframe
identity checks reject callbacks from replaced sources.

| 15-second payload-only baseline | BTCUSDT | ONGUSDT |
| --- | ---: | ---: |
| Orderbook first / median subsequent payload | 72,295 / 72,296 B | 65,246 / 65,233 B |
| Orderbook messages/s / payload bytes/s | 5.200 / 375,939 | 4.000 / 260,935 |
| Orderbook levels per message | 1000 bids + 1000 asks | 1000 bids + 1000 asks |
| Trades first / median subsequent payload | 1,095 / 1,095 B | 1,088 / 1,165 B |
| Trades messages/s / payload bytes/s | 0.600 / 662 | 0.267 / 306 |
| Trade items per measured message | 1 | 1 |
| 5m klines first / median subsequent payload | 94,654 / 94,654 B | 95,630 / 95,630 B |
| 5m klines messages/s / payload bytes/s | 0.800 / 75,723 | 0.800 / 76,504 |
| Candles per message | 1000 | 1000 |
| Combined messages/s / payload bytes/s | 6.600 / 452,324 | 5.067 / 337,744 |
| Concurrent realtime client connections | 3 | 3 |

Every orderbook update sends a full reconstructed snapshot, not a delta. Its payload carries symbol, generation,
bids, asks, exchange timestamp, matching-engine timestamp, backend receive time, update id, sequence, state, source,
version and best bid/ask. The backend authoritative depth and transmitted client depth are both 1000 per side; the
default DOM renders 16 rows, with responsive rendering bounded at 2–200 total rows.

Trades call `snapshot_after(0)` on every 30-ms server loop, but per-connection `seen_ids` filtering sends the
retained items only once on connection/bootstrap and then sends only unseen aggregates. The backend retains 500;
the frontend retains the latest 80. Therefore accumulated history is not resent on every event, but reconnect opens
a new connection and bootstraps all then-retained items. The measured post-switch windows contained one item per
message; quiet symbols need no fabricated trade for readiness.

Every native kline refresh replaces and sends the full retained history. The measured 5m stream sent 1000 candles
in every one of 12 messages in each window. It carries symbol, interval, tick size, candles, receive time, state,
source, version and generation. JSON parsing CPU was not separately isolated by this probe, so no CPU percentage or
mobile parsing-cost claim is made; repeated parsing/allocation of the measured full arrays is a direct behavioral
fact, while its device impact remains an acceptance measurement.

Backend authoritative full L2 must remain available to `LiveOrderBookProvider`, `PaperRuntime` book-update
processing, L2-walk PAPER Market fills/VWAP/slippage, and book-correlated trade/sweep projection. Client projection
optimization must not reduce or replace that backend truth.

### 10.2 M0 target client projection contract

The first event for a candidate generation is `workspace_snapshot`. It atomically carries:

- `kind`, `symbol`, `workspace_generation`, snapshot/event timestamp and composite health state;
- supported instrument metadata required by sizing and display: tick/quantity steps, precision, minimum quantity
  and minimum notional;
- a bounded client book projection with book update id/sequence/version, exchange/receive timestamps and best
  bid/ask;
- recent trade bootstrap, which may be explicitly empty-valid, with last trade sequence/identity if available;
- candle history bootstrap for the selected timeframe with interval and candle version/source timestamp;
- component subscription states, reconnect counts and latest errors.

Incremental events are limited to `book_delta`, `trade_batch`, `candle_update`, and `health`. Every event carries
`kind`, `symbol`, `workspace_generation`, event timestamp, component state and payload. `book_delta` additionally
carries the base/new book version and upstream update id/sequence plus changed/removed price levels;
`trade_batch` carries bounded new trades and stable trade identities/sequences; `candle_update` carries interval,
candle identity/start time, candle version and whether it appends or replaces the live candle; `health` carries the
component and composite state/observability fields. Source timestamps are mandatory where meaningful, and
sequence/version is mandatory where the source or normalized owner supplies it. The client rejects every event
whose symbol or generation differs from its candidate/active authority, and a book base-version or sequence break
forces fail-closed resnapshot rather than speculative merge.

### 10.3 M0 readiness and health contract

`WORKSPACE_READY` requires one valid fresh sequenced orderbook snapshot, a healthy trades subscription plus a
completed recent-trades bootstrap (including explicitly empty-valid), completed candle-history bootstrap, and a
healthy live-candle transport. A newly arriving trade is not required. Activation is one atomic authority swap only
after all mandatory components belong to the same candidate symbol/generation. Failure or timeout leaves the
previous Workspace visible and authoritative, reports the switch failure explicitly and discards the candidate;
candidate retention is not authorized until the later bounded warm-context lifecycle is implemented. A new symbol
label must never accompany empty or prior-generation projections.

Health states:

- `NOT_READY`: no usable validated snapshot; projections are hidden; market-data-dependent trading is disabled;
- `SYNCING`: subscription/bootstrap/resnapshot in progress; candidate is not visible; market-data-dependent trading
  is disabled;
- `READY`: all readiness-barrier components are current; all projections render and market-data-dependent PAPER
  behavior may use authoritative backend truth;
- `STALE`: last-known validated data may remain visibly marked, but it is not current liquidity truth and
  market-data-dependent trading is disabled;
- `DEGRADED`: one component has failed while others remain valid; healthy components and visibly marked last-known
  data may render, but any action depending on the failed/stale component is disabled fail closed.

Required observability is `last_book_ts`, `last_trade_ts`, `last_candle_ts`, book update id/sequence/version,
component subscription state, reconnect count and `last_error`, plus symbol/generation. Numeric staleness thresholds
remain `TUNABLE / MEASUREMENT-BASED`; M0 does not invent them.

### 10.4 M0 efficiency goals, migration safety and later acceptance

The immutable goals are one multiplexed Workspace client connection; bounded initial book projection plus deltas;
one-time recent-trades bootstrap plus new bounded batches; and one-time candle history plus live candle updates.
The existing DOM needs 16 rows by default and at most 200 total responsive rows, the frontend retains 80 Tape
items, and the current chart consumes 1000 candles. Therefore provisional limits are: enough book price coverage to
produce the current 200-row maximum at the selected compression with a measured safety margin, at most 80 recent
trade aggregates for bootstrap, and at most 1000 selected-timeframe candles for bootstrap. Exact book level/band,
delta-batch, queue, cadence and staleness numbers remain `TUNABLE / MEASUREMENT-BASED` and require M4 measurement
plus M8 load and device evidence rather than arbitrary constants.

Migration is additive: introduce the Hub behind existing normalized backend interfaces; keep full L2 and existing
PAPER consumers unchanged; add bounded client projection independently; prove snapshot/delta parity, ordering and
failure semantics before connecting the frontend; migrate Chart/DOM/Tape together to the multiplexed stream; run
local, proxy/tunnel and real-phone acceptance; only then remove the three SSE routes and per-consumer ownership.
No big-bang transport or PAPER rewrite is permitted.

Later deterministic/chaos acceptance categories are: A→B and rapid A→B→A; stale/late generation rejection;
missing book snapshot and candidate timeout with previous-Workspace preservation; stale/out-of-order delta,
sequence break and resnapshot; silent/slow and duplicate trades; kline bootstrap/live failure; upstream and client
reconnect/resume; isolated partial degradation; unsupported symbol; warm-context expiry; bounded backpressure and
slow-client eviction; and payload/bandwidth regression against this M0 baseline. Each case must prove correct
authority, explicit health, bounded queues/payloads and fail-closed market-data-dependent behavior.

### 10.5 M1 InstrumentRegistry checkpoint

M1 introduces one backend-owned registry over the existing normalized `InstrumentSnapshot`; it does not introduce
a parallel trading-metadata model. Refresh follows every `nextPageCursor`, rejects duplicate symbols and cursor
loops, skips unsupported or incomplete entries, and publishes one immutable candidate only after every page has
completed successfully. A failed initial refresh publishes nothing; a failed later refresh preserves the previous
valid snapshot. Supported instruments are exactly active `Trading`, USDT-quoted `LinearPerpetual` contracts with
complete positive price/quantity/notional constraints. Numeric trading constraints remain `Decimal`.

Normalized uppercase `get`, `supports` and sorted `list_supported` operations are snapshot-only and perform no
network request. `/api/instruments` preserves its existing compact `symbol` plus `tick_size` response shape while
being projected from the registry. Workspace switch tick-size admission and PAPER instrument lookup use the same
registry instance. M1 does not add a background refresh schedule; process-start refresh remains fail closed. M2 is
the exact next gated stage and is not implemented or authorized by this checkpoint.

### 10.6 M2 MarketDataHub checkpoint

M2 introduces one backend-owned `MarketDataHub` thread and one Bybit public linear WebSocket connection for all
currently subscribed orderbook and publicTrade topics. The Hub owns dynamic subscription, dispatch by exact symbol,
disconnect clearing, reconnect and complete resubscription. A subscription is `SUBSCRIBING` after send and becomes
`SUBSCRIBED` only after a normalized event is actually applied; reconnect count and latest error remain explicit.

Each symbol has one reusable `SymbolContext` containing the authoritative reconstructed book, aggregated trades,
derived 15-second candles, native candle buffers, subscription state, book sequence/version and last-update/health
metadata. Repeated subscription returns the same context. Ordinary Workspace switching no longer creates or closes
an exchange-facing book/trade engine: the compatibility manager waits on the candidate context, atomically changes
active generation/provider/PAPER callback, rejects stale consumers and leaves the previous Hub context intact.
Candidate failure still preserves the previous active Workspace.

Native candle history/live refresh remains the existing REST polling owned by each context; frontend still uses the
three existing SSE routes and their payload shapes. M2 does not implement multiplexed client transport, bounded
active/warm eviction, composite readiness, client projection deltas or `WorkspaceController`. These remain later
gated stages. M3 is the exact next migration stage.

### 10.7 M3 WorkspaceController, readiness and warm lifecycle checkpoint

M3 introduces one backend-owned `WorkspaceController` as the sole production authority for `requested_symbol`,
`active_symbol`, `active_generation`, switch state, pending candidate and latest switch error. A switch serializes
candidate preparation but does not block current read-only consumers. The active context/generation changes only
after the candidate passes one composite readiness barrier and the provider/PAPER callback swap succeeds.
The initial HTTP Workspace also waits on this barrier fail closed before the server begins serving.

The barrier requires a non-empty READY book with positive version/update/sequence identity, acknowledged healthy
trades subscription with completed bootstrap (explicitly empty is valid), non-empty selected 5-minute candle
history and healthy live candle state. A quiet symbol does not require a newly arriving trade. Timeout, unsupported
symbol or activation failure leaves the previous Workspace authoritative and records explicit failed state; a new
unready context is unsubscribed and discarded.

Successful switching retains the previous context as warm, supports A→B→A identity reuse, and bounds retention to
one warm context with a tunable 30-second default grace. Limit overflow or grace expiry unsubscribes and closes the
evicted context. The Hub remains the only exchange subscription owner. Existing POST switch and three SSE routes
remain compatibility adapters over controller authority, including generation and stale-consumer rejection.

At the M3 checkpoint, M4 efficient snapshot + delta client projections were the exact next gated stage;
chaos/regression hardening remained M7.

M3 does not implement bounded client projections/deltas, the multiplexed client stream or frontend migration.

### 10.8 M4 efficient snapshot + delta client projections checkpoint

M4 adds one stateful backend `ClientMarketProjection` between full authoritative `SymbolContext` truth and client
transport. It uses the controller-owned active context/generation and rejects stale generations. The full 1000×2
book remains unchanged for PAPER execution. Client book bootstrap is configurable and defaults to 250 levels per
side: the current responsive maximum of 200 DOM rows plus a 25 percent safety margin.

Each READY book event carries symbol, Workspace generation, projection/source versions, upstream update/sequence
identity, timestamps and health. A normal delta is the exact mutation from the previous bounded window to the new
one, including explicit size `0` deletes, displaced edge removal and newly revealed hidden levels. Client base
version mismatch, skipped source version, regressed upstream identity or recovery from untrusted health emits a
fresh bounded snapshot; non-READY truth emits health with `resync_required` and no apparently-current delta.

Trade bootstrap is capped at the frontend retention of 80 aggregates. Later batches contain only unseen IDs,
duplicate IDs are suppressed, and a quiet bootstrap is explicitly empty without fabricated trades. Candle
bootstrap is capped at 1000 for the selected interval. Later REST-poll projections emit only changed records with
open-time identity and explicit `replace` or `append`; unchanged polls emit nothing, while incompatible history
requires a bounded rebootstrap.

Migration is additive. `/api/client-market-projection/stream` exposes one selected projection kind with the common
future-M5 envelope, while all three legacy SSE routes and current frontend remain unchanged. M5 multiplexing,
frontend migration and real-phone acceptance have not started.

Payload-only live measurement used compact JSON before HTTP/TLS/tunnel overhead for 15.016 seconds on 2026-08-30:

| Projection measurement | BTCUSDT | ONGUSDT |
| --- | ---: | ---: |
| Book bootstrap / bounded levels | 18,268 B / 250+250 | 16,839 B / 250+250 |
| Book median delta / messages/s / bytes/s | 1,236.5 B / 5.061 / 6,697 | 1,119 B / 4.395 / 5,464 |
| Trades bootstrap bytes/items | 1,200 B / 1 | 142 B / 0 |
| Trades messages/s / bytes/s | 0.599 / 741 | 3.863 / 6,448 |
| 5m candle bootstrap bytes/items | 94,694 B / 1000 | 95,662 B / 1000 |
| 5m candle update median / messages/s / bytes/s | 299.5 B / 0.133 / 40 | 301 B / 0.333 / 100 |
| Combined incremental bytes/s | 7,478 | 12,013 |
| Reduction from M0 combined bytes/s | 444,846 B/s / 98.35% | 325,731 B/s / 96.44% |

The projection currently compares one full authoritative book snapshot to its previous 250×2 window per accepted
source update: bounded client output is correct, but the internal O(authoritative depth log depth) comparison is a
replaceable optimization boundary. The measurement proves payload reduction, not the cause or resolution of the
earlier phone failure. At the M4 checkpoint, M5 one multiplexed Workspace stream was the exact next gated stage.

### 10.9 M5 multiplexed Workspace stream checkpoint

M5 adds one backend-owned `WorkspaceStreamBroker` and additive `/api/workspace/stream` WebSocket endpoint. A new
generation-scoped stream begins with one atomic `workspace_snapshot` containing instrument sizing/display metadata,
bounded M4 book/trade/candle bootstraps, component states and Hub health/sequence/reconnect observability. Later
events share one `stream_id` and strictly increasing `event_sequence` and are limited to `book_delta`,
`trade_batch`, `candle_update` and `health`; every envelope carries symbol, Workspace generation, event timestamp,
component state and the complete M4 projection payload.

The broker retains at most 32 resumable sessions. Each session retains at most 256 sequenced events and permits at
most 64 pending outbound events. Reconnect may supply `stream_id` and `after_sequence`: available events replay in
order, while an invalid or expired replay position produces a fresh atomic `workspace_snapshot` with an explicit
resync reason. A component-level M4 resnapshot is likewise promoted to an atomic Workspace resnapshot rather than
allowing mixed component generations. The final snapshot assembly rechecks active generation and stale generation
polling fails closed.

The HTTP runtime uses WebSocket write timeout plus the bounded pending contract to evict slow clients. Ordinary
disconnect retains the bounded broker session for resume; stale generation, backpressure or write timeout removes
it. Ten-second stream health heartbeats preserve proxy observability without claiming frontend/PAPER readiness.
WebSocket framing is server-to-client text only in M5; client command/subscription ownership is not introduced.

Migration remains additive. The three legacy SSE routes, the M4 per-component projection SSE route, REST command
paths, authoritative full PAPER L2 and all frontend source remain unchanged. M6 atomic frontend generation
projection and transport migration are the exact next gated stage and have not started. Proxy/tunnel and real-phone
performance acceptance remain M8; M5 does not claim that the earlier phone failure is resolved.

### 10.10 M6 frontend atomic generation projection checkpoint

M6 replaces default frontend ownership of three independent `EventSource` connections with one
`BackendWorkspaceMarketDataStore` over `/api/workspace/stream`. The old `BackendSseMarketDataStore` remains an
explicit compatibility class and all backend legacy routes remain available; there is no automatic fallback that
could create two simultaneous symbol authorities. Vite dev and preview proxies now explicitly upgrade WebSockets.

One pure `workspaceProjection` reducer owns the client authority tuple `stream_id`, symbol, Workspace generation,
selected interval and monotonic `event_sequence`. A complete READY `workspace_snapshot` validates and converts
book, explicitly empty-valid trade bootstrap, non-empty selected-timeframe candle history and instrument tick
metadata before publishing one new immutable `MarketDataSnapshot`. Invalid or incomplete snapshots leave the prior
projection untouched. Chart, DOM and Smart Tape therefore observe one atomic external-store update rather than
independent component arrival.

Incremental events apply only to the requested symbol/interval and current stream/generation. Exact duplicates and
foreign authority are ignored; sequence gaps/regressions, malformed events, book base-version mismatch and invalid
candle append/replace semantics close the socket, clear resume authority, visibly degrade the retained projection
and reconnect for a fresh snapshot. Ordinary disconnect visibly marks the last validated book STALE and reconnects
with `stream_id` plus `after_sequence`; successful replay continues monotonically, while a backend resnapshot is
applied atomically. A transport heartbeat advances sequence but cannot restore degraded Workspace readiness.

Book deltas mutate the bounded M4 client window, trade batches deduplicate by stable ID and retain 80, candle
updates append/replace by open time and retain 1000, instrument tick size comes from the atomic snapshot, and book
health can retain last-known levels only with explicit STALE/DEGRADED state. Authoritative PAPER full L2 and all
command/order semantics remain backend-owned and unchanged.

Deterministic M6 projection/store plus legacy SSE parity tests pass, the full frontend regression suite exits zero,
and the production Vite build passes with 66 transformed modules. These are automated/build evidence only, not
browser, tunnel or real-phone acceptance. M7 chaos/regression hardening is the exact next gated stage; M8 real-phone
and tunnel performance acceptance has not started.

### 10.11 M7 deterministic chaos and regression checkpoint

Revision 1.79 records `M7 — DETERMINISTIC CHAOS / REGRESSION SUITE IMPLEMENTED / AUTOMATED PASS`. New bounded
backend tests exercise replay-window boundaries, invalid/future resume, queue overflow and clearing, stale
generation rejection, component-resnapshot escalation, heartbeat sequencing, duplicate/foreign attachment,
unknown streams, session pressure and mixed book/trade/candle churn on one stream and generation. The tests use no
wall-clock sleeps, live exchange dependency, proxy or tunnel.

New pure frontend/store tests exercise stale and future generations, foreign streams, symbol/interval mismatch,
exact duplicates, sequence gap/regression, malformed/unknown events, incomplete snapshots, authoritative recovery,
book displacement/reveal and base-version mismatch, duplicate/out-of-order trades, candle replace/append and wrong
interval, disconnect bursts, stale socket isolation, resume and forced fresh resnapshot. Existing M5 stream and M6
projection/store tests run beside the new cases as regression evidence.

The suite found no production defect and changed no production source. Legacy SSE compatibility, full authoritative
PAPER L2, REST commands and order/execution semantics remain unchanged. This is automated local evidence only: it
does not exercise proxy/tunnel throughput, socket write-timeout behavior under a real slow network, browser
rendering or a real phone. M8 local/proxy/tunnel and real-phone performance acceptance is the exact next gated stage
and is not started.

### 10.12 M8 real-browser failure and bounded layout correction

Revision 1.80 keeps M8 `OPEN / FAIL` after production/tunnel observation on 2026-08-30. ONGUSDT initially rendered
live DOM and Smart Tape, but a 5m→1m selection made Chart and DOM expand far beyond the viewport, Chart candles
became unusable, and DOM reported `LIVE BOOK UNAVAILABLE` while last-known Tape values remained visible. This is
failure evidence, not M8 acceptance.

Direct M5 probes proved complete READY ONGUSDT snapshots for both interval `5` and interval `1`, with the same
active Workspace generation, correct candle interval/history and READY book/candle components. Local production
browser reproduction isolated the visual defect to a circular layout boundary: the DOM `ResizeObserver` increased
the projected row count from the available ladder height, intrinsic grid content then increased the unbounded
minimum-height shell, and the newly enlarged ladder triggered another row calculation. Body height grew from a
720-pixel viewport to 2,088 pixels within 50 ms; Chart canvas and DOM followed the expanded grid. A simultaneous
tunnel WebSocket `ECONNABORTED` explained the unavailable book state; no generation/interval mismatch, empty candle
projection, mixed component authority or backend resnapshot loop was observed.

The bounded correction gives `.workspace-shell` an explicit Telegram stable-viewport/`100vh` height while
preserving its existing minimum-height and safe-area behavior, allowing the grid to distribute a finite available
height rather than derive it from DOM rows. A store regression covers atomic 5m→1m→5m transitions, stale socket
isolation, READY book, non-empty candle history, correct interval and absence of reconnect timers. Targeted
Chart/DOM/Workspace tests and a fresh production build pass. Rebuilt local production browser evidence remains
stable at body 720 px and Chart/DOM 591 px with 26 rows through 5m→1m→5m. M8 remains open until the same rebuilt
assets pass a fresh external tunnel/browser and real-phone acceptance sequence.

Revision 1.81 records that re-acceptance as PASS. Desktop Chrome and phone Chrome through the active `lhr.life`
tunnel both passed ONGUSDT 5m→1m→5m: Chart and DOM stayed bounded, candles remained visible, DOM and Smart Tape
continued live updates, and `LIVE BOOK UNAVAILABLE` did not recur. M8 is complete; measured payload reduction and
this device result remain separate evidence and do not prove transport overload was the original root cause.

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

Current checkpoint:

```text
WORKSPACE SYMBOL SWITCHING — BACKEND AUTHORITY FIX AUTOMATED PASS / REAL-PHONE TRANSPORT ACCEPTANCE FAIL
```

Open next work item:

```text
MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM — ARCHITECTURE CORRECTION
```

Open Positions real-phone acceptance remains `PASS`, and the backend symbol-authority/generation correction has
automated proof. The real-phone ONG result is nevertheless a transport acceptance failure: Chart, DOM and Tape were
blank despite a live READY backend. Section 10 is now the owning corrective architecture and M0 is its exact next
implementation step. The Hub and multiplexed stream are not implemented. Aggressive DOM Limit confirmation and
Done/Enter focus progression remain separately deferred.

## 15. Engineering completion criterion

Not merely green tests.

Completion means:
No known defects remain in scope, critical invariants pass, and real acceptance scenarios are stable on the actual phone.

## 16. Future track — Autonomous Android Manual Trading Terminal

Checkpoint: `AUTONOMOUS ANDROID MANUAL TRADING TERMINAL — FUTURE DIRECTION RECORDED / IMPLEMENTATION NOT AUTHORIZED`.

Status: `FUTURE / PLANNING ONLY / NOT_IMPLEMENTATION_AUTHORIZED`.

This is a separate future track after the current terminal completion and acceptance path. It does not replace the
desktop/web or Telegram Mini App prototype, does not start Android implementation, and does not change section 14's
immediate next step: `MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM — ARCHITECTURE CORRECTION`.

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
