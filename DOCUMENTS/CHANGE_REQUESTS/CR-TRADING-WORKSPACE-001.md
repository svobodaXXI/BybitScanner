# CR-TRADING-WORKSPACE-001 — Trading Workspace v1 / Manual Live Trading

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-TRADING-WORKSPACE-001",
  "title": "Trading Workspace v1 / Manual Live Trading",
  "status": "IN_PROGRESS",
  "revision": "1.23",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Record the implemented and verified smallest runnable Stage 8 Fast DOM client slice while preserving Paper-first safety and all deferred boundaries.",
  "non_goals": [
    "Implement any Stage 8 functionality beyond the bounded frontend foundation and structural shell",
    "Implement autonomous Trading Robot behavior or AUTOPILOT",
    "Connect the initial Trading Workspace execution path to a real-money Bybit account",
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
    "Prepare later human review and explicit implementation authorization",
    "Implement the human-authorized Stage 8 Block 1 React 19, TypeScript and Vite frontend foundation under terminal/frontend",
    "Record the approved documentation-only Fast DOM client-slice interaction, own-order presentation and market-data baseline",
    "Record the approved documentation-only single-workspace Terminal, Autopilot and Editor mode architecture"
  ],
  "prohibited_scope": [
    "Functional DOM, L2 ingestion, Market Data Engine, Paper Trading Engine or chart implementation",
    "Bybit order placement or account mutation",
    "Scanner, detector, Geometry, Signal admission or Telegram runtime changes",
    "Trading Robot implementation",
    "AUTOPILOT enablement",
    "Dependencies outside the bounded frontend build, styling, lint and focused-test foundation",
    "Any Stage 8 implementation beyond the explicitly authorized first runnable Fast DOM client slice"
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
    "The initial Trading Workspace execution backend is a virtual paper account and Paper Trading Engine behind a reusable execution interface; real-money Bybit execution is deferred",
    "Terminal remains usable when Scanner is stopped and is local-first but deployment-neutral for later VPS operation",
    "Telegram is the primary entry point and old signal deep links resolve durable SignalSnapshot history indefinitely",
    "Terminal and Signal Editor share one reusable chart engine",
    "Working Volume is exactly five percent or one twentieth of the active trading account USDT walletBalance before leverage, rounded down to the nearest ten USDT",
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
    ,"One Working Volume is account-scoped, leverage-independent and equals five percent of active-account USDT walletBalance rounded down to the nearest ten USDT"
    ,"Future Robot-controlled aggregate exposure is limited to nineteen Working Volumes per trading account, excluding MANUAL-controlled exposure unless a later approved policy changes that boundary"
    ,"Trading Results reports selected-period realized PnL in both USDT and percentage of a defined period deposit or equity reference without treating external cash flows as trading performance"
    ,"Trading credentials belong only to the Terminal backend security boundary; API Secret is never returned to the frontend or stored in Scanner, chart, Telegram or frontend-readable durable state"
    ,"Manual Live Trading v1 requires Bybit One-Way Mode with positionIdx zero; opposite-direction exposure requires an explicit close or reduce workflow, confirmed zero and reconciliation before a new opposite position"
    ,"Terminal never switches Bybit position mode automatically and blocks new exposure until an incompatible account or symbol mode is corrected and reconciled"
    ,"External exchange positions, orders, executions and protection are displayed and included in actual account risk without being relabelled as Terminal origin"
    ,"Exchange changes made through Bybit, MetaScalp or another external client are reconciled and adopted as factual state without automatic compensating orders that fight the exchange"
    ,"The OWNER may take an external position under Manual control only after successful reconciliation without creating an order or rewriting its external origin"
    ,"Emergency Close is a distinct auditable reduce-risk workflow that cannot intentionally reverse exposure, never blindly retries an uncertain close and completes only through CLOSED_RECONCILED semantics"
    ,"Full Close cleans Terminal-owned orders and protection but never silently cancels external orders; potentially exposure-reopening external orders require warning and separate OWNER confirmation before cancellation"
    ,"One negative exchange lookup never proves that an uncertain mutation did not exist; bounded repeated multi-source correlation ends in explicit unresolved reconciliation state rather than automatic not-submitted inference"
    ,"The Manual v1 upper workspace is intentionally minimal: the primary live chart occupies the left side and a narrow collapsible DOM plus execution-prints panel occupies the right side, while existing trading controls remain below"
    ,"DOM resting liquidity is represented by price, size and a stable visually scaled depth fill; execution prints represent aggressive trades rather than resting orders and encode aggressor side and execution volume"
    ,"A multi-level sweep ellipse may span only a reliably reconstructed consumed price range; ambiguous trade and order-book correlation falls back to a non-sweep print and never invents consumption"
    ,"The upper market-depth area permits only a compact reconciled position direction and PnL indicator and does not add a separate position card or other analytics widgets"
    ,"Manual Market, Limit and protection actions use Bybit-authoritative Command, Order, Execution and Position lifecycles with fail-closed reconciliation and no blind retry"
    ,"Quick DOM execution uses held BUY ORDER or SELL ORDER plus a second price-level tap, defaults to one Working Volume and suppresses repeated execution taps inside 300 milliseconds"
    ,"Manual Market opposite-side volume is capped at the current position remainder to reach FLAT without reversal, while a Manual Limit may close current exposure and leave an opposite-side remainder"
    ,"All active Limit orders for the selected account and symbol are visible regardless of Terminal or external origin, with confirmed exchange state controlling DOM and chart indicators"
    ,"Execution anti-bounce expires after 300 milliseconds but never overrides an UNKNOWN or RECONCILING command lock"
    ,"Degraded, unknown and reconciling state blocks new exposure while preserving only safely bounded risk reduction and cancellation"
    ,"After confirmed FLAT caused by Market, SL or TP, all remaining ordinary active Limits for that selected account and symbol enter automatic cancellation regardless of origin, without extending this rule to other symbols or conditional protection"
    ,"Manual Terminal v1 ordinary Limit orders use binding Good-Till-Cancelled timeInForce and remain active until execution, explicit user cancellation or approved Terminal cleanup; IOC, FOK and PostOnly are not the default Manual Limit semantics"
    ,"Fast DOM uses one CENTER control: one deliberate activation performs one-shot centering without locking, a deliberate double activation centers and enables LOCKED CENTERING, a double activation while locked disables it, and manual scrolling or repositioning disables it; active locked mode is shown by a persistent visible border or outline on CENTER"
    ,"Fast DOM uses one execution gesture state machine with device-specific mappings: touch uses a held primary BUY or SELL finger plus a secondary row-selection finger, while desktop uses a held primary mouse action plus a separately deliberate row action whose exact button mapping remains verification-gated; hover never submits a trading command"
    ,"A Scanner Telegram signal may expose a separate Open in MetaScalp action whose binding outcome is a new MetaScalp tab and new DOM for that signal symbol while all existing MetaScalp tabs and order books remain unchanged"
    ,"MetaScalp integration belongs to a separate Scanner/backend integration block and never expands the Fast DOM execution engine or Stage 8 scope"
    ,"The preferred future MetaScalp boundary is its official Linking API, with /api/combo retained only as the current closest researched candidate until repeated-call new-tab, existing-tab preservation, market mapping, not-running and local-port behavior are explicitly verified"
    ,"The selected frontend stack is one React 19 plus TypeScript plus Vite SPA for desktop web and Telegram Mini App, using npm with package-lock.json, Zustand for client/UI state, TanStack Query for REST/server state, a separate WebSocket realtime layer, Tailwind 4, selective shadcn/Radix ordinary controls, Vitest plus React Testing Library plus Playwright, and Biome"
    ,"High-frequency DOM rendering is isolated from the ordinary React render lifecycle; TanStack Query does not own high-frequency L2 updates, and this frontend decision does not select the chart or rendering engine"
    ,"Desktop fast Limit interaction uses side-explicit BUY/BID and SELL/ASK execution columns, left-click Limit placement, specific-order right-click cancellation, selected-order drag for modification, and no implicit Market order or trading double-click on the DOM ladder"
    ,"Holding BUY or SELL with the left mouse button enters the corresponding Limit placement mode so deliberate chart right-clicks may place multiple same-side Limit intents; normal non-marketable fast Limits require no confirmation, while marketable aggressive Limits require explicit confirmation and always remain Limit orders"
    ,"A single BUY or SELL activation prepares a Market order that requires confirmation with ticker, WV/USDT reference, calculated rounded base quantity, relevant prices, estimated VWAP and estimated L2 slippage from the authoritative normalized book"
    ,"BUY, SELL and LIMIT placement gestures use a binding 500-ms long-press threshold; entering LONG_PRESS_ACTIVE suppresses the original short-click action and remains independent from the 300-ms trading anti-bounce"
    ,"Fast order placement is fail-closed with one physical gesture producing at most one uniquely identified intent, no blind resend after ambiguity, client-order-identity reconciliation before recovery, new placement blocked in DEGRADED/OFFLINE/ambiguous state, and success sound only after exchange or execution-engine acknowledgement"
    ,"Cancelling an unconfirmed active-Limit line edit by clicking or tapping outside restores the exact original confirmed price and sends no modify request; only explicit confirmation commits an amend"
    ,"Working Volume remains a USDT accounting and risk unit, while actual execution and position ownership use authoritative base-asset coin quantity; fills and current remaining position quantity, not the original WV notional, govern reduce-only close and residual-tail reconciliation"
    ,"The Paper Trading Engine implements realistic accepted, working, partial/full fill, cancel/reject, position, realized/unrealized PnL and reconciliation-compatible state, may consume real L2 through the later approved market-data boundary, is reusable by the future virtual Robot, and preserves MANUAL versus ROBOT controller ownership"
    ,"CENTER uses an approved 300-ms desktop mouse double-click window and an approved 350-ms touch double-tap window; the first activation centers immediately, the second activation upgrades to LOCKED CENTERING, and CENTER mouse, CENTER touch, 500-ms long-press and 300-ms trading anti-bounce timers remain independent state domains"
    ,"Multiple own active orders may coexist at one DOM price; the displayed USDT amount is aggregated while every concrete order retains an independently cancellable identity marker ordered newest-to-left with touch-safe selection and explicit overflow when safe packing is exhausted"
    ,"Own-order markers have visual and pointer/touch priority over overlapping tape prints, which become partially transparent so the markers remain visible and selectable"
    ,"Quick volume is symbol-scoped, resets to one WV on every instrument entry or switch and never silently carries a prior symbol's adjustment; its indicator tooltip shows the corresponding USDT reference while execution remains based on rounded base-asset coin quantity"
    ,"One authoritative Market Data Engine consumes Bybit Public WebSocket L2 orderbook snapshot/delta semantics at an initial target depth of 50, reconstructs a normalized local book with sequence, resynchronization, timing and health state, and prevents frontend and Paper execution consumers from depending on Bybit-specific update mechanics"
    ,"Trading Workspace DOM, Market VWAP/slippage preview and Paper Trading Engine market execution consume the same authoritative normalized book; Market BUY walks asks and Market SELL walks bids from best outward rather than estimating execution from last price when usable L2 exists"
    ,"Paper market execution consumes authoritative opposite-side L2 liquidity so larger orders may receive worse average simulated execution, while resting paper Limits are not deemed fully filled merely on price touch"
    ,"Market-data-dependent execution fails closed unless the authoritative book is ready, sequence-consistent, resynchronized and sufficiently fresh; invalid or ambiguous liquidity is never fabricated for preview or Paper execution"
    ,"A dedicated bounded SECRET EXPOSURE AUDIT is required before any real Bybit credentials or live execution are introduced, covering tracked files, relevant Git history, configuration, logs, backups, credential patterns, ignore protections and available GitHub scanning posture with masked findings and rotation before any separately controlled history cleanup"
    ,"For the current Fast DOM client slice, ordinary Bid, Ask and price-level clicks never create orders; ordinary DOM left/right clicks have no trading action, while vertical mouse drag and wheel reposition the ladder and intentional manual movement disables locked CENTER"
    ,"The current Fast DOM client slice preserves one-shot CENTER on single click and center-plus-persistent lock on double click, with a clearly visible locked border or outline"
    ,"Multiple distinct own active Limits at one price render as one side-colored dot per concrete order on that row; activating one dot cancels only that order, while the side-colored aggregate USDT notional appears at the extreme left of the same row"
    ,"The market-data baseline is Bybit V5 public WebSocket orderbook depth 50 plus a conceptually separate publicTrade tape stream; the Market Data Engine maintains snapshot-plus-delta local state behind a depth-extensible normalized DOM contract and REST is not the primary live DOM feed"
    ,"High-frequency L2 delivery uses a dedicated state/data path rather than naive full React-state rerendering, remains future-Web-Worker-compatible and supports efficient or virtualized ladder rendering while backend services retain trading and execution authority"
    ,"Trading Workspace is one application and shared engine with switchable TERMINAL, AUTOPILOT and EDITOR modes rather than three applications or recreated chart engines"
    ,"Mode switching replaces the lower functional panel and mode-specific overlays or tools while preserving applicable symbol, timeframe, chart viewport, live market data, DOM/Tape, selected account and connection state"
    ,"Every mode exposes direct lower-panel navigation to the other two modes; the previously planned upper-header AUTOPILOT button is removed"
    ,"Switching TERMINAL, AUTOPILOT or EDITOR is navigation only and never by itself cancels orders, starts or stops Robot, closes positions, changes account or mutates trading state"
    ,"A key-icon control opens configured account selection and credential management, including a selectable Paper or Virtual account; real credential handling remains separately authorization-gated"
    ,"DOM plus Tape expansion must not blindly compress the upper header; final responsive rearrangement is a real-prototype UX decision point rather than a documentation-time invented layout"
    ,"The current product priority is to deliver the first real runnable Fast DOM and Trading Workspace prototype as soon as practicable and use it for UX tuning rather than image or mockup-driven design"
  ],
  "unresolved_decisions": [
    "Final adoption and version constraints for the researched KLineChart, FastAPI and SQLite/WAL directions after implementation planning and prototype evidence",
    "Authentication, authorization, Bybit credential custody and Telegram Mini App session security",
    "Exact supported-account compatibility and setup diagnostics for the binding One-Way Mode requirement within USDT Linear Perpetual scope",
    "Exact numeric reconciliation timeout, repeated-check interval, backoff and search-horizon configuration validated through later Bybit-specific testing",
    "USDT walletBalance refresh/cache timing, sub-ten-USDT behavior and insufficient-volume handling",
    "Exact active-order modification interaction and amend versus cancel-replace policy",
    "SignalSnapshot schema, target-method taxonomy, retention, migrations and deep-link routing",
    "Shared chart-engine selection and saved drawing schema",
    "Sound assets, delivery mechanism and user configuration",
    "Local deployment topology and later VPS migration boundary"
    ,"Final names and transition rules for MANUAL_CONTROLLED, ROBOT_CONTROLLED, TAKEOVER_PENDING, CLOSING and RECONCILING conceptual states"
    ,"Exact compact/overflow presentation when same-price own-order markers no longer fit with unambiguous touch-safe targets"
    ,"Exact resting Paper Limit queue-position, liquidity and partial-fill algorithm using market trades and L2 evolution"
    ,"Exact numerical authoritative-book staleness threshold and final READY/STALE/DEGRADED transition parameters"
    ,"Exact persisted field names and schema for immutable entry origin and entry reason"
    ,"DAY, WEEK, MONTH and YEAR calendar boundaries and timezone semantics"
    ,"Closed-trade analytics schema, ownership-history representation and aggregation strategy"
    ,"Whether initial analytics UI exposes optional provenance filters for all AUTOPILOT-managed, Robot-entry and manual-entry-handoff trades"
    ,"Exact Telegram Menu button layout and Bot API, Mini App or command mechanism"
    ,"Scanner Control IPC/API/process transport, command identity, concurrency lock and completion correlation"
    ,"Exact Telegram allowlist, session and authorization checks for Terminal, AUTOPILOT and Scanner control"
    ,"Encrypted credential-storage, key rotation, validation diagnostics and trading-account profile lifecycle design"
    ,"USDT walletBalance refresh timing and account-switch reconciliation state machine"
    ,"Working Volume behavior below the ten-USDT rounding quantum and its interaction with exchange minimum quantity and insufficient balance"
    ,"Concurrency and exposure reservation semantics for simultaneous future Robot commands and ownership handoffs near the nineteen-WV limit"
    ,"Selected-period percentage-PnL accounting for deposits, withdrawals, transfers, equity changes, period boundaries and timezone"
    ,"Final working/calculation depth beyond the preferred orderbook.50 starting candidate, exact sequence-gap rules, correlation window, confidence thresholds and same-sequence multi-message treatment"
    ,"PROBABLE sweep visualization and reliable trade-to-L2 correlation under ambiguous cancellation-versus-execution evidence"
    ,"Responsive adjustment around the preferred 20 asks plus 20 bids viewport, exact row height, DOM percentile/window/hysteresis, print-scaling window, update batching, render frequency, bounded tape retention and mobile Telegram Mini App performance limits"
    ,"Exact LOCKED CENTERING follow/recenter thresholds, central dead-zone, motion and sweep-follow interaction, border or outline styling, x10/x100 compression implementation, hidden-panel unsubscribe/grace behavior, third-party vendoring policy and future historical heatmap requirement"
    ,"Exact chart/rendering engine selection and adapter implementation under the approved React/TypeScript frontend stack"
    ,"Exact persistence, matching, latency, fee, funding, liquidity and fill-simulation policies for the initial Paper Trading Engine"
    ,"Exact MetaScalp Linking API behavior required to guarantee a new tab and new symbol DOM while preserving existing tabs, including exchange/market selection, Bybit USDT perpetual ticker mapping, not-running behavior and official local-port discovery"
  ],
  "researched_architecture_directions": [
    "Authenticated Bybit V5 REST commands are correlated with private order, execution, position and wallet events; REST acceptance alone is not final state confirmation",
    "Uncertain commands, startup, reconnect and full-close workflows reconcile authoritative exchange state instead of blind retry",
    "Telegram Mini App deep-link references identify durable SignalSnapshot records but authorization requires backend validation of raw initData, freshness and allowed numeric Telegram user identity",
    "SignalSnapshot is immutable versioned historical Scanner evidence and never owns trading, protection, PnL, controller or Robot state",
    "KLineChart remains a researched chart candidate behind a shared chart contract and adapter, but revision 1.17 does not select a chart/rendering engine; current Matplotlib/mplfinance remains the separate static Scanner report path",
    "Python with FastAPI is the preferred Terminal HTTP and WebSocket application boundary; frontend and Telegram Mini App are clients, never trading-state authority",
    "SQLite in WAL mode is the preferred local-first v1 persistence direction behind a replaceable storage boundary",
    "Durable exchange and backend event journal evidence remains distinct from mutable operational projections",
    "Trading mutations remain locked through startup, reconnect, account switch and uncertainty until credentials, streams, REST snapshots, commands, ownership and exchange state reconcile",
    "CredentialStore abstracts protected local Windows credential storage such as DPAPI or Credential Manager so later VPS deployment can replace the implementation without changing domain contracts",
    "Percentage return requires cash-flow-adjusted or time-weighted direction and sufficient valuation and cash-flow history; exact formula and fee, funding, transfer and timezone policy remain open",
    "Scanner Control is a single-flight application boundary around RUN_SCAN and may reuse the existing approved-pattern count without coupling Telegram to main.py internals",
    "Local-first deployment still requires an HTTPS-reachable Mini App boundary; raw public exposure of a development FastAPI port is not the intended architecture"
    ,"Terminal v1 remains scoped to Bybit USDT Linear Perpetual and requires One-Way Mode with positionIdx zero; simultaneous independent LONG and SHORT positions and hidden instant reversal are prohibited"
    ,"Asynchronous mutations follow command, REST acknowledgement, pending, private-event or reconciliation confirmation; semi-transparent remains unconfirmed and opaque remains exchange-confirmed"
    ,"Confirmed fills are deduplicated by durable execution identity such as execId and correlated through orderId or orderLinkId so duplicate, late or racing events cannot double-count quantity, PnL, analytics, sounds or markers"
    ,"Current position projection is keyed by trading account, symbol and relevant side or positionIdx identity; a position stream event is reconciled state input, not proof of a distinct economic trade"
    ,"Close Position is a multi-step reducing, observation, cleanup and REST-reconciliation workflow ending only at position zero with required symbol orders and protection removed"
    ,"Private WebSocket is realtime transport rather than durable truth; startup, reconnect and uncertain mutations use required REST positions, open orders, histories, executions and wallet/account state before streams resume synchronization"
    ,"A durable local TradingCommand correlation identity is persisted before or transactionally with submission; timeout-after-submit reconciles the original order before any exposure-increasing retry"
    ,"Active-account USDT walletBalance is the binding WV base and excludes leverage, totalAvailableBalance, totalEquity, non-USDT asset value and unrealized-PnL-expanded buying capacity"
    ,"WV sizing converts selected WV to target USDT and then floors instrument quantity to authoritative qtyStep while validating minOrderQty, minNotionalValue and maximum constraints without increasing requested exposure"
    ,"Insufficient normalized volume is a pre-submit business rejection REJECTED_INSUFFICIENT_VOLUME with user feedback Недостаточный объём; Terminal and future Robot never auto-increase exposure to satisfy exchange minima"
    ,"Limit and protection draft prices use authoritative tickSize normalization visible before confirmation; safe rounding direction remains order-specific design work"
    ,"Market WV is sizing intent rather than guaranteed fill size; actual engaged USDT and fractional WV display derive from confirmed executions and reconciled position state"
    ,"One normalized market-data source should serve DOM, execution-print visualization and any active manual pre-trade liquidity use rather than creating duplicate order-book subscriptions"
    ,"Trustworthy sweep visualization requires sequenced L2 state immediately before executions, public trade evidence, resulting book state and explicit fallback when consumption cannot be proved"
  ],
  "repository_confirmed_reuse": [
    "bybit_api.py and analyzer candle loading provide reusable public USDT-linear instrument and OHLCV access only behind a market-data boundary; they are not authenticated trading infrastructure",
    "CONTRACT-SIGNAL-001 and signal.filter own final approved admission, while main.py already counts approved_pattern_count independently of Telegram delivery",
    "telegram_bot.py provides outbound text, photo and inline-keyboard transport that may be reused without owning authentication, Scanner control or trading state",
    "contracts/signal_contract.py, analyzer results and geometry output provide source evidence from which a future versioned SignalSnapshot mapper may be designed, but current signal_memory.py is mutable symbol-keyed history and is not SignalSnapshot persistence",
    "chart.py, chart_clean.py and analyzer/charts.py form the existing static Matplotlib/mplfinance PNG report path and remain separate from the interactive Terminal renderer",
    "Current requirements include pybit and websocket-client and completed bounded Terminal backend foundations through Stage 7, but no Stage 8 React client, FastAPI runtime, selected chart engine or Paper Trading Engine is implemented",
    "No current order, execution, position, protection, TradingCommand, ExchangeEventJournal, account-isolation or reconciliation domain implementation exists"
  ],
  "context_decisions_required_before_implementation_plan": [
    "Exact supported-account prerequisites, One-Way setup diagnostics, category/order capabilities, full-position TP/SL compatibility and identifier constraints",
    "Final implementation names and persistence representation for the recorded command, order, execution, position, protection and ownership lifecycle semantics",
    "Versioned SignalSnapshot schema, immutable retention, migrations, target metadata and deep-link resolution",
    "Telegram backend authentication validation, freshness window, allowlist, session lifetime and authorization matrix",
    "Shared chart contract and KLineChart feasibility prototype criteria without coupling domain state to renderer APIs",
    "Terminal backend process topology, backend-to-frontend event protocol and local HTTPS ingress decision",
    "SQLite/WAL schema, transaction boundaries, journal/projection rebuild rules, backup and later storage migration boundary",
    "CredentialStore threat model, protected Windows implementation choice, secret rotation/removal and VPS replacement contract",
    "USDT walletBalance refresh timing, Market versus Limit sizing-price semantics, sub-ten-USDT behavior and exchange precision/minimum constraints",
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
    "This checkpoint changes only the ChangeRequest and its Project State and Roadmap pointers",
    "Rollback removes only this documentation amendment without runtime or exchange effects",
    "Existing completed Stage 0 through Stage 7 implementation checkpoints remain unchanged"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED_HUMAN_AUTHORIZED"},
    {"id": "SPEC", "status": "REVISION_1_4_APPROVED_HUMAN_AUTHORIZED_DOCUMENTATION_CHECKPOINT_ONLY"},
    {"id": "CONTEXT", "status": "AUTHORIZED_RESEARCH_IN_PROGRESS"},
    {"id": "IMPLEMENT", "status": "BOUNDED_STAGES_0_TO_7_COMPLETED_STAGE_8_BLOCK_1_AND_FAST_DOM_RUNNABLE_CLIENT_SLICE_IMPLEMENTED"},
    {"id": "VERIFY", "status": "BOUNDED_STAGES_0_TO_7_STAGE_8_BLOCK_1_AND_FAST_DOM_RUNNABLE_CLIENT_SLICE_VERIFIED"},
    {"id": "RECORD", "status": "NOT_STARTED_NOT_AUTHORIZED"}
  ],
  "current_phase": "IMPLEMENT",
  "current_checkpoint": "STAGE_8_FAST_DOM_RUNNABLE_CLIENT_SLICE_IMPLEMENTED_VERIFIED",
  "implementation_status": "STAGES_0_TO_7_STAGE_8_BLOCK_1_AND_FAST_DOM_RUNNABLE_CLIENT_SLICE_IMPLEMENTED_VERIFIED",
  "next_phase": "VERIFY",
  "next_phase_authorization": "NEXT_STAGE_8_SLICE_NOT_AUTHORIZED_ALL_DEFERRED_SCOPE_REQUIRES_SEPARATE_AUTHORIZATION",
  "related_commits": [
    {"phase": "BASELINE", "commit": "5b898963ef46bbd33771123ac169d7b8d52fc0e0"},
    {"phase": "SPEC_DOCUMENTATION_CHECKPOINT", "commit": "52f719351574d32aeb765fa833a27cc1e1bbbd25"},
    {"phase": "SPEC_REVISION_1_1_DOCUMENTATION_CHECKPOINT", "commit": "5e38b8a6df64e822e664de665701a53e76163fdd"},
    {"phase": "SPEC_REVISION_1_2_DOCUMENTATION_CHECKPOINT", "commit": "f8d0932afd9589998d09027477c67eb8ab7aa1a0"}
    ,{"phase": "SPEC_REVISION_1_3_DOCUMENTATION_CHECKPOINT", "commit": "3d0ba01895db0cd9c4fcd1670b06e46671d645a0"}
    ,{"phase": "SPEC_REVISION_1_4_DOCUMENTATION_CHECKPOINT", "commit": "aba84eeab539d329fc693728dc70bb38f7dee0cc"}
    ,{"phase": "CONTEXT_REVISION_1_5_INTERMEDIATE_RESEARCH_CHECKPOINT", "commit": "a70c99b1fb4a5e84847aab90d3d9dd3931340b29"}
    ,{"phase": "CONTEXT_REVISION_1_6_BYBIT_EXECUTION_AND_WV_RESEARCH_CHECKPOINT", "commit": "d82ad7803f9a21f21f12ce9e4975ae71fdbfbdc8"}
    ,{"phase": "CONTEXT_REVISION_1_7_EXECUTION_RECONCILIATION_MODEL_CHECKPOINT", "commit": "5fa3bba7b347739fb73e57f25306ec8a677643e4"}
    ,{"phase": "IMPLEMENT_STAGE_7_API_PROJECTION_CONTRACTS", "commit": "61520861b6058a585460b3f5f964613d19dcd35b"}
  ],
  "repository_sync": {
    "branch": "main",
    "baseline_local_head": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "baseline_origin_main": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "latest_saved_checkpoint": "61520861b6058a585460b3f5f964613d19dcd35b",
    "status": "STAGE_8_FAST_DOM_RUNNABLE_CLIENT_SLICE_IMPLEMENTED_VERIFIED_NEXT_SLICE_NOT_AUTHORIZED"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Recorded and human-approved the Trading Workspace v1 Manual Live Trading durable Task/Spec for documentation checkpoint commit only without CONTEXT or implementation authorization", "date": "2026-08-20"},
    {"revision": "1.1", "reason": "Human-approved documentation checkpoint recording leverage-independent Working Volume, immutable entry provenance, exclusive position ownership, future AUTOPILOT handoff, human takeover and ownership-scoped active-position operations without authorizing CONTEXT, external research or implementation", "date": "2026-08-21"},
    {"revision": "1.2", "reason": "Human-approved documentation checkpoint recording Working Volume detail interaction and AUTOPILOT trading-results, period metrics, provenance breakdown and durable analytics requirements while CONTEXT research remains in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.3", "reason": "Human-approved documentation checkpoint recording unified Scanner Telegram bot navigation and authorization-aware, concurrency-safe Scanner Control requirements while CONTEXT research remains in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.4", "reason": "Human-approved documentation checkpoint recording account management and isolation, refined account-scoped Working Volume, future per-account Robot exposure limit, percentage PnL and credential-security boundaries while CONTEXT research remains in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.5", "reason": "Human-approved intermediate durable CONTEXT architecture research checkpoint reconciling Bybit, Telegram, SignalSnapshot, chart, backend, persistence, recovery, security, analytics, Scanner Control and deployment directions with current repository boundaries; CONTEXT remains incomplete and in progress and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.6", "reason": "Human-approved intermediate durable CONTEXT checkpoint refining Bybit position mode, asynchronous confirmation, execution deduplication, close and recovery reconciliation, command correlation, preferred WV walletBalance base and exchange quantity/price normalization while CONTEXT remains incomplete and IMPLEMENT remains unauthorized", "date": "2026-08-21"},
    {"revision": "1.7", "reason": "Human-approved intermediate durable CONTEXT checkpoint recording the formal TradingCommand, Order, Execution, Position, reconciliation, exposure-gate, crash-recovery and transaction-atomicity model while preserving unresolved human decisions, active CONTEXT research and unauthorized IMPLEMENT", "date": "2026-08-21"},
    {"revision": "1.8", "reason": "Human-approved intermediate durable CONTEXT checkpoint binding active-account USDT walletBalance WV authority, One-Way Mode, no automatic mode switching, external-state adoption, Manual takeover, Emergency Close, external-order-aware Full Close and conservative negative-correlation policy without completing CONTEXT or authorizing IMPLEMENT", "date": "2026-08-21"},
    {"revision": "1.9", "reason": "Human-approved intermediate durable CONTEXT checkpoint recording the minimal upper Terminal workspace, one normalized public market-data owner, collapsible DOM and execution-print panel, preferred 20+20 viewport over deeper working data, interaction-safe recenter and STRONG-sweep follow, confidence and resync safety, reusable Manual book walk, bounded Canvas2D-oriented rendering and third-party license constraints without completing CONTEXT or authorizing IMPLEMENT", "date": "2026-08-21"},
    {"revision": "1.10", "reason": "Human-approved CONTEXT amendment superseding only the revision 1.9 fixed-period recenter direction with an approximately five-second configurable eligibility check and central-deviation threshold, while preserving immediate CENTER, higher-priority STRONG-sweep follow, manual-inspection suppression, incomplete CONTEXT and unauthorized IMPLEMENT", "date": "2026-08-22"},
    {"revision": "1.11", "reason": "Human-approved intermediate CONTEXT checkpoint recording Manual Market, Limit and SL/TP execution/protection semantics, fast two-touch DOM commands, fail-closed uncertainty, partial fills, order visibility and overlays, symbol cleanup and the narrow Manual-Limit reversal exception without completing CONTEXT or authorizing IMPLEMENT", "date": "2026-08-22"},
    {"revision": "1.12", "reason": "Human-approved CONTEXT checkpoint completing the Manual Market, Limit and SL/TP execution/protection research block with anti-bounce versus uncertainty locks, fail-closed degraded-state gates, Market and Limit reversal policies, account-wide realtime truth, origin-independent ordinary-Limit cleanup after confirmed FLAT and a final execution-state matrix while leaving overall CONTEXT active and IMPLEMENT planning and implementation unauthorized", "date": "2026-08-22"},
    {"revision": "1.13", "reason": "Documentation-only IMPLEMENT planning checkpoint decomposing the completed Manual Market, Limit and SL/TP execution/protection block into modular Terminal domain, Bybit adapter, execution-engine, reconciliation, persistence, projection, API and fast-DOM increments with explicit acceptance and test gates while leaving overall CONTEXT active and IMPLEMENT not started or authorized", "date": "2026-08-22"},
    {"revision": "1.14", "reason": "Human-approved corrective checkpoint binding GTC as the ordinary Manual Limit v1 timeInForce, recording truthful terminal AMENDED command completion and the pybit mutation no-retry gate, while Stage 5 remains not started and not authorized", "date": "2026-08-22"},
    {"revision": "1.15", "reason": "Human-approved documentation checkpoint recording default-off persistent AUTO CENTER plus separate one-shot CENTER, one execution gesture state machine with distinct touch and verification-gated mouse mappings, and a separate Telegram-to-MetaScalp new-tab/new-DOM requirement whose official Linking API behavior remains verification-gated; Stage 7 is complete and Stage 8 remains not started and not authorized", "date": "2026-08-22"},
    {"revision": "1.16", "reason": "Human-approved corrective documentation checkpoint replacing the separate AUTO CENTER and one-shot CENTER controls with one CENTER control whose single activation centers once, double activation centers and enables visible-border LOCKED CENTERING, repeated double activation or manual DOM navigation disables the lock, and whose double-activation recognition remains independent of the 300-ms trading anti-bounce; all revision 1.15 MetaScalp and input-device decisions remain unchanged and Stage 8 remains not started and not authorized", "date": "2026-08-22"},
    {"revision": "1.17", "reason": "Human-approved documentation checkpoint selecting the React 19 TypeScript Vite frontend toolchain, recording desktop DOM/chart Limit and confirmed Market interactions, a 500-ms long press, fail-closed fast-order safety, reversible pending Limit-line edits, coin-quantity position authority and the superseding Paper-first execution architecture; CENTER 300-ms mouse and 350-ms touch windows remain proposals pending verification, chart and L2 boundaries remain unresolved, and Stage 8 remains not started and not authorized", "date": "2026-08-22"},
    {"revision": "1.18", "reason": "Human-approved final pre-Stage-8 documentation checkpoint binding CENTER mouse/touch timings, same-price multi-order aggregation and touch-safe identity markers, symbol-scoped quick volume, the authoritative normalized Bybit L2 market-data boundary, L2-based Market preview and Paper market execution, fail-closed book health, a bounded unresolved resting-Limit fill model and a required future secret exposure audit without starting Stage 8, implementing runtime behavior or introducing real credentials", "date": "2026-08-22"},
    {"revision": "1.19", "reason": "Human-authorized Stage 8 Block 1 only checkpoint implementing and verifying the terminal/frontend React 19 TypeScript Vite foundation, structural PAPER/non-live workspace shell, Tailwind 4 styling, normalized frontend market-data boundary and focused tooling while leaving all functional DOM, L2, Paper Engine, chart, live trading, credential, MetaScalp and later Stage 8 work not implemented and separately authorization-gated", "date": "2026-08-22"},
    {"revision": "1.20", "reason": "Documentation-only checkpoint recording the current Fast DOM client-slice baseline: dedicated high-frequency state path, non-trading DOM mouse navigation, preserved CENTER behavior, individual same-price order dots with per-order cancellation and extreme-left aggregate USDT, Bybit V5 depth-50 orderbook plus separate publicTrade baseline, depth-extensible normalized contracts and explicit deferral of order-creation clicks and further trading mouse semantics without starting implementation", "date": "2026-08-22"},
    {"revision": "1.21", "reason": "Documentation-only checkpoint recording one shared 3-in-1 Trading Workspace with Terminal, Autopilot and Editor lower-panel modes, preserved workspace state, non-mutating mode navigation, lower-panel cross-mode buttons, key-icon account access including Paper, prototype-gated responsive header decisions and Fast DOM prototype delivery priority without Robot or Editor design, production implementation or changed Stage 8 authorization", "date": "2026-08-22"},
    {"revision": "1.22", "reason": "Explicit human authorization for only the smallest runnable Stage 8 Fast DOM client slice on the existing React TypeScript Vite foundation: shared three-mode shell, real chart surface, interactive non-trading DOM and Tape, deterministic labelled development market feed behind normalized boundaries, CENTER behavior, own-order fixture rendering, Paper account access location and focused tests; Robot, real credentials, trading execution, complete Editor and all deferred scope remain unauthorized", "date": "2026-08-22"},
    {"revision": "1.23", "reason": "Recorded the authorized runnable Fast DOM client slice as implemented and verified: shared state-preserving three-mode shell, SVG candlestick chart, compact interactive non-trading DOM and Tape, CENTER lock/manual movement, same-price Paper fixture dots and aggregate cancellation behavior, key-icon Paper account menu, normalized external market-data port with clearly labelled deterministic development feed, responsive layout, four focused tests, clean Biome, successful production build and HTTP 200 local startup smoke check; live Bybit, Robot, real credentials and all trading execution remain deferred", "date": "2026-08-22"}
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

The first execution deliverable is a usable manual Trading Workspace connected to a virtual paper account
and Paper Trading Engine. Real-money Bybit execution and autonomous robot execution are later. `AUTOPILOT`
is visible near the top market context but disabled in v1. Existing Bybit-oriented Stage 0 through Stage 7
contracts remain recorded implementation evidence; this product correction authorizes no runtime change and
requires later planning to route logical commands through the backend-neutral execution abstraction.

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
Revision 1.6 did not silently replace the approved deposit/equity wording. Later explicit human authority in
revision 1.8 binds active-account USDT `walletBalance` as the Manual v1 WV base.

### B. Researched and preferred directions

Terminal is position-mode aware. Revision 1.8 supersedes the earlier Hedge Mode research preference and binds
Manual v1 to One-Way Mode with `positionIdx=0`; independent simultaneous LONG and SHORT exposure and hidden
instant reversal are prohibited. Terminal inspects actual account/symbol position state and never silently
changes the user's Bybit position mode. Exact compatible account setup and diagnostics remain required.

For Working Volume, revision 1.8 binds the previously researched interpretation:

`WV_BASE = active trading account USDT walletBalance`

`raw_1_WV = USDT walletBalance × 5%`

`1_WV = floor(raw_1_WV / 10) × 10 USDT`

This excludes cross-asset `totalEquity`, `totalAvailableBalance`, leverage-adjusted buying power and direct
unrealized-PnL expansion. Leverage remains irrelevant. Exact wallet refresh/cache timing remains open.

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

## 15. Formal execution and reconciliation model

This revision records the human-approved intermediate CONTEXT model for USDT Linear Perpetual manual
trading. Names below describe normalized semantics and invariants, not final class, API, enum or storage
design. REST and WebSocket trade acknowledgements prove request acceptance only; they never prove a fill,
position change or completed cancellation/amendment. A command advances from durable creation and
submission attempt through pending confirmation to private-event or REST-reconciliation confirmation.
Any missing acknowledgement, timeout, transport loss, crash or contradictory evidence after submission
produces an uncertain/reconciliation state rather than an exposure-increasing retry.

### A. TradingCommand and order correlation

Every exposure-affecting command has a durable local `TradingCommand` identity. Create commands also have
a unique Terminal-generated `orderLinkId`, persisted with account, symbol, side, `positionIdx`, immutable
intent and normalized request data before network submission. `orderId` is exchange-assigned evidence
learned later from an acknowledgement, private event or REST recovery. A reused `orderLinkId` never
represents a new economic command.

The normalized order lifecycle distinguishes unknown/reconciling, pending confirmation, open, partially
filled and open, cancel pending, amend pending, filled, cancelled and rejected. Pending-trigger exists only
for applicable conditional orders. Cancelled derivatives orders may retain executions; cancellation never
deletes fill evidence. `Filled`, `Cancelled` and `Rejected` are terminal order states, while cancel-pending
and amend-pending are not. Late or replayed weaker evidence cannot regress a stronger confirmed state,
decrease cumulative filled quantity or invalidate an accepted execution. An execution arriving before an
order event creates or links an unknown/reconciling order projection and is still applied exactly once.

### B. Immutable execution evidence and projections

An exchange execution is immutable economic evidence. Its conceptual durable deduplication identity is:

`(trading_account_id, category, execId)`.

Only a newly accepted execution may change quantity, average entry, realized PnL, fee, engaged Working
Volume, analytics, sounds or chart markers. The same execution received again through WebSocket, REST,
replay or restart is a business no-op. Orders may have multiple executions, and executions discovered late,
after local cancellation or for unknown/external orders remain valid account evidence.

The operational position identity is:

`(trading_account_id, category, symbol, position_idx)`.

For USDT Linear, `position_idx=0` represents the One-Way leg, while Hedge Mode uses the independent long
and short legs represented by `position_idx=1` and `position_idx=2`. Side is validated normalized data but
does not replace the position index in identity. Position projections distinguish unsynchronized, synchronized
empty, synchronized open, reconciliation-required and ownership-conflict semantics. A private position event
is current-state input and is never execution evidence; a position message may exist without an economic
quantity change. Projection convergence combines deduplicated executions, current position snapshots,
order state and ownership metadata through the same execution-state owner.

### C. Origin, controller and external exchange state

Immutable origin/provenance and mutable current controller are separate concepts. Terminal Manual,
external clients and future Robot activity may provide different origins; Manual, future Robot, external,
none or unknown control are separate current-authority states. Exchange orders, executions or positions
without durable Terminal command correlation are never silently claimed as Terminal-origin. External state
still participates in truthful account projections. An unexplained active mixed exposure, reversal or
controller ambiguity creates an ownership conflict and blocks ordinary mutations until reconciled or
resolved by an approved policy. External closure to zero may converge without a continuing ownership
conflict after executions, orders and protection are reconciled.

### D. Reconciliation levels and exposure gates

Reconciliation is normal operation and has four composable levels:

* L1 command/order reconciliation correlates `TradingCommand`, submission attempt, `orderLinkId`, `orderId`,
  order records and executions after timeout, missing acknowledgement or ambiguous command outcome;
* L2 symbol/leg reconciliation rebuilds the affected orders, executions, position and ownership state after
  partial fills, cancel/fill races, event gaps, contradictory projections or external symbol mutation;
* L3 account reconciliation establishes account mode, wallet/Working-Volume input, positions, open orders
  and unsafe symbol conflicts after account-wide staleness, mode change or broad stream loss;
* L4 startup/reconnect reconciliation combines durable uncertain local state with REST account, wallet,
  position, order and execution evidence before private streams resume synchronized operation.

Locks are no broader than safe evidence permits: a bounded L1 may lock one command; unknown economic
impact locks at least its symbol/leg; account mode, wallet authority or broad execution gaps lock the account;
startup initially locks the backend and narrows only after inventory. New exposure requires synchronized
relevant account, symbol and leg, fresh required wallet/instrument evidence, known position mode and no
uncertain command or ownership conflict. Reduce-only and emergency risk reduction are evaluated separately
from new exposure, but are allowed only when current side, size and `positionIdx` are established sufficiently
to prevent reversal, duplicated close or accidental exposure increase.

### E. Crash safety, atomicity and Full Close

Network I/O is outside the storage transaction, so persisted command/attempt state records whether submission
was ready, started, accepted or uncertain. Restart never assumes that absence of a locally saved acknowledgement
means non-submission; it recovers the original `orderLinkId` through order, execution and position evidence.

Applying a normalized execution atomically journals the evidence, enforces its deduplication identity,
persists a new immutable execution, advances order and position projections, applies fee/PnL/WV effects and
updates reconciliation progress. Either all economic effects commit once or none commit. Duplicate evidence
may be journaled diagnostically but cannot repeat business effects. Reconciliation atomically applies missing
executions through the same path, updates projections and origin/controller conflicts, records convergence and
unlocks the scope; unlock cannot precede committed converged state. REST, WebSocket and recovery handlers do
not independently mutate competing business projections.

Full Close is a reducing workflow rather than one acknowledgement. It converges only when authoritative
evidence proves position zero, required remaining symbol orders and SL/TP/protection are removed, all relevant
executions are ingested and final REST reconciliation succeeds. An acknowledgement, one fill, a zero-looking UI
or one position event cannot claim `CLOSED_RECONCILED`.

### F. Formal invariants

1. No blind retry follows an uncertain create, amend, cancel or close submission.
2. Each execution identity changes economic state at most once, including after crash or replay.
3. An acknowledgement is not fill evidence and a position event is not execution evidence.
4. New exposure requires synchronized relevant scope; reduce-risk uses a separate safety gate.
5. `TradingCommand` and unique `orderLinkId` are durable before submission.
6. External state is never silently claimed as Terminal origin, and origin never substitutes for controller.
7. Realtime and reconciliation evidence converge through the same execution-state owner.
8. Order terminal state cannot erase executions; confirmed cumulative fill never decreases.
9. Late weaker evidence cannot regress stronger confirmed evidence or durable terminal state.
10. WebSocket reconnect alone does not restore synchronization; required REST gap recovery remains mandatory.
11. Unlock and converged projection/reconciliation state commit atomically.
12. Full Close succeeds only at zero position plus required order/protection cleanup and final reconciliation.
13. “Known not submitted” requires positive evidence; missing acknowledgement or search miss alone is insufficient.
14. Any automatic reducing action must be incapable of reversing or increasing exposure in the active position mode.

### G. Decisions resolved by later human authority

Revision 1.8 resolves the previously open WV base, position-mode, external-state, Manual-takeover,
Emergency-Close, external-order cleanup and negative-correlation policy directions. Exact numeric refresh,
timeout, retry interval, backoff and search-horizon parameters remain later configurable research/design work;
they do not weaken the recorded safety invariants.

This model is `MANUAL_LIVE_TRADING_V1_EXECUTION_RECONCILIATION_MODEL_RECORDED`, an intermediate CONTEXT
checkpoint. It does not complete CONTEXT, select implementation decomposition, install dependencies, authorize
production work or begin IMPLEMENT.

## 16. Human-approved execution and risk decisions

### A. Binding Working Volume authority

For Manual Live Trading v1, the authoritative Working Volume base is the active trading account's USDT
`walletBalance`:

`raw_1_WV = USDT walletBalance * 5%`.

The approved rounding rule then rounds one WV down to whole tens of USDT. For example, a 3,787-USDT
`walletBalance` produces raw WV 189.35 USDT and binding one WV 180 USDT. Leverage never multiplies WV.
`totalAvailableBalance`, `totalEquity`, BTC/USDC or other asset value and unrealized-PnL-expanded buying
capacity are not WV base. Future sizing uses current authoritative realized `walletBalance` according to a
later refresh/cache policy; this checkpoint does not choose that policy numerically.

### B. Binding One-Way Mode and mode handling

Manual v1 requires Bybit One-Way Mode and `positionIdx=0`. Independent simultaneous LONG and SHORT
positions on one symbol are prohibited. If a LONG exists, a new SHORT exposure is permitted only after an
explicit reducing/close workflow establishes confirmed reconciled zero; the mirrored rule applies from SHORT
to LONG. Hidden instant reversal is prohibited. Terminal and future Robot must not create an independent
opposite position over existing exposure.

Terminal never changes Bybit position mode automatically. An incompatible account/symbol mode blocks new
exposure and produces a clear operator-visible state. Mode correction occurs separately, followed by required
reconciliation before trading is enabled.

### C. External state and reconcile-and-adopt policy

Terminal detects and displays positions, orders, executions and protection created through the Bybit site/app,
MetaScalp or another client. Such state contributes to actual account exposure and risk and retains EXTERNAL
origin or its semantic equivalent. Future Robot receives no automatic external-position ownership or control
without a separate explicit handoff authorization.

When an originally Terminal-created position is changed externally, exchange state is factual:
`RECONCILE_AND_ADOPT / NEVER_FIGHT_THE_EXCHANGE_STATE`. External partial close changes the factual residual;
external volume increase changes factual exposure without relabelling its execution as Terminal-created;
external full close establishes factual zero subject to cleanup/reconciliation; and external SL/TP changes are
adopted after reconciliation. Terminal sends no compensating order merely to restore stale local intent.
External-intervention provenance remains durable evidence for later audit and analytics methodology.

### D. Manual takeover

The OWNER may take a reconciled EXTERNAL position under Manual control. Successful reconciliation and known
actual size, state and protection are prerequisites; uncertainty blocks takeover. Takeover creates no exchange
order, is not a new trade and never rewrites EXTERNAL origin. Only the current controller becomes MANUAL or its
semantic equivalent, after which Manual Terminal may operate within normal safety gates. Future Robot takeover
remains a separate explicit workflow.

### E. Emergency Close

Emergency Close is a separately identifiable and auditable reduce-risk workflow. It closes existing exposure,
must not intentionally create the opposite side and uses the freshest sufficiently confirmed/reconciled size.
Partial execution leaves the factual residual open. Timeout or uncertain outcome prohibits blind retry and
enters reconciliation. If size or direction is insufficiently reliable, the fastest available reconciliation
precedes close submission. Position zero alone is not final success: related orders and protection are checked,
and completion uses the existing `CLOSED_RECONCILED` semantics. Exact UI and API mechanisms remain open.

### F. Full Close and external orders

Ordinary Full Close closes the position, cleans Terminal-owned related orders/protection and reconciles.
External orders are never cancelled silently. If an external active order could reopen a position or increase
exposure after close, Terminal exposes a warning/non-converged state and requires separate OWNER confirmation
before cancelling that external order when cancellation is needed. `CLOSED_RECONCILED` requires confirmed
position zero, Terminal-owned cleanup, inspection and safe disposition of potentially dangerous external
orders, and final reconciliation.

### G. Negative correlation and search horizon

After uncertain create, amend, cancel or close, one negative REST lookup never proves that the exchange
mutation did not exist. Reconciliation correlates available `orderLinkId`/`orderId`, realtime and historical
orders, executions, position and other authoritative exchange state through bounded repeated checks and
backoff. Exact timeouts, intervals, backoff and horizon remain unapproved numeric parameters for later
Bybit-specific testing and should be configurable where appropriate.

Until outcome is proved, state remains outcome-uncertain/reconciliation-required, new exposure in the affected
scope is blocked and blind retry is prohibited. Exhausting the configured horizon does not automatically mean
“not found equals never existed”; the system retains explicit unresolved state for further recovery or OWNER
decision under a later approved policy.

These decisions refine rather than replace revision 1.7. ACK-versus-fill separation, immutable deduplicated
executions, pre-submit command correlation, PositionKey, origin/controller separation, L1-L4 reconciliation,
crash/replay idempotency, synchronized exposure gates and the separate reduce-risk path remain intact.

This amendment records checkpoint
`MANUAL_LIVE_TRADING_V1_HUMAN_EXECUTION_AND_RISK_DECISIONS_RECORDED`. CONTEXT remains active, incomplete and
not verified; no implementation plan or production work is authorized.

## 17. Approved upper workspace, DOM and execution-print direction

Revision 1.9 records the approved visual and product direction for the upper Manual Live Trading v1 workspace.
It preserves revision 1.8 and the existing lower trading panel requirements. The upper workspace is deliberately
minimal: the primary live chart is on the left and a narrow collapsible market-depth panel is on the right. The
right panel contains DOM/order-book levels and a realtime execution-print visualization. Trading controls, active
Limit orders, SL/TP and the other already approved Manual controls remain below and are not redesigned here. No
additional cards, execution tables, analytics widgets, large controls or Robot UI belong above the trading panel.

### 17.1 Collapse and shared market-data lifecycle

A small unobtrusive arrow control between chart and panel collapses the panel to the right and restores it on a
second activation. While closed, the chart expands into the released width. Hidden DOM and prints must not keep
performing expensive rendering. Their visual subscription or processing may suspend when no other active Terminal
function needs the data. When order-book data is also required for active sizing or liquidity checks, one normalized
market-data source is shared rather than duplicated. Exact frontend animation, state and subscription mechanics are
implementation details.

### 17.2 DOM semantics

The DOM presents bounded price levels around the spread. The approved preferred prototype viewport is approximately
twenty ASK levels above the spread and twenty BID levels below it. This is a UI viewport default, not the full local
book, and may adjust responsively on very small screens so that rows remain readable. Every visible level contains at
least price, resting limit liquidity/size and a proportional visual depth fill. Small, medium and large liquidity must
remain visually distinct; one extreme level must not destroy the useful scale of the remaining levels. Exact row
height, responsive adjustment and normalization parameters remain feasibility and UX details.

### 17.3 Execution prints and sweep evidence

A print represents an actual aggressive exchange execution, not a resting limit order. Buyer-initiated executions
are green and seller-initiated executions are red. New prints appear near their execution price while older prints
move left to preserve a short bounded visual history. Each print is a circle or vertically elongated ellipse, displays
an understandable execution volume, preferably USDT/USD-equivalent for USDT Linear, and uses a clamped size scale
that keeps small prints visible and prevents extreme prints from covering the workspace. Exact linear, nonlinear or
logarithmic scaling is not yet binding.

When sufficiently trustworthy evidence shows an aggressive flow consuming several resting levels, a sweep ellipse
may span the consumed price range: from the pre-execution best bid down to the final consumed bid for a sell, or from
the pre-execution best ask up to the final consumed ask for a buy. An exchange public-trade event is not assumed to
equal one original market order. Exchange executions remain distinct from a locally reconstructed aggressor-sweep
episode. Reconstruction requires sequenced L2 state immediately before executions, public trade evidence, consumed
levels and resulting book state, including reconnect and resync handling. Multiple trades, concurrent cancellations,
drops or ordering ambiguity can make the path unprovable. In that case the UI must show an ordinary volume-sized
print at the factual execution price, or another clearly non-sweep representation, and must never invent consumed
levels.

### 17.4 Compact position indicator

The upper market-depth area may contain only a compact indicator for an open Manual position. LONG uses an obvious
upward direction arrow; SHORT uses an obvious downward direction arrow, with the approved reference showing the
SHORT arrow in red. Positive PnL is green and negative PnL is red, for example an arrow with `+1.5%`. There is no
large position card in the upper area.
The indicator reuses authoritative reconciled position/account state; this revision does not define or replace the
PnL formula.

### 17.5 Performance constraints and unresolved research

The mobile Telegram Mini App and future web runtime require bounded DOM depth, bounded print retention, no unbounded
in-memory tape, incremental updates where practical, trustworthy reconnect/resync, usage-aware subscriptions, no
unnecessary hidden-panel rendering and responsive chart interaction. DOM depth, depth-fill scaling, print scaling,
sweep correlation/aggregation window, cancellation-versus-execution ambiguity, update batching, rendering frequency,
hidden-panel subscription lifecycle and mobile feasibility remain research-required. Research must also determine the
exact depth, gap-detection and correlation rules, confidence thresholds and whether real-world feed behavior supports
reliable multi-level sweep reconstruction at acceptable Mini App performance.

The unresolved research set is explicitly: responsive visible depth around the preferred 20+20 starting viewport;
final working and calculation depth beyond the preferred `orderbook.50` candidate; usefulness of 200/1000 depth;
exact gap-detection rules; sweep correlation window and confidence thresholds; treatment of same-sequence
multi-message trades; a possible distinct PROBABLE visualization; exact recenter interval and inactivity timeout;
sweep-follow animation; DOM percentile/window/hysteresis; print-scaling window; bounded tape retention; UI update
batching and render frequency; hidden-panel unsubscribe/grace behavior; book-walk depth source; x10/x100 compression
implementation and performance; third-party vendoring policy; historical heatmap need; and mobile Telegram Mini App
performance measurements.

### 17.6 Normalized public market-data boundary

The preferred architecture is a Bybit public market-data adapter feeding one normalized market-data owner per active
symbol/session. That owner reconstructs a trustworthy L2 book and retains bounded public trades, then supplies the
DOM renderer, execution tape, sweep reconstruction and Manual pre-trade book-walk/market-impact preview. DOM, tape
and other UI components must not open independent exchange subscriptions or connections. The UI does not parse raw
Bybit payloads, apply book deltas, determine sequence integrity, classify sweep confidence, perform book walk or own
exchange subscription lifecycle.

`bybit_api.py` remains the Scanner-oriented public OHLCV/instrument boundary and does not become the owner of the
Terminal live-L2 lifecycle. Scanner signal contracts are not live DOM/trade contracts, and the shared immutable
Scanner-to-Terminal SignalSnapshot remains separate. Public market executions are not private account executions:
the ExecutionEngine remains the trading/account-state owner, while normalized public market data is reusable
Terminal infrastructure consumed by DOM, tape, sweep and book-walk functions.

### 17.7 Bybit evidence, sweep confidence and resynchronization

Bybit V5 public L2 and `publicTrade` provide sufficient evidence for confidence-graded reconstruction through book
snapshot/delta data, update identifier `u`, cross sequence `seq`, book timestamp `cts`, public-trade timestamp `T`,
taker side `S`, price, volume, trade identity and trade sequence. A public L2 delete/update cannot by itself prove
fill rather than cancellation. A reconstructed sweep therefore remains evidence-based reconstruction and never a
guaranteed identity of one originating market order.

Conceptual confidence classes are `STRONG`, `PROBABLE`, `AMBIGUOUS` and `INVALID/GAP`. Only `STRONG` public evidence
permits the approved stretched MetaScalp-like ellipse in the v1 direction, and even that does not prove that all
executions belonged to one original market order. `PROBABLE` does not draw a stretched ellipse by default; a future
distinct representation requires separate approval. `AMBIGUOUS` renders an ordinary volume-sized print at the
factual execution price. `INVALID/GAP` disables sweep reconstruction.

On a sequence gap, reconnect or resnapshot, pending correlation windows are invalidated, trusted sweep rendering
stops, and local L2 is restored from a new authoritative snapshot. Reconstruction resumes only after trustworthy
state is re-established, and no sweep episode crosses a resynchronization boundary.

No exact or near-exact open-source implementation of the approved pre-event-BBO-to-last-consumed-level stretched
execution ellipse was confirmed in the researched projects. Sweep reconstruction consequently remains
BybitScanner-specific Terminal functionality over normalized L2 and public-trade evidence.

### 17.8 Reusable Manual book walk and visual scaling directions

The preferred Manual BUY/SELL preview walks the opposing sorted book level by level for the requested USDT notional,
allows a partial final level, and returns estimated filled quantity, VWAP/average fill, worst fill price, estimated
slippage, levels consumed and available/insufficient-depth status. This is an estimate, not an execution guarantee.
The independently adapted direction is informed by OpenBook and must use Bybit semantics, `qtyStep`, instrument
limits, Decimal-safe arithmetic, snapshot freshness/sequence and applicable exchange constraints. It does not design
or authorize Robot behavior.

The preferred non-binding DOM scale uses a rolling/recent high-percentile liquidity reference, normalization of
visible levels, a `0..1` clamp and an optional mild gamma or square-root visual transform. One extreme level must not
make the other rows visually empty. Bids and asks are not normalized independently without an explicit reason,
because separate scales can hide real imbalance. Exact percentile, window and hysteresis remain unresolved.

For prints, visual area should be approximately proportional to USDT notional, giving a base circle radius roughly
proportional to its square root, with rolling-percentile normalization, a minimum visible size and a maximum clamp.
Exact notional remains visible numerically. A stretched sweep ellipse uses width for execution/notional magnitude
and height for the trustworthy consumed price span; height must not simultaneously encode volume.

### 17.9 Rendering, bounded state and external reuse policy

The preferred v1 rendering direction is Canvas2D for DOM and prints/tape, with HTML/CSS/React for low-frequency
semantic UI. High-frequency market state stays in mutable bounded stores or references outside React render state,
and feed events are coalesced to at most one visual repaint per animation frame. This amendment selects no frontend
library. WebGL is not a v1 foundation; it remains an upgrade path for a future historical-liquidity heatmap or large
retained time-price surface only if performance evidence requires it.

Visible DOM, trade/print history and correlation windows are bounded; no unbounded historical accumulation is
permitted. Rendering lifecycle is separate from feed lifecycle, so hiding the panel stops expensive rendering while
the shared feed may remain active for another consumer. External projects' retention defaults are not adopted
automatically.

External research established: Flowsurface is GPL-3.0 and defaults to reference-only use; FlowMap is Apache-2.0 and
may be adapted only with required attribution, NOTICE/license and change obligations; eTape is MIT and may be
adapted with its required notice; OpenBook is MIT and its book-walk algorithm is a strong independent-adaptation
candidate; OrderFlowMap is MIT and small scaling/rendering ideas may be adapted. No external source is vendored or
copied by this amendment. Any later reused or adapted third-party code must retain a provenance and license inventory.

### 17.10 DOM viewport, working depth and navigation

Visible depth, local working depth and calculation depth are separate concerns. The Canvas renderer draws the
approximately 20 asks plus spread plus 20 bids viewport and only minimal transition context. The normalized
market-data owner may keep a deeper reconstructed book. Bybit `orderbook.50`, providing up to 50 asks and 50 bids,
is the preferred starting candidate: off-screen levels form an immediately available working margin when price or a
sweep moves beyond the viewport. This is not yet the final binding feed-depth choice, and local 50+50 availability
does not require rendering all one hundred rows.

Manual book-walk and market-impact calculations are not limited to the visible 20+20 levels. They may use 50, 200,
1000 or another suitable trustworthy Bybit depth source when a reliable estimate needs it, while the UI continues to
show the narrow viewport. Exact calculation depth remains unresolved pending feasibility evidence.

The DOM seeks to keep the spread near the central viewport area without recentering on every tick. Approximately
23 seconds is an approved preferred initial configurable UX value for periodic recentering when the user is not
interacting, no higher-priority sweep-follow behavior is active and market data is trustworthy. It is not a permanent
hard-coded constant. A small unobtrusive CENTER/recenter control immediately returns the current spread to the central
area; exact icon and motion remain UI details.

Manual scroll or pan temporarily suspends automatic recenter/follow so the viewport is not taken from the user. Auto
behavior may resume after configurable inactivity, or the user may restore it immediately with CENTER. Exact inactivity
timeout remains UX research. If a trustworthy active `STRONG` sweep extends beyond the current viewport, the DOM
immediately follows far enough in the sweep direction to show its continuation and last trustworthy consumed level.
After the sweep, normal spread-centering may return later. Exact snap or animation behavior remains unresolved.

The conceptual viewport priority is: explicit user interaction/manual inspection; trustworthy active `STRONG` sweep
follow; explicit CENTER command; periodic spread recenter. This preserves product intent rather than defining a final
frontend state machine: automation must neither interrupt inspection nor hide a meaningful sweep.

### 17.11 Optional presentation compression and prototype tuning

Price-scale controls `x1`, `x10` and `x100` are an optional deferred capability, not a requirement for the first usable
Terminal build. `x1` is normal exchange price-step presentation. `x10` and `x100` conceptually aggregate about ten or
one hundred adjacent price ticks into one visual bucket, combining bucket liquidity and projecting prints and sweeps
onto that scale. Compression is presentation over the same authoritative normalized L2, not another order book or
WebSocket connection, and must not degrade underlying state. Bucket price representation, rounding, print/sweep
projection, performance and UX remain unresolved. The first usable build may ship only `x1` while preserving a clean
future extension point.

Hands-on evaluation with a working DOM prototype is required for the 20+20 viewport, row height, approximately
23-second recenter value, recenter motion, interaction suspension, sweep follow, `orderbook.50` working candidate,
need for deeper calculation data and x10/x100 usefulness. These must remain configurable or replaceable without
redesigning the normalized market-data core. Existing bounded state, incremental updates, maximum one repaint per
animation frame and no-duplicate-subscription constraints remain binding directions.

This direction does not select chart or DOM libraries, redesign the chart or lower controls, implement frontend or
runtime behavior, create Robot contracts, expand AUTOPILOT, or change Scanner behavior. It remains compatible with
One-Way Mode, WV authority, reconcile-and-adopt, external-state visibility, Manual takeover, Full Close, Emergency
Close, draggable Limit/SL/TP lines and exchange-confirmation visual states.

This amendment records checkpoint
`MANUAL_LIVE_TRADING_V1_UPPER_WORKSPACE_DOM_PRINTS_DIRECTION_RECORDED`. CONTEXT remains active, incomplete and
not verified; no implementation plan or production work is authorized.

## 18. Threshold-based DOM recenter amendment

Revision 1.10 supersedes only the revision 1.9 periodic recenter timing direction. The former approximately
23-second periodic recenter value is historical and no longer governs product behavior. The DOM must not move
mechanically on a fixed interval. Preferred prototype behavior checks approximately every five seconds whether
recenter is needed. Five seconds is an initial configurable minimum/check interval, not a permanent hard-coded
constant. If spread remains sufficiently close to the central viewport zone, the DOM does not move; it recenters only
when spread deviation exceeds the configured central dead zone. This periodic eligibility check plus deviation
threshold is intended to avoid unnecessary visual movement.

The approved CENTER control remains immediate and does not wait for the periodic check. Trustworthy active `STRONG`
sweep follow remains higher priority and moves the viewport immediately when the last trustworthy consumed level
would otherwise be outside the visible window. Manual scroll, pan or inspection continues to suppress automatic
recenter/follow under the approved interaction policy so automation does not take the viewport from the user.

Exact check interval, deviation threshold, central dead-zone size, recenter animation or snap and inactivity timeout
remain configurable and unresolved until hands-on DOM prototype testing. The architecture must allow these values to
be tuned without redesigning normalized market-data infrastructure. Revision 1.9 remains otherwise intact, including
the preferred 20+20 viewport, `orderbook.50` working-depth candidate, separation of display, working and calculation
depth, STRONG-only stretched ellipse, confidence and resync rules, Canvas2D direction, optional deferred x1/x10/x100
compression, normalized market-data ownership, lower trading panel, Scanner boundary and Robot exclusion.

This amendment records checkpoint `MANUAL_LIVE_TRADING_V1_THRESHOLD_RECENTER_POLICY_RECORDED`. CONTEXT remains
active and incomplete, and no implementation plan or production work is authorized.

## 19. Manual Market, Limit and SL/TP execution/protection checkpoint

Revision 1.11 records the approved Manual execution and protection behavior below as product and safety semantics,
not implementation decomposition, API design or frontend state-machine design.

### 19.1 Market preview and fast DOM execution

Manual Market actions use the normalized trustworthy DOM for an estimated book-walk/slippage preview where current
depth is sufficiently fresh. The preview remains an estimate rather than an execution guarantee. Fast two-touch DOM
execution uses a held order-side control and a second tap on a price level:

* while BUY ORDER is held, tapping a BID level creates a BUY LIMIT at that price, while tapping an ASK level submits
  an immediate MARKET BUY without another confirmation;
* while SELL ORDER is held, tapping an ASK level creates a SELL LIMIT at that price, while tapping a BID level submits
  an immediate MARKET SELL without another confirmation.

The default quick-order volume is one Working Volume. Double-tapping BUY ORDER or SELL ORDER opens adjustment of that
side's quick-order dollar volume; exact control presentation is not decided here. An anti-bounce interval of 300 ms
ignores execution taps repeated too quickly. This UI suppression is not exchange idempotency and does not weaken
durable command identity, correlation, reconciliation or fail-closed safety.

### 19.2 Fail-closed submission and partial fills

If submission outcome or trading connectivity is uncertain, no blind retry is permitted: missing a trade is safer
than risking a duplicate position. A Market partial fill is accepted as factual execution and is not automatically
completed by another Market order. A Limit partial fill creates or updates the Position for the executed quantity;
the unfilled remainder continues as an active Limit until exchange-confirmed fill, cancel, expiry or other authoritative
transition.

Market opposite-side execution cannot reverse a position in one action. Its executable quantity is capped at the
confirmed remaining position quantity and may reach FLAT only; a separate later action may open new opposite exposure.
Manual Limit orders are the narrow approved exception to revision 1.8's general no-hidden-reversal direction: a Limit
may close existing exposure and its remaining quantity may open an opposite position under Bybit One-Way semantics.
This exception applies only to the explicitly placed Manual Limit; it does not permit Market reversal, hidden automatic
reversal or competing long/short legs.

### 19.3 Position-close cleanup and account-wide Limit visibility

When a Manual Position closes through Market, SL or TP, remaining applicable Limit orders for the current symbol enter
the approved automatic cleanup and reconciliation workflow. Terminal-owned related Limits are cancelled automatically.
External Limits are detected and shown but retain the revision 1.8 rule: they are never silently cancelled; where an
external order can reopen or increase exposure, cleanup remains non-converged until required OWNER confirmation and
authoritative cancellation/reconciliation. The UI never claims safe completion while a dangerous remainder persists.

Manual Terminal displays all active Limit orders for the selected Bybit account and current symbol, including orders
created by this Terminal, Bybit UI/API, MetaScalp or another client. Origin/provenance remains truthful and is not
rewritten. Bybit is authority for current Position, Order and Execution state; local projections converge through
startup/reconnect and event-gap reconciliation. New execution commands remain blocked whenever required account,
symbol, position, order or protection state is not trustworthy.

### 19.4 Command, Order, Execution and Position distinction

A Command is durable user intent and submission lifecycle; an Order is the exchange instruction and its remaining
quantity/status; an Execution is immutable deduplicated fill evidence; a Position is the reconciled current exposure
projection. REST or WebSocket acknowledgement is acceptance evidence, not final execution state. These semantics reuse
the revision 1.7 execution-state owner, idempotency, reconciliation and non-regression invariants.

### 19.5 Own-Limit DOM and chart representation

An own or Manual-controlled Limit is represented at its DOM price by a large direction-colored dot on the left and a
direction-colored remaining dollar volume within the row. The resting-depth visualization is shifted to the right,
with price values farther right beyond the main depth area. Tapping the dot immediately initiates cancel without an
additional confirmation, but the indicator and matching chart Limit-line disappear only after exchange-confirmed
cancellation or reconciliation. Pending, rejected and uncertain cancel outcomes retain truthful pending/error state
rather than pretending removal.

### 19.6 Protection direction and retained research references

Automatic preset SL/TP for Manual entries remains a future-capable idea, not a current Terminal v1 priority or binding
requirement. Existing manually controlled exchange-side SL/TP, confirmation, overlay, reconciliation and cleanup
semantics remain unchanged.

Related external research is retained as reference rather than dependency selection: Freqtrade informs lifecycle,
dry-run, persistence, locks and recovery patterns; Hummingbot informs connector, order tracking, user-stream and retry
patterns; OpenAlgo Charts informs chart-trading and drawing interaction; professional DOM systems inform rapid
price-level interaction and order visualization. Official Bybit V5 documentation remains authoritative for actual
order, execution, position, `orderLinkId`, limits and TP/SL behavior. No external project is adopted, vendored or made
an implementation dependency by this checkpoint.

This amendment records checkpoint `MANUAL_MARKET_LIMIT_SLTP_EXECUTION_PROTECTION_RECORDED`. CONTEXT remains active,
incomplete and not verified; implementation is not started or authorized.

## 20. Manual execution/protection completion decisions

Revision 1.12 completes the approved product and safety model for the Manual Market, Limit and SL/TP
execution/protection CONTEXT block. It refines revision 1.11 without starting implementation or selecting concrete
classes, endpoints, storage schema or UI framework.

### 20.1 Fast-input safety and command uncertainty

The execution anti-bounce interval is 300 ms. After an accepted execution tap, additional execution taps inside that
interval are ignored. Anti-bounce is only local fast-input suppression; execution uncertainty is a separate durable
safety lock. Expiry of 300 ms never permits a potentially duplicate command while the preceding execution command is
`UNKNOWN` or `RECONCILING`.

Every execution command has a unique durable identity and uses an appropriate Bybit client/order correlation identity,
such as `orderLinkId` where the final current API design supports it. Timeout, lost response, unstable transport or
ambiguous evidence transitions to `UNKNOWN/RECONCILING`, never blind retry. Potentially conflicting or duplicate
exposure remains blocked until actual Bybit Order, Execution and Position evidence reconciles the command. The safety
preference is an intentionally missed trade over duplicate or unintended exposure. A partial Market execution is not
automatically chased with another Market command.

### 20.2 Degraded-state risk gate and Market/Limit reversal

When trading state is degraded, unknown or reconciling, new entries, scale-in, exposure increases, new
exposure-increasing Limits and blind retries are blocked. Risk reduction may remain available only when current side,
size and state are sufficiently confirmed to guarantee bounded behavior: emergency Market Close, reduction of an
existing Position and cancellation of active Orders. Emergency Market Close is capped or reduce-only against the
confirmed remainder and cannot create reversal. If an earlier emergency close is `UNKNOWN`, another blind close is
blocked until reconciliation. OFFLINE never simulates successful execution or closure when Bybit confirmation is
unavailable.

Market opposite-side quantity is capped at the confirmed Position remainder and may reduce only to FLAT; requested
excess is discarded rather than opening reversal. A separate user action after confirmed FLAT may create opposite
exposure. Manual Limit semantics intentionally differ: a Manual Limit may close existing exposure and its remaining
quantity may open the opposite Position under the recorded One-Way policy.

### 20.3 Realtime account truth and reconciliation

Terminal displays every active Limit for the selected Bybit account and current symbol regardless of origin: Terminal,
Bybit UI/API, MetaScalp or another external client. Origin and ownership remain audit/reconciliation metadata and never
hide actual account Orders. Position or active-Order changes made externally while Terminal runs are adopted from
exchange state and update normal realtime UI/state without requiring manual Refresh.

WebSocket supplies realtime updates. Startup and reconnect reconciliation restore and compare at least Position, Open
Orders, relevant TP/SL or conditional state and Executions needed to resolve ambiguity. A Position WebSocket message is
not automatically evidence of a size change without comparison to factual state. Available Bybit identities and
sequencing are used for correlation where applicable. Terminal returns ONLINE only when authoritative state is
non-contradictory; otherwise new-exposure locks remain active.

### 20.4 Confirmed-FLAT ordinary-Limit cleanup

When the Manual Position for the current symbol is authoritatively confirmed FLAT because of Market close, Stop Loss
or Take Profit, Terminal automatically initiates cancellation of all remaining ordinary active Limit Orders for that
symbol on the selected account. The closing execution may originate from Terminal, Bybit, MetaScalp or another
external execution interface. This revision supersedes the revision 1.11 OWNER-confirmation exception only for this
confirmed-FLAT ordinary-Limit cleanup: ordinary Limits of every origin are included automatically.

Cleanup is symbol-scoped and never touches Orders for other symbols. It does not silently generalize ordinary-Limit
cleanup to TP/SL or conditional Orders; those require their separately recorded protection rules. Cancel acknowledgement
is not final cancellation. Exchange state confirms disappearance. If a Limit fills during the race between FLAT and
cancel, its Execution and resulting Position are accepted as factual Bybit state, surfaced and reconciled rather than
hidden by the cleanup workflow.

### 20.5 Final conceptual execution-state matrix

| Trading state | New entry / scale-in | Reduce / close | Cancel | New Limit / retry | Exit condition |
| --- | --- | --- | --- | --- | --- |
| `ONLINE` | Allowed | Allowed | Allowed | New Limit allowed | Remains ONLINE while required state is trustworthy |
| `DEGRADED` | Blocked | Allowed only when safely bounded | Allowed | Exposure-increasing Limit blocked; blind retry blocked | Authoritative evidence restores consistency |
| `UNKNOWN EXECUTION` | Duplicate or conflicting exposure blocked | Safe risk reduction may remain available from confirmed state | May remain available | Blind retry blocked | Command reconciliation resolves actual outcome |
| `RECONCILING` | Blocked | Risk reduction only when safely bounded | Allowed when safe | New exposure blocked | Authoritative reconciliation is complete and non-contradictory |
| `OFFLINE` | No execution may be represented as successfully completed | No close may be represented as successful without exchange confirmation | No cancellation may be represented as final without exchange confirmation | No optimistic success | Connectivity plus required reconciliation restores ONLINE |

The matrix does not weaken the separate Command, Order, Execution and Position meanings, immutable execution dedup,
acknowledgement-not-fill invariant or startup/reconnect exposure gates.

### 20.6 Completion assessment

The Manual Market / Limit / SL-TP Execution and Protection CONTEXT block is `SUFFICIENTLY_RESEARCHED` and complete for
transition to a future IMPLEMENT planning step. No concrete blocker remains before planning this block: the required
product behavior, authority, uncertainty policy, reconciliation inputs, state gates, cleanup, partial-fill and reversal
semantics are recorded. Concrete API calls, internal names, persistence layout, tunable timing and acceptance-test
decomposition belong to separately authorized IMPLEMENT planning and verification, not to additional product research.

This completion applies only to this CONTEXT block. The overall Trading Workspace CR remains `IN_PROGRESS` in
`CONTEXT / RESEARCH` because other documented context areas remain open. IMPLEMENT planning is not authorized by this
checkpoint, IMPLEMENT is `NOT_STARTED_NOT_AUTHORIZED`, and Robot remains out of scope.

This amendment records checkpoint `MANUAL_EXECUTION_PROTECTION_CONTEXT_SUFFICIENT_FOR_IMPLEMENT_PLANNING`.

## 21. Manual execution/protection IMPLEMENT plan

Revision 1.13 is planning only for the bounded Manual Market, Limit and SL/TP execution/protection block completed in
revision 1.12. It preserves all approved product semantics and does not authorize or begin production implementation.

### 21.1 Architectural and package boundaries

The minimum clean direction is one local `terminal/` Python package inside the existing repository and one backend
process boundary for the Terminal application. No microservices, broker or external queue are required for v1. Likely
module boundaries, subject to final naming review at authorization, are:

* `terminal/domain/`: pure versioned command, order, execution, position, protection, connectivity and projection
  contracts; identifiers; states; transition invariants; quantity/price policies; no pybit, HTTP, database or UI;
* `terminal/application/trading_application.py`: command entry boundary used by REST/UI; validates ownership and routes
  admitted intent through PreTradeGuard into the single execution-state owner;
* `terminal/application/execution_engine.py`: sole owner of command/order/execution/position/protection business-state
  transitions from REST acknowledgements, normalized private events and reconciliation;
* `terminal/application/pretrade_guard.py`: synchronized-account, instrument, WV, mode, exposure and uncertainty gates;
* `terminal/application/reconciliation.py`: L1-L4 orchestration that queries exchange evidence and submits normalized
  evidence back through ExecutionEngine rather than mutating projections independently;
* `terminal/application/projections.py`: normalized account/symbol DOM/chart/API projections derived from engine state;
* `terminal/exchange/bybit_v5_adapter.py`: authenticated REST/private-WS transport, payload normalization and transport
  errors only; no business projection ownership;
* `terminal/exchange/public_market_data.py`: interface to the separately planned normalized L2/tape owner used by
  preview and DOM; it must not turn Scanner `bybit_api.py` into a Terminal live-market-data lifecycle owner;
* `terminal/persistence/sqlite_store.py` plus schema/migration definitions: one controlled SQLite/WAL transaction
  boundary for command attempts, raw evidence, immutable executions, projections and reconciliation state;
* `terminal/api/`: REST command/snapshot and backend WebSocket event boundary; handlers never mutate trading state
  directly and expose normalized vocabulary rather than raw Bybit status;
* a future Terminal client workspace consumes those API/projection contracts. Its exact frontend filesystem/toolchain
  path is selected by the broader frontend checkpoint; no UI framework dependency is authorized here.

Existing `bybit_api.py` remains Scanner public OHLCV/instrument support and is not reused for authenticated execution.
Existing `contracts/signal_contract.py` remains Scanner signal evidence and is not a live order contract. Current
`chart.py`, `chart_clean.py` and `analyzer/charts.py` remain static Scanner rendering. `pybit==5.17.0` may be used behind
the adapter after method-shape verification; no other current module safely owns execution state or trading persistence.

Responsibility stays explicit: UI creates intent; TradingApplication admits a durable command; Bybit owns exchange
Orders and Executions; immutable Execution evidence updates Position through ExecutionEngine; reconciliation feeds the
same owner; ConnectivityGate controls permissions; DOM/chart projections are read models only.

### 21.2 Bybit V5 adapter plan and verification gate

Before implementation, current official Bybit V5 documentation and installed pybit signatures must be revalidated.
The presently verified USDT Linear direction is:

* create Market/Limit: `POST /v5/order/create`, `category=linear`, One-Way `positionIdx=0`, unique persisted
  `orderLinkId` (maximum 36 supported characters), with Market `slippageToleranceType` `TickSize` or `Percent` and
  separately approved/configured tolerance; acknowledgement is asynchronous;
* amend/cancel: `/v5/order/amend` and `/v5/order/cancel`, correlated by `orderId` or `orderLinkId`, with WebSocket or
  reconciliation confirmation; symbol-scoped cleanup first inventories ordinary orders and cancels only that set,
  rather than using an unfiltered cancel-all that could mix conditional protection;
* read recovery: `/v5/order/realtime` for paginated active/recent Orders, `/v5/order/history` when required,
  `/v5/position/list` for Position, `/v5/execution/list` for missed Executions and
  `/v5/market/instruments-info` for status, `tickSize`, `qtyStep`, `minOrderQty`, `minNotionalValue`,
  `maxOrderQty` and `maxMktOrderQty`;
* private realtime: category-specific `order.linear`, `execution.linear` and `position.linear` topics normalized into
  internal events. Position messages are snapshots/updates, not fill evidence; executions use `execId` deduplication;
* protection: `/v5/position/trading-stop`, `positionIdx=0`, planned full-position exchange-side TP/SL where applicable;
  Full mode supports Market TP/SL and system orders track position size, but one-sided modification can break paired
  binding and therefore requires snapshot/reconciliation handling;
* emergency close: opposite side, quantity capped to confirmed remainder, `reduceOnly=true`, with no duplicate submit
  after unknown outcome. Exact close parameter combination and current exchange maximum behavior are verified before
  implementation rather than inferred;
* startup/reconnect: establish private connectivity, query Position/Open Orders/protection and required execution
  history, correlate local uncertain commands, then unlock only a non-contradictory account/symbol state.

Market preview consumes the normalized public book and remains informational. Exchange-side slippage tolerance is the
execution protection boundary; its type/value is explicit configuration/human approval, never a hidden magic number.

### 21.3 Explicit execution-state model

The implementation separates command lifecycle from exchange-order projection but exposes this normalized combined
planning vocabulary:

| Current | Evidence/event | Next | Authority/invariant |
| --- | --- | --- | --- |
| `LOCAL_INTENT` | PreTradeGuard admits and durable identity is committed | `ADMITTED` | Local durable transaction |
| `ADMITTED` | Submission-attempt record committed immediately before I/O | `SUBMITTING` | ExecutionEngine/store |
| `SUBMITTING` | REST accepts request and returns identifiers | `ACKNOWLEDGED` | REST acceptance only; never fill |
| `SUBMITTING` | Positive known rejection/no submission evidence | `REJECTED/FAILED` | Guard, transport proof or exchange rejection |
| `SUBMITTING` | Timeout/lost response/ambiguous crash | `UNKNOWN` | No retry; reconciliation required |
| `ACKNOWLEDGED` | Order event/snapshot shows active Limit | `OPEN` | Private Order event or REST reconciliation |
| `ACKNOWLEDGED` or `OPEN` | New deduplicated fill with leaves | `PARTIALLY_FILLED` | Execution evidence; Position updates once |
| `ACKNOWLEDGED`, `OPEN` or `PARTIALLY_FILLED` | Filled quantity complete | `FILLED` | Deduplicated executions plus Order evidence |
| `OPEN` or `PARTIALLY_FILLED` | Cancel intent durably admitted | `CANCEL_PENDING` | Local intent; UI remains pending |
| `CANCEL_PENDING` | Confirmed exchange cancellation | `CANCELLED` | Order event or REST reconciliation |
| Any non-final submitted state | Contradictory/gapped evidence | `RECONCILING` | Reconciliation coordinator via engine |
| `UNKNOWN` | Correlated Order/Execution/Position evidence | Confirmed applicable state or `RECONCILING` | Bybit evidence, non-regressive |
| `RECONCILING` | Complete non-contradictory evidence committed | Applicable confirmed state | Atomic convergence/unlock |

`FAILED` is reserved for known local/pre-submit failure; `REJECTED` is authoritative exchange rejection. Market
partial fill followed by exchange cancellation preserves the Execution and terminal Order outcome without retry.
Final states never erase fills, and late weaker events cannot regress stronger confirmed state.

### 21.4 Connectivity and risk gate

ConnectivityGate is an account/symbol-aware application policy, not a UI boolean:

* `ONLINE`: synchronized state; new entry, scale-in, reduce/close, cancel and new Limit may pass other guards;
* `DEGRADED`: new exposure and exposure-increasing Limits blocked; safely bounded reduce/cancel may pass;
* `UNKNOWN_EXECUTION`: conflicting exposure and retry blocked; reconcile original command; bounded risk reduction only
  from confirmed state;
* `RECONCILING`: new exposure blocked; bounded reduction/cancel only; ONLINE requires committed convergence;
* `OFFLINE`: no mutation is represented as successful; new submissions are blocked and reconnect triggers recovery.

Emergency close uses confirmed side/size and cannot cross FLAT. UNKNOWN emergency outcome blocks another close until
reconciled. Permission checks execute server-side immediately before mutation, independently of client button state.

### 21.5 Fast DOM input and projection contract

The client gesture controller owns only transient hold/tap/double-tap and 300-ms debounce state. Holding BUY ORDER then
tapping BID emits BUY LIMIT intent; tapping ASK emits immediate MARKET BUY intent. Holding SELL ORDER then tapping ASK
emits SELL LIMIT intent; tapping BID emits immediate MARKET SELL intent. The second tap is confirmation; there is no
modal. Default quick intent is one WV. Double-tap on a side control edits that side's dollar/WV setting. Server admission
and UNKNOWN locks remain authoritative after debounce expires. Automatic preset Manual SL/TP stays an extension point,
not a mandatory v1 stage.

DOM projection joins normalized active Orders to the current symbol book by normalized price. Every active ordinary
Limit, including external orders, has direction color, large left dot, remaining dollar volume, right-shifted depth and
farther-right price; the same Order projects a chart Limit-line. Dot tap emits immediate cancel intent. `CANCEL_PENDING`
keeps a pending indicator/line until confirmed cancellation; rejection/unknown remains visible and truthful.

### 21.6 Market, Limit, normalization and cleanup algorithms

Market planning sequence: capture non-blocking fresh DOM preview; resolve configured one-WV/dollar intent; fetch or
revalidate instrument/account/position inputs; floor quantity to `qtyStep`; reject zero, sub-`minOrderQty` or
sub-`minNotionalValue`, or above allowed maximum; for opposite-side Market cap quantity to confirmed remainder; persist
command and `orderLinkId`; submit once with approved slippage protection; apply deduplicated fills; never chase a
partial remainder. A separate action is required after confirmed FLAT.

Limit planning sequence: normalize price to `tickSize` according to separately reviewed safe side semantics, compute
and floor quantity without increasing requested exposure, validate current metadata/minimums/maximums, persist identity
and submit. Partial fills update Position while remaining quantity stays active. Manual Limit may cross FLAT and open
opposite residual exactly as approved. Instrument metadata and wallet/position/gate inputs are revalidated at execution
time; no numeric exchange limits are hard-coded.

Confirmed-FLAT cleanup sequence is:

1. ExecutionEngine confirms Position transition to zero caused by Market, SL or TP.
2. Start a durable symbol/account cleanup record and snapshot all ordinary active Limits, regardless of origin.
3. Issue idempotently tracked cancel intents only for that ordinary symbol set; do not touch other symbols or silently
   include conditional/protection Orders.
4. Keep DOM/chart objects pending until Order events or REST reconciliation confirm each final state.
5. Ingest any fill racing cancellation through normal execution dedup; if exposure reopens, project factual Position,
   stop claiming FLAT completion and reconcile.
6. Complete cleanup only when Position and ordinary-order state are authoritative and non-contradictory; protection
   cleanup converges through its separate approved workflow.

### 21.7 Persistence and recovery boundary

Persist before submission: account/category/symbol, immutable command identity/type/side, requested WV/dollar intent,
normalized price/qty, position mode/index, `orderLinkId`, origin/controller, admission evidence and attempt state.
Persist as evidence: raw normalized exchange-event journal, `orderId` correlation, immutable executions keyed by
`(trading_account_id, category, execId)`, order/protection projections, position projection, connectivity/gate state,
cleanup and reconciliation records. One SQLite/WAL writer/transaction boundary atomically deduplicates an execution and
updates economic projections. No local projection overrides factual Bybit state.

Startup loads uncertain/local state, starts private streams without declaring ONLINE, snapshots instrument/account,
Position, ordinary/conditional Orders and protection, retrieves executions across the recovery horizon, correlates
identifiers, replays only unseen executions through ExecutionEngine, resolves cleanup/unknown commands, commits
convergence and then unlocks. Reconnect marks affected scope DEGRADED/RECONCILING, buffers or journals normalized events,
performs the same gap recovery and never treats WebSocket reconnection alone as synchronization. Offline executions are
recovered from REST and applied once.

### 21.8 Staged implementation sequence

| Stage | Scope and likely files | Acceptance and minimal tests | Rollback/safety boundary |
| --- | --- | --- | --- |
| 0. Contracts | New `terminal/domain/{models,states,events,policies}.py`; contract tests | Decimal-safe identifiers, states, transition table, PositionKey and exec dedup key are pure/deterministic | No network, DB or runtime wiring |
| 1. Store | New `terminal/persistence/{sqlite_store,schema}.py`; migration/store tests | WAL setup, command-before-submit, atomic exec dedup/projection and restart reload pass | Isolated local DB; schema versioned and disposable in tests |
| 2. Bybit reads/events | New `terminal/exchange/{bybit_v5_adapter,normalization}.py`; fixture/contract tests | Instrument, position, order, execution and protection snapshots plus order/execution/position event normalization | Read-only/testnet fixtures; no create/cancel enabled |
| 3. Engine/reconciliation | New `terminal/application/{execution_engine,reconciliation,projections}.py`; state/replay tests | REST/WS/recovery converge through one owner; duplicates and late evidence are non-regressive | No mutation adapter exposed |
| 4. Guard/identity | New `terminal/application/{pretrade_guard,trading_application}.py`; policy tests | WV normalization, unique persisted orderLinkId, ONLINE/degraded permissions and Market-to-FLAT cap pass | Submission port remains fake |
| 5. Market/Limit/cancel | Adapter mutation methods plus application handlers; mocked/testnet contract tests | Submit once, ACK pending, partial fills, active Limit, cancel pending/final and unknown timeout reconcile correctly | Feature/config kill switch defaults trading disabled; no production credential test |
| 6. Protection/cleanup | Protection application service and cleanup records/tests | Manual SL/TP confirmed lifecycle; FLAT ordinary-Limit cleanup, conditional separation and fill/cancel race converge | Cleanup scoped by account+symbol and ordinary-order inventory |
| 7. API/projections | `terminal/api/` routes/events plus authorization/serialization tests | UI receives normalized snapshots/pending states; handlers cannot bypass guard/engine | Backend remains local/test mode, no frontend dependency required |
| 8. DOM client slice | Approved future client path: gesture controller, DOM/Limit/chart projection tests | Exact hold/tap mapping, no modal, one-WV default, double-tap config, 300-ms debounce and truthful cancel projection | Client cannot submit outside authenticated application API |
| 9. Recovery integration | Startup/reconnect orchestration and end-to-end fake/testnet scenarios | Offline fills, external mutations, unknown submits and cleanup recover without duplicate economic effects | Real-money enablement remains off pending separate authorization/verification |

Each stage is independently reviewable and must preserve Scanner tests and subsystem separation. Stage 8 depends on the
broader approved frontend shell/toolchain boundary but does not require revisiting execution/protection product research.

### 21.9 Required test matrix

The bounded implementation verification suite must cover: successful Market and Limit; Market partial fill without
retry; Limit partial fill with active remainder; cancel of partial Limit; duplicate tap inside 300 ms; legitimate tap
after 300 ms when no uncertainty lock exists; post-300-ms tap blocked by UNKNOWN; timeout after submit; unknown outcome
reconciliation and no blind retry; reconnect with fills during outage; external Limit appearance/disappearance;
external Position modification; Market reduction capped at FLAT; separate post-FLAT action opening opposite exposure;
Limit crossing FLAT into opposite exposure; Market/SL/TP confirmed FLAT triggering ordinary-Limit cleanup; fill/cancel
race; cancellation ACK versus final cancellation; DEGRADED exposure block; safely bounded emergency reduction; unknown
emergency close blocking duplicate; OFFLINE never reporting success; duplicate WS/REST execution; restart after
command-before-submit and during execution transaction; and account/symbol isolation.

Tests progress from pure unit/state/property-style cases, through adapter payload fixtures and in-memory/temp SQLite,
to fake-exchange integration and explicitly authorized Bybit test/demo environment checks. No real-account mutation is
part of ordinary automated validation.

### 21.10 Acceptance and authorization boundary

Before IMPLEMENT may be authorized, human review must approve this bounded plan and exact file scope; the frontend
shell/path and dependencies needed by the authorized stages must be selected; current official Bybit V5 endpoint,
parameter, rate-limit and pybit method shapes must be reverified; test/demo credentials and a default-off trading kill
switch must be defined; migration/rollback and credential boundaries must be approved; and stage-specific acceptance
tests must be agreed. Real-money enablement requires later VERIFY evidence and separate authority.

The plan is implementable and ready for explicit human IMPLEMENT authorization after those pre-implementation gates
are satisfied or included in the authorized first planning stage. This document does not satisfy that authorization by
itself. Overall Trading Workspace CONTEXT remains active for other bounded blocks; IMPLEMENT remains
`NOT_STARTED_NOT_AUTHORIZED`, no dependencies are approved, and Robot remains out of scope.

This amendment records checkpoint `MANUAL_EXECUTION_PROTECTION_IMPLEMENT_PLAN_RECORDED`.

## 22. Authorization boundary

Revision 1.13 is a documentation-only IMPLEMENT planning checkpoint for one bounded completed CONTEXT block. Approved
SPEC revision 1.4 remains intact. Production
implementation, tests, dependencies, Bybit credentials, orders and runtime changes are
`NOT_STARTED_NOT_AUTHORIZED`. CONTEXT/RESEARCH is separately authorized and in progress, without any
claim that CONTEXT is complete, fully finalized or verified. IMPLEMENT
requires separate later approval and valid context.

## 23. Manual Limit GTC and pre-Stage 5 corrective checkpoint

Manual Terminal v1 ordinary Limit orders use `GTC` (`Good-Till-Cancelled`) as the binding/default
`timeInForce`. Such an order remains active until it is filled, explicitly cancelled by the user, or cancelled by an
approved Terminal cleanup workflow. `IOC`, `FOK` and `PostOnly` are not default ordinary Manual Limit semantics in the
current v1 scope.

The terminal command lifecycle distinguishes confirmed amend completion from the continuing exchange-order lifecycle.
REST amend acknowledgement remains intermediate acceptance evidence. Only confirmed modified-order evidence completes
the amend command as `AMENDED`; this terminal state is final, is not a fill, and does not imply that the exchange order
is closed. Ambiguous amend outcomes remain `UNKNOWN`/`RECONCILING` and preserve the no-blind-retry invariant.

Before Stage 5 implementation, its exact authorized scope must include a narrow ExecutionEngine mutation-outcome
ingestion boundary for REST acknowledgement, deterministic rejection, ambiguous/unknown outcome and confirmed amend
completion. Application code must not bypass ExecutionEngine ownership of command transitions.

Installed `pybit==5.17.0` has internal response-code retry behavior. A future Stage 5 mutation adapter must use
`force_retry=False`, explicitly disable mutation response retry codes, contain no mutation retry loop, classify
timeout or ambiguous response as `UNKNOWN`, and never perform blind retry. This is a binding implementation-safety
gate, not a change to product execution semantics.

Stage 5 remains `NOT_STARTED_NOT_AUTHORIZED`. This correction does not create an exchange mutation adapter, authorize
Bybit create/amend/cancel calls, complete overall CONTEXT, or expand Robot scope.

This amendment records checkpoint `MANUAL_LIMIT_GTC_AND_AMEND_LIFECYCLE_CORRECTION_RECORDED`.

## 24. DOM input and MetaScalp new-tab integration decisions

Revision 1.15 is a human-approved documentation checkpoint. It records product decisions only. It does
not start Stage 8, select a frontend technology, install a dependency, implement Scanner or Telegram
runtime behavior, or invoke MetaScalp or Bybit.

### 24.1 Single CENTER control and LOCKED CENTERING

Fast DOM uses one control below the Time & Sales / execution-prints area: `CENTER`. There is no separate
persistent AUTO CENTER button. LOCKED CENTERING defaults to disabled, so the DOM does not automatically
return the current market price to the center while the operator manually inspects levels.

One deliberate click or tap on `CENTER` immediately returns the current spread / working market area to
the central working region. This is one-shot centering only: it does not enable LOCKED CENTERING, and the
button remains in its normal visual state.

A deliberate double click or tap immediately centers the spread and enables LOCKED CENTERING. While
locked, the DOM may follow or recenter relative to the market according to later approved and verified
thresholds so the spread remains in the central working region. The `CENTER` button displays a persistent,
clearly visible border or outline for the entire active locked mode. Exact border color, thickness and
style remain frontend details.

A deliberate double click or tap while LOCKED CENTERING is active disables it and removes the border or
outline. Any deliberate manual DOM scrolling or repositioning also immediately disables LOCKED CENTERING,
removes the active border or outline and leaves manual navigation in control without automatic return.

Mouse, touch and pen/pointer inputs normalize to the same single- and double-activation semantics. CENTER
double-activation recognition is independent of the 300-ms trading execution anti-bounce. Its exact timing
remains a frontend/platform verification and configuration detail. This correction supersedes any earlier
revision 1.15 implication that persistent centering and one-shot CENTER require two separate controls.

### 24.2 One state machine, device-specific input mappings

Touch and desktop use the same execution gesture state machine, Stage 7 command contracts, 300-ms
anti-bounce and backend safety semantics, but have distinct device mappings:

* touch: a primary finger holds `BUY ORDER` or `SELL ORDER`; a secondary finger selects the DOM row and
  action;
* desktop: a primary mouse hold on `BUY ORDER` or `SELL ORDER` arms the corresponding mode, and a separate
  deliberate mouse action on a DOM row executes the armed action;
* exact desktop mouse-button mapping must be verified and human-approved before Stage 8 implementation;
* hover may provide preview or highlighting only and never creates a trading command.

The 300-ms anti-bounce applies after accepted execution actions regardless of input device. This client
suppression remains separate from durable command identity and UNKNOWN/RECONCILING locks.

### 24.3 Scanner Telegram signal to MetaScalp

A future Scanner Telegram signal may include a separate `Open in MetaScalp` button. This is a bounded
Scanner/Telegram-to-MetaScalp integration, not part of the Fast DOM execution engine. Activating the button
for a specific signal symbol has one binding product outcome:

1. MetaScalp opens a new tab;
2. that new tab contains a new order book / DOM for the signal symbol;
3. existing MetaScalp tabs and order books remain unchanged.

For example, activating the button on a `SOLUSDT` signal opens a new MetaScalp tab containing the
`SOLUSDT` DOM without replacing existing `BTCUSDT` or `ETHUSDT` tabs. A simple change-ticker operation on
an existing working DOM does not satisfy this requirement.

### 24.4 MetaScalp official API verification gate

The official MetaScalp Linking API is the preferred future integration boundary. Current research
identifies `/api/combo` as the closest official operation for opening a ticker/combo, but does not yet
prove that every call creates a new tab while preserving existing tabs. Before implementation, a separate
authorized verification must establish:

* exact current Linking API behavior;
* repeated `/api/combo` behavior for different tickers;
* whether every required call creates a new tab and preserves existing tabs;
* exchange and market selection semantics;
* Bybit USDT perpetual ticker mapping;
* behavior when MetaScalp is not running;
* official local-port discovery behavior.

If the official API cannot guarantee `NEW TAB + NEW DOM + PRESERVE EXISTING TABS`, implementation must
return an explicit integration blocker/product gap. It must not silently substitute change-ticker.

### 24.5 Architectural and lifecycle boundary

The intended future flow is:

`Telegram signal -> Telegram callback -> Scanner/backend integration boundary -> local MetaScalp helper/client -> official MetaScalp Linking API -> new MetaScalp tab/DOM`.

The browser or Telegram client never receives direct access to the local MetaScalp API. The local helper,
callback authorization, port discovery and failure handling belong to a separately authorized bounded
integration block.

Stage 7 is complete at commit `61520861b6058a585460b3f5f964613d19dcd35b`. Stage 8 remains
`NOT_STARTED_NOT_AUTHORIZED`; revision 1.17 selects the frontend stack but does not authorize its dependencies,
filesystem scope or implementation. MetaScalp integration does not expand Stage 8 and requires its own later
bounded implementation authorization.

This amendment records checkpoint
`DOM_INPUT_AND_METASCALP_NEW_TAB_INTEGRATION_DECISIONS_RECORDED`.

## 25. Corrective single-CENTER checkpoint

Revision 1.16 corrects only the revision 1.15 centering control semantics. The binding interaction is:

* `CENTER` single activation -> one-shot center only;
* `CENTER` double activation -> center and enable LOCKED CENTERING;
* `CENTER` double activation while locked -> disable LOCKED CENTERING;
* deliberate manual DOM scroll/reposition -> disable LOCKED CENTERING;
* LOCKED CENTERING active -> persistent visible border or outline on `CENTER`.

There is no separate AUTO CENTER control. The 300-ms trading anti-bounce remains independent. All
MetaScalp, touch/mouse trading execution and lifecycle decisions from revision 1.15 remain unchanged.
Stage 8 remains `NOT_STARTED_NOT_AUTHORIZED`.

This amendment records checkpoint `DOM_SINGLE_CENTER_LOCKED_MODE_SEMANTICS_RECORDED`.

## 26. Paper-first frontend and fast-order decisions

Revision 1.17 records product and technical decisions only. It does not start Stage 8, create a frontend,
install dependencies, enable a runtime, connect a paper or live account, or submit any exchange mutation.

### 26.1 Selected frontend stack and state boundaries

The selected client is one React 19 + TypeScript + Vite SPA used for both desktop web and Telegram Mini App.
Package management uses npm with a committed `package-lock.json`. Zustand owns bounded client/UI state.
TanStack Query owns REST/server-state fetching and caching but not high-frequency L2 updates. Realtime
presentation events use a separate WebSocket layer and the Stage 7 snapshot-first sequencing contracts.

Tailwind 4 is the styling foundation. shadcn/Radix may be used selectively for ordinary semantic controls;
they do not own the high-frequency ladder. Tests use Vitest, React Testing Library and Playwright. Biome
owns frontend formatting and linting. High-frequency DOM state/rendering must remain isolated from ordinary
React component render lifecycle. This stack decision does not select KLineChart or any other chart/rendering
engine; chart and high-frequency renderer selection remains separate.

### 26.2 Desktop DOM and chart Limit placement

The desktop DOM exposes side-explicit BUY/BID and SELL/ASK execution columns. A deliberate left click on a
DOM execution cell submits the corresponding Limit intent at that exact projected price. It never implicitly
creates a Market order. Double-clicking a trading DOM cell has no trading function. An existing order may be
selected and dragged into a pending modification interaction. Right-clicking a specific active order submits
a specific cancel intent; right-click in neutral space remains contextual and does not cancel an order.

Holding BUY with the left mouse button for the approved long-press threshold enters BUY LIMIT placement
mode. While the hold remains valid, deliberate chart right-clicks may submit multiple separately identified
Buy Limit intents. SELL is symmetric. A separate LIMIT/BUY ORDER hold-mode below the book may expose the
same repeated chart-Limit behavior. Each physical placement still creates at most one logical submission.

Normal non-marketable fast Limit placement requires no confirmation. A Buy Limit at or above the current
Ask, or a Sell Limit at or below the current Bid, is marketable/aggressive and requires explicit confirmation.
It remains a Limit order and is never silently converted to Market. Successful placement emits its
characteristic sound only after backend/execution-engine acknowledgement, never on the local pointer action.

### 26.3 Confirmed Market preparation

A single BUY or SELL activation prepares a Market order and requires explicit confirmation. Its preview
contains the ticker, selected WV and USDT reference, calculated base-asset coin quantity after instrument
`qtyStep` rounding, relevant market price information, estimated average execution price/VWAP and estimated
L2 slippage. The preview remains informational; the exact normalized L2 and market-data boundary is unresolved
and requires a later decision. A DOM ladder click never substitutes for this Market flow.

### 26.4 Long press and independent timing domains

`LONG_PRESS_THRESHOLD = 500 ms` for BUY, SELL and LIMIT placement gestures. Transition from `PRESSED` to
`LONG_PRESS_ACTIVE` suppresses the original short-click action so one physical interaction cannot both open
a Market confirmation and enter Limit placement mode. Long-press timing is independent of the existing
300-ms trading anti-bounce.

The single-CENTER semantics from revision 1.16 remain binding. A 300-ms mouse double-click window and a
350-ms touch double-tap window are currently proposed values only; repository authority does not yet record
them as approved binding timings. They remain pending frontend/platform verification and explicit approval.
CENTER recognition is independent from trading anti-bounce and long-press timing.

### 26.5 Fail-closed fast-order network safety

Fast hold-mode placement is fail-closed: missing an order is preferable to duplicate exposure. Every order
intent receives a unique client order identity / `orderLinkId`. One physical gesture creates at most one
logical submission. Timeout, disconnect or ambiguous transport outcome never triggers blind automatic
resend. The original client identity is reconciled against command, order, execution and position evidence
before any separately authorized recovery action. New fast placement is blocked while connectivity or
execution state is `DEGRADED`, `OFFLINE`, `UNKNOWN` or otherwise ambiguous.

### 26.6 Pending Limit-line edit rollback

Dragging an existing active Limit line enters a pending edit state and retains its original authoritative
confirmed price. Clicking or tapping outside the edited line cancels the pending edit, restores exactly the
original confirmed price and sends no modify-order request. Only an explicit confirmation action submits the
changed price. Pending local geometry never becomes exchange truth.

### 26.7 Working Volume and coin-quantity authority

Working Volume remains an accounting/risk unit equal to five percent of account equity/deposit expressed in
USDT. Entry sizing flows from WV to target USDT notional, calculated base-asset quantity, instrument `qtyStep`
rounding and actual filled quantity. After execution, authoritative ownership of that position portion is the
actual filled coin quantity. Partial fills and reconciliation update that factual remaining quantity.

Closing quantity is never recalculated from the original USDT WV amount. Full close uses the current actual
position size / remaining base-asset quantity with reduce-only semantics and reconciles fills to avoid residual
tails. Current USDT notional is informational and dynamic; it does not redefine the original engaged-WV count.

### 26.8 Superseding Paper-first execution architecture

The initial Trading Workspace must not connect to the real Bybit trading account for execution. Its first
execution backend is a virtual paper account and Paper Trading Engine. Real-money Bybit execution is deferred.
Logical Workspace commands target a backend-neutral execution abstraction, conceptually:

`Trading Workspace -> Execution interface -> PAPER initially / BYBIT_LIVE later`.

The paper backend supports realistic accepted, working, partial/full fill, cancel/reject, position,
realized/unrealized PnL and reconciliation-compatible state. Where appropriate it consumes real normalized
market/L2 data for fills and slippage simulation; the exact source, freshness and simulation policy remain
owned by the later L2 decision. The same Paper Trading Engine and execution contract must be reusable by the
future virtual Robot. MANUAL versus ROBOT controller/ownership remains explicit even when both use paper
execution.

This Paper-first decision supersedes the earlier real-Bybit-first priority. It does not delete or silently
reinterpret completed Stage 0 through Stage 7 implementation history, enable the existing Bybit mutation
adapter, or authorize a Paper engine implementation. A later bounded planning/implementation checkpoint must
reconcile the execution abstraction with current contracts before runtime use.

Stage 8 remains `NOT_STARTED_NOT_AUTHORIZED`.

This amendment records checkpoint `PAPER_FIRST_FRONTEND_AND_FAST_ORDER_DECISIONS_RECORDED`.

## 27. Final pre-Stage-8 market-data and Paper execution decisions

Revision 1.18 is documentation and specification only. It does not start Stage 8, create frontend or
runtime code, install dependencies, implement the Paper Trading Engine, connect real Bybit credentials,
submit exchange orders, perform MetaScalp integration or execute the required future secret audit.

### 27.1 Binding CENTER timing domains

Desktop mouse `CENTER` double-click recognition uses 300 ms. Touch `CENTER` double-tap recognition uses
350 ms. The first click or tap performs one-shot spread centering immediately and is never delayed while
waiting for a possible second activation. A second activation inside the applicable device window upgrades
the gesture to LOCKED CENTERING. A repeated double activation disables LOCKED CENTERING. Intentional manual
DOM scrolling or repositioning also disables it and removes the locked border or outline.

The CENTER mouse timer, CENTER touch timer, `LONG_PRESS_THRESHOLD = 500 ms`, and trading anti-bounce of
300 ms are independent state and timer domains. Numerical equality never permits implementation coupling.

### 27.2 Same-price own orders, markers and print priority

Multiple own active orders may coexist at one DOM price. The monetary value shown on that price row is the
sum of all active own-order amounts at that exact price in USDT. Aggregation never removes concrete identity:
every order has its own marker/dot mapped to its specific order identity or client order identity, and
cancelling a marker cancels only that order.

The first order creates the first marker. Every newer same-price order creates a marker to the left of the
previous marker, preserving a deterministic creation/order relationship. Visible dots may be compact, but
their hit targets should be approximately 44x44 CSS px where feasible and adjacent targets must resolve
unambiguously. Touch usability takes priority over density. When safe placement is exhausted, the UI must
use explicit compact/overflow behavior rather than continuously shrinking spacing or hit targets. The exact
overflow presentation remains a bounded later UI-detail decision.

Tape/trade prints must not hide own-order markers. A print overlapping the marker region becomes partially
transparent enough to keep the marker clearly visible. The marker has higher visual and pointer/touch
hit-test priority, so activating the overlapping marker area selects or cancels the concrete order rather
than selecting the print.

### 27.3 Symbol-scoped quick volume

Quick volume does not persist between symbols. Entering or switching to an instrument resets quick volume
to `1 WV`; a larger or smaller selection from the previous symbol never carries over silently. The swords
indicator continues to express engaged/selected WV under the existing contract. Its hover/tap tooltip shows
the corresponding USDT reference, such as `1 WV = 100 USDT` or `2.5 WV = 250 USDT`. Execution quantity
remains the already-approved rounded base-asset coin quantity, not the display amount.

### 27.4 Authoritative normalized L2 boundary

The browser/frontend is not the authoritative reconstructor of raw Bybit L2. The target path is:

`Bybit Public WebSocket -> Market Data Engine / Bybit adapter -> authoritative normalized local L2 book -> DOM, Market preview, Paper Trading Engine, and later Robot paper execution`.

The initial source is Bybit Public WebSocket L2 order book with target depth 50. The Market Data Engine owns
snapshot/delta consumption, local reconstruction, required sequence/update metadata, gap detection,
reconnect/resubscribe, and valid snapshot resynchronization before usability. It tracks exchange timestamps
where available, local receive/update timing and explicit health/readiness state. Frontend and Paper Engine
consume a normalized internal representation and do not depend directly on Bybit-specific snapshot/delta,
`u` or `seq` mechanics. The adapter can later be replaced or extended without redesigning Workspace
execution semantics.

DOM display, Market BUY/SELL VWAP/slippage preview and Paper market simulation consume the same authoritative
normalized book/state rather than reconstructing independent copies. Market BUY walks asks from best outward;
Market SELL walks bids from best outward until the required quantity/notional is covered. Preview can report
the relevant best bid/ask, estimated rounded coin quantity, average execution price/VWAP, absolute and
percentage slippage and useful consumed-depth/level count. When authoritative usable L2 exists, last traded
price alone is not a valid market-execution estimate.

### 27.5 Paper fills and bounded unresolved resting-Limit model

Paper Market BUY consumes available asks and Paper Market SELL consumes available bids from the authoritative
normalized book. Larger orders can therefore receive a worse simulated average execution than smaller orders.

A resting Paper Limit is not automatically fully filled merely because market price touched its level. The
future design must consider market trades, L2 evolution, partial fills and an appropriate queue/liquidity
model. The exact queue-position and fill algorithm is not approved and must not be invented at this checkpoint;
it remains an explicit bounded Paper Engine design item.

### 27.6 Fail-closed market-data safety

The book exposes states conceptually equivalent to `NOT_READY`, `SYNCING`, `READY`, and `STALE`/`DEGRADED` as
appropriate. If sequence integrity is uncertain, reconnect/resync is incomplete, a required snapshot is
missing, freshness exceeds the later-approved threshold, or authoritative state is otherwise ambiguous, new
actions requiring reliable current data fail closed. An untrusted book cannot be used as current for a new
Market preview/execution, fast placement is blocked where validated current context is required, and Paper
Engine does not fabricate liquidity. Eligibility resumes only after valid resynchronization. The exact numeric
staleness threshold remains unresolved.

### 27.7 Required future secret exposure audit

Before any real Bybit credentials or live execution are introduced, a separate bounded SECRET EXPOSURE AUDIT
is required. Its scope includes current tracked files; relevant Git history; `.env` and config files; relevant
text/log and backup/reference artifacts; Telegram tokens; Bybit API key/secret patterns; private keys and
password-like credentials; high-confidence/high-entropy indicators; `.gitignore`; and available GitHub secret
scanning/push-protection posture.

Findings must be masked or fingerprinted and secrets must never be printed in full. A real active secret is
rotated/revoked before history cleanup. Any history cleanup is a separate explicitly controlled action. This
audit is recorded here but was not executed by revision 1.18.

Paper-first architecture remains authoritative: the initial execution backend is PAPER, the execution
contract remains reusable by Manual Workspace and future virtual Robot, and MANUAL versus ROBOT ownership
remains explicit. Real-money Bybit execution is not re-authorized. Stage 8 remains
`NOT_STARTED_NOT_AUTHORIZED` and requires separate exact-scope and dependency authorization.

This amendment records checkpoint `AUTHORITATIVE_L2_AND_PAPER_EXECUTION_DECISIONS_RECORDED`.

## 28. Stage 8 Block 1 frontend foundation implementation

Revision 1.19 records the explicitly authorized Stage 8 Block 1 only. The new client lives at
`terminal/frontend/`, inside the existing independent Trading Terminal subsystem. It is a React 19,
TypeScript and Vite SPA foundation with an npm lockfile, Tailwind 4 styling foundation, Biome validation and
a focused Vitest/React Testing Library test. The application shell is split into small header and panel
components and establishes instrument/header, chart placeholder, DOM/order-book placeholder, unavailable
trading-controls placeholder and connection/status regions. The current execution mode is visibly and
semantically identified as `PAPER` and `NON-LIVE`.

The only integration contract introduced is a frontend-facing normalized market-data snapshot and order-book
shape. It deliberately contains no raw Bybit WebSocket message, snapshot/delta, `u` or `seq` mechanics. No
Market Data Engine, realtime connection or backend integration is implemented by this block.

Validation completed for the bounded frontend: dependency audit reported zero vulnerabilities; Biome passed;
the focused PAPER-only structural-shell test passed; strict TypeScript project compilation passed; and Vite
produced a production bundle successfully. The generated bundle is excluded from Git.

This block did not implement a functional DOM, L2 ingestion, Market Data Engine, Paper Trading Engine,
market-order simulation, chart engine, working BUY/SELL or any trading control, order gesture or marker,
authenticated Bybit connection, credential handling, account mutation, Scanner/Telegram change, Robot,
AUTOPILOT or MetaScalp integration. No real credential was read or used and no exchange order/account mutation
occurred. Stage 8 is not complete; every next block requires a new exact-scope authorization.

This amendment records checkpoint `STAGE_8_BLOCK_1_FRONTEND_FOUNDATION_IMPLEMENTED_VERIFIED`.

## 29. Stage 8 Fast DOM client-slice UX decisions

Revision 1.20 is documentation only. It does not modify `terminal/frontend/`, install dependencies, connect
market data, implement the DOM or authorize another Stage 8 implementation block.

### 29.1 Frontend rendering and authority boundary

The client remains React plus TypeScript plus Vite. High-frequency L2 updates must use a dedicated
market-data/state path and must not drive naive full-tree React-state rerendering. That path remains
compatible with a future Web Worker boundary. The DOM ladder uses efficient or virtualized rendering where
appropriate. Backend services remain the sole trading/execution authority; client rendering state is never
execution truth.

### 29.2 Current-stage mouse navigation and CENTER

For this client slice, clicking Bid, Ask or price cells does not create an order. Ordinary left or right
click on the DOM has no trading action. The operator may grab and drag the ladder vertically, and the mouse
wheel scrolls or repositions it. Intentional manual drag, scroll or reposition disables locked CENTER mode.

The existing CENTER contract remains: one click immediately performs one-shot spread centering; a deliberate
double click centers and enables persistent locked centering; and the locked state has a clearly visible
button border or outline.

This current-stage rule supersedes only earlier proposals that assigned Limit placement or another trading
action to ordinary DOM price/Bid/Ask cell clicks. It does not remove the separately approved concrete
own-order-dot cancellation described below.

### 29.3 Same-price own Limits

The model and UI support multiple distinct active own Limit orders at the same exact price. That DOM row
shows one dot per concrete order in a horizontal row. Buy dots are green; Sell dots use the selected
sell-side color. Activating a specific dot cancels only the order represented by that dot. Every other order
at the same price remains active.

The aggregate notional of all own active Limits at that price is displayed numerically in USDT inside the
DOM, on the same price row, at its extreme left. Its color matches the order side and dots. For example,
three Buy orders of 100, 150 and 250 USDT display three green dots and `500 USDT`; activating the 150-USDT
order's dot cancels only that concrete order.

### 29.4 Market-data baseline

Bybit V5 public WebSocket is the live market-data source. The initial DOM baseline is orderbook depth 50,
maintained locally from snapshot and delta semantics by the authoritative Market Data Engine. The tape / Time
& Sales baseline is the separate `publicTrade` stream. REST is not the primary live DOM feed.

The normalized DOM contract must not permanently encode depth 50: deeper books may be introduced later
without redesigning consumers. Order-book/L2 and trade/tape streams remain conceptually separate, while their
timestamps may be correlated in a later authorized design.

### 29.5 Explicit deferrals

The current slice defers creating orders by clicking DOM price, Bid or Ask cells; detailed quick-volume
trading controls; and final trading mouse-button semantics beyond cancellation of the specifically selected
own-order dot. No additional trading interaction is implied or authorized.

Fast DOM client-slice implementation remains `NOT_STARTED_NOT_AUTHORIZED` and requires a separate exact-scope
authorization. This amendment records checkpoint
`STAGE_8_FAST_DOM_CLIENT_SLICE_UX_DECISIONS_RECORDED`.

## 30. Single 3-in-1 Trading Workspace architecture

Revision 1.21 is documentation only. Trading Workspace is one application and one shared underlying engine
with three switchable operating modes. It is not three separate applications and does not recreate three
chart engines.

### 30.1 Modes and lower functional panel

* `TERMINAL`: the shared chart and market-data workspace with manual trading controls in the lower panel.
* `AUTOPILOT`: the same shared chart and market-data workspace for future live Robot observation/control,
  with the lower manual panel replaced by Autopilot-specific status and controls. Robot logic is neither
  designed nor implemented here.
* `EDITOR`: the same shared chart/workspace with the lower trading panel replaced by Editor-specific tools.
  Complete Editor functionality is neither designed nor implemented here.

Each mode exposes direct buttons to the other two modes in its lower functional panel: Terminal exposes
`AUTOPILOT | EDITOR`; Autopilot exposes `TERMINAL | EDITOR`; and Editor exposes `TERMINAL | AUTOPILOT`.
The previously planned upper/header Autopilot button is removed. In Terminal, both mode buttons belong to the
lower trading/control-panel area. This supersedes only the earlier upper-header Autopilot placement.

### 30.2 Shared and mode-specific state

Mode switching does not recreate or reset the primary workspace. Applicable shared state includes selected
symbol, timeframe, chart viewport/zoom/position, live market data, DOM/Tape state, selected trading account
and connection state. For example, BTCUSDT 5m with a particular viewport and open DOM/Tape remains the same
market workspace when switching Terminal to Autopilot.

Switching primarily replaces the lower functional/control panel and mode-specific controls, overlays or tools.
Manual, Autopilot and Editor controls remain logically separate despite sharing the workspace and engine.

### 30.3 Non-mutating navigation and account access

Mode switching is not a trading action. It never by itself cancels orders, starts or stops Robot, closes a
position, changes the selected account or otherwise mutates trading state. Every such mutation requires a
separate explicit control.

A key-icon control opens the account-selection/credentials area. The account system supports selection among
configured accounts, including a Paper / Virtual account. This checkpoint does not implement or authorize
real-account credential handling.

### 30.4 Responsive header decision point and priority

Expanding DOM plus Tape must not merely compress upper/header labels until the interface becomes cramped. The
final responsive behavior is evaluated with the real working prototype. Later options may move information or
controls into the lower panel, hide low-priority header information conditionally or remove redundancy; no
final rearrangement is selected here.

The active product priority remains: get the first real, runnable Fast DOM / Trading Workspace prototype into
the user's hands as soon as practicable. That prototype becomes the basis for real UX tuning rather than
continued image/mockup-driven design. This checkpoint does not expand into Robot or Trading Intelligence
design, starts no production implementation and does not authorize the Fast DOM client slice.

This amendment records checkpoint `SINGLE_3_IN_1_TRADING_WORKSPACE_ARCHITECTURE_RECORDED`.

## 31. Stage 8 runnable Fast DOM client-slice authorization

The user explicitly authorizes implementation of only the smallest useful locally runnable prototype on the
existing `terminal/frontend/` foundation. Authorized scope is the shared Terminal/Autopilot/Editor shell with
preserved workspace state; a stable real chart surface; a compact non-trading DOM and adjacent Tape; CENTER
single/double/locked/manual-scroll behavior; a normalized deterministic feed clearly labelled development
data when live backend market data is unavailable; same-price own-order fixture visualization and individual
fixture cancellation; Paper account access location; responsive prototype usability; and focused tests/build.

This authorization does not include Robot logic, Trading Intelligence, strategy or real execution, DOM-cell
order creation, complete Editor, final quick-volume mechanics, real credential handling, MetaScalp or
unrelated Scanner work. Browser code remains outside raw Bybit snapshot/delta reconstruction; live Bybit data
requires the authoritative adapter/Market Data Engine boundary. This checkpoint records
`STAGE_8_FAST_DOM_RUNNABLE_CLIENT_SLICE_IMPLEMENTATION_AUTHORIZED`.

## 32. Stage 8 runnable Fast DOM client-slice implementation result

The authorized slice is implemented under `terminal/frontend/`. The application now runs as one shared
Terminal/Autopilot/Editor workspace; lower-panel mode switching retains chart zoom and the mounted market
workspace and performs no trading mutation. Autopilot and Editor are explicit non-functional placeholders.

The shared workspace contains a dark graphite SVG candlestick surface with Buy/Bid green and Sell/Ask red,
an adjacent compact DOM and Tape, right-to-left depth fills, wheel and vertical-drag repositioning, one-shot
CENTER, double-click locked CENTER with visible outline and manual-movement unlock. Ordinary DOM level clicks
do not create orders. Clearly labelled Paper development fixtures demonstrate multiple same-price dots,
extreme-left aggregate USDT and per-dot cancellation of only the selected fixture order.

The key-icon account location opens a Paper / Virtual selection panel and explicitly disables real credentials.
Market data is not live Bybit in this slice: a deterministic `DEVELOPMENT` snapshot supplies depth 50,
candles, own-order fixtures and a separate Tape collection behind a normalized `MarketDataPort` consumed via
an external-store hook. Browser code contains no raw Bybit snapshot/delta or sequence mechanics; a future
normalized live backend adapter can replace the development port.

Verification passed: Biome check; four focused Vitest/React Testing Library tests covering state-preserving
mode switching, CENTER locking/unlocking, non-trading DOM clicks, individual fixture cancellation and the
depth-extensible development adapter; strict TypeScript and Vite production build; and a bounded Vite startup
smoke check returning HTTP 200 before clean shutdown.

No live Bybit connection, Robot logic, Trading Intelligence, strategy, real order/account mutation, real
credential handling, complete Editor or final quick-volume mechanics were implemented. Every next Stage 8
slice requires separate authorization. This amendment records
`STAGE_8_FAST_DOM_RUNNABLE_CLIENT_SLICE_IMPLEMENTED_VERIFIED`.
