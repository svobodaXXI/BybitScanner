# Robot Protection Optimization Implementation Plan

Status: **OWNER-APPROVED IMPLEMENTATION PLAN**

Date: 2026-10-06

Purpose: turn the fresh MUBARAKUSDT/JNJUSDT `ingress_overflow` incident and the follow-up architecture review into the canonical implementation sequence for Robot protection reliability.

This plan is product-critical. It outranks Terminal/UI work, Geometry research, and Robot feature expansion until the protection path is proven stable in a fresh full PAPER acceptance.

## 1. Proven incident and current baseline

Fresh PAPER evidence proved that MUBARAKUSDT and JNJUSDT were emergency-closed by one shared protection incident:

- `ROBOT_PROTECTION_EMERGENCY_CLOSE`
- reason: `MARKET_DATA_CONTINUITY_LOST`
- cause: `ingress_overflow`
- stage: `protection_recovery`
- STOP/TAKE were not crossed on either trade;
- JNJUSDT had been managed normally for almost an hour before the shared failure;
- the protection ingress reached capacity 64 and queue latency reached ~31.9 s;
- a slow owner task reached ~8.4 s;
- protection processing itself reached ~4.1 s.

The emergency close was correct fail-closed behavior after continuity was lost. The defect class is the architecture that allowed protection continuity to be lost.

Already completed:

1. **Slice 1 / PR #392 — protection ingress priority**
   - protection tasks no longer wait behind an entire FIFO backlog of ordinary owner work;
   - one mutation owner is preserved;
   - real overflow still fails closed.

2. **Slice 2A / PR #393 — robot candidate hot-path indexes**
   - schema v25 adds indexes on `robot_candidates(trading_account_id, symbol)` and `(trading_account_id, status)`;
   - hot-path candidate lookup no longer scales linearly with historical candidate count;
   - measured incident-DB path fell from ~200 ms per lookup to single-digit / low-double-digit milliseconds.

In progress:

3. **Slice 2B / PR #394 — no REST fallback on owner-thread protection close**
   - protection close uses authoritative streamed in-memory book evidence;
   - continuity recovery may use the already-prefetched off-thread recovery snapshot;
   - no authoritative book means no fabricated fill; obligation remains durable and fail-closed.

## 2. Target architecture

The intended end-state is a two-plane design.

### Market-data plane

Responsibilities:

- maintain Bybit WebSocket subscriptions;
- assemble and validate order books;
- track continuity using Bybit sequence/update identifiers;
- perform any REST snapshot/recovery I/O outside the mutation owner;
- emit compact immutable protection evidence.

Network I/O, snapshot reconstruction, and raw book maintenance must not block the Robot mutation owner.

### Robot mutation plane

Responsibilities:

- consume already-validated protection evidence;
- evaluate STOP/TAKE/lifecycle rules;
- mutate authoritative Robot/PAPER state;
- persist durable events/state transitions;
- never perform unbounded network I/O on the hot protection path.

The single-owner mutation invariant remains authoritative until a separately approved architecture replaces it.

## 3. Implementation order

Do the following slices in order. Do not jump to policy relaxation before the mechanical latency risks are removed.

### P0-A — finish Slice 2B: protection close must be network-free

Owner-thread protection close may not call REST.

Acceptance:

- zero network calls in STOP, TAKE and protection emergency-close dispatch;
- streamed authoritative book produces the same execution result as before;
- missing/stale authoritative book produces no synthetic fill;
- replay remains idempotent;
- continuity-loss recovery remains fail-closed;
- Robot PAPER CI PASS.

Current vehicle: PR #394.

### P0-B — remove remaining owner-thread REST paths

Audit all remaining owner-thread calls that can reach `get_book` or other blocking external I/O.

Known starting points:

- `robot_match_symbol`;
- `_dispatch_robot_market_book`;
- `open_positions` if it can execute on the mutation owner;
- Box/manual-close execution plans;
- manual PAPER market orders;
- any instrument/candle/provider call with hidden network fallback.

Required implementation rule:

- ordinary control work may use an off-thread I/O stage followed by a serialized mutation handoff;
- protection-critical work may use only already-authoritative in-memory evidence or an off-thread snapshot explicitly handed into the owner;
- no hidden provider fallback from owner code.

Acceptance:

