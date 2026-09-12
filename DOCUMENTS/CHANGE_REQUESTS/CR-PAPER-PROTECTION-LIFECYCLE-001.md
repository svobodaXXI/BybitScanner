# CR-PAPER-PROTECTION-LIFECYCLE-001 — Autonomous PAPER Protection Execution Lifecycle

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-PAPER-PROTECTION-LIFECYCLE-001",
  "title": "Autonomous PAPER Protection Execution Lifecycle",
  "status": "AWAITING_APPROVAL",
  "revision": "1.0",
  "lifecycle_stage": "CONTEXT",
  "objective": "Specify D2 correction: autonomous event-driven PAPER protection, durable crossing obligations, restart-safe serialized closing and evidence-based Robot trade finalization, independent of UI and entry admission.",
  "non_goals": [
    "Runtime/source/test/schema implementation in this documentation task",
    "Changes to structural STOP/TAKE strategy, sizing, wedge strategy or LIVE",
    "BSBUSDT D1 invalid structural STOP / partial-fill recovery",
    "Invented historical replay or fill prices"
  ],
  "approved_scope": [
    "TASK/SPEC/CONTEXT documentation in this single owning CR",
    "Record user-required invariants, investigation evidence, primary-source references, target responsibilities and acceptance"
  ],
  "prohibited_scope": [
    "Runtime/source/test/schema changes before separately approved IMPLEMENT",
    "Unrelated/user-owned file changes, commit or push",
    "Adding OPEN to RobotBreakoutMonitor entry advancement",
    "Changing D1 recovery or strategy"
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
    "Documentation only; IMPLEMENT not authorized",
    "Protection ownership follows exposure independently of UI, selected account/symbol and Robot entry state",
    "Preserve LONG bid <= STOP / bid >= TAKE; SHORT ask >= STOP / ask <= TAKE",
    "Latch first confirmed crossing durably before execution; retreat cannot cancel it",
    "Reuse MarketDataHub, serialized runtime, PAPER executor and shared accounting",
    "Duplicate events, ambiguity and restart cannot lose committed obligations or duplicate close effects",
    "Actual execution evidence proves fill economics and FLAT; Robot closure is idempotent",
    "Unobserved downtime-only crossings are a separate semantic decision; no fabricated historical execution"
  ],
  "unresolved_decisions": [
    "Approve proposed detailed lifecycle and choose exact durable schema plus atomic dispatch/correlation API before IMPLEMENT",
    "Freeze event admission/backpressure, maximum healthy processing latency and ingress-to-durability crash handling",
    "Prove position lifecycle/controller and execution-to-trade attribution; freeze percentage-PnL denominator and fee allocation against owning accounting semantics"
  ],
  "acceptance_criteria": [
    "All section 14 invariants hold",
    "All mandatory scenarios T01-T20 and boundary cases in section 16 pass at actual shared execution/persistence boundaries",
    "No UI, fresh-candle, admission-state or selected-account dependency in protection execution",
    "Correlated actual fill -> FLAT -> cleanup -> Robot trade CLOSED evidence"
  ],
  "verification_requirements": [
    "Documentation: standalone CR validation, protected task finish and exact-scope user-owned-work guard",
    "Future IMPLEMENT: focused scheduling/trigger/persistence/account/restart integration tests",
    "Future acceptance: isolated PAPER runtime with browser closed, different symbol and MAINNET UI selection",
    "No historical tests or document validation establish runtime acceptance"
  ],
  "risks": [
    "Lossy latest-book coalescing loses transient crossing evidence",
    "Current path has no durable trigger obligation or production Robot close callback",
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
      "status": "DETAILS_DRAFT_FOR_REVIEW"
    },
    {
      "id": "CONTEXT",
      "status": "INVESTIGATION_RECORDED_WITH_GAPS"
    },
    {
      "id": "IMPLEMENT",
      "status": "NOT_AUTHORIZED_NOT_STARTED"
    },
    {
      "id": "VERIFY",
      "status": "RUNTIME_NOT_STARTED"
    },
    {
      "id": "RECORD",
      "status": "GIT_CHECKPOINT_NOT_AUTHORIZED"
    }
  ],
  "current_phase": "CONTEXT",
  "current_checkpoint": "D2_SPEC_CONTEXT_DOCUMENTED_FOR_REVIEW",
  "implementation_status": "NOT_IMPLEMENTED",
  "next_phase": "IMPLEMENT",
  "next_phase_authorization": "NONE; resolve design gates and obtain separate explicit approval",
  "related_commits": [
    {
      "phase": "AUTHORITATIVE_BASELINE",
      "commit": "14f9b514966fd89d0cb6ebe178a6ece0501ffb56"
    }
  ],
  "amendment_history": [
    {
      "revision": "1.0",
      "date": "2026-09-13",
      "reason": "User-authorized D2 TASK/SPEC/CONTEXT capture; no runtime or Git-write authorization"
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

Date: 2026-09-13 (Europe/Moscow).
Baseline branch: `robot-v0-1-admission-gate`.
Baseline HEAD: `14f9b514966fd89d0cb6ebe178a6ece0501ffb56`.

**DOCUMENTATION ONLY. IMPLEMENT NOT AUTHORIZED.** User requirements are binding; the detailed
mechanisms below are proposed design for review, not claims of deployed capability.

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

This document owns D2 TASK/SPEC/CONTEXT. D2 acceptance and the current required implementation scope
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
- Runtime, source, tests or schema edits now; commits/pushes without separate authorization.

## 4. Current architecture

```text
Selected Workspace L2 -> update consumer -> serialized owner queue
 -> process_orderbook_update (active READY PAPER account required)
 -> _match_symbol: LIMIT matching, then protection predicates
 -> PaperMarketExecutor -> ExecutionEngine -> SQLite execution/projection
 -> FLAT + PnL/fees + protection cleanup
 -> [missing production Robot trade finalizer]

APPROVED Robot retest -> match_resting_orders -> robot_match_symbol
 -> selected book or REST fallback -> same _match_symbol
```

`mutate_paper_protection_leg()` stores confirmed_active prices, not worker readiness.
`robot_match_symbol()` bypasses UI account/symbol selection, but its monitor caller selects only
APPROVED. Trade creation promotes the candidate to OPEN and ends this coverage route. Workspace
switching detaches the previous consumer and changes the provider's single selected buffer.
Queued updates are coalesced and matching reads the latest book. `close_robot_trade()` has persistence
implementation but no production caller after the protection-trigger execution.

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
- realized_pnl_pct: existing owning convention, with denominator and gross/net treatment frozen
  before IMPLEMENT rather than guessed here.

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

Now: CR documentation and validation only; incident-position repair is not authorized.
Before IMPLEMENT: resolve metadata design gates, freeze exact paths/schema/transactions, record an
approved amendment and pass applicable harness/governance gates. Prior closed monitor CR does not
authorize this scope.

Future sequence: focused integration -> isolated PAPER restart/crash proof -> runtime acceptance
(browser absent, different symbol, MAINNET UI selection) -> evidence review -> authorized rollout.
Use isolated PAPER storage for fault injection; never reset active user trades. Upgrade discovers
existing positions/protection without entry replay or historical fabrication. Establish compatibility
and recovery readiness before admitting new risk.

Rollback preserves obligations, identities and executions. Do not downgrade to a reader that cannot
recover pending obligations while exposure survives. Drain/reconcile or use an approved compatible
rollback; do not delete economic evidence. No runtime acceptance is claimed by document checks.

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

## 20. Expected future IMPLEMENT surface

Candidates for later exact scope, not present edit authorization:

| Module | Responsibility |
| --- | --- |
| terminal/runtime/paper_runtime.py | Coverage activation, matcher, serialized closing |
| terminal/runtime/paper_http_server.py | Provider/queue integration and independent consumers |
| terminal/market_data/hub.py | Autonomous interests and reconnect coverage |
| terminal/market_data/workspace_controller.py | Only if needed to preserve protection interest |
| terminal/persistence/sqlite_store.py | Trigger/dispatch durability, recovery queries and finalization |
| terminal/persistence/schema.py | Only approved migration required by selected design |
| terminal/application/execution_engine.py | Execution correlation/finalization integration |
| terminal/paper/executor.py | Minimal shared identity/result integration; preserve economics |
| terminal/application/robot_recovery.py | Recovery/finalization without entry replay |
| terminal/application/robot_breakout_monitor.py | Handoff only if needed; no OPEN entry filtering |
| Existing protection/runtime/persistence/Robot tests | Matrix and fault-injection evidence |

New modules/classes require responsibility-based justification. No name-driven supervisor class,
separate OS process, second market feed or second trading engine is prescribed.
