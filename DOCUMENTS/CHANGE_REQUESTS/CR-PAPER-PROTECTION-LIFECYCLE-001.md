# CR-PAPER-PROTECTION-LIFECYCLE-001 — Autonomous PAPER Protection Execution Lifecycle

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-PAPER-PROTECTION-LIFECYCLE-001",
  "title": "Autonomous PAPER Protection Execution Lifecycle",
  "status": "IMPLEMENTED_VERIFYING",
  "revision": "1.6",
  "lifecycle_stage": "VERIFY",
  "objective": "Own the deployed D2 PAPER protection lifecycle, runtime verification, continuity-loss recovery, ingress reliability corrections and evidence-based Robot trade finalization, independent of UI selection.",
  "non_goals": [
    "Changes to structural STOP/TAKE strategy, sizing, wedge strategy or LIVE",
    "BSBUSDT D1 invalid structural STOP / partial-fill recovery",
    "Invented historical replay or fill prices",
    "Blind mutation of legacy runtime rows merely to make status labels look clean"
  ],
  "approved_scope": [
    "PAPER protection lifecycle implementation and verification already deployed through the related commits",
    "Record user-required invariants, runtime evidence, concrete defects/blockers and remaining acceptance gaps in this owning CR"
  ],
  "prohibited_scope": [
    "LIVE behavior or mutation-gate changes",
    "Unrelated/user-owned file changes",
    "Adding OPEN to RobotBreakoutMonitor entry advancement",
    "Changing D1 recovery, structural STOP/TAKE strategy, sizing or ownership semantics"
  ],
  "authoritative_references": [
    "AGENTS.md",
    "DOCUMENTS/ASSISTANT_PROTOCOL.md",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_RULES.md",
    "DOCUMENTS/PROJECT_STATE.md#CURRENT_DEVELOPMENT_PRIORITY",
    "DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-BREAKOUT-MONITOR-001.md",
    "DOCUMENTS/PAPER_LIVE_SHARED_TRADING_CORE_RECOVERY.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md",
    "DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md"
  ],
  "approved_decisions": [
    "PAPER implementation is deployed; VERIFY proceeds from real operator usage and concrete observed blockers",
    "Protection ownership follows exposure independently of UI, selected account/symbol and Robot entry state",
    "Preserve LONG bid <= STOP / bid >= TAKE; SHORT ask >= STOP / ask <= TAKE",
    "Latch first confirmed crossing durably before execution; retreat cannot cancel it",
    "Reuse MarketDataHub, serialized runtime, PAPER executor and shared accounting",
    "Duplicate events, ambiguity and restart cannot lose committed obligations or duplicate close effects",
    "Actual execution evidence proves fill economics and FLAT; Robot closure is idempotent",
    "Unobserved downtime-only crossings are a separate semantic decision; no fabricated historical execution",
    "D2.3 realized_pnl_pct is frozen (owner decision, 2026-09-13) as (realized_pnl_usdt - fees_costs_usdt) / actual_entry_notional_usdt * 100, where realized_pnl_usdt is gross realized trading PnL from actual execution evidence, fees_costs_usdt is the actual accumulated fee cost attributable to this Robot trade close lifecycle, and actual_entry_notional_usdt is the actual Robot-owned entry quantity multiplied by the actual average entry price (leverage ignored); actual_wv MUST NOT be used as the denominator because it represents a WV fraction, not an absolute USDT notional, in this repository; fail closed if actual_entry_notional_usdt cannot be proven from authoritative Robot-owned execution/position evidence -- never guess or substitute aggregate/manual-owned quantity"
  ],
  "unresolved_decisions": [
    "Eliminate the recurring normal-runtime protection ingress saturation that can fence Robot admission even when the affected covered symbol has no open Robot exposure",
    "Fix closed-trade fee attribution so fees_costs_usdt includes all attributable Robot entry and exit fees without symbol-wide/manual contamination"
  ],
  "acceptance_criteria": [
    "All section 14 invariants hold",
    "All mandatory scenarios T01-T28 and boundary cases in section 16 pass at actual shared execution/persistence boundaries",
    "No UI, fresh-candle, admission-state or selected-account dependency in protection execution",
    "Correlated actual fill -> FLAT -> cleanup -> Robot trade CLOSED evidence"
  ],
  "verification_requirements": [
    "Use read-only durable runtime evidence for incident diagnosis before mutation",
    "Continue normal PAPER operation and inspect only concrete blockers encountered in practice",
    "Keep focused deterministic regressions for changed critical behavior; avoid broad speculative test campaigns",
    "Do not claim unobserved runtime scenarios from CI alone"
  ],
  "risks": [
    "Lossy latest-book coalescing loses transient crossing evidence",
    "Closed-trade fee attribution can be incomplete even when protection closure succeeds",
    "Symbol-only identity can close or attribute a later/manual position incorrectly",
    "Uncertain dispatch, unavailable liquidity and attribution gaps require reconciliation",
    "Local protection cannot observe events during process/transport downtime"
  ],
  "rollback_boundaries": [
    "Documentation may be superseded without runtime changes; preserve incident evidence",
    "Future rollback preserves unresolved obligations and execution identities, never restores UI-dependent coverage while exposure survives",
    "Approve schema compatibility/downgrade plan before migration"
  ],
  "implementation_phases": [
    {
      "id": "TASK",
      "status": "DOCUMENTED_USER_AUTHORIZED"
    },
    {
      "id": "SPEC",
      "status": "IMPLEMENTED_BASELINE_WITH_CURRENT_AMENDMENTS"
    },
    {
      "id": "CONTEXT",
      "status": "RUNTIME_EVIDENCE_CURRENT"
    },
    {
      "id": "IMPLEMENT",
      "status": "PAPER_DEPLOYED"
    },
    {
      "id": "VERIFY",
      "status": "RUNTIME_IN_PROGRESS"
    },
    {
      "id": "RECORD",
      "status": "RUNTIME_EVIDENCE_RECORDED"
    }
  ],
  "current_phase": "VERIFY",
  "current_checkpoint": "EDGE_INGRESS_SATURATION_CURRENT_BLOCKER_ARCHITECTURE_PLAN_RECORDED",
  "implementation_status": "PAPER_DEPLOYED_VERIFYING",
  "next_phase": "VERIFY",
  "next_phase_authorization": "Continue runtime verification and fix only observed concrete blockers",
  "related_commits": [
    {
      "phase": "AUTHORITATIVE_BASELINE",
      "commit": "14f9b514966fd89d0cb6ebe178a6ece0501ffb56"
    }
,
    {
      "phase": "PAPER_RUNTIME_VERIFYING",
      "commit": "d4d550ecf4899bee59a01dff21a11b58ee6c701d"
    }
  ],
  "amendment_history": [
    {
      "revision": "1.0",
      "date": "2026-09-13",
      "reason": "User-authorized D2 TASK/SPEC/CONTEXT capture; no runtime or Git-write authorization"
    },
    {
      "revision": "1.1",
      "date": "2026-09-13",
      "reason": "Owner froze D2.3 realized_pnl_pct denominator/fee-allocation accounting convention prior to resuming D2.3 IMPLEMENT"
    }
,
    {
      "revision": "1.2",
      "date": "2026-09-18",
      "reason": "Recorded deployed PAPER runtime evidence from GIGGLEUSDT STOP closure and current concrete blockers: incomplete fee attribution, legacy sync_state labels on pre-fix positions, and unresolved Robot reconciliation-required state"
    },
    {
      "revision": "1.3",
      "date": "2026-09-18",
      "reason": "Recorded KSMUSDT ingress_overflow root cause and approved recovery design: force a fresh authoritative snapshot after continuity loss instead of waiting indefinitely for a future WebSocket snapshot"
    },
    {
      "revision": "1.4",
      "date": "2026-09-18",
      "reason": "Recorded deployed KSMUSDT restart-safe REST snapshot recovery, successful evidence-based reconciliation to PAUSED, confirmed synced PAPER projection after recovery close, and a second EDGEUSDT ingress_overflow with no position/trade/execution proving the remaining blocker is recurring ingress saturation rather than emergency-close recovery"
    },
    {
      "revision": "1.5",
      "date": "2026-09-18",
      "reason": "Recorded systemic ingress architecture review, external mature-project references, and a staged minimal-change correction plan prioritizing exposure safety, lifecycle-scoped overflow handling, and removal of unnecessary per-book-event owner work before any queue redesign"
    },
    {
      "revision": "1.6",
      "date": "2026-09-18",
      "reason": "Removed stale pre-implementation and pre-recovery statements, refreshed current architecture/deployment authority, removed duplicate unresolved metadata, and demoted superseded incident text so current sections no longer contradict deployed runtime"
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

Date: 2026-09-18 (Europe/Moscow).
Historical baseline branch: `robot-v0-1-admission-gate`.
Historical baseline HEAD: `14f9b514966fd89d0cb6ebe178a6ece0501ffb56`.
Current deployed PAPER checkpoint recorded in sections 21-22:
`d4d550ecf4899bee59a01dff21a11b58ee6c701d`.

Sections 1-16 preserve the original D2 design baseline where still accurate. Sections 17 and 20 were refreshed after
deployment so they no longer describe implementation as future/unauthorized. Sections 21-22 and the current metadata
are authoritative for deployed PAPER behavior, runtime evidence, current blockers and the active correction design.

## 1. Problem statement and evidence

D2 is a financially significant PAPER execution defect: active persisted STOP/TAKE can remain
unevaluated after a Robot trade opens. It is separate from BSBUSDT D1, where structural STOP
planning fails after a partial fill.

| Evidence | FARTCOINUSDT | 1000TAGUSDT |
| --- | --- | --- |
| Candidate | `507c993dd4c0b2c02f403e95` | `e844939cd6c0ea4768c38b3e` |
| Position | LONG 1736 | LONG 372 |
| Average entry | `0.1438168778801843317972350230` | `0.6709088709677419354838709677` |
| Effective STOP | `0.14318` | `0.6678` |
| Effective TAKE | `0.14511` | `0.6804` |
| Protection | `confirmed_active` | `confirmed_active` |
| Evidence time UTC | 2026-09-12 20:36:16.182 | 2026-09-12 20:31:12.296 |
| User-supplied crossing | STOP, candle low `0.14308` | TAKE, candle high `0.6832` |
| Observed result | Position/candidate OPEN | Position/candidate OPEN |

The preceding read-only investigation queried `paper_runtime.sqlite3` with SQLite `mode=ro`
and `query_only`. Both symbols had entry Buy executions and no closing Sell execution; Robot
exit fields were null. The read-only account endpoint showed active UI account BYBIT MAINNET while
Robot PAPER was RUNNING/READY. These are incident-time observations, not current-state promises.

The user supplied candle-cross checks (85/90 candles); these are not historical bid/ask traces.
In-memory probes of actual function bodies demonstrated OPEN exclusion and correct predicates when
the crossing values were supplied as bids. No closing mutation was invoked. Inspected logs predated
the trades. Exact historical invocation counts and crossing-time L2 inputs remain unproven; absence
of a closing execution is not proof that every possible matcher call was absent.

## 2. Scope

This document owns the D2 lifecycle, deployed behavior, runtime evidence and current correction design. D2 acceptance and the current required implementation scope
apply to Robot-owned protected PAPER positions. The shared PAPER protection mechanism must remain
architecturally reusable for manual PAPER positions, but extending or changing the full manual PAPER
trading lifecycle is not a separate objective or acceptance obligation of this CR. References elsewhere
in this CR to shared PAPER coverage describe architectural reusability, not an expansion of that scope.
Manual positions must never be mistakenly adopted or attributed as Robot-owned. All existing ownership,
ambiguity and fail-closed requirements remain binding, including manual/Robot isolation checks.

Responsibilities: autonomous coverage, reliable event delivery, durable crossing latch, serialized
bounded closing, failure/restart recovery, protection cleanup and Robot exit recording.

One owning file under `DOCUMENTS/CHANGE_REQUESTS/` satisfies CONTRACT-CHANGE-REQUEST-001. No new run,
global priority change or separate index update is required by the loaded routing for this
documentation task. The closed breakout-monitor CR and existing run records remain unchanged.

## 3. Out of scope

- `_structural_extreme()`, STOP geometry/distance policy, TAKE strategy, sizing and wedge strategy.
- BSBUSDT D1 unprotected partial-fill recovery and its emergency decision policy.
- LIVE execution, adapter changes, credentials or new exchange permissions.
- Re-entry, adding OPEN to the entry filter, a second execution/accounting engine or market feed.
- Candle-high/low trigger substitution and retrospective simulated fills.
- General manual takeover or allocation of mixed ownership; ambiguity fails closed.

## 4. Current architecture

```text
Bybit public WS
  -> MarketDataHub
  -> per-symbol SymbolContext / PublicOrderBookBuffer
  -> RobotProtectionCoverageManager
  -> SerializedPaperRuntime owner queue
  -> PaperRuntime.process_robot_market_event()
  -> Robot entry LIMIT matching / fill finalization / STOP-TAKE evaluation
  -> shared PAPER executor + ExecutionEngine
  -> SQLite projections, durable obligations and Robot trade finalization
```

Robot coverage is independent of Workspace account/symbol selection. Coverage currently includes OPEN Robot exposure,
unresolved protection obligations, and APPROVED `RETEST_DETECTED` entry lifecycles that require event-driven LIMIT
matching. Every admitted Robot coverage update is currently a distinct non-coalesced owner task because transient
STOP/TAKE crossing evidence must not be overwritten.

Continuity loss is fail-closed. PR #138/#139 added fresh authoritative REST snapshot recovery and restart-safe
rehydration of durable `ROBOT_PROTECTION_COVERAGE_LOST` state. Real KSMUSDT runtime evidence proved
`fence -> restart -> snapshot recovery -> EMERGENCY_CLOSE -> FLAT -> explicit reconcile -> PAUSED`.

The remaining architectural blocker is not missing recovery. It is recurring saturation of the shared bounded
Robot-protection ingress under ordinary coverage traffic, including pre-entry symbols with no position. Section 22
owns the current pressure-point analysis and staged minimal-change design.

## 5. Root cause

Protection responsibility is attached to viewing a symbol or advancing entry; neither owns exposure
for its full lifetime. Coverage must follow durable protected positions and unresolved obligations.
Correct inequalities cannot repair missing calls. Successful shared closure also lacks Robot
bookkeeping integration.

Keep four boundaries distinct: coverage, transient-event loss, durable trigger/dispatch, and
downstream finalization. Do not attribute D2 to D1 geometry failure.

## 6. Target architecture and external references

```text
Durable protected PAPER positions / unresolved obligations
 -> runtime-owned protection responsibility
 -> independent MarketDataHub coverage
 -> ordered valid executable-side quote event
 -> durable irreversible crossing obligation
 -> serialized shared PAPER execution
 -> actual execution evidence -> FLAT -> cleanup
 -> idempotent Robot trade finalization when attribution is proven
```

`PaperProtectionSupervisor` is a responsibility label, not a required class. The serialized owner
remains the mutation owner. Market-data threads must not use its SQLite connection or submit orders.
Reuse existing components before introducing narrowly scoped integration.

Primary sources reviewed 2026-09-13 under EXTERNAL_REFERENCE_REUSE_POLICY. No code is copied.
These sources are design accelerators, not local authority or proof of our durability guarantees.

| Source | Extracted pattern | Decision / local adaptation |
| --- | --- | --- |
| [NautilusTrader OrderEmulator](https://nautilustrader.io/docs/latest/concepts/orders/emulated/) | Local conditional orders subscribe to trigger data, release through ordinary execution and reactivate restored orders | ADAPT: shared PAPER owner, bid/ask events and stable identity; prove SQLite/dispatch guarantees separately |
| [Hummingbot PositionExecutor](https://hummingbot.org/strategies/v2-strategies/executors/positionexecutor/) | Position management and exit conditions continue after entry | ADAPT exposure lifetime; REJECT importing triple-barrier strategy, time exits or sizing |
| [Freqtrade stoploss / emergency_exit](https://www.freqtrade.io/en/stable/stoploss/) | Protection failure has an explicit exit route | ADAPT failure-path discipline only; D2 retains unresolved triggered closes, without changing D1 emergency policy |
| [QuantConnect/LEAN Stop Market Orders](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/stop-market-orders) | Trigger and actual Market fill differ; stop price is not guaranteed fill price | ADAPT actual shared PAPER L2 economics; REJECT importing bar-based fill assumptions |

Current implementation binds matching to UI/entry. Existing project intent requires a shared
autonomous trading core. References support separation of conditional intent, observation and
execution without replacing local safety, ownership or PAPER/LIVE contracts.

## 7. Durable trigger semantics

Preserve effective normalized projection prices and inclusive predicates:

| Side | STOP | TAKE |
| --- | --- | --- |
| LONG | best bid <= stop | best bid >= take |
| SHORT | best ask >= stop | best ask <= take |

Only valid, correctly scoped, ordered, ready L2 evidence qualifies. No last-trade, candle, mid-price
or synthetic fallback. A first valid quote already beyond the threshold qualifies; no preceding
safe-side quote is required. Reject stale/wrong-generation input and expose data gaps.

Proposed lifecycle facts, not mandatory new enums:
armed protection -> TRIGGERED -> dispatch pending -> resolved execution/FLAT -> cleanup/finalization.
Failure/ambiguity are unresolved overlays, never terminal success.

Atomically latch the first qualifying event before releasing close execution. Retain winning leg,
effective threshold, observed bid/ask, source event identity/sequence/generation, source/receipt
timestamps, account/category/symbol/position index, position lifecycle identity, protection revision
and observed quantity. Shared position evidence remains current-quantity authority.

One winning obligation exists per protected position lifecycle. Duplicate events and the sibling
leg cannot dispatch another competing close. Preserve STOP precedence if both predicates qualify
on one valid observation; report invalid geometry rather than repair it here. Retreat cannot undo
the latch. Serialize pre-trigger amend/delete with observation; reject stale protection revisions.
After trigger, ordinary amendment/deletion cannot erase the obligation. A concurrent authorized
manual close may satisfy it through correlated FLAT evidence. This arbitration is proposed for review.

Protection revision alone is not lifecycle identity: it may reset after cleanup. A delayed obligation
must not close a later position on the same symbol. Exact schema and atomic API are pre-IMPLEMENT gates.

## 8. Market-data subscription ownership

Coverage comes from non-flat PAPER positions with confirmed protection and unresolved obligations.
Manual protection remains manual; shared execution is not Robot adoption. Acquire/reconcile coverage
at startup and on protection/position changes. Release interest only when no unresolved protection
obligation or other consumer needs the symbol. Reuse existing MarketDataHub transport and contexts.

Workspace and protection consumers must coexist. UI switching cannot detach protection interest;
MAINNET UI selection cannot suppress PAPER execution. Reconnect restores required symbol interests.

Do not route crossing-sensitive evidence through the current single-slot latest-book queue.
Preserve ordered observations before lossy presentation coalescing, using an immutable event path
to the owner or an equivalent reviewed durable ingress design. Queueing only an ID and rereading
a mutable current book is insufficient. Multi-symbol fairness and bounded backpressure are required:
no silent loss and no unbounded queue. If readiness/continuity cannot be proven, expose unhealthy
coverage and constrain new Robot risk through existing safety gates; do not claim healthy protection.
This is not a new emergency liquidation rule for data loss.

Desired subscription and ready coverage are different facts. Offline transport cannot satisfy
readiness; activation/restart must expose the gap. A watchdog may repair coverage but minute polling
cannot be the primary trigger engine. Freeze and measure healthy processing latency and overload
behavior before acceptance; exact bounds remain an implementation-readiness decision.

## 9. Serialized execution boundary

After trigger commit, the owner re-reads account, lifecycle, side/current quantity, control and
unresolved execution evidence. Close only the bounded residual of that same lifecycle; never
reverse or consume a replacement position. Reuse PaperMarketExecutor and ExecutionEngine accounting.

Link obligation and shared command/order/execution identity before dispatch. The current protection
path calls the executor directly: add durable correlation, not a second executor. The existing
UI-dependent full_close wrapper is not assumed to supply safe deduplication automatically.

Trigger and execution books are distinct evidence. Execute against a valid execution-time book;
record actual simulated VWAP and fees, never manufacture a fill at the STOP/TAKE threshold.
An empty LIMIT inventory must not disable protection. An unrelated LIMIT exception must not starve
protection evaluation. Preserve serialized orders and ownership-scoped cleanup; no broad foreign
order cancellation.

## 10. Idempotency

Use durable unique obligation identity and atomic dispatch claim linked to shared commands/executions.
A stable request string or in-memory in-flight flag alone is insufficient. Repeated event/attempt
delivery returns existing progress, never a fresh command.

Persist dispatch intent/correlation before mutation. After an interrupted response, reconcile by
retained identity and immutable executions; no response is not proof of no fill. A new attempt is
permitted only after the prior attempt is authoritatively resolved and same-lifecycle residual remains.
Keep the original trigger across attempts. A manual close that already made this lifecycle FLAT
prevents a second close. Do not infer safety from an empty/missing projection alone.

## 11. Restart/recovery

Startup rebuilds coverage and loads unresolved obligations before permitting new Robot risk where
unresolved safety blocks it. OPEN candidates never route back to entry finalization.

- Trigger committed, not dispatched: resume that obligation with valid execution-time data.
- Dispatch/result uncertain: reconcile shared evidence, no blind resend.
- Fill persisted, obligation pending: derive progress from correlated execution/position evidence.
- FLAT with protection present: complete shared cleanup idempotently.
- Protection cleared but Robot trade OPEN: finalize bookkeeping from retained evidence, no new close.
- Missing/conflicting attribution: remain reconciliation-required; no invented reason or economics.

If a cross occurs entirely during downtime and price retreats before the first valid restored quote,
this CR does not infer it from candles or fabricate an old fill. Historical replay is DEFERRED to a
separate semantic decision. Record the observation gap. If price is still beyond the threshold on
the first valid restored quote, that quote triggers normally.

Ingress before durable latch is also a crash boundary. Freeze the guaranteed event-admission point
and any durable inbox design before IMPLEMENT. Do not claim durable observation from an in-memory
queue acknowledgement. Every committed trigger survives restart; uninterrupted observation of
unavailable market events is not claimed.

## 12. Robot trade close integration

Shared execution -> position -> FLAT/cleanup remains accounting authority. Correlate the exact trade
using existing origin/controller and order/execution relationships, not symbol alone. Existing Robot
commands may carry MANUAL labels in this prototype: do not rewrite historical provenance or mistake
an enum for proof. Mixed/ambiguous attribution is a gate, not an invented allocation model.

After proven closure, call SQLiteStore.close_robot_trade() idempotently. Use:
- exit_time_ms: actual terminal execution time;
- exit_price: correlated closing-fill VWAP if multiple fills;
- exit_reason: durable winning STOP/TAKE leg when that execution actually caused closure;
- realized PnL/fees: attributable shared execution economics, not cumulative symbol values from
  unrelated trades;
- realized_pnl_pct: owner-frozen (2026-09-13) as
  `(realized_pnl_usdt - fees_costs_usdt) / actual_entry_notional_usdt * 100`, where
  `actual_entry_notional_usdt` is the actual Robot-owned entry quantity multiplied by the actual
  average entry price (leverage ignored). `actual_wv` MUST NOT be used as the denominator: in this
  repository it represents a WV fraction, not an absolute USDT notional. Fail closed if
  `actual_entry_notional_usdt` cannot be proven from authoritative Robot-owned execution/position
  evidence; never guess or substitute aggregate/manual-owned quantity.

Planning prices may differ from normalized protection prices. Effective trigger prices come from
the confirmed projection; exit prices always come from execution. Do not invent Robot trades for
manual positions or D1 pre-trade exposure.

The existing close function atomically records trade exit and candidate OPEN -> CLOSED. Integrate
it in an appropriate transaction or recoverable finalization step. A crash after shared FLAT/cleanup
must remain repairable. If another authorized close wins, preserve the proven actual exit cause;
a pending trigger alone cannot relabel a manual fill STOP/TAKE.

## 13. Failure modes

| Failure | Required behavior |
| --- | --- |
| Missing subscription, stale/disconnected data | Restore through hub; expose unhealthy coverage; no synthetic price |
| Crossing then retreat | Keep committed obligation; use current valid book for fill |
| Duplicate/out-of-order/old generation | No duplicate dispatch; reject stale input without erasing latch |
| Queue overload/gap | Explicit degraded coverage and reviewed backpressure, no latest-only fallback |
| Trigger persistence failure | No uncorrelated dispatch; expose failure and retain/reconcile admitted evidence |
| Insufficient liquidity / executor failure | Preserve trigger; resolve attempt before safe retry |
| Ambiguous result / owner timeout | Continue monitored reconciliation; no blind resend |
| Partial close evidence | Same-lifecycle residual only, no increase/reversal |
| Manual close / replacement position | Reconcile original lifecycle; never close replacement |
| FLAT but trade finalization fails | Retry bookkeeping from durable evidence, not trading |
| Unknown ownership/economics | Reconciliation; no unsafe close or false attribution |

Current PAPER Market matching is all-fill-or-error for insufficient depth. Partial-result tests
exercise the execution contract boundary; they must not pretend today's matcher partially fills.

## 14. Safety invariants

1. Every non-flat confirmed-protected PAPER position owns autonomous coverage; unavailable data is
   explicitly unhealthy, not a silent healthy activation.
2. Workspace-selected symbol cannot affect execution.
3. Active UI account cannot affect PAPER/Robot protection execution.
4. First confirmed crossing is durably latched before execution.
5. Retreat cannot cancel the obligation.
6. Duplicate notifications cannot duplicate close executions.
7. Restart preserves committed triggered closes.
8. Failed/ambiguous close remains recoverable and monitored.
9. Authoritative execution/position evidence alone proves FLAT.
10. FLAT clears/terminalizes protection without deleting pending audit/finalization evidence.
11. Proven Robot closure records exit/economics idempotently and transitions candidate CLOSED.
12. OPEN candidates never return to entry finalization.
13. Adding OPEN to the RobotBreakoutMonitor entry filter is prohibited.
14. Structural STOP, TAKE strategy, sizing, wedge logic, LIVE and D1 recovery remain unchanged.
15. Account/category/symbol/lifecycle/controller scope is enforced; manual stays manual and a later
    position cannot inherit an old obligation.

## 15. Acceptance criteria

All invariants and the test matrix must pass at actual shared runtime/persistence boundaries.
Correlate activation, coverage readiness, trigger/latch, dispatch identity, fill, authoritative FLAT,
cleanup and Robot finalization. confirmed_active, an HTTP acknowledgement, mocked success or a cleared
chart line alone is insufficient evidence. D2 remains open until runtime verification; this CR's
documentation validation and prior in-memory probes are not runtime acceptance.

## 16. Test matrix

| ID | Scenario | Required assertion |
| --- | --- | --- |
| T01 | UI/browser closed | Coverage and execution continue |
| T02 | Workspace another symbol | Both positions independently covered |
| T03 | UI account MAINNET | PAPER closes; no LIVE mutation |
| T04 | LONG STOP | bid <= STOP latches correct leg |
| T05 | LONG TAKE | bid >= TAKE latches correct leg |
| T06 | SHORT STOP | ask >= STOP latches correct leg |
| T07 | SHORT TAKE | ask <= TAKE latches correct leg |
| T08 | Cross then immediate retreat | Latch survives; fill uses actual execution-time book |
| T09 | Duplicate book updates | One obligation and dispatch per attempt |
| T10 | Close execution failure | Trigger retained; safe resolved retry eligibility |
| T11 | Ambiguous close result | Monitored reconciliation; no blind resend |
| T12 | Restart after trigger before execution | Same obligation resumes |
| T13 | Restart after dispatch before result persistence | Identity reconciliation prevents duplicate |
| T14 | Already FLAT on recovery | Cleanup/finalization only |
| T15 | Protection cleared, trade OPEN | Recover finalization from retained evidence |
| T16 | Robot exit fields | Actual time/VWAP/reason/PnL/fees and correct percentage convention |
| T17 | Candidate terminal transition | OPEN -> CLOSED exactly once |
| T18 | Concurrent/duplicate attempts | No duplicate close or reversal |
| T19 | Later ticks / duplicate signal | No re-entry of terminal idea |
| T20 | No fresh candle | Quote-driven protection operates |
| T21 | Two symbols cross while owner busy | Neither lost to global coalescing |
| T22 | Reconnect/old events/overload | Stale input rejected; gap exposed; committed latch survives |
| T23 | Downtime-only cross then retreat | No fabricated historical fill |
| T24 | Manual protection / mixed attribution | Shared protection stays manual; no false Robot adoption |
| T25 | New position after original FLAT | Old obligation cannot close replacement |
| T26 | Amend/delete races / both legs | Reviewed ordering; one winner; no unlatching |
| T27 | Residual/manual close race | Same-lifecycle authoritative quantity only |
| T28 | Crash at each persistence boundary | No lost committed trigger; bookkeeping survives cleanup |

Use deterministic quote sequences plus real temporary SQLite and shared PAPER executor for integration.
Inject failures at actual persistence/dispatch boundaries. Preserve existing direction, cleanup,
idempotency, account switching and Robot entry regressions. No synthetic UI tests.

## 17. Rollout/verification

The PAPER protection lifecycle is deployed and remains in runtime VERIFY.

Current verification policy:

1. use normal PAPER operation;
2. when a concrete blocker occurs, inspect durable state and the connected lifecycle read-only first;
3. fix the proven root cause with the smallest safe scope;
4. use focused deterministic regression for changed critical behavior;
5. verify the same real runtime path after deployment;
6. keep LIVE untouched unless separately authorized.

The KSMUSDT continuity-loss recovery path is runtime-proven. The current runtime blocker is recurring protection
ingress saturation demonstrated by EDGEUSDT. The next implementation work follows section 22's staged design:
measure queue pressure, remove unnecessary hot-path work, then lifecycle-scope overflow consequences before any
larger scheduling change.

Rollback must preserve obligations, execution identities, ownership evidence and fail-closed state. Never delete
economic evidence or downgrade to a reader that cannot recover pending obligations while exposure survives.

## 18. Dependencies

- MarketDataHub/Workspace context sharing and independent protection interests.
- SerializedPaperRuntime owner-thread execution, fair event processing and bounded ingress.
- Shared protection, command/execution deduplication, position/accounting persistence.
- Existing lifecycle/controller evidence and unambiguous execution-to-Robot-trade correlation.
- Existing Robot close persistence and restart responsibilities.
- Owning PAPER/LIVE contracts and roadmap. This CR does not complete Workspace acceptance or reopen
  the closed entry-monitor CR.

D1 is separate, not a dependency requiring design changes here. Later reuse of shared execution
primitives does not merge the two defects or redefine invalid-structural-STOP recovery.

## 19. Risks and limits

Local protection requires a running process and valid data. Downtime and pre-durability loss are
explicit limits, not promises of exchange-side protection. Durability applies to committed obligations
and idempotent effects. Mixed ownership, weak lifecycle identity, unbounded queues and inconsistent
projection/obligation state are release blockers unless safely represented and tested.

Liquidity may cause slippage; STOP/TAKE is not a guaranteed fill price. Do not silently change the
accounting denominator or fee convention, or use original planned WV as closing quantity. Historical
cross reconstruction requires a separate decision, not an implementation shortcut.

## 20. Current implementation surface

| Module | Current responsibility |
| --- | --- |
| `terminal/runtime/paper_runtime.py` | Robot event processing, entry LIMIT matching/finalization, protection crossing, continuity recovery, reconciliation bridge |
| `terminal/runtime/paper_http_server.py` | Market-data coverage manager, bounded serialized ingress, authoritative REST recovery snapshot, HTTP Robot routes |
| `terminal/market_data/hub.py` | Shared symbol-context ownership, subscription lifetime and reconnect generation |
| `terminal/persistence/sqlite_store.py` | Robot candidate/trade/protection obligation persistence, ownership evidence and idempotent finalization |
| `terminal/persistence/schema.py` | Durable schema, including emergency-close lifecycle support |
| `terminal/application/execution_engine.py` | PAPER execution application and authoritative position projection updates |
| `terminal/paper/executor.py` | Shared PAPER LIMIT/MARKET execution semantics and fees |
| `terminal/application/robot_recovery.py` | Durable Robot recovery-state transitions |
| `terminal/application/robot_breakout_monitor.py` | Pre-entry lifecycle, authoritative-fill finalization and Robot entry maintenance |
| focused Robot protection/runtime tests | Critical deterministic regression evidence |

Current design constraints:

- keep one serialized PAPER mutation owner;
- keep one shared market-data hub and one shared PAPER execution/accounting core;
- do not add OPEN back to entry advancement;
- do not add a second protection engine, second market feed or second trading engine;
- optimize the existing ingress/hot path before considering broader queue architecture.

## 21. Runtime evidence — 2026-09-18

This section records observed production-PAPER evidence after deployment of
`e5319da29029d7c463a5cc7dc428a35a01cceb8b`. It supersedes the earlier
documentation-only status statements only for the concrete behavior proven here; unobserved scenarios remain
unproven.

### 21.1 Proven GIGGLEUSDT Robot lifecycle

Read-only inspection of `paper_runtime.sqlite3` showed one durable Robot trade:

- symbol: `GIGGLEUSDT`
- candidate: `ff3772b4da2d163da2f58c42`
- direction/pattern: `LONG / Falling Wedge`
- source timeframe: `5`
- entry path: `LIMIT`
- actual WV: `1`
- average entry: `35.56210826210826210826210826`
- entry quantity: `7.020`
- STOP: `35.40`
- TAKE: `36.2629000`

The durable protection obligation proves a normal STOP close:

- winning leg: `STOP`
- obligation status: `RESOLVED`
- observed bid/ask at latch: `35.37 / 35.39`
- STOP trigger: `35.40`
- actual closing SELL execution price: `35.34770940170940170940170940`
- actual closing quantity: `7.020`
- trade exit reason: `STOP`
- candidate/trade lifecycle terminalized successfully.

This proves the deployed chain for this incident:
Robot-owned protected position -> quote crossing -> durable STOP obligation -> shared PAPER close execution ->
FLAT/trade close bookkeeping.

### 21.2 Accounting defect: entry fee omitted from closed-trade fee total

The same durable evidence exposes a concrete accounting defect.

Executions:

- entry BUY fee: `0.1497876000000000000000000000 USDT`
- exit SELL fee: `0.1488845520000000000000000000 USDT`
- gross realized trading PnL from price movement: `-1.50508 USDT`

But `robot_trades.fees_costs_usdt` stores only
`0.1488845520000000000000000000`, i.e. the exit fee. The entry fee is omitted.

Therefore the stored `realized_pnl_pct=-0.6625239547198833548304399017` understates the actual loss under the
owner-frozen section 12 convention. With both attributable fees, the trade economics are:

- total attributable fees: `0.298672152 USDT`
- net result after both fees: `-1.803752152 USDT`
- fee-inclusive realized PnL percentage: approximately
  `-0.7225239547198833548304399017%`

**Status: OPEN DEFECT.** Fix must aggregate all attributable Robot entry and exit fees for the lifecycle without
pulling unrelated/manual symbol executions into the trade.

### 21.3 PAPER position sync-state defect and deployed correction

Runtime Telegram `/positions` showed existing open PAPER positions with
`sync_state=reconciliation_required` even though the fills were produced by the local PAPER simulator.

Root cause was identified: the generic execution projection helper marked every execution-derived projection
`reconciliation_required`, including simulator-owned PAPER market and LIMIT fills.

Correction merged/deployed in `e5319da29029d7c463a5cc7dc428a35a01cceb8b`:

- simulator-owned PAPER market fills now write `sync_state="synced"`;
- simulator-owned PAPER LIMIT fills now write `sync_state="synced"`;
- generic/exchange evidence keeps the conservative `reconciliation_required` default;
- command correlation remains preserved.

Legacy projections created before this deployment are not rewritten automatically. AEONUSDT may therefore retain
the old label until its lifecycle changes; that legacy display is not itself proof that Robot runtime is fenced.

KSMUSDT subsequently closed through the post-fix local PAPER path and its position projection became
`sync_state="synced"`.

**Status: CODE FIX DEPLOYED AND REAL-RUNTIME CONFIRMED.**

### 21.4 Robot runtime fence — KSMUSDT ingress overflow

At 2026-09-18 14:52 MSK, Telegram `/robot` reported:

- Robot: `ROBOT_RUNNING / RECONCILIATION_REQUIRED` ("Запущен / Нужна сверка");
- watching: 9 candidates;
- open Robot positions: 2.

Read-only durable inspection then proved the exact runtime reason:

`ROBOT_PROTECTION_COVERAGE_LOST symbol=KSMUSDT reason=ingress_overflow`.

KSMUSDT durable state at diagnosis:

- position: LONG `57.97` @ `4.298402967051923408659651544`;
- Robot trade: OPEN, Falling Wedge, LIMIT entry;
- STOP: `4.270`;
- TAKE: `4.38433150975609700`;
- entry quantity: `57.97`;
- entry position version: `1`;
- protection obligation: none;
- executions: one BUY entry execution only; no closing execution.

Therefore the safety fence itself worked: once ordered protection evidence could no longer be admitted, Robot
stopped admitting new risk. However the recovery path did not complete.

That diagnosis exposed the then-deployed recovery gap: unhealthy coverage could wait indefinitely for a naturally
arriving WebSocket snapshot.

PR #138 added active fresh REST order-book snapshot recovery through the existing serialized
`recover_robot_protection_continuity_loss()` / durable `EMERGENCY_CLOSE` path. PR #139 made that recovery
restart-safe by rehydrating the durable continuity-loss reason after backend restart. Section 21.8 records the real
KSMUSDT runtime proof.

**Status: RECOVERY DEFECT FIXED AND RUNTIME PROVEN; RECURRING INGRESS SATURATION REMAINS SEPARATE.**

### 21.5 Rising Wedge / SHORT parity status

PR #135 added focused deterministic PAPER acceptance for the mirrored Rising Wedge path:

`Rising Wedge -> SHORT -> breakout below lower boundary -> retest -> SELL LIMIT -> SHORT position ->
STOP/TAKE -> TAKE close`.

CI passed; the SHORT parity change was introduced at `e5319da29029d7c463a5cc7dc428a35a01cceb8b`
and remains included in the current deployed PAPER runtime `d4d550ecf4899bee59a01dff21a11b58ee6c701d`.

**Status: IMPLEMENTED AND DETERMINISTICALLY VERIFIED; REAL PAPER RUNTIME SHORT TRADE STILL UNOBSERVED.**

### 21.6 Current concrete issue list

| Item | State | Severity / effect |
| --- | --- | --- |
| GIGGLEUSDT STOP lifecycle | PROVEN WORKING | Core autonomous STOP close and durable terminalization succeeded |
| Closed-trade fee aggregation | OPEN DEFECT | Entry fee omitted; fee-inclusive PnL/PnL% is inaccurate |
| New PAPER fill sync state | RUNTIME CONFIRMED | KSMUSDT recovery close advanced the position to FLAT with `sync_state="synced"` |
| Pre-fix AEONUSDT sync label | LEGACY STATE | Old row may still display `reconciliation_required`; no blind rewrite |
| KSMUSDT protection ingress overflow recovery | RUNTIME PROVEN WORKING | Restart rehydrated durable loss, fresh REST snapshot recovery closed unambiguous Robot exposure through `EMERGENCY_CLOSE`, then explicit reconcile completed with no unresolved objects and landed PAUSED |
| Recurring protection ingress saturation | CURRENT BLOCKER | A second `ingress_overflow` occurred on EDGEUSDT even though EDGE had no position, Robot trade or execution; this proves the remaining failure is producer/queue pressure in coverage processing, not close recovery |
| Rising Wedge SHORT runtime behavior | IMPLEMENTED, NOT YET REAL-RUNTIME-PROVEN | Deterministic acceptance passed; await ordinary PAPER runtime observation |

Verification policy remains operator-driven: normal PAPER usage -> concrete observed blocker -> systematic inspection
of the connected lifecycle -> minimal root-cause fix. No broad speculative audit or mass test campaign is implied
by this record.

### 21.7 Implemented continuity-loss recovery contract

The authoritative snapshot recovery design recorded in revision 1.3 is now implemented and runtime-proven for the
KSMUSDT incident:

- continuity loss durably fences Robot admission;
- unhealthy coverage does not rely on a random future WebSocket snapshot;
- a fresh authoritative Bybit REST snapshot carries source identity/timestamps into the existing recovery path;
- recovery is deduplicated per symbol while in flight;
- unambiguous Robot exposure exits through the durable `EMERGENCY_CLOSE` obligation/dispatch path;
- ambiguity remains fail-closed;
- process restart rehydrates the durable continuity-loss reason;
- successful exposure recovery does not silently reopen admission;
- explicit evidence-based Robot reconciliation is required and lands `PAUSED` on clean success.

This item is no longer an open implementation blocker. The remaining protection-runtime blocker is repeated ingress
saturation before/around entry, described in sections 21.8-22.

### 21.8 Deployed KSMUSDT recovery evidence and second EDGEUSDT overflow

After PR #138 and PR #139 were merged and deployed at
`d4d550ecf4899bee59a01dff21a11b58ee6c701d`, the backend was restarted against the existing incident database.

The restart-safe recovery path successfully consumed the durable runtime reason
`ROBOT_PROTECTION_COVERAGE_LOST symbol=KSMUSDT reason=ingress_overflow`, obtained a fresh authoritative Bybit
REST order-book snapshot, and routed the incident through the existing serialized
`recover_robot_protection_continuity_loss()` / durable `EMERGENCY_CLOSE` path.

Read-only runtime evidence after restart:

- KSMUSDT position: `FLAT`, quantity `0.00`;
- position projection: `sync_state="synced"`, version `2`;
- realized PnL projection: `1.773709999999999999999999994 USDT`;
- accumulated fee projection: `0.3000783300000000000000000000 USDT`;
- no open KSMUSDT Robot trade remained.

The durable Robot runtime correctly remained `RECONCILIATION_REQUIRED` after exposure recovery instead of silently
reopening admission. An explicit call to the existing evidence-based Robot reconciliation endpoint then returned:

- `success=true`;
- mode `ROBOT_RUNNING`;
- recovery status `PAUSED`;
- zero unresolved candidate IDs;
- zero unresolved trade IDs;
- zero unresolved protection obligation IDs;
- `reason=null`.

This proves the intended safety sequence in real PAPER runtime:

`durable continuity-loss fence -> restart -> fresh authoritative REST snapshot -> EMERGENCY_CLOSE -> FLAT ->
explicit reconciliation -> PAUSED`.

**KSMUSDT recovery status: RUNTIME PROVEN.**

Immediately afterward, ordinary runtime produced a second durable fence:

`ROBOT_PROTECTION_COVERAGE_LOST symbol=EDGEUSDT reason=ingress_overflow`.

Read-only EDGEUSDT inspection at that time proved:

- position projection: none;
- open Robot trade: none;
- Robot trade rows: none;
- executions: none.

Therefore EDGEUSDT had no Robot exposure requiring emergency close. The repeated overflow cannot be explained by the
previous KSM close-recovery defect. It demonstrates a remaining upstream runtime problem: the bounded Robot
protection ingress can saturate under normal coverage traffic itself, including symbols covered before entry.

Current implementation facts relevant to that blocker:

- `SerializedPaperRuntime` uses one global Robot-protection pending counter with default capacity `64`;
- every admitted Robot coverage book update is a distinct serialized owner task and is intentionally not coalesced;
- the same capacity is shared across all covered Robot symbols;
- coverage includes OPEN Robot trades, unresolved protection obligations, and APPROVED `RETEST_DETECTED`
  pre-entry lifecycles with a working or imminent Robot LIMIT;
- once the global pending count reaches capacity, the next event fails closed with
  `ProtectionIngressOverflow` and the symbol is fenced.

The current evidence does **not** yet prove whether saturation is primarily caused by aggregate WebSocket event
rate, slow owner-thread work, unfair cross-symbol scheduling, avoidable pre-entry traffic, or a combination.
Do not treat queue-size increase alone as a root-cause correction.

**Current blocker: recurring protection ingress saturation in ordinary Robot coverage flow.**

### 21.9 Consolidated remaining defects / blockers after KSM recovery

1. **Recurring protection ingress saturation — CURRENT RUNTIME BLOCKER.**
   The safety fence and recovery now work, but normal operation can still repeatedly trip the bounded ingress queue.
   EDGEUSDT proves this can happen before any position exists and can unnecessarily fence all new Robot admission.

2. **Closed-trade fee aggregation — OPEN ACCOUNTING DEFECT.**
   GIGGLEUSDT still proves `robot_trades.fees_costs_usdt` omits the attributable entry fee, so fee-inclusive
   realized PnL/PnL% is understated.

3. **Legacy pre-fix projection labels — LEGACY DATA ONLY.**
   Old rows may retain `reconciliation_required`; do not rewrite history merely for presentation. The post-fix
   KSMUSDT close proves current local PAPER execution now produces a clean `synced` projection.

4. **Rising Wedge SHORT — IMPLEMENTED, REAL RUNTIME TRADE STILL UNOBSERVED.**
   Deterministic PAPER acceptance exists, but ordinary runtime SHORT evidence remains pending.

The next architecture/debugging task is specifically to localize and remove unnecessary ingress pressure while
preserving the critical invariant that a transient STOP/TAKE crossing cannot be silently coalesced away.

## 22. Systemic ingress architecture review — 2026-09-18

This review follows two real runtime `ingress_overflow` incidents. It separates proven facts from pressure points and
proposed changes. No code behavior is authorized merely by this review.

### 22.1 Proven current architecture

Current flow:

`Bybit WS -> MarketDataHub -> SymbolContext/PublicOrderBookBuffer -> RobotProtectionCoverageManager ->
SerializedPaperRuntime -> PaperRuntime.process_robot_market_event()`.

Proven properties:

- shared `MarketDataHub`, independent Robot coverage, and depth-1000 symbol contexts;
- every accepted Robot book update becomes a distinct non-coalesced owner task;
- one global Robot-protection pending counter has default capacity `64`;
- OPEN positions, unresolved obligations, and APPROVED `RETEST_DETECTED` pre-entry lifecycles share that capacity;
- each `process_robot_market_event()` loads Robot candidates, checks active PAPER LIMITs, runs
  `process_authoritative_fill()`, and evaluates protection;
- EDGEUSDT overflowed with no position, Robot trade or execution, proving the queue can saturate before exposure.

### 22.2 Code-level pressure points

These are evidenced code-level pressure points, not yet individually proven as the sole runtime cause:

1. **Global cross-symbol coupling.** One symbol can consume the same 64-task budget used by every other symbol.
2. **Pre-entry and open-exposure traffic have identical queue priority and overflow consequence.**
3. **No-fill events do unnecessary owner work.** `process_authoritative_fill()` runs even when
   `_match_limits_only()` applied zero executions.
4. **Candidate lookup is account-wide on every event** and then filtered by symbol in Python.
5. **Every Robot event materializes a full normalized L2 snapshot** even though STOP/TAKE crossing needs only the
   executable-side best quote and most resting-limit updates are non-crossing.
6. **Overflow severity is not lifecycle-scoped.** A zero-exposure EDGE-like symbol can fence all new Robot admission.

### 22.3 External references reviewed

Per `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md`, these are design references only.

**Bybit V5 order book — ADOPT continuity semantics**

- https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook
- https://bybit-exchange.github.io/docs/v5/market/orderbook

Useful pattern: snapshot establishes authoritative state; ordered deltas use source IDs; fresh snapshot is the
re-synchronization boundary. Linear level-1000 order book is published at up to 200 ms cadence.

Decision: keep the PR #138/#139 snapshot recovery; never weaken sequence evidence or fabricate missed events.

**Hummingbot OrderBookTracker / ClientOrderTracker — ADAPT responsibility separation**

- https://hummingbot.org/connectors/connectors/architecture/
- https://hummingbot.org/connectors/connectors/build/

Useful pattern: market-data tracking is separate from in-flight order lifecycle, per trading pair, with snapshots
used to repair order-book continuity.

Decision: keep our existing hub/executor, but distinguish market-data continuity role from Robot lifecycle risk.

**NautilusTrader DataEngine / MessageBus — ADAPT typed routing, not a new bus**

- https://nautilustrader.io/docs/latest/concepts/message_bus/
- https://nautilustrader.io/docs/nightly/concepts/architecture/

Useful pattern: data/events/commands have explicit semantics and instrument-aware routing while the trading core can
remain single-threaded.

Decision: do not add a general message bus; make existing Robot coverage targets explicit by role
(`ENTRY_PENDING`, `EXPOSURE`, `OBLIGATION`).

**LMAX Disruptor — ADAPT backpressure principles only**

- https://lmax-exchange.github.io/disruptor/user-guide/

Useful pattern: producer/consumer lag is first-class and bounded processing must not silently overwrite unconsumed
critical events.

Decision: add lightweight queue lag/high-watermark observability; reject a Disruptor-style rewrite for Robot v0.1.

### 22.4 Recommended minimal correction sequence

**Slice A — measure the real saturation boundary.**

Add only lightweight diagnostics to the existing runtime: current/max pending count, enqueue-to-owner latency,
processing duration, symbol/coverage role and overflow high-watermark. No new metrics stack or daemon.

**Slice B — remove unnecessary hot-path work without changing semantics.**

1. retain the result of `_match_limits_only()`;
2. call `process_authoritative_fill()` only when an entry LIMIT execution was actually applied;
3. replace account-wide candidate scans in this hot path with a symbol-scoped persistence query;
4. reuse an owned fill-finalization helper/monitor instead of constructing a new monitor per event where practical.

This is the preferred first implementation slice after diagnostics.

**Slice C — scope continuity-loss consequence to lifecycle risk.**

Expose a small typed coverage target:

- `ENTRY_PENDING`: no proven Robot exposure;
- `EXPOSURE`: Robot-owned non-flat/partial-fill exposure;
- `OBLIGATION`: unresolved durable close.

Policy:

- `EXPOSURE` / `OBLIGATION` overflow keeps the current global fail-closed fence and snapshot recovery;
- `ENTRY_PENDING` with proven zero fill cancels/terminalizes only that entry lifecycle instead of forcing the
  entire Robot into `RECONCILIATION_REQUIRED`;
- partial fill, ambiguous execution evidence or uncertain ownership immediately escalates to exposure-grade handling.

This directly addresses the EDGEUSDT failure class while preserving KSMUSDT safety.

**Slice D — only if metrics still show sustained backlog.**

Reserve capacity for exposure/protection work so pre-entry traffic cannot starve it. If still needed, use small
per-symbol bounded admission/fair scheduling behind the same single mutation owner. Preserve exact ordered
protection events and never silently coalesce a possible STOP/TAKE crossing.

Do not add a second trading engine, second WebSocket stack, general message bus, multi-process executor, Kafka,
Redis, Aeron or Disruptor for this problem unless later evidence proves the current single-owner model cannot meet
the required rate.

### 22.5 Rejected shortcuts

Do not use as the primary fix:

- only raising `protection_ingress_capacity`;
- silent latest-only coalescing;
- automatically clearing `RECONCILIATION_REQUIRED` after emergency close;
- removing entry LIMIT event handling without a replacement correctness contract;
- broad reconnect/restart on every overflow;
- moving SQLite mutation off the single owner before cheaper hot-path work is measured and removed.

### 22.6 Separate accounting defect

The GIGGLEUSDT fee issue remains independent. The focused fix is to correlate Robot-owned entry execution fee(s)
plus the proven close execution fee, store that lifecycle total in `fees_costs_usdt`, and recompute the frozen
fee-inclusive `realized_pnl_pct`. Never aggregate all executions for a symbol because manual/unrelated fills must
not contaminate Robot economics.