- deterministic fake slow REST cannot block the owner thread;
- no execution semantics change;
- no duplicate commands/fills;
- explicit metrics identify any remaining blocking task.

### P0-C — protection subscription lease per owned position/obligation

Every open Robot trade and unresolved protection obligation owns a market-data subscription lease.

Contract:

- Workspace/UI symbol changes cannot remove the only protection stream;
- lease begins before or atomically with executable protection ownership;
- lease remains while position/protection obligation is active;
- lease releases only after durable terminalization/reconciliation;
- multiple owners of the same symbol share one physical subscription via reference counting or equivalent ownership;
- restart reconstructs leases from durable Robot state.

This should make the PR #394 fallback case ("latched protection but no streamed book") exceptional rather than normal.

Acceptance:

- switching Workspace symbols cannot remove protection coverage;
- restart restores every required lease before Robot becomes admission-ready;
- no subscription leak after terminalization;
- duplicate leases do not create duplicate market streams.

### P0-D — active Robot state in owner-owned RAM

Remove SQLite reads from the per-event protection path where durable correctness does not require re-reading the database.

Maintain an owner-owned in-memory index, at minimum:

`symbol -> active candidate / trade / protection obligation / ownership state`

Rules:

- SQLite remains the durable source for restart/recovery;
- RAM is rebuilt deterministically from durable state at startup/reconcile;
- every mutation updates durable state and RAM under the same owner sequencing;
- no separate unsynchronized cache writer;
- a cache miss that cannot be proven safe fails closed and rehydrates from durable state rather than guessing.

Goal:

- protection event cost must be independent of historical candidate/trade volume.

Acceptance:

- protection hot path performs zero full-history scans;
- benchmark remains effectively flat as history grows by at least an order of magnitude;
- restart/recovery equivalence tests prove the RAM view reconstructs the same authoritative state.

### P0-E — compact immutable ProtectionEvidence handoff

Raw book processing should not be performed as part of a Robot mutation task.

Introduce an immutable evidence object conceptually equivalent to:

`ProtectionEvidence(symbol, generation, seq, update_id, bid, ask, received_at_ms, continuity_state)`

The market-data plane prepares it. The owner consumes it.

Requirements:

- sequence/generation provenance is explicit;
- event identity remains deterministic;
- STOP-wins / TAKE ordering remains unchanged;
- stale/out-of-generation evidence is rejected;
- evidence cannot be mutated after admission.

Acceptance:

- owner latency no longer contains book parsing/merge/reconstruction;
- replay of the same evidence cannot double-execute;
- reconnect/generation barrier tests remain GREEN.

## 4. P1 — Bybit continuity recovery with sequence-aware stitching

Only after P0-A through P0-E are stable, improve recovery policy.

Use Bybit order-book continuity metadata (`u`, `seq`, generation/reconnect state) to distinguish:

1. continuity is intact;
2. continuity was broken but can be reconstructed exactly;
3. continuity cannot be proven.

Desired recovery flow:

1. freeze new Robot admissions for the affected protection scope;
2. buffer incoming deltas outside the owner;
3. obtain REST snapshot outside the owner;
4. stitch snapshot + buffered deltas according to Bybit sequence rules;
5. reconstruct authoritative price path if possible;
6. if the gap is fully proven and STOP/TAKE ordering is determinable, recover without unnecessary emergency close;
7. if price path cannot be proven, retain current fail-closed emergency-close behavior.

Hard rule:

**A current REST snapshot alone never proves that STOP/TAKE was not crossed during a missing interval.**

No "our own backlog caused it, therefore continue" exception is allowed.

Acceptance:

- reconstructable gaps recover without capital-destructive false emergency close;
- unreconstructable gaps remain fail-closed;
- tests cover STOP crossed, TAKE crossed, both/ordering ambiguity, and neither crossed;
- recovery provenance is persisted for incident diagnosis.

## 5. P1 — replace fixed freshness with continuity-aware freshness

The current ~1 s freshness threshold is useful but too coarse as the final rule.

Target decision should combine:

- stream health;
- sequence continuity;
- generation/reconnect identity;
- latest receive/source timestamp;
- an explicit bounded age threshold appropriate to the market-data channel.

Do not remove age limits. Sequence continuity supplements freshness; it does not make arbitrarily old data executable.

