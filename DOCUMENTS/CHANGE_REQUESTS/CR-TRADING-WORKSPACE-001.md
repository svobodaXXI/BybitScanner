# CR-TRADING-WORKSPACE-001 — Trading Workspace v1 / Manual Live Trading

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-TRADING-WORKSPACE-001",
  "title": "Trading Workspace v1 / Manual Live Trading",
  "status": "IN_PROGRESS",
  "revision": "1.1",
  "lifecycle_stage": "SPEC",
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
  ],
  "unresolved_decisions": [
    "Frontend, backend, chart library and persistence technology selection",
    "Authentication, authorization, Bybit credential custody and Telegram Mini App session security",
    "Bybit account mode, position mode, product/category and supported order capability boundaries",
    "Exact exchange reconciliation state machines, timeout policies, idempotency identifiers and orderLinkId mapping",
    "Exact Working Volume equity source, refresh timing, rounding, minimum quantity and insufficient-balance behavior",
    "Exact active-order modification interaction and amend versus cancel-replace policy",
    "SignalSnapshot schema, target-method taxonomy, retention, migrations and deep-link routing",
    "Shared chart-engine selection and saved drawing schema",
    "Sound assets, delivery mechanism and user configuration",
    "Local deployment topology and later VPS migration boundary"
    ,"Final names and transition rules for MANUAL_CONTROLLED, ROBOT_CONTROLLED, TAKEOVER_PENDING, CLOSING and RECONCILING conceptual states"
    ,"Exact persisted field names and schema for immutable entry origin and entry reason"
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
    {"id": "SPEC", "status": "REVISION_1_1_APPROVED_HUMAN_AUTHORIZED_DOCUMENTATION_CHECKPOINT_ONLY"},
    {"id": "CONTEXT", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "IMPLEMENT", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "VERIFY", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "RECORD", "status": "NOT_STARTED_NOT_AUTHORIZED"}
  ],
  "current_phase": "SPEC",
  "current_checkpoint": "MANUAL_LIVE_TRADING_V1_OWNERSHIP_AND_WORKING_VOLUME_SPEC_APPROVED_RECORDED",
  "implementation_status": "IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED",
  "next_phase": "CONTEXT",
  "next_phase_authorization": "NOT_AUTHORIZED_PENDING_HUMAN_SPEC_APPROVAL",
  "related_commits": [
    {"phase": "BASELINE", "commit": "5b898963ef46bbd33771123ac169d7b8d52fc0e0"},
    {"phase": "SPEC_DOCUMENTATION_CHECKPOINT", "commit": "52f719351574d32aeb765fa833a27cc1e1bbbd25"}
  ],
  "repository_sync": {
    "branch": "main",
    "baseline_local_head": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "baseline_origin_main": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "latest_saved_checkpoint": "52f719351574d32aeb765fa833a27cc1e1bbbd25",
    "status": "DOCUMENTATION_CHECKPOINT_APPROVED_FOR_COMMIT"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Recorded and human-approved the Trading Workspace v1 Manual Live Trading durable Task/Spec for documentation checkpoint commit only without CONTEXT or implementation authorization", "date": "2026-08-20"},
    {"revision": "1.1", "reason": "Human-approved documentation checkpoint recording leverage-independent Working Volume, immutable entry provenance, exclusive position ownership, future AUTOPILOT handoff, human takeover and ownership-scoped active-position operations without authorizing CONTEXT, external research or implementation", "date": "2026-08-21"}
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

## 10. Authorization boundary

This revision records the human-approved revision 1.1 TASK/SPEC documentation checkpoint only. Production
implementation, tests, dependencies, Bybit credentials, orders and runtime changes are
`NOT_STARTED_NOT_AUTHORIZED`. CONTEXT has not started and is not authorized. Separate later approval and
valid CONTEXT are required before IMPLEMENT.
