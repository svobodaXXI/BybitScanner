# CR-TRADING-WORKSPACE-001 — Trading Workspace v1 / Manual Live Trading

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-TRADING-WORKSPACE-001",
  "title": "Trading Workspace v1 / Manual Live Trading",
  "status": "IN_PROGRESS",
  "revision": "1.6",
  "lifecycle_stage": "CONTEXT",
  "objective": "Specify a deployment-neutral local-first Trading Workspace v1 for safe manual live trading on the user's real Bybit account without authorizing implementation.",
  "non_goals": [
    "Implement production code, tests, dependencies or runtime behavior in this checkpoint",
    "Implement autonomous Trading Robot behavior or AUTOPILOT",
    "Make Paper Trader the first implementation priority",
    "Couple Terminal availability to Scanner runtime",
    "Treat chart, UI acknowledgement or local expected state as authoritative exchange truth",
    "Change Scanner detection, Signal admission, Telegram delivery or trading behavior"
  ],
  "approved_scope": [
    "Record the Manual Live Trading v1 product, UX, safety and architecture specification",
    "Define subsystem boundaries among BybitScanner, Trading Terminal and Trading Robot",
    "Define durable signal deep-link and SignalSnapshot requirements",
    "Define shared chart-engine, market entry, order overlay, SL/TP, close cleanup and reconciliation requirements",
    "Define Working Volume as exactly five percent of own account equity before leverage",
    "Reserve future robot observation and manual-control transfer compatibility without implementing it",
    "Prepare later human review and explicit implementation authorization"
  ],
  "prohibited_scope": [
    "Production or test implementation",
    "Bybit order placement or account mutation",
    "Scanner, detector, Geometry, Signal admission or Telegram runtime changes",
    "Trading Robot implementation",
    "AUTOPILOT enablement",
    "Speculative dependency installation",
    "Commit or push before explicit user approval"
  ],
  "authoritative_references": [
    "AGENTS.md#Task-and-change-routing",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
    "DOCUMENTS/ROADMAP.md#CR-TRADING-WORKSPACE-001",
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md"
  ],
  "context_scope_paths": [
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md",
    "DOCUMENTS/PROJECT_CONTRACTS.md",
    "DOCUMENTS/ASSISTANT_PROTOCOL.md"
    ,"main.py"
    ,"bybit_api.py"
    ,"telegram_bot.py"
    ,"notification.py"
    ,"signal_adapter.py"
    ,"signal_memory.py"
    ,"contracts/signal_contract.py"
    ,"analyzer/core.py"
    ,"analyzer/charts.py"
    ,"chart.py"
    ,"chart_clean.py"
    ,"requirements.txt"
  ],
  "context_test_paths": [
    "tests/test_change_request_governance.py",
    "tests/test_context_dump_governance.py",
    "tests/test_codex_workflow_governance.py"
  ],
  "context_excerpt_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
    "DOCUMENTS/ROADMAP.md#CR-TRADING-WORKSPACE-001"
  ],
  "approved_decisions": [
    "BybitScanner, Trading Terminal and Trading Robot are independent top-level subsystems",
    "Manual live trading on the user's real Bybit account is the first Trading Workspace implementation priority",
    "Terminal remains usable when Scanner is stopped and is local-first but deployment-neutral for later VPS operation",
    "Telegram is the primary entry point and old signal deep links resolve durable SignalSnapshot history indefinitely",
    "Terminal and Signal Editor share one reusable chart engine",
    "Working Volume is exactly five percent or one twentieth of own account equity before leverage",
    "Bybit-confirmed state controls active visual state and execution feedback",
    "Full position close includes confirmed market close, ticker-wide order and protection cleanup, and reconciliation before success",
    "Semi-transparent means not confirmed by Bybit in the displayed state; opaque means exchange-confirmed",
    "Future MANUAL versus ROBOT ownership and TAKE_MANUAL_CONTROL compatibility is reserved but robot behavior is excluded from v1"
    ,"Working Volume is independent of leverage: one WV is exactly five percent of real USDT equity and leverage never multiplies the intended WV-based position size"
    ,"Position ownership is explicit as MANUAL or ROBOT and only one controller has normal mutation authority at a time"
    ,"AUTOPILOT conceptually transfers one eligible position from MANUAL to ROBOT ownership while preserving human observation and Close Position override"
    ,"Human takeover transfers ROBOT ownership back to MANUAL only after robot mutation is stopped and current Bybit state is reconciled"
    ,"Active Positions has separate MANUAL and AUTOPILOT sections with ownership-scoped individual and bulk close operations"
    ,"Immutable entry origin and entry reason are distinct from mutable current controller ownership"
    ,"Human-opened trades retain MANUAL origin and MANUAL_ENTRY or Ручной вход reason through any AUTOPILOT handoff or human takeover; Terminal and Robot do not infer a different human motive after entry"
    ,"Future Robot-opened trades use ROBOT origin and may preserve a structured Robot entry reason defined by later Strategy or Robot design"
    ,"The compact engaged Working Volume indicator provides desktop hover and touch interaction details for actual USDT volume, reference one-WV value and displayed WV count without becoming accounting truth"
    ,"AUTOPILOT live workspace exposes a Trading Results page with back navigation that does not mutate ownership or trading state"
    ,"AUTOPILOT results support DAY, WEEK, MONTH and YEAR periods and durable closed-trade analytics"
    ,"Selected-period results include closed, profitable and losing trade counts, realized USDT PnL, current equity, current open AUTOPILOT position count and aggregate actual AUTOPILOT USDT position volume"
    ,"Profitable and losing counts expose a pattern plus entry-reason breakdown sorted by trade count descending"
    ,"Analytics distinguishes Robot entries from manual entries later managed by AUTOPILOT while preserving immutable entry provenance"
    ,"Presentation analytics derive from durable authoritative trading and account data, never rounded WV display, Telegram messages, chart objects or current Scanner state"
    ,"The Scanner Telegram bot provides a visible unified Menu entry for Terminal, Trading Results, AUTOPILOT and Run Scanner navigation"
    ,"Menu Terminal entry opens an independently usable Manual Terminal without requiring signal_id or SignalSnapshot while preserving signal-specific deep links"
    ,"Menu Trading Results and AUTOPILOT entries route to their approved workspaces without transferring state ownership to the bot"
    ,"Run Scanner crosses a Scanner Control command boundary such as RUN_SCAN; Scanner owns execution and Telegram does not couple to main.py internals"
    ,"Scanner Control prevents incompatible duplicate concurrent runs and reports accepted or started, already running, completed and failed outcomes"
    ,"Telegram menu, deep-link and command knowledge never grants trading or Scanner-control authority without the researched authorization boundary"
    ,"Terminal provides account-profile management and clearly identifies the active Bybit trading account and its current USDT deposit or equity value"
    ,"Trading state, reconciliation, analytics and future Robot state are isolated by trading account; account switching disables mutations until selected-account loading and reconciliation complete"
    ,"One Working Volume is account-scoped, leverage-independent and equals five percent of the applicable USDT deposit or equity rounded down to the nearest ten USDT"
    ,"Future Robot-controlled aggregate exposure is limited to nineteen Working Volumes per trading account, excluding MANUAL-controlled exposure unless a later approved policy changes that boundary"
    ,"Trading Results reports selected-period realized PnL in both USDT and percentage of a defined period deposit or equity reference without treating external cash flows as trading performance"
    ,"Trading credentials belong only to the Terminal backend security boundary; API Secret is never returned to the frontend or stored in Scanner, chart, Telegram or frontend-readable durable state"
  ],
  "unresolved_decisions": [
    "Final adoption and version constraints for the researched KLineChart, FastAPI and SQLite/WAL directions after implementation planning and prototype evidence",
    "Authentication, authorization, Bybit credential custody and Telegram Mini App session security",
    "Exact supported-account and position-mode compatibility and setup prerequisites for the preferred Hedge Mode direction within USDT Linear Perpetual scope",
    "Exact exchange reconciliation state machines, timeout policies, idempotency identifiers and orderLinkId mapping",
    "Human-approved finalization of USDT walletBalance as the WV base, plus refresh timing, sub-ten-USDT behavior and insufficient-volume handling",
    "Exact active-order modification interaction and amend versus cancel-replace policy",
    "SignalSnapshot schema, target-method taxonomy, retention, migrations and deep-link routing",
    "Shared chart-engine selection and saved drawing schema",
    "Sound assets, delivery mechanism and user configuration",
    "Local deployment topology and later VPS migration boundary"
    ,"Final names and transition rules for MANUAL_CONTROLLED, ROBOT_CONTROLLED, TAKEOVER_PENDING, CLOSING and RECONCILING conceptual states"
    ,"Exact persisted field names and schema for immutable entry origin and entry reason"
    ,"DAY, WEEK, MONTH and YEAR calendar boundaries and timezone semantics"
    ,"Closed-trade analytics schema, ownership-history representation and aggregation strategy"
    ,"Whether initial analytics UI exposes optional provenance filters for all AUTOPILOT-managed, Robot-entry and manual-entry-handoff trades"
    ,"Exact Telegram Menu button layout and Bot API, Mini App or command mechanism"
    ,"Scanner Control IPC/API/process transport, command identity, concurrency lock and completion correlation"
    ,"Exact Telegram allowlist, session and authorization checks for Terminal, AUTOPILOT and Scanner control"
    ,"Encrypted credential-storage, key rotation, validation diagnostics and trading-account profile lifecycle design"
    ,"Authoritative USDT deposit or equity definition, refresh timing and account-switch reconciliation state machine"
    ,"Working Volume behavior below the ten-USDT rounding quantum and its interaction with exchange minimum quantity and insufficient balance"
    ,"Concurrency and exposure reservation semantics for simultaneous future Robot commands and ownership handoffs near the nineteen-WV limit"
    ,"Selected-period percentage-PnL accounting for deposits, withdrawals, transfers, equity changes, period boundaries and timezone"
  ],
  "researched_architecture_directions": [
    "Authenticated Bybit V5 REST commands are correlated with private order, execution, position and wallet events; REST acceptance alone is not final state confirmation",
    "Uncertain commands, startup, reconnect and full-close workflows reconcile authoritative exchange state instead of blind retry",
    "Telegram Mini App deep-link references identify durable SignalSnapshot records but authorization requires backend validation of raw initData, freshness and allowed numeric Telegram user identity",
    "SignalSnapshot is immutable versioned historical Scanner evidence and never owns trading, protection, PnL, controller or Robot state",
    "KLineChart is the preferred researched v1 interactive renderer behind a shared chart contract and adapter; current Matplotlib/mplfinance remains the separate static Scanner report path",
    "Python with FastAPI is the preferred Terminal HTTP and WebSocket application boundary; frontend and Telegram Mini App are clients, never trading-state authority",
    "SQLite in WAL mode is the preferred local-first v1 persistence direction behind a replaceable storage boundary",
    "Durable exchange and backend event journal evidence remains distinct from mutable operational projections",
    "Trading mutations remain locked through startup, reconnect, account switch and uncertainty until credentials, streams, REST snapshots, commands, ownership and exchange state reconcile",
    "CredentialStore abstracts protected local Windows credential storage such as DPAPI or Credential Manager so later VPS deployment can replace the implementation without changing domain contracts",
    "Percentage return requires cash-flow-adjusted or time-weighted direction and sufficient valuation and cash-flow history; exact formula and fee, funding, transfer and timezone policy remain open",
    "Scanner Control is a single-flight application boundary around RUN_SCAN and may reuse the existing approved-pattern count without coupling Telegram to main.py internals",
    "Local-first deployment still requires an HTTPS-reachable Mini App boundary; raw public exposure of a development FastAPI port is not the intended architecture"
    ,"Terminal v1 remains scoped to Bybit USDT Linear Perpetual and is position-mode aware; Hedge Mode is preferred because independent LONG and SHORT operations may coexist, while Terminal never silently changes exchange position mode"
    ,"Asynchronous mutations follow command, REST acknowledgement, pending, private-event or reconciliation confirmation; semi-transparent remains unconfirmed and opaque remains exchange-confirmed"
    ,"Confirmed fills are deduplicated by durable execution identity such as execId and correlated through orderId or orderLinkId so duplicate, late or racing events cannot double-count quantity, PnL, analytics, sounds or markers"
    ,"Current position projection is keyed by trading account, symbol and relevant side or positionIdx identity; a position stream event is reconciled state input, not proof of a distinct economic trade"
    ,"Close Position is a multi-step reducing, observation, cleanup and REST-reconciliation workflow ending only at position zero with required symbol orders and protection removed"
    ,"Private WebSocket is realtime transport rather than durable truth; startup, reconnect and uncertain mutations use required REST positions, open orders, histories, executions and wallet/account state before streams resume synchronization"
    ,"A durable local TradingCommand correlation identity is persisted before or transactionally with submission; timeout-after-submit reconciles the original order before any exposure-increasing retry"
    ,"USDT walletBalance is the preferred researched WV base because it represents the account's own USDT funds without leverage, available-balance buying power, non-USDT valuation or direct unrealized-PnL expansion; approved SPEC change requires separate human authority if needed"
    ,"WV sizing converts selected WV to target USDT and then floors instrument quantity to authoritative qtyStep while validating minOrderQty, minNotionalValue and maximum constraints without increasing requested exposure"
    ,"Insufficient normalized volume is a pre-submit business rejection REJECTED_INSUFFICIENT_VOLUME with user feedback Недостаточный объём; Terminal and future Robot never auto-increase exposure to satisfy exchange minima"
    ,"Limit and protection draft prices use authoritative tickSize normalization visible before confirmation; safe rounding direction remains order-specific design work"
    ,"Market WV is sizing intent rather than guaranteed fill size; actual engaged USDT and fractional WV display derive from confirmed executions and reconciled position state"
  ],
  "repository_confirmed_reuse": [
    "bybit_api.py and analyzer candle loading provide reusable public USDT-linear instrument and OHLCV access only behind a market-data boundary; they are not authenticated trading infrastructure",
    "CONTRACT-SIGNAL-001 and signal.filter own final approved admission, while main.py already counts approved_pattern_count independently of Telegram delivery",
    "telegram_bot.py provides outbound text, photo and inline-keyboard transport that may be reused without owning authentication, Scanner control or trading state",
    "contracts/signal_contract.py, analyzer results and geometry output provide source evidence from which a future versioned SignalSnapshot mapper may be designed, but current signal_memory.py is mutable symbol-keyed history and is not SignalSnapshot persistence",
    "chart.py, chart_clean.py and analyzer/charts.py form the existing static Matplotlib/mplfinance PNG report path and remain separate from the interactive Terminal renderer",
    "Current requirements include pybit and websocket-client but no authenticated Terminal client, FastAPI application, KLineChart frontend or SQLite trading store is implemented",
    "No current order, execution, position, protection, TradingCommand, ExchangeEventJournal, account-isolation or reconciliation domain implementation exists"
  ],
  "context_decisions_required_before_implementation_plan": [
    "Exact Hedge Mode and supported-account prerequisites, positionIdx handling, category/order capabilities, full-position TP/SL compatibility, identifier rules and authoritative reconciliation matrices",
    "Command, order, execution, position, protection and ownership lifecycle schemas including duplicate, race, gap and uncertain-result handling",
    "Versioned SignalSnapshot schema, immutable retention, migrations, target metadata and deep-link resolution",
    "Telegram backend authentication validation, freshness window, allowlist, session lifetime and authorization matrix",
    "Shared chart contract and KLineChart feasibility prototype criteria without coupling domain state to renderer APIs",
    "Terminal backend process topology, backend-to-frontend event protocol and local HTTPS ingress decision",
    "SQLite/WAL schema, transaction boundaries, journal/projection rebuild rules, backup and later storage migration boundary",
    "CredentialStore threat model, protected Windows implementation choice, secret rotation/removal and VPS replacement contract",
    "Human-approved final WV-base decision after the preferred USDT walletBalance finding, refresh timing, Market versus Limit sizing-price semantics, sub-ten-USDT behavior and exchange precision/minimum constraints",
    "Cash-flow-adjusted return, fees, funding, valuation snapshots, period boundaries and timezone accounting",
    "Scanner Control command identity, single-flight ownership, process boundary, status correlation and safe errors",
    "Implementation phase decomposition, acceptance tests, dependency approvals and explicit human IMPLEMENT authorization"
  ],
  "acceptance_criteria": [
    "All Manual Live Trading v1 product and safety requirements are recorded in one owning durable ChangeRequest",
    "Subsystem independence and Scanner-off Terminal operation are explicit",
    "Durable old-signal deep links and historical-versus-current visual distinction are explicit",
    "Working Volume, market entry, Limit, SL/TP, close cleanup, overlays, fills and feedback semantics are explicit",
    "Exchange authority and reconciliation requirements prevent optimistic success claims",
    "Robot integration is reserved without entering v1 implementation scope",
    "Working Volume leverage independence, fractional display and active-position indicator semantics are explicit",
    "Exclusive controller ownership, AUTOPILOT handoff, human takeover and ownership-scoped close behavior are explicit",
    "Immutable entry provenance is separated from current controller and remains stable across ownership transfers",
    "Working Volume details, AUTOPILOT results navigation, period metrics, interactive breakdowns and durable analytics requirements are explicit",
    "Unified Scanner bot navigation, independent Terminal entry, analytics/AUTOPILOT routing and concurrency-safe Scanner Control requirements are explicit",
    "Trading-account management, active-account identification, account isolation and reconciled switching requirements are explicit",
    "Account-scoped rounded-down Working Volume, future per-account Robot exposure limit and account-aware analytics requirements are explicit",
    "Selected-period USDT and percentage PnL requirements and deferred external-cash-flow accounting decisions are explicit",
    "Trading credential custody and frontend, Scanner, chart and Telegram secret-exclusion boundaries are explicit",
    "Implementation remains not started and not authorized",
    "Only authoritative documentation changes in this checkpoint"
  ],
  "regression_requirements": [
    "No production or test files change",
    "Scanner, Geometry, Signal admission and Telegram runtime semantics remain unchanged",
    "CR-TRADING-INTELLIGENCE-001 remains research authority and is not repurposed as terminal implementation authority",
    "Unrelated dirty and untracked files remain untouched"
  ],
  "verification_requirements": [
    "ChangeRequest schema validation",
    "Durable workflow and ContextDump recovery validation",
    "Project State, Roadmap and ChangeRequest identity/revision/status consistency review",
    "Scoped documentation diff and git diff --check",
    "Git status review confirming unrelated work is untouched"
  ],
  "risks": [
    "Real-money loss from ambiguous intent, stale state, duplicate commands or optimistic UI",
    "Credential exposure or unauthorized Telegram/WebApp access",
    "Terminal and exchange state divergence",
    "Incorrect cleanup leaving active orders after position close",
    "Old signal context being confused with current market state",
    "Chart-engine duplication between Signal Editor and Terminal",
    "Local-only assumptions blocking later VPS deployment",
    "Premature robot coupling or AUTOPILOT exposure"
  ],
  "rollback_boundaries": [
    "This checkpoint changes only the new ChangeRequest and its Project State and Roadmap pointers",
    "Rollback removes the uncommitted specification checkpoint without runtime or exchange effects",
    "No implementation artifact, dependency, migration or account state exists"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED_HUMAN_AUTHORIZED"},
    {"id": "SPEC", "status": "REVISION_1_4_APPROVED_HUMAN_AUTHORIZED_DOCUMENTATION_CHECKPOINT_ONLY"},
    {"id": "CONTEXT", "status": "AUTHORIZED_RESEARCH_IN_PROGRESS_BYBIT_EXECUTION_AND_WV_INTERMEDIATE_CHECKPOINT_APPROVED_RECORDED"},
    {"id": "IMPLEMENT", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "VERIFY", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "RECORD", "status": "NOT_STARTED_NOT_AUTHORIZED"}
  ],
  "current_phase": "CONTEXT",
  "current_checkpoint": "MANUAL_LIVE_TRADING_V1_BYBIT_EXECUTION_RECONCILIATION_AND_WV_RESEARCH_INTERMEDIATE_CHECKPOINT_APPROVED_RECORDED",
  "implementation_status": "IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED",
  "next_phase": "IMPLEMENT",
  "next_phase_authorization": "IMPLEMENT_NOT_STARTED_NOT_AUTHORIZED_CONTEXT_RESEARCH_IN_PROGRESS",
  "related_commits": [
    {"phase": "BASELINE", "commit": "5b898963ef46bbd33771123ac169d7b8d52fc0e0"},
    {"phase": "SPEC_DOCUMENTATION_CHECKPOINT", "commit": "52f719351574d32aeb765fa833a27cc1e1bbbd25"},
    {"phase": "SPEC_REVISION_1_1_DOCUMENTATION_CHECKPOINT", "commit": "5e38b8a6df64e822e664de665701a53e76163fdd"},
    {"phase": "SPEC_REVISION_1_2_DOCUMENTATION_CHECKPOINT", "commit": "f8d0932afd9589998d09027477c67eb8ab7aa1a0"}
    ,{"phase": "SPEC_REVISION_1_3_DOCUMENTATION_CHECKPOINT", "commit": "3d0ba01895db0cd9c4fcd1670b06e46671d645a0"}
    ,{"phase": "SPEC_REVISION_1_4_DOCUMENTATION_CHECKPOINT", "commit": "aba84eeab539d329fc693728dc70bb38f7dee0cc"}
    ,{"phase": "CONTEXT_REVISION_1_5_INTERMEDIATE_RESEARCH_CHECKPOINT", "commit": "a70c99b1fb4a5e84847aab90d3d9dd3931340b29"}
  ],
  "repository_sync": {
    "branch": "main",
    "baseline_local_head": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "baseline_origin_main": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "latest_saved_checkpoint": "a70c99b1fb4a5e84847aab90d3d9dd3931340b29",
    "status": "INTERMEDIATE_CONTEXT_BYBIT_EXECUTION_AND_WV_RESEARCH_CHECKPOINT_APPROVED_FOR_COMMIT"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Recorded and human-approved the Trading Workspace v1 Manual Live Trading durable Task/Spec for documentation checkpoint commit only without CONTEXT or implementation authorization", "date": "2026-08-20"},
    {"revision": "1.1", "reason": "Human-approved documentation checkpoint recording leverage-independent Working Volume, immutable entry provenance, exclusive position ownership, future AUTOPILOT handoff, human takeover and ownership-scoped active-position operations without authorizing CONTEXT, external research or implementation", "date": "2026-08-21"},
    {"revision": "1.2", "reason": "Human-approved documentation checkpoint recording Working Volume detail interaction and AUTOPILOT trading-results, period metrics, provenance breakdown and durable analytics requirements while CONTEXT research remains in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.3", "reason": "Human-approved documentation checkpoint recording unified Scanner Telegram bot navigation and authorization-aware, concurrency-safe Scanner Control requirements while CONTEXT research remains in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.4", "reason": "Human-approved documentation checkpoint recording account management and isolation, refined account-scoped Working Volume, future per-account Robot exposure limit, percentage PnL and credential-security boundaries while CONTEXT research remains in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.5", "reason": "Human-approved intermediate durable CONTEXT architecture research checkpoint reconciling Bybit, Telegram, SignalSnapshot, chart, backend, persistence, recovery, security, analytics, Scanner Control and deployment directions with current repository boundaries; CONTEXT remains incomplete and in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.6", "reason": "Human-approved intermediate durable CONTEXT checkpoint refining Bybit position mode, asynchronous confirmation, execution deduplication, close and recovery reconciliation, command correlation, preferred WV walletBalance base and exchange quantity/price normalization while CONTEXT remains incomplete and IMPLEMENT remains unauthorized", "date": "2026-08-21"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## 1. Product and deployment boundary

BybitScanner detects opportunities and signals; it is neither Terminal nor Robot. Trading Terminal is
the operator's unified manual trading and monitoring workspace. Trading Robot remains independent and
is excluded from v1. Terminal must work with Scanner stopped and initially runs locally. Business logic
must remain deployment-neutral so Scanner, trading backend, persistence, Telegram/Mini App and trading
services can later move to a 24/7 VPS. Future Telegram Scanner START/STOP/RESTART/STATUS controls are
reserved; Terminal availability must not depend on Scanner state.

The first deliverable is usable manual live trading on the user's real Bybit account. Paper Trader and
autonomous robot execution are later. `AUTOPILOT` is visible near the top market context but disabled in v1.

## 2. Telegram deep links and durable signal context

Telegram is the primary Terminal entry. Scanner signal posts expose `Open in terminal`. Every signal has
a durable `signal_id` and `SignalSnapshot`; old links remain valid independently of Scanner restart,
runtime state or age. Opening one restores original geometry, context, target and potential alongside
the current market, with historical and current state visually distinct. A trade opened from an old
signal is a new current trade linked by `source_signal_id`.

SignalSnapshot preserves target value, calculation method, metadata, exactness/approximation and original
potential percent. Terminal shows the original potential and current remaining potential. Geometric
projection is labelled approximate unless the pattern method supports a more exact target; it is never
presented as guaranteed precision.

## 3. Shared chart workspace

Terminal and Signal Editor use the same reusable chart engine, not separate implementations. Required
capabilities are TradingView-like mobile pinch zoom, pan, price/time scale compression and expansion,
candles, volume, crosshair, magnet, diagonal/trend and horizontal lines, Fibonacci retracement/extension,
saved/restorable market-coordinate drawings, Scanner geometry and interactive trading overlays.

Above the chart: symbol selector, adjacent timeframe selector, prominent live price with movement color,
and disabled v1 AUTOPILOT. Symbol changes occur inside Terminal. All other trading controls are below chart.

## 4. Working Volume and market actions

Canonical label is `Рабочий объём` / `Working Volume`: exactly 5% (1/20) of own account equity/deposit
before leverage. One WV is independent of leverage: leverage must not multiply Working Volume or the
intended WV-based position size. With 1,000 USDT real equity, 1 WV is 50 USDT, 2 WV is 100 USDT and
3 WV is 150 USDT. Future exchange/API leverage handling cannot redefine this product rule. Default
BUY/SELL and new Limits use one editable Working Volume.

Terminal displays a Working Volume indicator under or near the chart, conceptually crossed swords plus
a number such as `⚔ 2.4`. It represents WV actually engaged in the current position. Fractional WV is
displayed to one decimal place; underlying trading and accounting state is never rounded by this UI rule.
The compact indicator exposes details by hover on desktop and tap or equivalent touch interaction in a
Mini App. At minimum the detail shows actual engaged USDT position volume, current/reference value of
one WV in USDT and displayed WV count, for example `⚔ 2.4`, `Engaged: 120 USDT`, `1 WV: 50 USDT`.

BUY immediately submits a real market LONG; SELL submits a real market SHORT. Fill confirmation comes
from Bybit state, not button press. `Close position by market` closes 100% for the current ticker.

Full-close success requires: confirmed 100% market close; cancellation of all remaining LONG and SHORT
Limits for the ticker; cancellation of remaining SL/TP; and reconciliation until position is zero and
applicable active orders are zero. Failure exposes remaining orders/errors and never claims full cleanup.

## 5. Limit orders

LONG and SHORT Limits have separate vertically arranged collapsible rows (`LONG LIMITS — N`,
`SHORT LIMITS — N`), each with cancel-all-direction action and expandable individual orders. Creating a
Limit opens an editable price/Working Volume card. Green circular confirm submits; only after Bybit
confirmation does it become a red cancel X. Confirmed cards retain price/volume. Cancellation removes
exchange and visual state only after confirmed cancellation/reconciliation.

## 6. Stop Loss and Take Profit

STOP and TAKE are separate, clear vertical controls below chart. Inactive controls allow creation.
STOP starts as a draggable semi-transparent red draft around 12% on the protective side of current price;
the exact price card and line synchronize bidirectionally. Green confirm submits. After Bybit confirms,
the line becomes opaque, confirm becomes red cancel X, and the active card has a strong red border.

TAKE follows the same lifecycle with green styling. From a Scanner signal its initial draft uses the
signal target/potential. It is immediately draggable/editable; after confirmation the card has a strong
green border and the confirm becomes cancel X.

## 7. Overlay interaction and exchange confirmation

Limit is thin solid: LONG green, SHORT red, with compact right price label. SL is red dashed with `SL`
label; TP is green dashed with `TP` label. Draft, pending or modifying state is semi-transparent;
exchange-confirmed state is opaque.

Selecting a right-side label reveals a red X immediately to its right. Active real objects disappear
only after Bybit-confirmed cancellation/reconciliation. When dragging an active Limit/SL/TP, it becomes
semi-transparent and modification-pending; card price follows the line. It remains pending until exchange
confirmation. Rejection restores the last confirmed price/state and shows a concise error. Exact amend
submission timing/policy remains a later design decision and must not send unsafe pixel-level requests.

## 8. Fills, sounds and notifications

Actual fills are chart markers anchored to fill time/price: LONG is a green upward isosceles triangle;
SHORT is a red downward triangle. Multiple fills remain multiple markers. Later interaction may expose
fill details.

Confirmed execution-event hooks include `LONG_FILLED`, `SHORT_FILLED`, `STOP_FILLED`,
`TAKE_PROFIT_FILLED`, `POSITION_CLOSED`, and `ORDER_REJECTED`/`ERROR`. Distinct sounds and concise
notifications are driven by confirmed exchange events, never button press. Notifications include relevant
direction, symbol, volume, execution price and close/PnL data. Submitted/active order is distinct from
filled/executed trade.

## 9. State authority and future robot reservation

Chart/UI state is never exchange truth. Real order and position lifecycles reconcile chart objects,
local trading state and actual Bybit state; UI confirmation follows exchange confirmation.

Future Terminal may show robot positions, actions, statuses, concise comments and a separate technical
event log, and may support safe `TAKE_MANUAL_CONTROL`. Ownership must be able to distinguish `MANUAL`
and `ROBOT`; after takeover Robot must stop modifying that position. These are compatibility constraints,
not v1 robot implementation scope.

### 9.1 Exclusive position ownership and AUTOPILOT handoff

Every active trade/position has conceptual `MANUAL` or `ROBOT` ownership. Scanner, Terminal and Robot
remain independent, and only one controller may have normal mutation authority for a position at a time.

Every trade also preserves immutable entry provenance, conceptually `entry_origin`, separately from the
mutable current controller. Exact field naming belongs to later CONTEXT/architecture work. A human-opened
trade has origin `MANUAL` and entry reason `MANUAL_ENTRY` / `Ручной вход`. Terminal and Robot must not
retroactively infer or guess the human's real trading motive.

If that trade later transfers to AUTOPILOT, origin remains `MANUAL` and reason remains `MANUAL_ENTRY`;
only current controller becomes `ROBOT`. If the human later takes control back, controller returns to
`MANUAL` while origin remains unchanged. A Robot live view therefore may show:

* Entry origin: `MANUAL`;
* Entry reason: `Ручной вход`;
* Current controller: `ROBOT` / `AUTOPILOT`.

Future trades opened directly by Robot have origin `ROBOT` and may store a structured Robot reason such
as `BREAKOUT` or `RETEST`. The complete Robot reason taxonomy is deferred to future Strategy/Robot design.

For a future eligible trade, AUTOPILOT means `MANUAL → ROBOT`: the future Robot takes management control
of that specific trade. While ROBOT owns it, Terminal remains a live observation surface. Manual BUY,
SELL and order-management controls are hidden or disabled; Limit, SL and TP remain visible but cannot be
clicked or dragged. Human `Close Position` remains available. Live detail includes controller, symbol,
LONG/SHORT, pattern, entry reason such as BREAKOUT/RETEST, entry price, size, Working Volume indicator,
SL, TP and available state/PnL.

Robot implementation and autonomous decision logic remain outside Manual Live Trading v1. This contract
only prevents v1 architecture and UI state from making later ownership and observation impossible.

### 9.2 Human takeover and close arbitration

The inverse transition is `ROBOT → MANUAL`. Before manual controls return, Robot mutation authority must
stop and reconciliation must establish current exchange state. Ownership change alone must not recreate
existing exchange orders or protection. Architecture must prevent simultaneous Robot and human mutation.

Human Close Position is an override while ROBOT owns the trade. It must first fence Robot mutations/new
commands for the affected position, then execute the existing close, cleanup and reconciliation workflow
without racing Robot management.

### 9.3 Active trades / positions workspace

A navigation control available from Manual Terminal and AUTOPILOT live view opens Active Positions with
two independent collapsible sections:

* `MANUAL` — active MANUAL-owned positions;
* `AUTOPILOT` — active ROBOT-owned positions.

Each entry shows at least symbol, LONG/SHORT, entry price, current size, Working Volume display, live
state/PnL and applicable SL/TP. Selecting it opens its live Terminal/chart view. Every entry supports
individual Close Position.

Each section also owns a separate bulk action. `Close All MANUAL` affects only MANUAL positions;
`Close All AUTOPILOT` affects only ROBOT positions. Groups are never implicitly mixed. ROBOT-owned bulk
close first fences Robot mutation/new commands for affected positions. Every individual or bulk full
close retains ticker cleanup and reconciliation invariants: required Limits/SL/TP are removed and the
intended terminal state is proven before success.

Conceptual states sufficient for later design include `MANUAL_CONTROLLED`, `ROBOT_CONTROLLED`,
`TAKEOVER_PENDING`, `CLOSING` and `RECONCILING`. Names and transitions may be refined during later
authorized CONTEXT/architecture work; this revision does not implement a state machine.

## 10. AUTOPILOT trading results and durable analytics

AUTOPILOT live workspace provides a visible `Trading Results` / `Результаты торговли` navigation control,
preferably in the lower screen area. It opens a dedicated analytics page with normal back navigation to
the previous AUTOPILOT/live screen. Navigation must not change position ownership or trading state.

The results page supports at least `DAY`, `WEEK`, `MONTH` and `YEAR`. Period selection changes historical
metrics for that interval; exact calendar and timezone semantics are deferred to CONTEXT/architecture.
For the selected period it shows at least:

* total closed trades;
* profitable and losing trade counts;
* realized trading PnL in USDT;
* current total account deposit/equity;
* current open AUTOPILOT-controlled position count;
* current aggregate actual USDT position volume in AUTOPILOT-controlled positions.

Aggregate actual USDT volume is not replaced by Working Volume count. Profitable and losing counts are
interactive: desktop hover and touch/Mini App tap expose a breakdown by `pattern + entry_reason`, sorted
by trade count descending. The final Robot entry-reason taxonomy remains outside this amendment.

Analytics preserves immutable provenance. A human-created trade handed to AUTOPILOT remains
`entry_origin = MANUAL` and `entry_reason = MANUAL_ENTRY` / `Ручной вход`; AUTOPILOT management does not
rewrite it. The data model distinguishes Robot-entered trades from manual entries later managed by
AUTOPILOT. Future optional filters may expose all AUTOPILOT-managed trades, Robot entries and manual
entries handed to Robot, but the initial UI is not required to expose this filter.

Closed-trade history is durable across restart and retains enough information to reproduce period results:
symbol, direction, entry/close timestamps, entry origin/reason, applicable pattern, controller/ownership
history sufficient to establish AUTOPILOT management, realized USDT PnL, actual position volume and WV
context. Exact schema, tables and aggregation remain CONTEXT/architecture decisions.

Presentation derives from durable authoritative trading/account data. Rounded `⚔ N.N` is never an
accounting input. Historical results are never reconstructed from Telegram messages, chart objects or
current Scanner state.

Robot/autonomous trading remains out of scope. This section defines only Terminal/AUTOPILOT UX,
historical analytics and future-compatible data requirements.

## 11. Unified Scanner Telegram bot menu and Scanner Control

The existing Scanner Telegram bot exposes a visible `Меню` / `Menu` navigation entry with at least:

* `Терминал` / `Terminal`;
* `Статистика` / `Trading Results`;
* `Автопилот` / `AUTOPILOT`;
* `Запустить сканер` / `Run Scanner`.

Exact layout and Telegram UI mechanism are deferred to CONTEXT/UI design. Terminal entry opens Manual
Terminal without requiring a SignalSnapshot or `signal_id`, so Terminal remains independently usable
from Scanner signals and can later select a symbol, active position or other supported view. This does
not replace immutable signal deep links, which continue opening signal-specific Terminal context.

Statistics routes to the approved trading-results/analytics workspace and preserves period and analytics
contracts. AUTOPILOT routes to its workspace or controlled-positions view. Navigation may remain visible
in v1 while unsupported Robot actions are disabled; Robot implementation remains out of scope.

`Run Scanner` requests a new scan through a Scanner Control boundary, conceptually `RUN_SCAN`. Telegram
does not own Scanner internals or couple to `main.py`; Scanner owns execution. Exact IPC, API and process
transport are deferred to CONTEXT/architecture.

Scanner Control prevents accidental incompatible concurrent duplicate runs from repeated requests and
can report at least accepted/started, already running, completed and failed. A repeated command while a
scan is active must not silently start another scan. Telegram provides concise user feedback for these
outcomes; completed feedback includes approved/found pattern count when available.

Terminal, AUTOPILOT and Run Scanner entry points obey the researched Telegram/Terminal authorization
boundary. Possession of a menu or deep link alone grants neither trading nor Scanner-control authority.
Exact allowlist, session and authentication mechanism remains a CONTEXT decision.

Scanner, Terminal and Robot remain independent. The Scanner bot is only a navigation/control integration
surface and owns no Terminal trading state, Robot state, exchange orders/positions or trading analytics.

## 12. Trading accounts, account-scoped Working Volume and analytics

Terminal provides a compact trading-account control, conceptually `🔑`, which opens Trading Accounts.
The user can add a Bybit account profile, assign a human-readable name, submit API Key and API Secret,
validate credentials and connectivity, view sufficient non-secret validated key/account diagnostics,
switch saved accounts and remove a profile. Exact credential storage is deferred to CONTEXT/security
architecture. The active account is clearly visible using the consistent product convention
`🔑 Основной = 2 000 USDT`, where the value is the relevant current USDT deposit/equity under the final
CONTEXT accounting definition.

Every wallet/equity, Working Volume, position, order, execution, trade, protection, journal,
reconciliation, analytics and future Robot/AUTOPILOT state object belongs to one trading-account context.
State from different accounts must never be mixed. During account switching, trading mutations are
disabled; the selected account state is loaded and reconciled with Bybit before LIVE controls are enabled.
Exact switching state-machine names remain a CONTEXT decision.

Working Volume remains independent of leverage and is calculated separately for the relevant account:

`raw_1_WV = USDT_deposit × 5%`

`1_WV = floor(raw_1_WV / 10) × 10 USDT`

Thus deposits of 2,000, 2,150, 3,780 and 9,999 USDT yield respectively 100, 100, 180 and 490 USDT per
WV. Leverage never multiplies or otherwise alters WV. The authoritative meaning of the calculation-base
USDT deposit/equity remains a CONTEXT/accounting decision. The approved `⚔ N.N` position display and its
popover remain: actual engaged USDT volume, current/reference 1-WV value and displayed WV count. Its
one-decimal rounding is presentation-only and never accounting truth.

Future Robot/AUTOPILOT has a per-account risk invariant:
`ROBOT_EXPOSURE_LIMIT = 19 WV per trading account`. Aggregate actual exposure across ROBOT-controlled
positions must not knowingly exceed that limit. If 17.5 WV is already controlled, no more than 1.5 WV
may be added. MANUAL-controlled positions are excluded unless a later approved risk policy changes that
rule. Handoff and takeover preserve exposure accounting; simultaneous-command reservation semantics are
deferred to future architecture/Robot design. Robot implementation remains outside Manual Live Trading v1.

For DAY, WEEK, MONTH and YEAR, Trading Results reports realized PnL in USDT and as a percentage of a
defined deposit/equity reference appropriate to the selected period, conceptually the period-opening
account deposit/equity. The percentage is never derived from rounded WV display. CONTEXT must define
deposit, withdrawal, transfer, equity-change, period-boundary and timezone accounting so external cash
flows do not appear as trading PnL; this SPEC does not invent a mid-period cash-flow formula.

Analytics is account-aware: one account's statistics never silently include another account. Future
cross-account portfolio analytics must be explicit. API Secret is not exposed back to the frontend after
submission; Mini App/frontend is not a durable secret store; Scanner, chart state and Telegram messages
never own trading credentials. Credentials belong to the Terminal backend/security boundary, with exact
encrypted storage deferred to CONTEXT.

## 13. CONTEXT architecture research record

### A. Approved SPEC requirements preserved

Revision 1.4 remains the approved product authority. Working Volume is account-scoped and independent
of leverage: `raw_1_WV = USDT_deposit × 5%`, then
`1_WV = floor(raw_1_WV / 10) × 10 USDT`. Leverage never multiplies WV; `⚔ N.N` is one-decimal
presentation only and actual USDT state is authoritative. Account isolation, immutable entry provenance,
exclusive MANUAL/ROBOT control, human close override, the future 19-WV per-account Robot limit and the
current exclusion of MANUAL exposure from that Robot-specific limit are unchanged. Robot remains out of
scope. Scanner, Terminal and Robot remain independent, and Terminal works with or without `signal_id`.

### B. Researched architecture directions

#### Bybit execution and recovery

Terminal uses authenticated Bybit V5 REST together with private order, execution, position and
wallet/account streams. REST create, amend or cancel acceptance is not final trading-state confirmation.
One order may produce multiple fills; duplicates, races and event ordering cannot be assumed away.
Commands require client correlation and idempotency, using an identity such as `orderLinkId` where the
final supported Bybit contract permits. An uncertain submit, amend or cancel result enters reconciliation,
not blind retry. Startup, reconnect, uncertain commands and Close Position all require REST snapshots and
reconciliation against exchange state.

Exchange execution events drive confirmed fill semantics, notifications and sounds. Exchange-side
full-position TP/SL is the preferred v1 protection direction where final Bybit capability and account-mode
constraints permit. Full close is a workflow whose success invariant is position zero, required remaining
symbol orders removed, required SL/TP/protection removed, and local/exchange state reconciled. REST
acceptance alone cannot claim this invariant.

The operational gate is conceptually `STARTING → credential/account validation → connectivity → private
stream → REST wallet/order/position snapshots → uncertain-command recovery → ownership/state verification
→ SYNCHRONIZED → TRADING_ENABLED`. If authoritative state cannot be established, state is
`TRADING_LOCKED`; mutations remain disabled during critical uncertainty or incomplete reconciliation.
Exact state names remain design-level. Loss of Terminal connectivity must not intentionally remove
exchange-side protective SL/TP.

#### Telegram, SignalSnapshot and authorization

Scanner signal messages may open Terminal using a Telegram Mini App deep link whose start parameter
references a durable signal. That reference is not authorization. Terminal backend validates raw Telegram
WebApp `initData`, checks freshness and enforces an allowed numeric Telegram user identity; mutable
username and untrusted frontend or `initDataUnsafe` data are not authentication authority. Knowing a bot,
menu or deep link grants no trading or Scanner-control authority. API credentials never enter Telegram
messages or Scanner state.

`SignalSnapshot` is immutable, durable, stably identified and schema-versioned historical evidence. An old
message resolves its original snapshot rather than recomputing current Scanner state. A future schema may
retain symbol, timeframe, pattern, direction, score, geometry, target, original potential, creation time
and required rendering/evidence metadata; exact fields and migrations remain open. SignalSnapshot owns no
position, order, execution, SL/TP, PnL, controller/ownership or Robot state. Trade may optionally reference
a snapshot. Terminal does not call detector internals at runtime and also opens without `signal_id`.

#### Interactive chart and Terminal application boundary

KLineChart is the researched preferred v1 interactive renderer because its direction covers realtime
candles and volume, mobile and scale interaction, overlays, horizontal/trend/Fibonacci tools, magnet,
persistent market-coordinate points, selection/drag and locked/read-only objects. Terminal and Signal
Editor share a renderer-neutral Chart Contract/Adapter, with a KLineChart adapter below it. Domain and
trading logic must not depend directly on KLineChart APIs. Existing Matplotlib/mplfinance remains the
separate static Scanner/Telegram/report renderer and is not replaced by this direction.

The preferred Terminal boundary is a Python backend with FastAPI for HTTP/WebSocket application access:
REST carries commands and snapshots; backend-to-frontend WebSocket carries realtime state/events. The
Telegram Mini App/browser is a client, and frontend/chart state is never trading truth. These are
researched directions, not installed dependencies or implementation completion.

#### Persistence, credentials and deployment

SQLite with WAL mode is the preferred v1 local-first, single-user/single-backend persistence direction,
behind a storage abstraction that permits later migration. Durable responsibilities remain conceptually
separate: SignalSnapshot, TradingAccount metadata, Trade, Order, Execution, Position projections,
Protection/SL-TP state, TradingCommand, ExchangeEventJournal, closed-trade analytics/history and required
account valuation/cash-flow history. Journal is durable evidence of exchange/backend events; projection is
derived current operational state. They must not collapse into one mutable record.

Terminal backend owns credentials. Frontend/Mini App does not durably store API Secret and never receives
it back after submission; Scanner does not own it. A `CredentialStore` abstraction fronts protected local
Windows storage such as DPAPI or Credential Manager equivalent without coupling domain/application logic
to Windows APIs. Exact library/API and encrypted-storage design remain open; VPS replaces the
CredentialStore implementation without changing account/domain contracts.

The current target is local-first, but Telegram Mini App normally requires an HTTPS-reachable application
boundary. A raw development FastAPI port exposed directly to the public Internet is not the intended
architecture. Exact local HTTPS ingress/tunnel/provider remains a deployment decision. VPS migration
should primarily change deployment, ingress/TLS, supervision, credential store, backup/operations and
optional Bybit IP binding, not Scanner/Terminal domain contracts.

#### Analytics, Robot compatibility and Scanner Control

Trading Results retains DAY/WEEK/MONTH/YEAR realized USDT PnL, return percentage, win/loss counts,
pattern plus entry-reason breakdown, account isolation and Robot-versus-MANUAL_ENTRY provenance. Simple
period PnL divided by current deposit is insufficient when external cash flows occur. The preferred
direction is cash-flow-adjusted or time-weighted return semantics supported by durable valuation,
timestamp, transfer/cash-flow, realized result and required fee/funding inputs. Exact transfers,
deposits, withdrawals, fees, funding, boundaries and timezone formula remains unresolved.

Robot compatibility preserves MANUAL/ROBOT ownership, immutable origin/reason, `MANUAL_ENTRY` /
`Ручной вход`, handoff/takeover, read-only Robot live view, human Close Position override and the approved
19-WV per-account Robot exposure invariant. No Robot behavior is implemented or authorized.

Telegram Menu retains Terminal, Trading Results, AUTOPILOT and Run Scanner. Run Scanner crosses
`Telegram/UI → Scanner Control → Scanner application/pipeline` with conceptual `RUN_SCAN` and results
`STARTED`, `ALREADY_RUNNING`, `COMPLETED` with `approved_pattern_count` when available, and `FAILED` with
safe error information. Scanner Control owns single-flight/duplicate prevention; Telegram never invokes
or owns `main.py` internals. Redis, Celery or brokers are not justified for current single-user local-first
v1 without later evidence.

### C. Repository-confirmed reuse and boundaries

* `bybit_api.py` and the analyzer candle path provide public USDT-linear instrument/OHLCV access reusable
  behind a market-data boundary; the current unauthenticated HTTP session is not a trading adapter.
* `CONTRACT-SIGNAL-001` and `signal/filter.py` own final admission. `main.py` already increments
  `approved_pattern_count` only after final `approved`, before Telegram delivery, so Scanner Control can
  later expose that run result through an application boundary without duplicating admission policy.
* `telegram_bot.py` is a reusable outbound text/photo/inline-keyboard transport. It currently owns no
  inbound Mini App authentication, Scanner Control, Terminal state or trading authority.
* `contracts/signal_contract.py` plus analyzer/geometry output contain useful source evidence for a future
  SignalSnapshot mapper. `signal_memory.py` is mutable, symbol-keyed JSON history with limited fields and
  cannot serve as immutable versioned SignalSnapshot persistence.
* `chart.py`, `chart_clean.py` and `analyzer/charts.py` are the static Matplotlib/mplfinance PNG path. They
  remain useful for Scanner/Telegram reports but are not an interactive chart engine.
* Current dependencies include `pybit` and `websocket-client`; repository inspection finds no authenticated
  trading/private-stream service, FastAPI app, KLineChart frontend, SQLite trading store, or order,
  execution, position, protection, command, journal, account-isolation and reconciliation domain model.
* Existing authority forbids Geometry from trading decisions/execution and makes final Signal admission the
  sole normal persistence/notification gate. The researched architecture conforms by consuming normalized
  evidence and state rather than detector internals.

### D. Unresolved CONTEXT decisions

Before an implementation plan, CONTEXT must still resolve Bybit account/position modes and supported
capabilities; command and reconciliation schemas; SignalSnapshot versioning and retention; Telegram auth
freshness/session/allowlist policy; shared chart contract and KLineChart feasibility evidence; backend
event protocol and HTTPS ingress; SQLite transactions, journal projection/rebuild, backup and migration;
CredentialStore threat model and implementation; WV equity source/refresh/minimum behavior; return,
cash-flow, fee, funding, boundary and timezone accounting; and Scanner Control process/single-flight/error
contracts. Preferred technology directions are not implementation selections or dependency approvals.

### E. Required before an implementation plan

The next planning gate requires a reviewed domain contract set for account identity, commands, orders,
fills, positions, protection, ownership and reconciliation; explicit Bybit capability and failure matrices;
versioned SignalSnapshot and frontend event contracts; security and credential threat model; persistence
and recovery design; analytics accounting decision; chart adapter acceptance/prototype criteria; deployment
and Scanner Control boundaries; dependency review; verification strategy; and separate human IMPLEMENT
authorization. CONTEXT remains open until these are resolved or explicitly deferred through governance.

## 14. Refined Bybit execution, reconciliation and Working Volume research

### A. Approved SPEC requirements preserved

Approved SPEC revision 1.4 remains authoritative: USDT Linear Perpetual is the product direction;
semi-transparent means requested/local but not exchange-confirmed and opaque means exchange-confirmed;
full close removes all remaining ticker Limit orders and SL/TP/protection and reconciles; leverage never
participates in WV; `⚔ N.N` is display-only; normalization must never silently increase selected exposure.
This CONTEXT amendment does not silently replace the approved deposit/equity wording with a new binding
SPEC definition.

### B. Researched and preferred directions

Terminal is position-mode aware. Hedge Mode is the preferred researched v1 direction because independent
LONG and SHORT operations may require simultaneous opposite-side positions. Relevant side identity and
`positionIdx` are explicit where required, keyed with trading account and symbol. Terminal inspects actual
account/symbol position state and never silently changes the user's Bybit position mode during startup.
Exact compatible account modes and setup prerequisites must be explicit before implementation.

For Working Volume, the preferred researched interpretation is:

`WV_BASE = active trading account USDT walletBalance`

`raw_1_WV = USDT walletBalance × 5%`

`1_WV = floor(raw_1_WV / 10) × 10 USDT`

This intentionally excludes cross-asset `totalEquity`, `totalAvailableBalance`, leverage-adjusted buying
power and direct unrealized-PnL expansion. It best matches own real USDT funds, but remains a researched
interpretation pending any required SPEC refinement. Leverage remains irrelevant in every case.

Full-position exchange-side TP/SL remains the preferred v1 protection direction where final Bybit,
account and position-mode compatibility permits. Protection should survive loss of Terminal/frontend
connectivity. Exchange automatic adjustment or cancellation is useful but never replaces Terminal
verification of final protection, order and position state after close or recovery.

### C. Newly refined CONTEXT findings

Asynchronous mutations follow the invariant:

`Command → REST request/acknowledgement → PENDING → private exchange event or reconciliation → CONFIRMED`.

REST acceptance alone never makes create, amend, cancel, protection or other asynchronous state visually
or operationally confirmed. Timeout or connection loss enters an uncertain/reconciliation path rather
than blind resubmission.

Fills are execution-driven. One order may yield multiple executions. A durable execution identity such as
`execId` is deduplicated, with `orderId` and preferred client `orderLinkId` correlation, so duplicate,
late or racing order/execution events cannot double-count filled quantity, position, PnL, analytics,
execution sounds or chart markers. Newly accepted confirmed executions, not REST ACK or generic order
status, emit `▲ LONG`, `▼ SHORT` markers and execution feedback. Duplicate-looking terminal order states
are not independent fills.

A private position event does not prove that economic quantity changed. Current authoritative projection
is reconciled by trading account, symbol and relevant side/`positionIdx`; position messages are state
inputs rather than one-to-one trade events.

Close Position is a reconciled workflow:

`CLOSE_REQUESTED → determine current side/size/position identity → submit reducing close → observe
executions/position → verify zero → remove approved remaining ticker orders → verify/clean SL/TP/protection
→ final REST reconciliation → CLOSED_RECONCILED`.

These labels are conceptual. The exact safe Bybit sequence and filters remain state-machine design. No
single button press or ACK claims success before the approved terminal invariant is proven.

Private WebSocket provides realtime transport, not durable truth. Startup, reconnect and uncertain
mutations reconcile required positions, current/open orders, order history when necessary, execution
history and wallet/account state through authoritative REST sources. Wallet stream is not assumed to be a
complete initial snapshot. Private streams continue realtime synchronization only after reconciliation.

Every create-order command receives durable client correlation identity; `orderLinkId` is preferred where
applicable. Local `TradingCommand` identity is persisted before or transactionally with submission under
the final storage design. After timeout, the original command/order is reconciled before any new
exposure-increasing retry. Blind BUY/SELL retry after an uncertain result is prohibited.

Working Volume is a USDT sizing intent. The command pipeline is conceptually:

`selected_WV_count → target_USDT → raw instrument quantity using sizing price → floor to qtyStep →
validate minOrderQty → validate minNotionalValue → validate maximum quantity/notional → exchange_qty`.

All constraints come from authoritative instrument metadata and are not hardcoded. Quantity rounds down,
never up. Market versus Limit sizing-price semantics remain open. If normalization cannot produce a valid
order, the command is rejected before exchange creation as normal business outcome
`REJECTED_INSUFFICIENT_VOLUME`, shown as `Недостаточный объём`. Terminal does not auto-increase to the
minimum. UI can show selected WV/USDT, current one-WV value and determinable exchange minimum. Future
Robot follows the same no-increase rule.

Limit/SL/TP prices use authoritative `tickSize`. Draft price is normalized and shown before confirmation,
so the chart does not knowingly display one confirmed price while submitting a materially different one.
Safe rounding direction remains specific to order/protection semantics and is not generalized here.

Market BUY/SELL requests target exposure but does not guarantee exact filled exposure. Partial or other
exchange outcomes are possible. Actual engaged USDT and `⚔ N.N` derive from confirmed executions and
reconciled position state, so one selected WV may result in a displayed value such as `⚔ 0.8`.

### D. Decisions still unresolved

CONTEXT still requires exact command/order/execution/position state machines and per-command reconciliation
matrices; Market sizing-price/slippage policy; full-position TP/SL behavior under the chosen position mode;
account/mode prerequisites; transactional boundary across TradingCommand, journal and projections;
SignalSnapshot schema/versioning/retention; Telegram auth/session policy; Chart Adapter feasibility;
backend realtime protocol and HTTPS ingress; SQLite rebuild, backup and migrations; CredentialStore threat
model; cash-flow, fees, funding, period and timezone analytics; Scanner Control transport/correlation;
dependency approval, verification strategy and future implementation decomposition. Preferred directions
do not remove these decisions.

## 15. Authorization boundary

Revision 1.6 is a human-approved intermediate durable CONTEXT research checkpoint. Approved
SPEC revision 1.4 remains intact. Production
implementation, tests, dependencies, Bybit credentials, orders and runtime changes are
`NOT_STARTED_NOT_AUTHORIZED`. CONTEXT/RESEARCH is separately authorized and in progress, without any
claim that CONTEXT is complete, fully finalized or verified. IMPLEMENT
requires separate later approval and valid context.