Acceptance:

- quiet symbols do not create unnecessary protection stalls merely because no unrelated book update occurred;
- genuinely stale or disconnected books remain non-authoritative.

## 6. Pre-LIVE gate — exchange-native catastrophic protection

Before real-money LIVE activation, the local process must not be the only line of defense.

Target:

- place exchange-native Bybit protective STOP/TP or equivalent conditional reduce-only/close-on-trigger protection for every LIVE-owned position where the strategy contract permits it;
- local Robot remains the supervisory layer for partial management, translated STOPs, re-entry, advanced exits and reconciliation;
- exchange protection is reconciled continuously against local intent;
- local process/network/server failure must not remove the base catastrophic STOP.

Required design before implementation:

- exact mapping of partial fills and multi-part positions to exchange protection quantity;
- STOP replacement/translation ordering;
- atomicity/race handling during position changes;
- restart reconstruction;
- conflict handling between local close and exchange trigger;
- dual-account/master-junior ownership later must not share protection identifiers.

LIVE remains prohibited until this gate and all other LIVE authorization gates are explicitly accepted.

## 7. Observability and SLOs

Protection reliability must have measurable budgets rather than only pass/fail incidents.

Persist/expose at least:

- protection ingress depth/high watermark;
- queue latency p50/p95/p99/max;
- protection task processing p50/p95/p99/max;
- ordinary owner-task max and category;
- count of ingress overflows;
- count/duration of missing protection leases;
- count/duration of latched `DISPATCHING` obligations waiting for authoritative evidence;
- REST/network calls attempted from owner thread — target **zero**;
- continuity recovery outcomes: exact-recovered / emergency-close / unresolved.

Initial engineering SLOs for PAPER should be frozen after measurement on the repaired runtime, not guessed in this document.

Any protection overflow during a clean full PAPER acceptance is a release blocker until classified.

## 8. Validation sequence

After P0 slices are merged:

1. synchronize laptop runtime to the same authoritative `main`;
2. perform the owner-controlled canonical restart;
3. allow schema migrations to complete;
4. confirm Robot protection health and lease reconstruction;
5. run a clean full Scanner/PAPER acceptance over the complete eligible universe;
6. require normal Telegram delivery and natural Robot candidates;
7. monitor protection latency/overflow metrics for the whole run;
8. acceptance fails if the run is interrupted, if protection overflows, or if a real owned position enters unexplained emergency close/reconciliation debt.

Do not count the interrupted 2026-10-06 run as acceptance; internet loss prevented completion.

## 9. Routing relative to the rest of the backlog

Until the P0 protection plan passes fresh PAPER acceptance:

- Robot protection/recovery work is first priority;
- CELO dust cleanup may be completed when its already-prepared safe fix is ready, but must not displace a protection P0;
- Box dual-grid/re-entry/multi-TF/master-junior remain queued after reliability;
- Geometry/calibration remains parked unless a concrete signal defect blocks Robot;
- Terminal/UI/manual chart/autopilot/shortcut cosmetics remain last.

## 10. External design references

The direction is informed by established trading-system patterns, not copied wholesale:

- Hummingbot: dedicated order-book/data-source layer feeding local book state rather than strategy code performing request-time market-data I/O;
- NautilusTrader: data engine + indexed in-memory cache + message/event separation;
- Freqtrade: exchange-hosted stop-loss as a protection layer rather than relying exclusively on the trading process;
- Bybit V5: WebSocket sequence/update identifiers and exchange-native TP/SL / reduce-only / close-on-trigger primitives.

Repository invariants and real BybitScanner evidence remain authoritative if they conflict with an external framework pattern.

## 11. Definition of done

This optimization epic is complete only when all of the following are true:

- no network I/O can block the protection mutation owner;
- an active Robot position cannot silently lose its market-data coverage lease;
- protection hot-path latency is independent of accumulated history;
- continuity state is sequence-aware and observable;
- reconstructable gaps recover without needless emergency close;
- unreconstructable gaps remain fail-closed;
- full natural PAPER acceptance completes with zero unexplained protection overflows;
- pre-LIVE architecture includes exchange-native catastrophic protection;
- restart/recovery preserves the same ownership and protection invariants.

Until then, feature expansion must not outrank this reliability work.
