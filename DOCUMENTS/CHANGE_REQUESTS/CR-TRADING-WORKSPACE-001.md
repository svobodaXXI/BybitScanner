# CR-TRADING-WORKSPACE-001 — Trading Workspace v1 / Manual Live Trading

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-TRADING-WORKSPACE-001",
  "title": "Trading Workspace v1 / Manual Live Trading",
  "status": "IN_PROGRESS",
  "revision": "2.6",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Complete and accept Manual Terminal v1 through PAPER protection lifecycles, Open Positions UX, secure real-account management and authoritative real-account execution while keeping IMPLEMENT in progress.",
  "non_goals": [
    "Implement autonomous Trading Robot behavior or AUTOPILOT",
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
    ,"Implement the human-authorized Stage 8 independent BUY and SELL USDT-notional amount controls and authoritative engaged position-notional display in ModePanel"
    ,"Implement the approved NotionalIntent Market nearest-step policy with a five-percent ceil-overshoot ceiling, whole-USDT position display and localized failure messages"
    ,"Implement an isolated one-command Playwright E2E harness over the real PAPER backend and frontend with temporary runtime persistence and authoritative backend-state assertions"
    ,"Implement deterministic fail-closed frontend/backend Trading Workspace contract consistency checks with selective tools.dev.verify routing"
    ,"Implement the human-authorized PAPER Full Close action using authoritative remaining coin quantity, safe FLAT no-op behavior and authoritative frontend exposure refresh"
    ,"Implement the human-authorized PAPER Limit create, durable idempotency, authoritative active-order projection and safe concrete-order cancel lifecycle with binding GTC"
    ,"Implement the human-authorized PAPER resting Limit price-only amend with durable idempotency and authoritative in-place projection"
    ,"Run PAPER execution through a dedicated serialized runtime-owner lane with live symbol metadata and live order-book authority"
    ,"Implement the ONGUSDT live order-book and public-trade streams, cumulative Smart Tape aggregation, x5 DOM projection and a stable fixed price ladder"
    ,"Implement and verify the Lightweight Charts 5.2.1 interactive chart workspace and follow-latest runtime action"
    ,"Record the isolated Smart Tape to fixed DOM spatial-alignment patch while keeping its main integration pending"
    ,"Implement and manually accept live PAPER unrealized PnL plus the compact position-controls layout"
    ,"Record the human-approved documentation-only side-specific LIMITS UX, chart-draft and immediate DOM-Limit paths, and explicit supersession map without authorizing implementation"
    ,"Implement one revision-ordered frontend PAPER authority, coalesced reconciliation and mutation responses carrying their serialized resulting PAPER state"
    ,"Implement the account-wide PAPER Open Positions inventory and money-sensitive per-symbol Full Close reconciliation without optimistic row removal or blind retry"
    ,"Complete account-wide PAPER Open Positions with backend-owned per-symbol current PnL, symbol tick-size price formatting and serialized idempotent Close All orchestration"
    ,"Implement one canonical authoritative Workspace symbol-switch path shared by ticker autocomplete and Open Positions navigation, with atomic market-data and PAPER projection transition safety"
    ,"Complete and accept the missing chart Drawing Tools Ruler through the established drawing lifecycle"
    ,"Upgrade the existing Fibonacci drawing with binding retracement/extension levels, chart-authoritative labels and translucent adjacent fills"
    ,"Complete and accept authoritative STOP and TAKE PROFIT lifecycles on PAPER before real-account enablement"
    ,"Complete active-symbol-first Open Positions ordering, highlighting and Close All presentation without changing Close All execution semantics"
    ,"Implement backend-secured Bybit API credential management and safely reconciled configured-account switching without exposing API Secret to the frontend"
    ,"Extend the established Terminal execution and reconciliation architecture to the selected real account for Market, Limit, STOP and TAKE without blind retry"
    ,"Complete the real-money security, reconciliation and acceptance gate before Manual Terminal v1 closure"
    ,"Implement the first default-off LIVE execution slice for explicitly confirmed manual MARKET BUY and MARKET SELL on the active writable Bybit MAINNET account, with durable idempotency, account/session fencing, single-attempt dispatch, REST-only reconciliation, an authoritative acceptance-notional ceiling and no LIVE Limit, STOP, TAKE or full-close capability"
    ,"Implement restart-safe REST-only recovery for unresolved durable LIVE MARKET actions without mutation redispatch or new command identity"
    ,"Implement the final fail-closed LIVE MARKET pre-dispatch validation boundary without enabling real exchange dispatch"
    ,"Record the human-approved planning-only future direction for an autonomous Android manual Trading Workspace without authorizing implementation or selecting a final Android stack"
  ],
  "prohibited_scope": [
    "Further unapproved DOM, L2, Market Data Engine, Paper Trading Engine or chart implementation beyond recorded checkpoints",
    "Scanner, detector, Geometry, Signal admission or Telegram runtime changes",
    "Trading Robot implementation",
    "AUTOPILOT enablement",
    "Dependencies outside the bounded frontend build, styling, lint and focused-test foundation",
    "Any unapproved expansion beyond the recorded Manual Terminal v1 completion blockers"
  ],
  "authoritative_references": [
    "AGENTS.md#Task-and-change-routing",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
    "DOCUMENTS/ROADMAP.md#CR-TRADING-WORKSPACE-001",
    "DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md"
  ],
  "context_scope_paths": [
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md",
    "DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md",
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
    ,"Holding BUY or SELL with the left mouse button enters the corresponding Limit placement mode so deliberate chart right-clicks may place multiple same-side Limit intents; fast DOM classifies the selected price before command creation, routing resting selections to canonical GTC Limit creation and spread-crossing selections to canonical Market execution"
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
    ,"Mobile chart chrome is compact and retains right price and bottom time scales, current-price marker, ticker-timeframe-price ordering and compact access to the approved drawing tools"
    ,"The mobile right panel is a collapsible aligned PRINTS FIELD plus DOM with a persistent handle; opening it translates the chart and its price scale left without changing chart geometry, scale or candle-to-scale distance"
    ,"The prints field visualizes executed market trades by aligned price level and includes a mirrored LONG or SHORT direction arrow with live green-profit or red-loss PnL percentage"
    ,"The lower mobile trading panel begins at left with engaged-WV swords, BUY and SELL, places Limits below on the left, vertically stacks STOP over TAKE PROFIT at right, and has one compact bottom-row key/account/deposit button beside AUTOPILOT and EDITOR"
    ,"The entire lower panel can collapse downward behind a persistent restore handle; this vertical collapse expands chart, prints and DOM into the freed height, unlike right-panel opening which never rescales the chart"
    ,"A normal mobile BUY or SELL short tap performs the ordinary Market action at selected working volume, with opposite-side execution capped at the confirmed remaining position so it reaches zero without crossing into reversal"
    ,"The mobile fast Limit gesture holds BUY or SELL with finger one and positions a chart-price preview with finger two; releasing finger two first submits without extra confirmation, while releasing the held side first cancels without submission"
    ,"A single tap on an active Limit line keeps it active and opaque while revealing its right-end price and specific-order cancel cross"
    ,"Dragging an active Limit line makes it transparent and temporarily inactive; release shows proposed price and green confirmation, confirmation commits, and outside activation rolls back to the original active opaque price"
    ,"The current prototype palette is not the target; later visual work follows the previously supplied approved terminal reference without inventing unapproved exact colors"
    ,"STOP and TAKE begin as transparent pending full-position protection proposals, become active and opaque only after explicit confirmation, and expose confirmed price plus projected loss/profit percentage after initiation"
    ,"There is exactly one full-position TAKE; partial profit taking uses ordinary Limit orders rather than TP1, TP2 or TP3"
    ,"Active STOP and TAKE quantities always synchronize to 100 percent of current position size without automatically moving their confirmed prices when position size or average entry changes"
    ,"Opening from a scanner signal may offer one dismissible pending TAKE proposal per signal unless an active TAKE exists or that signal proposal was explicitly skipped; normal opening never auto-proposes TAKE"
    ,"With no position the permanent position amount is zero, position PnL is absent and STOP/TAKE are unavailable while entry controls remain available; a confirmed new position transitions the UI automatically"
    ,"BUY and SELL have independent configured volumes, each used by both that side's Market tap and two-finger fast-Limit gesture"
    ,"The swords area permanently displays current position USDT and has separate holds for current one-WV value and for average entry plus base-asset quantity"
    ,"The compact Limit inventory has exactly one BUY-direction and one SELL-direction composite row with count, adaptive expansion and confirmation-gated individual and direction-wide cancellation"
    ,"Prints-field position PnL is actual live unrealized position-engine percentage with a vertical LONG up or SHORT down arrow and no additional position detail"
    ,"An open position always has a non-draggable almost-white highlighted average-entry line whose exact price appears at its right end only while the line is held"
    ,"Active Limits use solid canonical direction colors, STOP/TAKE use distinct muted dashed protection styling, and average entry uses an almost-white highlighted solid line"
    ,"The reference-derived palette baseline uses graphite surfaces and canonical BUY/Bid #3BC639 plus SELL/Ask #CD0000 consistently across candles, best book, prints and active Limit lines; exact muted STOP/TAKE shades remain unresolved"
    ,"The main trading panel exposes separate BUY LIMITS and SELL LIMITS controls; the former owns BUY/Long creation and inventory presentation and the latter owns SELL/Short creation and inventory presentation"
    ,"A short BUY LIMITS or SELL LIMITS activation opens only that side's compact creation UI and creates the existing pending editable LimitDraft and dashed chart line through the established explicit-confirmation workflow"
    ,"A long BUY LIMITS or SELL LIMITS activation opens that side's active current-symbol inventory directly above its control, ordered by increasing absolute distance from current market price while preserving existing concrete-order actions"
    ,"Fast DOM Limit placement uses the existing held BUY or SELL control and immediately submits a Limit at the tapped DOM price without a pending draft, checkmark or ordinary resting-order confirmation; multiple DOM taps during one hold may submit multiple side-matching Limits"
    ,"Chart fast-Limit placement retains the existing pending LimitDraft workflow, while immediate DOM placement reuses authoritative tick normalization, sizing, idempotent Limit submission, persistence, execution, reconciliation and fill/cancel synchronization without duplicating matching or position arithmetic"
    ,"Limit submission remains fail closed and idempotent: one client_action_id is generated once for a submission attempt, repeated confirmation while submitting reuses that same action and promise, and an ambiguous result retains the same identity for reconciliation rather than generating a new identifier or blind retry"
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
    ,"Only WorkingVolumeIntent Market sizing uses nearest adjacent qtyStep with midpoint ties floored; a ceil candidate is allowed only when reference-notional overshoot is at most ten percent, otherwise admission fails closed for insufficient sizing precision, while NotionalIntent and all Limit sizing retain floor semantics"
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
    "WorkingVolumeIntent Market nearest-step sizing remains implemented and PAPER-runtime validated",
    "ModePanel initializes independent BUY and SELL numeric amounts from authoritative one_wv_usdt, submits valid positive values through NotionalIntent, preserves user edits across execution refresh and displays engaged_notional_usdt beneath swords"
  ],
  "regression_requirements": [
    "Only the authorized ModePanel production, focused test and optional style files change alongside this ChangeRequest",
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
    "This checkpoint changes only this ChangeRequest",
    "Rollback removes only this documentation amendment without runtime or exchange effects",
    "Existing completed Stage 0 through Stage 7 implementation checkpoints remain unchanged"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED_HUMAN_AUTHORIZED"},
    {"id": "SPEC", "status": "REVISION_1_4_APPROVED_HUMAN_AUTHORIZED_DOCUMENTATION_CHECKPOINT_ONLY"},
    {"id": "CONTEXT", "status": "AUTHORIZED_RESEARCH_IN_PROGRESS"},
    {"id": "IMPLEMENT", "status": "REVISION_2_2_LIVE_MARKET_FOUNDATION_AUTHORIZED"},
    {"id": "VERIFY", "status": "REVISION_2_2_PENDING"},
    {"id": "RECORD", "status": "REVISION_2_2_PENDING"}
  ],
  "current_phase": "IMPLEMENT",
  "current_checkpoint": "REVISION_2_2_LIVE_MARKET_EXECUTION_FOUNDATION_AUTHORIZED",
  "implementation_status": "REVISION_2_2_IMPLEMENTATION_AUTHORIZED_NOT_YET_VERIFIED",
  "next_phase": "VERIFY",
  "next_phase_authorization": "AFTER_SCOPED_IMPLEMENTATION_WITH_REAL_DISPATCH_DEFAULT_OFF",
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
    ,{"phase": "INTERACTIVE_TRADING_CHART_WORKSPACE", "commit": "e0141d3a7f15f2679af36d5726335b610ffe8352"}
    ,{"phase": "CHART_FOLLOW_LATEST_RUNTIME_FIX", "commit": "74fb37db6554657f05d44d1631b583194021e5e0"}
  ],
  "repository_sync": {
    "branch": "main",
    "baseline_local_head": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "baseline_origin_main": "5b898963ef46bbd33771123ac169d7b8d52fc0e0",
    "latest_saved_checkpoint": "74fb37db6554657f05d44d1631b583194021e5e0",
    "status": "TRADING_CHART_IMPLEMENTED_SPATIAL_ALIGNMENT_INTEGRATION_PENDING"
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
    {"revision": "1.23", "reason": "Recorded the authorized runnable Fast DOM client slice as implemented and verified: shared state-preserving three-mode shell, SVG candlestick chart, compact interactive non-trading DOM and Tape, CENTER lock/manual movement, same-price Paper fixture dots and aggregate cancellation behavior, key-icon Paper account menu, normalized external market-data port with clearly labelled deterministic development feed, responsive layout, four focused tests, clean Biome, successful production build and HTTP 200 local startup smoke check; live Bybit, Robot, real credentials and all trading execution remain deferred", "date": "2026-08-22"},
    {"revision": "1.24", "reason": "Explicit human authorization for only the smallest Telegram Mini App phone-test integration around the existing frontend: Telegram WebApp container adapter, mobile viewport/safe-area handling, local browser preservation, server-side Bot API menu-button configuration using existing Telegram ownership and a temporary development HTTPS tunnel workflow without frontend secrets, permanent hosting, redesign, trading, Robot or credential implementation", "date": "2026-08-22"},
    {"revision": "1.25", "reason": "Recorded the Telegram Mini App phone-test slice as implemented and verified: the same React/Vite Workspace initializes through a browser-safe Telegram adapter, applies content safe areas and stable viewport sizing, remains locally runnable, accepts temporary trycloudflare development hosts, and configures the existing bot private-chat menu through an HTTPS-only server-side helper using existing local credentials; focused frontend, Python, build, governance and startup-host checks passed, while installation and user launch of the temporary tunnel remain the next user-side steps", "date": "2026-08-22"},
    {"revision": "1.26", "reason": "Documentation-only checkpoint preserving approved mobile Trading Workspace UX clarifications for compact chart chrome/tools, aligned collapsible prints-plus-DOM geometry, position PnL placement, lower-panel layout and collapse, non-reversing Market taps, two-finger chart Limit placement, active Limit reveal/cancel and confirmed move rollback semantics, and reference-led color direction; overall mobile design remains incomplete and no implementation slice is started or authorized", "date": "2026-08-22"},
    {"revision": "1.27", "reason": "Second documentation-only mobile UX checkpoint recording pending and full-position STOP/TAKE workflows, quantity and average-entry invariants, scanner-signal TAKE proposal suppression, no-position state, independent BUY/SELL volumes, permanent position-USDT and distinct hold details, two-row Limit inventory, actual live unrealized PnL indicator, average-entry line, order-line classes and the sampled graphite plus canonical #3BC639/#CD0000 palette; contradictory earlier mobile wording is superseded, design remains incomplete and no new implementation is started or authorized", "date": "2026-08-23"},
    {"revision": "1.28", "reason": "Human-approved documentation-only amendment superseding the general Market floor-to-qtyStep contract only for WorkingVolumeIntent Market sizing: select the mathematically nearest adjacent qtyStep with midpoint ties floored, permit ceil only through a maximum ten-percent reference-notional overshoot gate, otherwise reject fail closed for insufficient sizing precision; NotionalIntent, all Limit sizing, coin-quantity execution, factual engaged-WV projection and existing safety stages remain unchanged, and implementation is not started or authorized", "date": "2026-08-24"},
    {"revision": "1.29", "reason": "Documentation-only checkpoint recording observed PAPER runtime PASS evidence for implemented WorkingVolumeIntent Market nearest-step sizing, reduce-first behavior, cap-to-remainder, no flip-through-zero and authoritative PAPER-state Working Volume refresh while preserving existing lifecycle and safety semantics and authorizing no further implementation", "date": "2026-08-24"},
    {"revision": "1.30", "reason": "Human-authorized Stage 8 implementation checkpoint adding independent numeric BUY and SELL USDT-notional amounts initialized from authoritative one_wv_usdt, validation against empty or non-positive submission, edit-preserving PAPER refresh and permanent authoritative engaged_notional_usdt display beneath swords while preserving existing execution safety semantics", "date": "2026-08-24"},
    {"revision": "1.32", "reason": "Human-authorized Workflow Acceleration Package 2 checkpoint implementing an isolated one-command Playwright PAPER E2E harness over the real loopback backend and frontend, temporary SQLite runtime data, backend readiness, authoritative state assertions and unconditional teardown without changing trading semantics", "date": "2026-08-24"},
    {"revision": "1.33", "reason": "Human-authorized Workflow Acceleration Package 4 checkpoint deriving deterministic frontend/backend contract checks from existing Python models, enums and PAPER projections plus a checked frontend contract module, intentional mismatch fixtures and selective tools.dev.verify routing without changing trading semantics", "date": "2026-08-24"},
    {"revision": "1.34", "reason": "Human-authorized bounded PAPER Full Close implementation using backend-authoritative remaining coin quantity, opposite-side reduce-only execution, safe already-FLAT no-op, no flip-through-zero, checked frontend/backend request contract, authoritative exposure refresh and real PAPER E2E coverage", "date": "2026-08-25"},
    {"revision": "1.35", "reason": "Human-authorized bounded PAPER Limit foundation implementing checked BUY/SELL GTC contracts, shared sizing admission, durable idempotent create/cancel ledger, authoritative SQLite resting-order projection, simple Terminal controls/list and real PAPER lifecycle E2E without matching, partial fills, DOM, L2 or live execution", "date": "2026-08-25"},
    {"revision": "1.36", "reason": "Human-authorized bounded PAPER resting Limit amend/reprice implementing checked price-only mutation, shared price normalization, durable idempotency, atomic in-place persistence, authoritative UI refresh and real PAPER create-amend-cancel E2E without quantity amend, matching, DOM, L2 or live execution", "date": "2026-08-25"},
    {"revision": "1.37", "reason": "Checkpoint of serialized owner-thread PAPER execution, live ONGUSDT metadata and order-book authority, noncontiguous newer update-ID acceptance, 50-ms cumulative Smart Tape, x5 DOM compression, stable fixed ladder, canonical trade colors and IPv4 Vite binding while retaining the unresolved Tape-to-DOM spatial projection defect as the first next step", "date": "2026-08-26"},
    {"revision": "1.38", "reason": "Recorded the verified Lightweight Charts 5.2.1 Chart UX and follow-latest runtime fix in main, local-network mobile browser validation, and the separately implemented but unmerged Smart Tape to fixed DOM spatial-alignment patch with integration onto current main as the first next step", "date": "2026-08-26"},
    {"revision": "1.39", "reason": "Recorded DOM_STALE_CENTER_CAN_MOVE_SPREAD_OUTSIDE_FIXED_LADDER as a known unresolved issue after end-to-end runtime tracing proved that order-book quantities remain intact and that resolution requires a separately approved CENTER policy decision", "date": "2026-08-26"},
    {"revision": "1.40", "reason": "Recorded the implemented and human-accepted live PAPER unrealized-PnL and position-controls checkpoint, authoritative average-entry projection, live midpoint calculation, restored Smart Tape prints after duplicate-backend ownership diagnosis, accepted mobile control grouping and Chart live/interaction work as the next implementation priority", "date": "2026-08-26"},
    {"revision": "1.41", "reason": "Human-approved documentation-only amendment establishing the authoritative LIMITS button, creation popup, inventory overlay and equal chart/DOM fast-Limit entry paths on one shared LimitDraft architecture; explicitly superseding conflicting permanent rows, individual-cancel confirmation, release-to-submit, chart-only, dedicated DOM order controls and cross-spread Market conversion without authorizing implementation", "date": "2026-08-27"},
    {"revision": "1.42", "reason": "Human-approved documentation-only amendment replacing the unified LIMITS control and inventory with separate BUY LIMITS and SELL LIMITS controls, retaining side-specific pending-draft creation and chart fast-Limit drafts, and authorizing immediate multi-tap resting DOM Limit submission without pending drafts or ordinary per-order confirmation while preserving aggressive-Limit safety and authoritative execution synchronization; no implementation is authorized by this amendment", "date": "2026-08-27"},
    {"revision": "1.43", "reason": "Explicit human authorization to begin and continue production implementation of the already-approved revision 1.42 §50.1-§50.7 side-specific LIMITS and immediate DOM Limit placement amendment without changing its specification", "date": "2026-08-27"},
    {"revision": "1.44", "reason": "Implemented the PAPER authoritative-state synchronization foundation with durable monotonic revisions, serialized mutation-plus-state responses, one frontend authority, coalesced no-drop refresh, stale-response rejection, operation-scoped mutation activity and definitive Limit-draft lifecycle completion", "date": "2026-08-28"},
    {"revision": "1.45", "reason": "Recorded the canonical Trading Workspace master architecture and external-reference roadmap, its cross-session routing and the PHONE LIMIT MUTATION PATH DIAGNOSTIC as the immediate next action while preserving unaccepted Stage 1 status", "date": "2026-08-28"},
    {"revision": "1.48", "reason": "Implemented the systemic side-LIMIT creation-popup correction: an editable precision-preserving price draft, submission-boundary authoritative tick normalization and validation, shared TradingControl confirmation, and canonical PaperLimitDraftSubmitController to executePaperLimitCommand to PaperTradingStore mutation/state flow; phone acceptance remains pending", "date": "2026-08-28"},
    {"revision": "1.49", "reason": "Implemented systemic active-LIMIT chart edit interaction with a binding 300-ms hold, one order-id-keyed pointer state machine, local tick-normalized candidate projection, explicit shared-control confirm/cancel, and canonical identity-preserving PAPER amend through PaperTradingStore; phone acceptance remains pending", "date": "2026-08-28"},
    {"revision": "1.50", "reason": "Corrected the critical chart fast-Limit exactly-once violation by removing the competing touchstart intent source and retaining Pointer Events as the single cross-input semantic placement boundary; phone acceptance remains pending and active-LIMIT amend acceptance is paused", "date": "2026-08-28"},
    {"revision": "1.51", "reason": "Recorded BUY/SELL chart fast-Limit exactly-once real-phone acceptance and implemented one App-owned side-specific selected USDT volume source shared by quick Market controls, editable Limit popup, chart fast-Limit, DOM fast-Limit and popup submission; Stage 5 acceptance remains pending", "date": "2026-08-28"},
    {"revision": "1.52", "reason": "Implemented one shared Enter/Done lifecycle for trading numeric inputs: prevent default focus progression, stop propagation and blur without submission across BUY/SELL quick volume and Limit popup volume/price; phone acceptance remains pending", "date": "2026-08-28"},
    {"revision": "1.53", "reason": "Replaced the phone-rejected blur-only Done behavior with one terminal focus boundary and completion latch that owns post-Enter focus and rejects implicit sibling-input focus until an explicit pointer edit begins; phone acceptance remains pending", "date": "2026-08-28"},
    {"revision": "1.54", "reason": "Recorded the user's intentional deferral of the unresolved real-phone Done/Enter focus progression, removed temporary on-screen focus/IME diagnostics, preserved the current functional focus policy, and returned acceptance priority to the existing LIMIT sequence", "date": "2026-08-28"},
    {"revision": "1.55", "reason": "Recorded real-phone PASS evidence for the approximately 300-ms active-LIMIT edit hold and drag/release dashed-candidate controls, preserved the unresolved deferred Done/Enter issue, and clarified that the current × restore behavior remains incomplete because × must authoritatively cancel while outside activation alone abandons the edit", "date": "2026-08-28"},
    {"revision": "1.61", "reason": "Recorded real-phone acceptance of the complete active-LIMIT interaction slice: solid tap cancellation affordance, pre-hold movement abort, 300-ms hold-only edit, immediate dashed re-grab, authoritative per-line amend/cancel, consume-once outside restore, and mixed normal-draft plus edited-active GLOBAL confirm/cancel semantics", "date": "2026-08-28"},
    {"revision": "1.62", "reason": "Recorded real-phone acceptance of immediate resting DOM LIMIT placement through the shared canonical PAPER Limit-create lifecycle, including consecutive independent intents, stable identity, 300-ms anti-bounce, ambiguity lock, side-specific selected volume, authoritative Chart/DOM/Panel projection, equivalent PRICE/SIZE row activation and cancel-only own-order dots; aggressive DOM Limit confirmation and Done/Enter remain separately deferred", "date": "2026-08-28"},
    {"revision": "1.63", "reason": "Recorded the implemented collapsible DOM plus Smart Tape structural micro-slice with targeted tests, production build and exact-path verification passing while manual/real-phone acceptance remains pending; also referenced the approved post-current-stage central VPS migration direction without implementing it", "date": "2026-08-28"},
    {"revision": "1.64", "reason": "Recorded the account-wide PAPER Open Positions implementation and corrected its money-sensitive Full Close reconciliation so completed-but-still-open and ambiguous outcomes retain one stable locked attempt until authoritative FLAT; focused regressions, production build and fresh change-review pass while real-phone acceptance remains pending", "date": "2026-08-29"},
    {"revision": "1.65", "reason": "Completed account-wide Open Positions with backend-owned per-symbol current PnL and tick metadata plus serialized idempotent Close All orchestration while keeping phone acceptance pending", "date": "2026-08-29"},
    {"revision": "1.66", "reason": "Refined the real-phone Open Positions presentation with compact labeled rows, PnL percent and the header Close All control while keeping acceptance pending", "date": "2026-08-29"},
    {"revision": "1.67", "reason": "Recorded real-phone PASS and completion acceptance for account-wide PAPER Open Positions, and authorized WORKSPACE SYMBOL SWITCHING as the exact next implementation slice", "date": "2026-08-29"},
    {"revision": "1.68", "reason": "Implemented one canonical Workspace symbol-switch path shared by authoritative ticker autocomplete and confirmed Open Positions navigation, generalized the real backend active market-data session beyond ONGUSDT, added stale-source guards and kept real-phone acceptance pending", "date": "2026-08-29"},
    {"revision": "1.69", "reason": "Implemented the bounded real-phone symbol-switch layout refinement by moving ticker/timeframe into Chart, account control beside BUY/SELL LIMITS, shrinking adaptive chart label typography, reallocating the removed top strip height, and fixing clipped authoritative DOM own-order dots while keeping phone acceptance pending", "date": "2026-08-29"},
    {"revision": "1.70", "reason": "Recorded the human-approved autonomous Android manual terminal future direction as a planning-only track without authorizing implementation or changing the immediate Workspace acceptance path", "date": "2026-08-30"},
    {"revision": "1.71", "reason": "Recorded the human-approved Market Data Hub plus multiplexed Workspace stream architecture correction after backend authority passed but real-phone transport acceptance failed; promoted the former deferred consolidation, preserved fail-closed generation authority, and defined registry, readiness, health, migration and chaos-test contracts without implementing them", "date": "2026-08-30"},
    {"revision": "1.72", "reason": "Completed documentation-only M0 by inventorying the current per-symbol workers and three-SSE browser topology, recording bounded BTCUSDT and ONGUSDT payload/rate measurements, and defining target snapshot/delta, readiness, health, efficiency, additive migration and later chaos-acceptance contracts without implementing the Hub or changing transport/PAPER semantics", "date": "2026-08-30"},
    {"revision": "1.73", "reason": "Implemented and verified M1 as one authoritative backend InstrumentRegistry with complete Bybit linear pagination, strict Workspace-compatible filtering, Decimal-safe normalized metadata, duplicate/cursor-loop protection, atomic snapshot publication and previous-snapshot preservation; routed instruments API, Workspace switching and PAPER lookup through that registry without implementing M2", "date": "2026-08-30"},
    {"revision": "1.74", "reason": "Implemented and verified M2 as one long-lived backend MarketDataHub owning a shared Bybit public linear WebSocket, multi-symbol book/trade subscriptions, normalized dispatch, reconnect/resubscribe and reusable SymbolContexts; preserved generation-gated Workspace/PAPER/HTTP compatibility without implementing multiplexed frontend transport or later readiness/lifecycle stages", "date": "2026-08-30"},
    {"revision": "1.75", "reason": "Implemented and verified M3 as one backend WorkspaceController owning requested/active symbol authority, generation, pending candidate, composite book/trades/candle readiness, explicit switch failure and bounded warm-context reuse/expiry while preserving Hub ownership, PAPER semantics and existing SSE compatibility", "date": "2026-08-30"},
    {"revision": "1.76", "reason": "Implemented and verified M4 as one backend ClientMarketProjection with configurable bounded book bootstrap and exact window deltas/resnapshot, bounded deduplicated trade bootstrap/batches, one-time candle bootstrap/changed-record updates, additive projection SSE and measured BTC/ONG payload reduction while preserving full PAPER L2 and legacy frontend SSE", "date": "2026-08-30"},
    {"revision": "1.77", "reason": "Implemented and verified M5 as one additive generation-scoped multiplexed Workspace WebSocket with atomic bounded snapshot, sequenced book/trade/candle/health envelopes, bounded replay/resume, resnapshot on ambiguity and bounded slow-client eviction while preserving legacy SSE, REST commands, full PAPER L2 and unchanged frontend ownership", "date": "2026-08-30"},
    {"revision": "1.78", "reason": "Implemented and verified M6 as one frontend atomic Workspace projection over the M5 multiplexed WebSocket with complete snapshot gating, strict symbol/generation/sequence authority, bounded book/trade/candle updates, resume and fail-closed fresh resnapshot while preserving backend legacy SSE, full PAPER L2 and command semantics", "date": "2026-08-30"},
    {"revision": "1.79", "reason": "Implemented and verified M7 as deterministic bounded backend and frontend chaos/regression coverage for authority isolation, sequence and resnapshot boundaries, replay and queue pressure, reconnect/resume, component escalation and mixed projection churn while preserving legacy SSE, full PAPER L2 and command/order semantics; M8 device and transport acceptance remains not started", "date": "2026-08-30"},
    {"revision": "1.80", "reason": "Kept M8 open after production/tunnel real-browser 5m-to-1m acceptance exposed a reproducible Chart/DOM viewport feedback loop plus a coincident tunnel WebSocket abort; implemented and built a bounded stable-viewport shell correction and atomic 5m-to-1m-to-5m regression while requiring fresh tunnel/browser and real-phone re-acceptance before PASS", "date": "2026-08-30"},
    {"revision": "1.81", "reason": "Completed M8 after rebuilt production assets passed desktop and real-phone Chrome acceptance through the active lhr.life tunnel for ONGUSDT 5m-to-1m-to-5m with bounded Chart and DOM, visible candles, live DOM and Smart Tape, and no recurrence of LIVE BOOK UNAVAILABLE", "date": "2026-08-30"},
    {"revision": "2.0", "reason": "Implemented and accepted account-wide read-only LIVE reconciliation after a production build and real-phone test against a saved Bybit MAINNET account: fresh Refresh/Reconnect reached READY, showed real Equity and Wallet plus 33 positions and 13 active orders, preserved Paper as the sole Current account without switching, performed no LIVE mutations and exposed no credentials; next stage is active-account switching plus account-scoped Workspace activation without LIVE mutations", "date": "2026-08-31"},
    {"revision": "2.1", "reason": "Human-approved documentation-only bounded architecture amendment separating immutable PAPER storage identity from active session authority, defining one account-scoped Workspace projection router, atomic eligible account switching, session-aware stale rejection, a backend PAPER-only mutation gate, read-only LIVE views and unchanged public symbol/market-data authority; production implementation remains separately authorization-gated", "date": "2026-08-31"},
    {"revision": "2.2", "reason": "Human-authorized first safe LIVE execution slice limited to explicit manual MARKET BUY and MARKET SELL for the active writable Bybit MAINNET session, with durable command identity and idempotency, account/session fencing, persist-before-dispatch, default-off dual real-money gates, backend acceptance-notional ceiling, single-attempt mutation, UNKNOWN safety barrier and REST-only reconciliation; LIVE Limit, STOP, TAKE, full close, private WebSocket, autonomous dispatch and real-order acceptance remain unauthorized", "date": "2026-09-01"}
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

Normal resting fast Limit placement requires no confirmation. Fast DOM classifies intent before command
creation: BUY below Ask and SELL above Bid use the canonical GTC Limit path, while BUY at or above Ask and
SELL at or below Bid use the canonical Market path and are never created as Limits first. Missing required
authoritative book quotes remains fail-closed. Successful placement emits its characteristic sound only after
backend/execution-engine acknowledgement, never on the local pointer action.

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

## 33. Telegram Mini App phone-test slice authorization

The user explicitly authorizes only the smallest integration needed to open the existing runnable Workspace
inside Telegram on a phone. Authorized work is a Telegram WebApp container adapter in the same frontend,
basic viewport/safe-area handling, Vite development-tunnel compatibility, and a server-side Bot API helper
that configures the existing bot's private-chat menu button using the existing local token/chat configuration.

Development access uses a temporary HTTPS tunnel to the local Vite server; localhost remains supported for
browser debugging and no permanent hosting is introduced. Tokens and secrets remain server-side and are never
compiled into frontend code. This authorization excludes redesign, Robot, real trading, real credentials and
all unrelated functionality. It records `STAGE_8_TELEGRAM_MINI_APP_PHONE_TEST_SLICE_AUTHORIZED`.

## 34. Telegram Mini App phone-test slice implementation result

The existing React/Vite Workspace is now also a Telegram Mini App without creating a second frontend. A
browser-safe Telegram adapter calls `ready()` and `expand()` when embedded, applies Telegram content safe-area
insets and stable viewport height, and sets prototype-compatible header/background colors. Outside Telegram
the adapter is a no-op, so the existing localhost browser path remains supported and the shared
Terminal/Autopilot/Editor workspace architecture is unchanged.

The Vite development server accepts temporary `trycloudflare.com` tunnel hosts. The existing Telegram
transport owns an HTTPS-only Bot API menu-button helper, and a bounded configuration tool reuses the existing
local bot-token and owner-chat configuration. No token, exchange key or other secret is shipped to frontend
code or committed.

Verification passed: Biome; six focused frontend tests including Telegram browser and embedded behavior;
strict TypeScript and Vite production build; 37 focused Telegram delivery and governance tests; Python
compilation; diff checking; and a Vite startup smoke check returning HTTP 200 for both localhost and a
`trycloudflare.com` Host header before clean shutdown.

Phone launch still requires the user to install and start `cloudflared`, keep the local Vite server running,
and configure the resulting temporary HTTPS URL on the existing bot menu. This is a development/testing path,
not permanent hosting. No redesign, Robot logic, real trading, real credential handling or unrelated feature
was implemented. This amendment records
`STAGE_8_TELEGRAM_MINI_APP_PHONE_TEST_SLICE_IMPLEMENTED_VERIFIED`.

## 35. Mobile Trading Workspace UX clarification checkpoint

Revision 1.26 is documentation and context preservation only. It changes no frontend or runtime code, starts
no implementation and authorizes no implementation slice. The earlier implemented prototype and Telegram
container checkpoints remain historical implementation evidence; overall mobile UX design remains incomplete
and further clarification is expected.

### 35.1 Compact mobile chart core

The chart retains its price scale on the right, time scale along the bottom and current-price marker on the
price scale. Its compact top information order is `TICKER → TIMEFRAME SWITCHER → CURRENT ASSET PRICE`, with
the timeframe switcher immediately after the ticker. Prototype/service labels and explanatory copy that are
not part of trading operation are removed from the target trading UI.

Chart tools include inclined/trend line, horizontal line, ray, horizontal ray, Fibonacci, ruler and magnet.
They use a compact chart-tools UI and do not permanently consume a large part of the chart.

### 35.2 Aligned PRINTS FIELD and DOM panel geometry

The standalone Tape table below the chart is removed from the target mobile layout. Executed market trades
are visualized at their corresponding price levels in a `PRINTS FIELD` immediately left of the DOM rather
than in a conventional table. Prints and DOM levels align vertically, and the Prints field is approximately
comparable in area/width to the DOM field.

The expanded horizontal structure is `CHART + its price scale | PRINTS FIELD | DOM | persistent panel handle`.
The right Prints-plus-DOM panel slides out and hides; the same persistent handle remains visible while open
and closed so it can close or restore the panel.

Opening this panel never compresses, rescales or zooms the chart. The chart and its own price scale translate
horizontally to the left as one geometry-preserving unit: chart scale and the distance from current
price/candles to that price scale remain unchanged. Closing the panel returns that unit to its normal
horizontal position.

### 35.3 Position direction and live PnL in Prints

The Prints field also shows open-position direction and live PnL percentage. LONG uses the lower-left area;
SHORT mirrors it in the upper-left area. The indicator includes the directional arrow and percentage. Profit
is green, for example `+1.5%`; loss is red, for example `-1.5%`.

### 35.4 Lower trading panel layout and collapse

The first row directly below the chart begins at the left edge as
`crossed-swords engaged-WV indicator → BUY → SELL`; the swords indicator is not right-aligned. The active
Limit-order list sits below BUY/SELL at the left. At the right edge, STOP is vertically above TAKE PROFIT.
When the right panel is open, STOP/TP visually occupy the trading-panel area beneath it.

The bottom row is `AUTOPILOT | EDITOR | compact account button`. There is exactly one account control in this
row and none above the chart. The one compact button contains the key icon, compact/smaller account name
(`PAPER` in the current prototype) and deposit amount within the same button.

The entire lower trading panel can slide down and hide, leaving a persistent restore handle analogous to the
right-panel handle. Hiding it expands the chart and the open Prints/DOM panel vertically into the freed space,
making their rendering visibly larger. This is intentionally distinct from opening the right panel: lower
panel hiding adds vertical rendering area, whereas right-panel opening only translates the unchanged chart
geometry horizontally.

### 35.5 BUY/SELL Market behavior and two-finger fast Limit

BUY and SELL remain primary trading controls. A normal short tap performs the ordinary Market action with
the currently selected Working Volume. An opposite-side Market action reduces or closes an existing position
first and cannot flip through zero in the same action. If selected volume exceeds the confirmed remaining
opposite position, execution is capped at that actual remainder and excess volume does not open the reverse
side.

The approved touch fast-Limit interaction is specifically two-finger:

1. Finger one presses and continues holding BUY or SELL.
2. Finger two touches the chart, creating a horizontal Limit preview at that chart price, and may move it.
3. Releasing finger two while finger one still holds the side submits immediately at the selected Working
   Volume; there is no extra green-check confirmation for this fast gesture.
4. Releasing finger one before finger two cancels the gesture, removes the preview and submits no order.

Fast-hold safety remains unchanged: placement fails closed under degraded or ambiguous connectivity, every
intent has a unique client order identity, and reconciliation precedes any recovery that could duplicate or
make the action unsafe. The order line becomes opaque/active only when the authoritative confirmed order
state permits it.

### 35.6 Existing active Limit-line interaction

A single tap on an already active Limit line does not deactivate or move it. The line remains opaque and
active at its existing price; the tap reveals that price at the right end and a cancel cross to the right of
the price. The cross cancels only that concrete order.

Dragging an active line makes it transparent and temporarily inactive while repositioning. Releasing at the
proposed price retains the proposed line, shows its new price at the right end and displays a green circular
checkmark. No amendment is committed until that checkmark is activated. After successful confirmation, the
line is active and opaque at the new price. If the user instead activates outside the line and its
confirmation controls, the pending move is cancelled without a separate cancel button and the order returns
to its original price and active/opaque state.

### 35.7 Visual direction and precedence reconciliation

The current prototype colors are not the accepted target. Future visual work follows the previously supplied
and approved trading-terminal reference. This checkpoint does not fabricate exact color values that have not
been finalized.

For mobile/touch UX, this section supersedes earlier wording that placed a standalone Tape below the chart,
located the account/key control above the chart, treated right-panel expansion as a possible chart
compression/rearrangement, required confirmation for a normal BUY/SELL Market activation, or mapped the
second held-side finger exclusively to a DOM row. The approved mobile second finger now selects a chart price
for a Limit; the order is submitted when that finger releases while the side remains held. The green check is
only for confirming a moved existing Limit, never for the two-finger fast-Limit gesture. Existing desktop
input mappings, backend authority, confirmed-state presentation, anti-bounce, unique identity,
reconciliation and fail-closed safety remain unchanged unless explicitly superseded above.

This amendment records checkpoint
`STAGE_8_MOBILE_TRADING_WORKSPACE_UX_CLARIFICATIONS_RECORDED`. No next implementation slice is authorized.

## 36. Mobile Trading Workspace UX clarification checkpoint 2

Revision 1.27 is documentation/context preservation only. It changes no UI, frontend, backend or runtime
behavior and starts or authorizes no additional implementation. Revision 1.26 remains binding except where
this section explicitly supersedes its wording. The overall mobile UX design remains incomplete.

### 36.1 STOP and TAKE creation

Tapping STOP creates a transparent, inactive pending STOP line. Its proposed initial trigger price derives
from a configurable percentage distance from the relevant current/position price under existing order
semantics. The current LONG design example is `-2%`; this is not a permanently hard-coded constant. The user
may confirm the initial proposal immediately or move it and then confirm. Only successful confirmation makes
the STOP active and opaque. Once its workflow is initiated/established, the STOP button shows trigger price
and projected loss percentage beneath `STOP`.

Tapping TAKE similarly creates a transparent, inactive pending TAKE line. Its preferred initial target is the
calculated pattern target/potential when available. Otherwise it uses a configurable fallback currently
intended around `+3%` to `+4%`; the exact fallback remains unresolved. The user may confirm immediately or
move and confirm. Only successful confirmation makes it active and opaque. Once initiated/established, the
TAKE button shows target/execution price and projected profit percentage beneath `TAKE`.

Before the user initiates a STOP or TAKE, those buttons show no speculative price or percentage. The sole
exception is the signal-entry pending TAKE proposal in section 36.4.

### 36.2 One full-position TAKE and protection editing

There is exactly one primary TAKE PROFIT for the position. It protects/exits the full position; the UI does
not introduce TP1, TP2 or TP3. Partial profit-taking uses ordinary Limit orders.

A single tap on an active STOP or TAKE keeps its line active and opaque and reveals its price plus a
delete/cancel control. Deleting either STOP or TAKE requires explicit confirmation. Dragging an active
protection line makes it transparent and pending while repositioning. Release shows the proposed price and a
green circular confirmation checkmark. Activating the checkmark confirms the modification; activating
outside instead cancels the pending move and restores the original active price and opaque state.

### 36.3 Full-position quantity and average-entry invariants

Active STOP quantity and active TAKE quantity each always equal 100% of the current position size. Position
increases automatically increase both quantities; decreases and partial exits reduce them to the actual
remainder. Full close invokes the established post-close protection cleanup. Quantity synchronization alone
never changes a confirmed STOP or TAKE price.

Additional fills may change average entry. That recalculates displayed STOP loss percentage and TAKE profit
percentage and synchronizes both quantities to the full current position, but never automatically moves
either confirmed protection price. Moving a confirmed price always requires explicit user editing.

### 36.4 Scanner-signal TAKE proposal

Opening Trading Workspace from a scanner signal immediately offers a transparent pending TAKE proposal. It
uses the signal target/potential when available, otherwise the configured fallback. This is never an active
order automatically: the user may move it, and the green check submits/confirms it. Activating anywhere
outside the pending line and its confirmation control means SKIP: dismiss the proposal and submit nothing.

For the same signal, no new proposal appears if an active TAKE already exists or if the user explicitly
skipped that signal's proposal on an earlier open. Manual TAKE remains available later. Opening Workspace
without signal context never automatically proposes TAKE and only restores actual current position, order
and protection state.

### 36.5 No-position and open-position UI states

With no open position, the swords engaged-WV indicator is in zero state and its permanent position amount is
`0 USDT`. STOP and TAKE remain visible but inactive/unavailable because nothing exists to protect. BUY, SELL,
their volume controls and entry Limit orders remain available. The Prints-field position direction/PnL
indicator is absent.

When a Market fill or filled Limit creates a position, the UI automatically enters open-position state,
updates swords/WV and position USDT, shows the direction/PnL indicator and enables STOP/TAKE.

### 36.6 Independent side volumes and swords information

BUY and SELL volumes are independently configurable. A small dropdown arrow/control directly beneath BUY
sets BUY volume; the equivalent control beneath SELL sets SELL volume. BUY volume applies to both short-tap
BUY Market and the two-finger BUY fast Limit. SELL volume applies to both corresponding SELL actions. The
gesture chooses order type; the configured volume for that side chooses quantity.

The first row remains left-starting `crossed swords → BUY → SELL`. Current position amount in USDT is always
visible beneath the swords/engaged-WV indicator and follows the position's visual direction color. Two
distinct hold targets provide different information:

* holding swords shows the compact conceptual tooltip `1 РО = 100 USDT`, using the current one-WV value in
  whole USDT without cents;
* holding the permanent position-USDT amount shows current average entry price and current base-asset/coin
  quantity.

### 36.7 Two-row Limit-order inventory

The compact inventory contains exactly two primary rows: active BUY/LONG-direction Limits and active
SELL/SHORT-direction Limits. Each collapsed row shows the active count, a separate square expand-arrow
segment and a rightmost cancel-all cross. The direction row has rounded left corners; the final cross forms
the rounded right edge; row, arrow and cross read as one compact composite control.

The arrow expands all active Limits for that direction downward when space permits and upward otherwise.
Every individual item has its own cancel cross and individual cancellation requires confirmation. The
collapsed row's rightmost cross cancels all active Limits of that direction and also requires confirmation.

### 36.8 Live position PnL and average-entry line

The minimal Prints-field indicator uses actual live unrealized position PnL percentage from the authoritative
position/trading engine, never raw price distance from average entry. LONG remains lower-left and shows a
vertical up arrow, for example `↑ +1.5%`; SHORT remains upper-left and shows a vertical down arrow, for
example `↓ -1.5%`. Arrows are vertical, not diagonal. This indicator contains no position USDT, average
entry, coin quantity or additional detail.

While a position is open, the chart always shows a horizontal average-entry-price line. It automatically
moves when actual average entry changes and is never manually draggable. It is light gray/almost white with
a subtle visible highlight/glow, not direction-colored. Its numeric price is normally hidden. Holding the
line shows the exact price at its right end immediately before the chart price scale; release hides it again.
The position-USDT hold tooltip remains the alternate access path when chart lines are crowded.

### 36.9 Order-line classes and reference-derived palette

Active BUY/SELL Limit lines are solid and use the same canonical directional colors as their prints and best
Bid/Ask. STOP and TAKE are dashed and use distinct, less-bright/more-muted protection shades, remaining
visually distinct from Limits and average entry. Exact muted STOP/TAKE codes are not finalized. Average entry
is the almost-white highlighted solid line described above.

The supplied terminal screenshot is an implementation design reference, not an image-generation request.
Its sampled baseline is:

* primary graphite `RGB 69,69,69 / #454545`;
* lighter panel/surface `RGB 88,88,88 / #585858`;
* secondary dark graphite `RGB 67,67,67 / #434343`;
* canonical bright BUY/best Bid `RGB 59,198,57 / #3BC639`;
* secondary green `RGB 79,168,74 / #4FA84A`;
* canonical bright SELL/best Ask `RGB 205,0,0 / #CD0000`;
* secondary dark red `RGB 177,22,0 / #B11600`;
* orange/warning reference `RGB 216,146,75 / #D8924B`.

These are screenshot-derived values subject to nearby compression/antialiasing pixel variants. The current
canonical implementation direction is BUY/Bid `#3BC639` and SELL/Ask `#CD0000`; they must not be silently
replaced by unrelated generic green/red values.

Chart and Prints use the same graphite background and read as one continuous surface/color family. Bullish
candles, best Bid, BUY prints and BUY Limit lines share `#3BC639`. Bearish candles, best Ask, SELL prints and
SELL Limit lines share `#CD0000`. This is one directional language across candles, best book, prints and
active Limit lines.

### 36.10 Precedence reconciliation and design status

For mobile UX, this section supersedes any older wording that implies one shared BUY/SELL volume, hides
position USDT behind the swords hold, derives Prints PnL from raw price distance, introduces partial TP
controls, automatically moves confirmed STOP/TAKE prices after size or average-entry changes, permanently
labels average-entry price on the chart, uses a different Limit-list representation, or leaves the palette at
generic/prototype colors. Section 35's `selected Working Volume` means the independently configured volume
for the activated side. Its Prints PnL wording means actual engine unrealized PnL, and its color deferral is
superseded by the sampled baseline here except that exact muted STOP/TAKE shades remain unresolved.

All unrelated desktop mappings, backend/execution authority, protection cleanup, reconciliation, unique
identity and fail-closed safety contracts remain unchanged. The mobile design is still not finished and more
clarification will follow. This amendment records
`STAGE_8_MOBILE_TRADING_WORKSPACE_UX_CLARIFICATIONS_2_RECORDED`; it authorizes no implementation.

## 37. Working Volume Market nearest-step sizing amendment

Revision 1.28 is a human-approved documentation-only sizing amendment. It supersedes the revision 1.13
general Market floor-to-`qtyStep` direction only when the volume source is `WorkingVolumeIntent` and the
order kind is Market. It does not start or authorize implementation.

After authoritative WV-to-USDT sizing, Working Volume Market raw base-asset quantity is compared against
its adjacent floor and ceil `qtyStep` candidates. The candidate with the smaller absolute quantity error,
equivalently the smaller absolute reference-notional error at the same sizing reference price, is selected.
An exact midpoint or other exact tie selects floor.

A nearest ceil candidate is admissible only when its reference-notional overshoot relative to the target
Working Volume notional satisfies:

```text
overshoot_ratio =
    (candidate_reference_notional - target_wv_notional)
    / target_wv_notional

overshoot_ratio <= 0.10
```

If nearest selection requires ceil and `overshoot_ratio > 0.10`, admission fails closed with an explicit
insufficient-sizing-precision / excessive-WV-rounding-overshoot rejection. It must not silently fall back to
a materially undersized floor candidate and present that quantity as the requested Working Volume. If floor
is the nearest candidate, floor remains admissible subject to all later checks.

`NotionalIntent` retains its existing floor-to-`qtyStep` safety contract. Every Limit order, including a
Limit sourced from `WorkingVolumeIntent`, also retains floor-to-`qtyStep` normalization without increasing
requested exposure.

After quantity selection, all existing safety stages remain binding and unchanged: authoritative instrument
metadata; minimum and maximum quantity; minimum notional; opposite-side Market reduce/close-first
classification; cap to actual confirmed remaining position quantity; `reduceOnly`; no flip-through-zero;
connectivity, trust and reconciliation gates; durable command identity; persistence-before-submit;
idempotency; deduplicated execution evidence; and fail-closed uncertain-outcome handling.

Execution remains base-asset coin-quantity based. Partial and full close use factual remaining coin quantity,
never a recalculation from original WV notional. Engaged WV remains derived from the authoritative factual
position projection and current one-WV context, not from an assumption that a requested `1 WV` was executed
exactly.

Acceptance example:

```text
PAPER equity                 = 5000 USDT
1 WV                         = 250 USDT
BTCUSDT sizing reference     = 64250 USDT/BTC
qtyStep                      = 0.001 BTC
raw quantity                 ≈ 0.00389105 BTC
floor candidate              = 0.003 BTC
floor reference notional     = 192.75 USDT
ceil candidate               = 0.004 BTC
ceil reference notional      = 257.00 USDT
ceil overshoot               = (257.00 - 250.00) / 250.00 = 0.028 = 2.8%
decision                     = 0.004 BTC because 2.8% <= 10%
```

For a tiny-WV case where the nearest executable ceil candidate exceeds the target reference notional by
more than ten percent, the request is rejected fail closed. It is not converted into a substantially
different exposure and does not fall back to a materially undersized floor candidate as if full WV sizing
precision had been achieved.

This narrow amendment records checkpoint
`WORKING_VOLUME_MARKET_NEAREST_STEP_SIZING_AMENDMENT_RECORDED`. Historical revision 1.13 remains evidence
of the former general Market floor contract. No runtime, application, frontend or test implementation is
started or authorized by this checkpoint.

## 38. Working Volume Market PAPER runtime-validation checkpoint

Revision 1.29 records documentation-only runtime validation of the already implemented revision 1.28
WorkingVolumeIntent Market nearest-step policy. It does not change production code, expand scope, weaken
any lifecycle or safety gate, or authorize further implementation.

Observed PAPER evidence:

```text
PAPER equity / one WV        = 5000 USDT / 250 USDT
initial position             = Long 0.005 BTC / 1.28501 WV
BUY 1 WV result              = Long 0.009 BTC / 2.313018 WV
selected increment           = +0.004 BTC nearest-step sizing
first SELL result            = Long 0.005 BTC
second SELL result           = Long 0.001 BTC
third SELL result            = Flat 0 BTC
UI engaged-WV sequence       = 1.3 -> 2.3 -> 1.3 -> 0.3 -> 0.0
```

Runtime validation result:

```text
nearest-step sizing                         PASS
reduce-first                                PASS
cap-to-remainder                            PASS
no-flip-through-zero                        PASS
authoritative PAPER-state WV refresh        PASS
```

The BUY observation confirms selection of the `+0.004 BTC` nearest executable step. The successive SELL
observations confirm reduce-first execution, capping to the factual remaining coin quantity, transition to
FLAT without reversal, and no flip-through-zero. The UI sequence follows the authoritative PAPER position
state, including the residual `0.001 BTC` position and final zero state; displayed WV remains a factual
projection rather than execution authority.

All revision 1.28 safety semantics remain binding, including authoritative instrument metadata, admission
checks, opposite-side classification, `reduceOnly`, reconciliation, durable identity, idempotency and
fail-closed uncertain-outcome handling. This amendment records checkpoint
`WORKING_VOLUME_MARKET_NEAREST_STEP_PAPER_RUNTIME_VALIDATED`.

## 39. Stage 8 independent Market notional amounts implementation checkpoint

Revision 1.30 records the human-authorized implementation and focused verification of independent numeric
amount fields directly beneath BUY and SELL. On entry to TERMINAL, both fields initialize from authoritative
`/api/paper-state.one_wv_usdt`; the current PAPER value is `250`. Each field remains independently editable,
contains only its numeric value and submits a short-tap Market action through the existing USDT
`NotionalIntent` path without frontend WV conversion. Empty, non-finite and non-positive values do not
submit.

Successful execution still refreshes authoritative PAPER state. That refresh updates engaged Working Volume
and the permanent current-position amount beneath swords from `engaged_notional_usdt`, displaying zero when
flat, but does not overwrite a user-edited side amount. A pristine side may follow a refreshed authoritative
one-WV value independently of an edited opposite side.

This slice does not change backend execution classification or quantity normalization. Existing reduce-first,
cap-to-confirmed-remainder, reduce-only, no-flip-through-zero, PAPER authority, reconciliation, command
identity and fail-closed safety behavior remain binding. STOP, TAKE and unrelated UI are unchanged.

This amendment records checkpoint
`STAGE_8_INDEPENDENT_MARKET_NOTIONAL_AMOUNTS_IMPLEMENTED_VERIFIED`. No further implementation is authorized
by this checkpoint.

## 40. Market-amount sizing and presentation implementation checkpoint

Revision 1.31 records implementation and scoped verification of the approved Market-amount cluster.
`NotionalIntent` Market sizing now selects the nearest adjacent `qtyStep`; an exact midpoint tie selects
floor. A ceil candidate is admitted only when its reference-notional overshoot is at most five percent.
When the nearest candidate requires a larger overshoot, admission fails closed with
`INSUFFICIENT_SIZING_PRECISION`. The existing `WorkingVolumeIntent` Market nearest-step ceiling remains ten
percent, and every Limit sizing path retains floor-to-step semantics.

The permanent authoritative position notional beneath swords is presented as whole USDT while the backend
projection remains exact. The client maps insufficient sizing precision to
`Сумма слишком мала для шага объёма`; other incomplete BUY and SELL outcomes are shown as `BUY отменено`
and `SELL отменено` respectively.

All existing opposite-side Market cap-to-confirmed-remainder, `reduceOnly`, no-flip-through-zero,
protection, connectivity, trust, reconciliation, command identity and fail-closed semantics remain
unchanged. This amendment records checkpoint
`MARKET_AMOUNT_CLUSTER_IMPLEMENTED_VERIFIED`.

## 41. Isolated PAPER Workspace E2E runtime harness checkpoint

Revision 1.32 records the human-authorized Workflow Acceleration Package 2 implementation. The canonical
`cd terminal/frontend && npm run e2e` command allocates isolated loopback ports, starts the existing PAPER
HTTP runtime against a temporary SQLite database, waits for health, serves the existing Vite frontend,
drives Chromium through Playwright, asserts both UI behavior and authoritative `/api/paper-state`, and always
stops spawned processes and removes temporary runtime and test-result data.

The scenario covers initial authoritative PAPER state, edit-preserving BUY amount refresh, Market BUY
position mutation, backend-derived displayed USDT notional, oversized opposite Market flattening without
reversal, and the approved insufficient-sizing message with unchanged FLAT backend state. The runtime remains
PAPER-only through `PaperOnlyAdapter`; no live exchange adapter, credential, real order or external mutation
path is enabled. Production defaults remain `paper_runtime.sqlite3` and port `8765`; environment overrides
exist only to make the same launch path safely isolatable.

This amendment records checkpoint `ISOLATED_PAPER_WORKSPACE_E2E_IMPLEMENTED_VERIFIED`.

## 42. Workflow Acceleration Package 4 contract-consistency checkpoint

Revision 1.33 records the human-authorized deterministic Trading Workspace contract checker. The one-command
entry point `python -m tools.dev.contract_consistency` compares the frontend request, response, enum, volume,
position-side and handled-reason declarations against existing backend dataclasses, enums and the statically
discoverable PAPER state projection. The frontend consumes its checked declarations directly, preventing a
separate unused schema copy.

Focused tests inject unsupported sides and units, missing backend response fields, invented handled reason
codes and request-shape drift and prove fail-closed output. `tools.dev.verify` routes the checker only when
Terminal API, relevant execution-contract backend paths, the checked frontend contract/consumer, or the
checker and its tests are in scope. Trading authority, PAPER-only execution, reconciliation, no-flip,
durable identity and all prior safety semantics are unchanged. This amendment records checkpoint
`WORKFLOW_ACCELERATION_PACKAGE_4_CONTRACT_CONSISTENCY_IMPLEMENTED_VERIFIED`.

## 43. PAPER Full Close / Close-to-FLAT implementation checkpoint

Revision 1.34 records the human-authorized bounded Full Close slice. TERMINAL now exposes
`Закрыть позицию` through a dedicated checked request contract containing only client action identity and
symbol. The backend rereads authoritative PAPER position state: LONG closes with SELL and SHORT closes with
BUY for exactly the factual remaining base-asset quantity. The request is reduce-only and cannot become an
entry, scale-in or flip-through-zero operation.

Already-FLAT state completes as an idempotent no-op without creating an order or execution. A successful
close refreshes authoritative PAPER state and the frontend engaged Working Volume and position notional;
the canonical FLAT projection is zero quantity, `0.0` engaged WV and `0` USDT engaged notional. Focused
runtime tests cover LONG, SHORT, no flip and repeated FLAT close, while the isolated real PAPER E2E covers
open position, Full Close, backend FLAT and frontend zero-exposure refresh.

PAPER-only execution, persistence-before-submit, unique command identity, exactly-once execution evidence,
fail-closed admission and reconciliation locks remain unchanged. DOM, L2, chart trading, Limit, SL/TP,
AUTOPILOT/Robot and live Bybit execution remain outside this slice. This amendment records checkpoint
`PAPER_FULL_CLOSE_TO_FLAT_IMPLEMENTED_VERIFIED`.

## 44. PAPER Limit Order Foundation implementation checkpoint

Revision 1.35 records the human-authorized bounded PAPER Limit foundation. Checked create and cancel
contracts support BUY or SELL, existing USDT/Working Volume sizing, positive normalized Limit price and
binding `GTC`. Admission reuses the existing `PreTradeGuard`; no parallel quantity or price normalization
was introduced.

SQLite schema v5 adds authoritative resting PAPER Limit orders and a durable client-action ledger. Repeating
the same create action and payload returns the original order without duplication; reuse with conflicting
intent fails closed. Concrete-order cancel is durable and idempotent, and cancelling an already cancelled or
absent identity is a successful no-op that cannot mutate a position. Resting orders do not match or fill in
this slice.

TERMINAL provides temporary functional side, price and amount controls, authoritative active-order refresh
and per-order cancel. The real PAPER E2E covers create BUY Limit, authoritative appearance, UI display,
cancel, authoritative disappearance and safe repeat cancel. Focused tests also cover BUY/SELL, GTC,
duplicate create, invalid price/amount, contract drift and schema-backed persistence. DOM, L2, chart
interaction, aggressive-Limit confirmation, SL/TP, partial fills, matching, WebSocket, live execution and
Robot/AUTOPILOT remain excluded. This amendment records checkpoint
`PAPER_LIMIT_ORDER_FOUNDATION_IMPLEMENTED_VERIFIED`.

## 45. PAPER resting LIMIT Amend / Reprice implementation checkpoint

Revision 1.36 records the human-authorized bounded PAPER resting Limit price-only amend. A checked request
identifies one active order by durable `order_id`, supplies a durable `client_action_id` and changes only the
Limit price. Existing `PreTradeGuard` admission and price normalization remain authoritative; the order ID,
side, original quantity and binding `GTC` are preserved.

SQLite schema v6 extends the PAPER action ledger with `amend`. The normalized price update and action record
commit atomically. Repeating the same action and payload is idempotent without creating another order;
conflicting identity reuse fails closed. Missing, inactive or cross-symbol orders cannot be amended.
The active-order projection and temporary TERMINAL control refresh immediately from backend authority.

Focused runtime, persistence, contract-consistency and component tests cover the mutation invariants. The
real PAPER E2E covers create BUY Limit, amend price, unchanged identity/side/quantity/GTC, authoritative and
UI price refresh, cancel and disappearance. Quantity amend, fills, partial fills, matching, queue modelling,
cancel-replace, aggressive execution, DOM, L2, chart drag, WebSocket market data, SL/TP, Live Bybit and
Robot/AUTOPILOT remain excluded. This amendment records checkpoint
`PAPER_LIMIT_AMEND_REPRICE_IMPLEMENTED_VERIFIED`.

## 46. Live Trading Workspace market-data and PAPER-runtime checkpoint

Revision 1.37 records the current verified implementation checkpoint while the overall ChangeRequest remains
`IMPLEMENT / IN_PROGRESS`. PAPER execution now owns `SQLiteStore` on a dedicated runtime-owner thread;
threaded HTTP workers submit serialized Market, state, Limit create/amend/cancel and Full Close operations
through that lane. `SQLiteStore._assert_owner()` and fail-closed behavior remain binding.

Production PAPER execution is no longer BTC-only. It uses authoritative Bybit instrument metadata and the
live book provider for `ONGUSDT`; direct PAPER BUY live smoke completed and authoritative PAPER state showed
a Long position. The public market-data runtime consumes `orderbook.50.ONGUSDT`, exposes the book through
SSE and accepts every strictly newer update ID while ignoring stale or duplicate IDs; update IDs are not
required to be contiguous. Live observation remained continuously READY for approximately 30 seconds with
50 bids and 50 asks and increasing update ID and sequence.

Public trades are aggregated in 50 ms windows, separately by side and across successive same-side
executions. Each cumulative print preserves authoritative execution-price geometry, total quantity and
notional, execution range and swept ticks. Its height represents swept price range and its width uses weak
`log1p` USDT-volume compression. DOM uses a five-native-tick display step (`0.00005` for ONGUSDT), sums
liquidity with side-aware bucketing, preserves authoritative native best Bid/Ask and renders a continuous
16-row ladder whose geometry survives missing liquidity and market-data deltas. BUY/Bid/candle styling uses
`#3BC639`; SELL/Ask/candle styling uses `#CD0000`. Vite explicitly binds `127.0.0.1`, avoiding Windows
`localhost` resolution to `::1`.

This visual checkpoint is not complete. Live screenshot evidence shows a material Smart Tape spatial
projection defect: prints near approximately `0.09455-0.09470` were rendered against a fixed DOM spread near
approximately `0.09520-0.09525`. The first recovery task is to enforce the invariant that an execution at
price X renders at exactly the same Y coordinate as the DOM row for X. Inspect the shared price-to-row/Y
projection, obsolete row offsets and CSS top/bottom offsets, Tape versus DOM coordinate origins,
`ladderCenterPrice`/top price, row height and clipping/container offsets.

Only after exact spatial alignment, verify temporal public-trade versus order-book/SSE synchronization.
Then further narrow cumulative-print bubbles and replace frontend tick-size inference with authoritative
read-only tick size in the SSE contract. The later CENTER UX remains: single tap performs one-shot center,
double tap enables locked auto-centering and manual scroll disables the lock. The stale UI label
`Market data: deterministic development feed` must also be corrected later to reflect the actual live source.

This amendment records checkpoint `LIVE_TRADING_WORKSPACE_MARKET_DATA_CHECKPOINT_RECORDED`; it does not mark
Trading Workspace complete and authorizes no new implementation beyond the already completed working-tree
scope.

## 47. Interactive Chart UX and isolated spatial-alignment checkpoint

Revision 1.38 records the current authoritative main checkpoint
`74fb37db6554657f05d44d1631b583194021e5e0` while the overall ChangeRequest remains
`IMPLEMENT / IN_PROGRESS`.

The Chart UX batch is implemented in main by
`e0141d3a7f15f2679af36d5726335b610ffe8352`. The previous SVG prototype was replaced with
Lightweight Charts 5.2.1, providing responsive candlesticks, time and right-price scales, grid and
crosshair; directional midpoint-anchored pinch scaling with a three-percent dead zone and 1.55 dominance
ratio; horizontal, vertical and independent diagonal scaling; manual/automatic price-scale control;
cursor-anchored wheel and Ctrl+wheel scaling; direct axis scaling; horizontal pan; and follow-latest UI.
The chart drawing layer provides Select, Crosshair, Trend Line, Horizontal Line, Ray, Horizontal Ray,
Vertical Line, Fibonacci, Ruler and Rectangle tools with enlarged hit areas, selection, anchor/object
dragging, Delete/Escape and mobile delete, lock, clear, undo/redo, nearest-OHLC Magnet and version-1
localStorage persistence per symbol and timeframe. Canonical BUY `#3BC639` and SELL `#CD0000` colors remain
preserved.

The follow-latest runtime defect is fixed in main by
`74fb37db6554657f05d44d1631b583194021e5e0`. The chart-stage capture handler previously called
`setPointerCapture()` for the `→|` button, preventing its click, while `scrollToPosition(0, false)` did not
represent the configured realtime position with the active right offset. Gesture capture now ignores the
follow-latest control, the control calls the Lightweight Charts public `scrollToRealTime()` API, and
follow-latest state remains derived from the factual visible logical range. Manual runtime verification
passed: panning into history shows `→|`, activation returns the chart to latest, and the control disappears
only after latest is reached.

Smart Tape to fixed-DOM spatial alignment is implemented only in isolated commit
`87a8573c654ad2df339217ea86669a9e702004ac` on branch
`codex/spatial-tape-dom-alignment` in `C:\BybitScanner-spatial`; it is not merged into main. The patch maps
the principal `lastExecutionPrice` through the same side-aware x5 compressed DOM bucket and exact fixed row
Y coordinate, while sweep range affects bubble height only. Examples are BUY `0.09233 → 0.09230` and SELL
`0.09247 → 0.09250`. DOM and Tape share `--dom-row-height: 1.36rem` and a common vertical origin; the stale
numeric `top: 2rem` mismatch is removed. Browser pixel audit measured zero-pixel alignment delta.

The isolated spatial branch is based on an older checkpoint. The first next task is to rebase or otherwise
safely integrate it onto current main `74fb37db6554657f05d44d1631b583194021e5e0`, review conflicts—especially
`styles.css`—run spatial, Chart UX and follow-latest regressions, and complete manual review before merging.
Only after spatial alignment integration: verify temporal `publicTrade` to order-book synchronization,
further narrow cumulative Smart Tape bubbles, replace frontend tick-size inference with authoritative
frontend tick size, and later implement the new CENTER UX. This order must not change without a separate
decision.

For current local/mobile testing, the PAPER backend runs from `C:\BybitScanner` with
`python -m terminal.runtime.paper_http_server` at `http://127.0.0.1:8765`; current public market streams use
`ONGUSDT`. The frontend runs from `C:\BybitScanner\terminal\frontend` with
`npm run dev -- --host 0.0.0.0`; the observed LAN URL was `http://192.168.100.8:5173/`, and the Trading
Workspace opened successfully in a phone browser. Telegram Mini App/button configuration was not part of
this checkpoint; testing used the browser over the local network.

This amendment records checkpoint `TRADING_CHART_IMPLEMENTED_SPATIAL_ALIGNMENT_INTEGRATION_PENDING`. It
does not mark Trading Workspace complete and does not claim that the isolated spatial patch is in main.

## 48. Known unresolved fixed-ladder stale-center issue

Revision 1.39 records `DOM_STALE_CENTER_CAN_MOVE_SPREAD_OUTSIDE_FIXED_LADDER` as a known unresolved issue.
With LOCKED CENTERING disabled, the continuous fixed 16-row DOM ladder preserves its last `centerPrice`.
During sufficiently fast market movement, the current spread can leave the narrow visible window. Rows in
the lower portion may then appear to be empty bid rows at x3 or x10 even though that portion of the ladder
no longer covers the current bid region. A real one-shot CENTER returns the spread and populated bid rows to
the ladder; it intentionally does not enable persistent following.

Correlated runtime tracing followed one update through Bybit WebSocket handling,
`PublicOrderBookBuffer`, SSE serialization, the browser EventSource, `normalizeLevels`, `projectDomBook`
and the rendered `DomPanel`. The investigation excluded backend depth loss, SSE truncation, frontend
normalization truncation, compressed-bucket aggregation loss, `formatDomSize`, JSX/CSS hiding, stale
repository or Vite proxy routing, and `WinError 10053` as causes. The latter is handled as an ordinary
disconnected SSE client and does not clear or stop the independent order-book worker.

Verified diagnostic steps included changing depth from 50 to 1000, observing a live READY book with 1000
bids and 1000 asks, exercising a dense synthetic projection regression, tracing backend-to-rendered-row
update identity and quantities, verifying CENTER/manual recenter behavior, and checking the backend and
Vite listener processes, working paths and `/api` proxy target. The depth increase and dense projection
test are independent capacity/regression protections; neither is considered a fix for this stale-center
issue.

The Smart Tape-to-DOM spatial invariant remains binding: execution price X must use the same shared
side-aware compressed bucket and exact Y coordinate as DOM price X. Any future centering change must move
DOM and Smart Tape through their shared `centerPrice` without changing this invariant.

Resolution requires a separate explicit CENTER design decision. Candidate policies are auto-follow until
the first manual drag/reposition, recenter only when the spread exits the visible ladder, default locked
follow, or another explicitly approved CENTER UX. The recommended option for later review is auto-follow
until the first manual drag/reposition. This checkpoint does not select or implement any option and leaves
the approved one-shot and LOCKED CENTERING semantics unchanged.

This amendment records checkpoint `DOM_STALE_CENTER_KNOWN_UNRESOLVED_ISSUE_RECORDED` and introduces no
CENTER implementation authorization.

## 49. Live PAPER position PnL and accepted controls checkpoint

Revision 1.40 records checkpoint `LIVE_PAPER_POSITION_PNL_UX_ACCEPTED`. The PAPER state projection now
exposes authoritative `average_entry`. The existing PAPER refresh supplies position side, symbol and full
average-entry precision; no second polling loop was added. App derives current price from the live order-book
midpoint `(bestBid + bestAsk) / 2`. One shared pure helper calculates LONG and SHORT unrealized PnL for both
Smart Tape and the lower POSITION INFO. Average entry is rounded to five decimals only for presentation;
the PnL calculation retains the full authoritative value.

Human mobile and desktop smoke review accepted restored Smart Tape publicTrade prints, live unrealized PnL
movement on a fresh LONG position from approximately zero percent with the market, five-decimal average-entry
display and the compact lower controls. The accepted grouping is LEFT `BUY / SELL`, CENTER
`swords/RO + Full Close + POSITION INFO`, RIGHT-CENTER `LIST / AUTOPILOT`, and RIGHT `STOP / TAKE`.
Full Close continues through the existing `/api/full-close` path; execution semantics are unchanged.

The runtime diagnosis also established an operational Windows hazard: multiple backend listener/process
ownership around port 8765 can leave an older backend serving a newer frontend, producing paper-state and
market-data schema version skew. Once port ownership was reduced to one backend from the current working
tree, order-book availability, publicTrade prints and PnL data flow were restored. Browser-extension warnings
were unrelated.

The exact next implementation priority is `CHART LIVE/INTERACTION WORK`: (1) proper live candle-price
updates, (2) normal pan/zoom, (3) directional two-finger pinch behavior on mobile, (4) verification of
price/time coordinate mapping, (5) removal of unnecessary drawing tools, then (6) completion of the remaining
drawing tools. Temporal publicTrade-to-order-book synchronization is explicitly deferred behind this Chart UX
priority and is not started by this checkpoint.

## 50. Authoritative side-specific LIMITS UX amendment

Revision 1.42 records checkpoint
`SIDE_SPECIFIC_LIMITS_AND_IMMEDIATE_DOM_PLACEMENT_RECORDED_DOCUMENTATION_ONLY`.
This section is the authoritative LIMITS UX and architecture specification and fully supersedes revision
1.41's unified-control model. This is a documentation-only amendment: the ChangeRequest remains
`IN_PROGRESS` in `IMPLEMENT`, no production implementation is authorized by this checkpoint, and existing
backend, frontend, tests and runtime behavior are unchanged.

### 50.1 Main trading-panel controls

The old unified `LIMITS N` control, its symbol-wide adjacent cancellation cross and the shared LONG/SHORT
inventory overlay are removed from the target UX. Their place contains two distinct controls:
`BUY LIMITS` and `SELL LIMITS`. `BUY LIMITS` owns only BUY/Long Limit creation and inventory presentation
for the current symbol. `SELL LIMITS` owns only SELL/Short Limit creation and inventory presentation.

### 50.2 Single activation: side-specific pending draft

A single activation of `BUY LIMITS` opens the existing compact creation fields for BUY/Long only. Selecting
its price creates the existing pending editable BUY `LimitDraft`, renders its dashed BUY line on the chart
and preserves the established draft editing, tick normalization, sizing, duplicate protection and explicit
checkmark-confirmation workflow.

A single activation of `SELL LIMITS` provides the exact mirrored SELL/Short behavior. Neither control creates
a separate draft model or submission system. Existing dismissal, popup-to-line price synchronization,
authoritative `tickSize` requirement and ambiguous-submit lock remain binding.

### 50.3 Long activation: side-specific active inventory

A long activation of `BUY LIMITS` opens directly upward from that button a list containing only active BUY
Limits for the current symbol. A long activation of `SELL LIMITS` opens the mirrored list containing only
active SELL Limits. Each list orders rows by increasing absolute distance between order price and current
market price, so the nearest order is first at the top. Stable order identity resolves equal-distance ties.

Existing available concrete-order actions remain available in the applicable side list. Individual-order
cancellation requires no additional confirmation where already approved. All rows and counts change only
after authoritative cancellation or fill state is received; optimistic removal remains prohibited.

### 50.4 Existing chart fast-Limit workflow

The existing BUY/SELL hold plus chart workflow remains unchanged. A chart price selection creates the
existing pending editable `LimitDraft` and dashed chart line and requires the established explicit draft
confirmation. Multi-draft behavior already implemented for chart placement is preserved. Ordinary short-tap
BUY/SELL Market semantics and the 200-ms hold threshold are unchanged.

### 50.5 Immediate DOM fast-Limit placement

While the existing BUY hold is active, each tap on a DOM price immediately submits one BUY Limit at that DOM
price. While the existing SELL hold is active, each tap immediately submits one SELL Limit. A DOM placement
creates no pending draft, dashed line or green checkmark and requires no ordinary per-order confirmation for
a resting Limit. Multiple DOM taps during the same continuing hold may submit multiple independent Limits.

Every DOM placement is a Limit intent and must never be converted to Market. On successful authoritative
creation it appears in active Limits, as a solid active chart Limit line and in the applicable side-specific
inventory. It disappears after authoritative full fill or cancellation; a partial fill remains active with
its authoritative remainder. Existing fill/cancel refresh and reconciliation remain the only UI authority.

### 50.6 Shared execution and safety boundaries

Immediate DOM placement bypasses only the pending-draft presentation and per-order confirmation stages. It
must reuse the existing side-aware tick normalization, side-configured sizing and quantity conversion,
stable per-attempt `client_action_id`, duplicate protection, Limit submission API, persistence, PAPER/live
execution boundary, reconciliation and authoritative projection pipeline. It must not duplicate matching,
execution or Position arithmetic.

Resting DOM selections submit through canonical GTC Limit creation without confirmation. Spread-crossing
BUY at or above Ask and SELL at or below Bid submit through canonical Market execution and are not created as
Limits first. Required book authority remains fail-closed; this routing does not weaken command identity,
ambiguity, reconciliation, or acknowledgement safeguards.

### 50.7 Explicit supersession and preserved semantics

Revision 1.42 supersedes revision 1.41 §50.1-§50.7 and every associated metadata summary that requires:

1. one unified `LIMITS N` control or one shared LONG/SHORT inventory overlay;
2. a combined LONG/SHORT creation popup rather than side-specific BUY or SELL creation;
3. DOM and chart price selection to share the same pending `LimitDraft` presentation lifecycle;
4. a pending dashed line, green checkmark or ordinary resting-order confirmation for immediate DOM placement;
5. only one DOM Limit submission during a continuing BUY/SELL hold.

Earlier sections 5, 19, 21.5, 26.2, 35.5, 35.7 and 36.7 and their metadata are superseded wherever they
conflict with §50.1-§50.6. Unrelated semantics remain authoritative, including fail-closed behavior,
idempotency, ambiguous-outcome reconciliation, existing Market behavior outside hold, chart fast-Limit
drafts, PAPER matching and execution math, fill/cancel synchronization, STOP, TAKE and Position behavior.

## 51. PAPER authoritative state synchronization checkpoint

Revision 1.44 records checkpoint `PAPER_AUTHORITATIVE_STATE_SYNCHRONIZATION_IMPLEMENTED` while the overall
ChangeRequest remains `IMPLEMENT / IN_PROGRESS`. SQLite schema v9 owns a durable monotonic PAPER state
revision per account and symbol, including a safe v8 migration. Limit create, effective cancel, effective
amend, Market execution, Full Close execution and Limit fills advance the revision transactionally with
their authoritative state change through the serialized PAPER runtime owner. Idempotent replay and no-op
amend do not advance it.

PAPER mutation HTTP responses now carry the mutation result and the resulting authoritative `paper_state`
from the same serialized runtime operation. The frontend has one `PaperTradingStore` that applies only
non-older revisions, coalesces refresh requests made during an in-flight refresh into one required follow-up,
and tracks mutation activity by operation identity instead of one global submission lock. Reconciliation
polling remains a fallback for missing state and active Limit fills; ordinary mutation correctness no longer
depends on a subsequent GET. The Limit-draft submission promise now resolves only after resulting state and
the definitive draft lifecycle have been applied.

This checkpoint establishes only the authoritative PAPER state foundation. It does not complete LIMITS UX,
chart active-order rendering, DOM own-order presentation, transport redesign, STOP/TAKE, Live execution,
Robot/AUTOPILOT or the overall Trading Workspace.

## 52. Canonical master roadmap and current phone blocker

Revision 1.45 records checkpoint `TRADING_WORKSPACE_MASTER_ROADMAP_RECORDED`. The master architecture roadmap is
`DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md`. Future implementation slices must remain consistent with its
architectural sequence and acceptance gates unless a proven defect requires a documented scoped deviation.

The PAPER authoritative-state synchronization foundation has been implemented and audited in code but has not
passed real phone acceptance. After the latest backend and frontend restart, the real phone observation is that
LIMIT currently neither creates nor cancels. The immediate next action is `PHONE LIMIT MUTATION PATH DIAGNOSTIC`,
tracing the phone interaction through the frontend request, Vite proxy, backend handler, serialized PAPER runtime,
SQLite, mutation response, `PaperTradingStore`, and UI to identify the first broken transition. Stage 1 remains
open; this documentation checkpoint does not mark the synchronization slice or LIMIT behavior accepted or complete.

## 53. Stage 6 authoritative PAPER DOM projection implementation checkpoint

Revision 1.46 records checkpoint `PAPER_DOM_AUTHORITATIVE_PROJECTION_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
The DOM PAPER own-order input now maps the same `PaperTradingStore` active Limit snapshot used by the Chart
and side-specific LIMIT inventories. Stable backend order identity is preserved as one DOM dot per order;
same-price order notionals are summed for the row presentation. `DomPanel` no longer snapshots or locally
deletes PAPER orders. A dot cancellation enters the same canonical PAPER Limit cancel command and mutation
path as individual inventory cancellation, and UI removal occurs only when the returned authoritative
`paper_state` is applied (or later reconciliation supplies it).

This checkpoint implements only the Stage 6 DOM projection ownership slice. Stage 1 remains open, Stage 6
is not fully complete, and real-phone production acceptance is still required. The exact next action is one
real-phone production pass covering create, amend, individual DOM-dot cancel, fill, and two same-price orders,
while comparing BUY/SELL LIMIT counts, DOM dots/totals, Chart active lines, and backend active orders.

## 54. Side-LIMIT popup lifecycle and collapsed cancel controls checkpoint

Revision 1.47 records checkpoint `SIDE_LIMIT_POPUP_LIFECYCLE_FIXED_PHONE_ACCEPTANCE_PENDING`.
Collapsed BUY LIMITS and SELL LIMITS controls now expose independent side-specific cancellation targets.
The primary target retains short-tap creation and long-press inventory behavior; the adjacent cancellation
target opens only that side's existing confirmation and is disabled for an empty side. Creation, inventory,
and side-cancel presentation are mutually exclusive.

Side confirmation now dismisses on CANCEL activation, KEEP, or backdrop activation. CANCEL snapshots the
selected side's authoritative active orders, closes presentation immediately, and then routes every concrete
order through the existing canonical PAPER Limit cancellation callback. No optimistic order removal, local
order state, batch endpoint, or second cancellation transport is introduced; subsequent counts and projections
remain owned by `PaperTradingStore` state. Stage 1 and Stage 6 remain unaccepted pending real-phone production
verification. The exact next action is a phone pass for both sides covering collapsed primary tap, long press,
independent cancellation target, KEEP, backdrop dismissal, successful cancellation, and authoritative projection.

## 55. Systemic side-LIMIT creation popup checkpoint

Revision 1.48 records checkpoint `SIDE_LIMIT_EDITABLE_PRICE_CANONICAL_CONFIRM_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
Opening BUY LIMITS or SELL LIMITS now creates the applicable side-specific `LimitDraft` immediately and keeps the
compact popup open as its editor. The price is a decimal-keyboard-oriented text input that preserves the exact
typed value; invalid or empty input remains editable and cannot submit. Authoritative `tickSize` normalization is
performed at validation/submission rather than on each keystroke.

The popup checkmark uses the shared `TradingControlButton` activation state machine and confirms the current draft
through `PaperLimitDraftSubmitController`, `PaperTradingStore.runMutation`, `executePaperLimitCommand`, the existing
backend Limit endpoint and the returned authoritative `paper_state`. Successful authoritative creation dismisses
the draft and popup; rejected validation or mutation leaves it available for correction, while ambiguous submission
remains locked for reconciliation. No backend, persistence, transport, matching or second Limit business path was
introduced.

This checkpoint belongs to master-roadmap Stage 5 and shared Stage 7 interaction semantics before Stage 6 phone
acceptance resumes. It does not accept or complete Stage 1, Stage 5 or Stage 6. The exact next action is one real-phone
BUY LIMITS creation using a manually edited valid decimal price, verifying one order appears without reload in the
BUY LIMITS count, DOM dot/total, Chart active line and backend active-order state.

## 56. Systemic active-LIMIT chart edit checkpoint

Revision 1.49 records checkpoint `ACTIVE_LIMIT_CHART_EDIT_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`. Active chart
Limit lines remain solid and immovable on ordinary touch. A pointer must remain pressed for exactly 300 ms before
the one order-id-keyed edit controller enters editable mode; only then does the line become dashed and vertical
movement update a tick-normalized local candidate. Release preserves the dashed candidate with explicit green
confirmation and red cancellation controls. Pointer cancellation, cancellation control and outside activation
restore the authoritative original projection without a backend mutation.

Green confirmation alone emits one stable physical amend intent through `executePaperLimitAmend`,
`PaperTradingStore.runMutation`, the existing PAPER amend endpoint and the returned authoritative `paper_state`.
The request identifies the existing `order_id`; backend price-only amend preserves that identity and cannot create
a second order. Rejection or transport failure restores/refetches authoritative state and does not retain the local
candidate as if successful. This belongs to master-roadmap Stage 6 projection ownership and Stage 7 shared pointer
semantics. Stage 1 and Stage 6 remain unaccepted. The exact next action is one real-phone hold-drag-release-confirm
pass on an active Limit, verifying short touch does nothing, dashed mode begins only after 300 ms, cancel/outside
restores the original price, and confirm moves the same order across Chart, DOM, inventory and backend state.

## 57. Chart fast-LIMIT exactly-once correction checkpoint

Revision 1.50 records checkpoint `CHART_FAST_LIMIT_EXACTLY_ONCE_FIXED_PHONE_ACCEPTANCE_PENDING`. The production
duplicate was state-level: one physical phone tap could deliver both Pointer Events `pointerdown` and legacy
`touchstart`; `ChartPanel` treated both as independent placement sources and each called the same App draft-creation
callback. Each call dispatched a separate `begin`, and distinct timestamp-derived draft IDs were retained as two
independently editable and submittable pending drafts. BUY and SELL were equally affected because both sides share
that callback and reducer path.

Pointer Events are now the sole chart fast-Limit activation source for touch, pen and mouse. The competing
`touchstart` callback and its order-sensitive timestamp suppression workaround were removed. Consequently one
physical chart activation while side hold is active produces one normalized semantic placement callback and one
pending Limit draft. This is not visual deduplication and does not remove a duplicate after creation. Stage 5 and
Stage 7 remain unaccepted, active-LIMIT amend phone acceptance remains paused, and the exact next action is one
real-phone production pass for both BUY and SELL proving each single chart tap creates exactly one pending line,
dragging reveals no second line at the original price, and confirming produces exactly one backend order.

## 58. Side-volume synchronization checkpoint

Revision 1.51 records checkpoint `SIDE_SELECTED_VOLUME_SINGLE_SOURCE_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING` and
records the user's successful real-phone BUY and SELL chart fast-Limit exactly-once acceptance. `App` now owns
exactly one selected USDT volume string per side. The BUY and SELL quick-volume fields and Limit creation popup
are two editable views of those same independent values. Market submission, chart fast-Limit draft creation, DOM
fast-Limit submission and normal popup Limit submission read the applicable current side value at intent creation.
Hold mode carries only side identity and no longer snapshots a separate volume.

Popup editing stays open and updates only its side. Empty, nonnumeric, non-finite, zero and negative input fails
closed; existing backend sizing, Working Volume definition, leverage, quantity and order lifecycle semantics remain
unchanged. A pending draft may retain its immutable creation snapshot, but popup confirmation deliberately builds
the command intent from the canonical current side selection, so that snapshot is not a competing editable source.
Stage 5 remains unaccepted. The exact next action is one real-phone pass changing BUY volume in both views and then
SELL volume in both views, proving side isolation and identical sizing across Market, chart fast-Limit, DOM
fast-Limit and popup Limit creation.

## 59. Trading numeric-input Enter/focus checkpoint

Revision 1.52 records checkpoint `TRADING_NUMERIC_INPUT_DONE_BLUR_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
The BUY and SELL quick-volume inputs and Limit-popup volume and price inputs now share one keyboard lifecycle.
They advertise `enterKeyHint="done"`; Enter prevents the browser's implicit focus progression, stops propagation
and blurs the current input. Existing controlled `onChange` ownership remains the value commit boundary, so Done
does not focus a sibling, activate the popup checkmark, submit a Market or Limit order, or close the popup.

No form submission, hidden submit control or explicit focus-transfer code existed; the mobile browser was free to
infer next-field behavior because the numeric inputs previously provided neither a completion hint nor an Enter
handler. Side-volume synchronization, validation, price normalization and all command paths remain unchanged.
Stage 5 remains unaccepted. The exact next action is one real-phone pass pressing Done in BUY quick volume, SELL
quick volume, Limit-popup volume and Limit-popup price, proving each keyboard closes with no focus transfer and no
order submission.

## 60. Trading numeric-input terminal focus-boundary correction

Revision 1.53 records checkpoint `TRADING_INPUT_FOCUS_BOUNDARY_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING` and
supersedes revision 1.52's insufficient blur-only completion mechanism. Real-phone evidence proves that after the
controlled BUY input committed and the Enter handler blurred it, the WebView subsequently focused the next editable
trading input in DOM order. Repository audit proves there is no form, implicit submit control, autofocus, explicit
sibling-focus call or controlled-input remount responsible. The exact Android WebView sub-event (`keyup` versus an
IME-only completion action) is not observable from repository state and is therefore not asserted.

One shared terminal focus policy now moves Enter completion to the non-input trading boundary and latches completion.
Any subsequent implicit focus event targeting a marked trading numeric input is redirected to that boundary. An
explicit pointer interaction on a trading numeric input releases the latch before focus, so navigation between fields
remains available only by deliberate tap. No timeout, hidden input, per-field focus handler or order submission was
introduced. The policy covers BUY quick volume, SELL quick volume, Limit-popup volume and Limit-popup price. Stage 5
remains unaccepted. The exact next action is one real-phone Done pass across all four inputs, verifying the keyboard
closes, no sibling gains focus, popup state remains intact and no order is submitted.

## 61. Real-phone Done/Enter focus progression deferred

Revision 1.54 records that real-phone Done/Enter focus progression remains unresolved after both the blur-only
mechanism and the shared terminal focus-boundary correction failed to stop the WebView from advancing focus. The
temporary on-screen focus/IME diagnostic did not produce evidence sufficient to justify further work and has been
removed. No claim is made that the behavior is fixed.

By explicit user decision, this issue is intentionally `DEFERRED` and is not an acceptance blocker for continuing
the current LIMIT work. The existing functional Enter/Done handler, terminal focus boundary and completion latch
remain in place without further semantic changes. Acceptance returns to the previous LIMIT sequence; the exact next
action is the revision 1.51 side-volume synchronization phone pass, followed by the pending LIMIT creation and
authoritative-projection acceptance sequence.

## 62. Active-LIMIT edit phone checkpoint and remaining control correction

Revision 1.55 records real-phone `PASS` evidence that an active LIMIT enters edit mode after an approximately
300-ms hold and that drag/release preserves a dashed candidate with visible `✓` and `×` controls. These accepted
interaction facts do not complete Stage 5, which remains `IN_PROGRESS`.

The current `×` behavior restores the authoritative original projection without cancelling the order. That behavior
is not the required final contract. The required control split is: `×` performs authoritative LIMIT cancellation;
outside activation abandons the edit and restores the authoritative original projection; and `✓` performs the
authoritative identity-preserving LIMIT amend. Revision 1.55 records this gap only and implements no correction.

Real-phone Done/Enter focus progression remains unresolved and intentionally deferred by the user. It is not an
acceptance blocker for continuing the current LIMIT sequence, and no claim is made that it is fixed. The current
blocker is the active-LIMIT `×` semantic mismatch. The exact next roadmap action is a bounded correction that routes
`×` through authoritative cancellation while preserving outside-abandon and `✓`-amend semantics. No deliberate
deviation from the master roadmap is introduced.

## 63. Active-LIMIT edit command-semantics implementation checkpoint

Revision 1.56 records checkpoint `ACTIVE_LIMIT_EDIT_COMMAND_SEMANTICS_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
The active-LIMIT edit candidate remains local until one of three distinct intents occurs. Green `✓` sends the
existing identity-preserving amend command for the authoritative `order_id`; red `×` sends the existing canonical
single-order PAPER LIMIT cancel command for that same authoritative `order_id`; outside activation abandons only
the local candidate and performs no backend mutation, restoring the original authoritative projection.

The controller now represents amend and cancel as separate in-flight states. Both commands apply only their
returned authoritative `paper_state` through `PaperTradingStore`; cancellation does not optimistically remove a
line, and failure leaves the authoritative order available for projection or reconciliation. Stage 5 and Stage 6
remain unaccepted pending real-phone verification. The exact next action is one real-phone active-LIMIT edit pass:
create an active LIMIT, drag it to a candidate price, tap red `×`, and verify without reload that the same order
disappears from Chart, the applicable BUY/SELL LIMITS count, DOM own-order projection, and backend active orders.

## 64. Active-LIMIT pending-candidate re-drag checkpoint

Revision 1.57 records checkpoint `ACTIVE_LIMIT_PENDING_CANDIDATE_REDRAG_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
After the initial 300-ms hold, drag and release, the dashed active-LIMIT candidate remains the same local edit
session and may be grabbed and dragged again immediately, without another hold threshold. Every release returns
the same authoritative `order_id` to `PENDING_CONFIRM` at its latest tick-normalized candidate price, with green
amend and red cancel controls still available. This re-drag cycle is repeatable until the session is resolved.

Re-drag uses the existing active-line hit target, pointer handlers and pointer capture. Pointer movement changes
only the local candidate and emits no amend or cancel command. Green `✓`, red `×` and outside-dismiss retain the
revision 1.56 command semantics, and no backend API or order lifecycle path changes. Stage 5 and Stage 6 remain
unaccepted pending real-phone verification. The exact next action is one real-phone active-LIMIT edit pass: hold,
drag and release an active LIMIT, re-grab the dashed candidate twice without another hold, release at each new
price, then verify `✓`, `×` and outside remain available and authoritative behavior occurs only on the final action.

## 65. Active-LIMIT initial-hold phase synchronization checkpoint

Revision 1.58 records checkpoint `ACTIVE_LIMIT_INITIAL_HOLD_PHASE_SYNCHRONIZED_PHONE_ACCEPTANCE_PENDING`.
The active-LIMIT controller now synchronizes its imperative pointer-phase reference with every React state
transition. A quick release therefore observes and terminates the current `PRESSING` phase immediately, clears
the hold timer, and cannot later enter edit mode after the finger has already lifted.

The explicit phase boundary remains authoritative: a solid `ACTIVE` Limit enters `PRESSING` and becomes editable
only when the 300-ms threshold completes; movement or release before that threshold does not edit it. Only an
existing dashed `PENDING_CONFIRM` candidate enters `EDITING` immediately on pointer down, using the same pointer
capture and repeatable local re-drag path recorded in revision 1.57. DOM classes and visual style do not select
gesture timing. Amend, cancel, outside-dismiss, backend APIs and authoritative `order_id` semantics are unchanged.
Stage 5 and Stage 6 remain unaccepted pending real-phone verification. The exact next action is one phone pass
proving a short tap leaves a solid active LIMIT unchanged, a 300-ms hold enters dashed editing, and the released
dashed candidate can then be re-grabbed immediately without another hold.

## 66. Active-LIMIT hold-only edit and tap-cancel affordance checkpoint

Revision 1.59 records checkpoint `ACTIVE_LIMIT_HOLD_ONLY_EDIT_TAP_CANCEL_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
The active-LIMIT state machine now distinguishes an idle solid order, a solid order with its cancellation
affordance visible, an unresolved hold candidate, and the existing edit lifecycle. A valid short tap releases
before 300 ms without significant movement, keeps the order solid and authoritative, and exposes one red `×` for
that `order_id`. Merely exposing the control performs no backend mutation; `×` alone enters the existing canonical
single-order PAPER cancellation command, while outside activation hides it without mutating the order.

`PRESSING` records its pointer origin and uses the existing eight-pixel chart touch movement tolerance. Movement
beyond that tolerance before 300 ms marks the gesture aborted and clears the hold timer. It cannot change the
candidate price, cannot later enter editing, and release returns to idle `ACTIVE` without showing `×`. Only an
unmoved hold that reaches 300 ms enters dashed `EDITING`. An existing `PENDING_CONFIRM` candidate retains immediate,
repeatable re-grab. Amend, edit-mode cancel, outside-abandon, backend APIs and authoritative projection ownership
are unchanged. Stage 5 and Stage 6 remain unaccepted pending real-phone verification. The exact next action is one
phone pass covering solid-line short tap and outside dismissal, pre-threshold drag abort, 300-ms hold entry, and
immediate dashed-candidate re-grab before exercising the visible red `×` cancellation.

## 67. Active-LIMIT global edit boundary and shared candidate actions checkpoint

Revision 1.60 records checkpoint `ACTIVE_LIMIT_GLOBAL_EDIT_BOUNDARY_SHARED_CANDIDATES_IMPLEMENTED_PHONE_ACCEPTANCE_PENDING`.
While an authoritative active LIMIT is dashed in `EDITING` or `PENDING_CONFIRM`, only that order-id-keyed line,
its own controls and the global visible-candidate controls belong to the current edit interaction boundary. A
capture-phase pointer outside that boundary abandons the local edit, restores the original authoritative price,
performs no backend mutation and consumes the physical gesture before any other active line, pending draft or
chart overlay can act on it. The next interaction requires a second explicit gesture.

The global candidate action layer now explicitly consists of both ordinary pending Limit drafts and the edited
active-LIMIT candidate whenever it is dashed and pending confirmation. Global `✓` preserves the existing ordered
draft-confirm path and then authoritatively amends the edited active candidate at its latest price using the same
`order_id`. Global `×` preserves ordinary draft dismissal and authoritatively cancels the edited active order via
the existing single-order PAPER cancel command. Neither action creates a parallel backend command or locally fakes
success. Global controls are inside the edit boundary and therefore cannot trigger outside-abandon before their
intended action. Per-line `✓`/`×`, immediate dashed re-grab, solid-line tap cancellation and outside restore remain
unchanged. Stage 5 and Stage 6 remain unaccepted pending real-phone verification. The exact next action is one
real-phone pass with one ordinary pending draft plus one edited active LIMIT, proving outside taps are dismiss-only
and GLOBAL `✓`/`×` include both visible dashed candidates through their respective canonical command paths.

## 68. Active-LIMIT interaction real-phone acceptance

Revision 1.61 records real-phone `PASS` for the active-LIMIT interaction slice implemented through revisions
1.56-1.60. A short tap on a solid active LIMIT exposes its solid red cancellation `×`; outside activation hides
that affordance without mutation. Pre-threshold movement aborts the hold without editing or moving the order,
while an approximately 300-ms stationary hold enters dashed editing and the resulting candidate supports immediate,
repeatable re-grab.

Per-line `×` authoritatively cancels the actual order, and per-line `✓` authoritatively amends the same `order_id`
without replacement or duplication. Any activation outside the current edited line, including another solid or
dashed line, abandons the edit, restores the original price without backend mutation and consumes that gesture.
The mixed visible-candidate set is also accepted: GLOBAL `×` discards normal pending drafts and authoritatively
cancels the edited active LIMIT, while GLOBAL `✓` confirms normal pending drafts and authoritatively amends the
edited active LIMIT using the same identity.

This acceptance closes the bounded active-LIMIT interaction blocker but does not complete master-roadmap Stage 5,
Stage 6 or the overall LIMIT acceptance gate. Done/Enter focus progression remains deliberately deferred. By the
user's explicit post-checkpoint priority, the exact next task is `DOM LIMIT ORDER PLACEMENT`: implement direct
LIMIT placement through DOM/order-book interaction using the existing canonical PAPER LIMIT lifecycle. This
revision records that routing only and does not implement or newly authorize a parallel order lifecycle.

## 69. DOM LIMIT order placement real-phone acceptance

Revision 1.62 records real-phone `PASS` for immediate resting DOM LIMIT placement. Holding BUY or SELL and
selecting a DOM level with the second finger now creates one canonical PAPER Limit using the current selected
volume for that side. PRICE and SIZE activation on the same row resolve to the same normalized `level.price`;
an own-order dot remains a cancel-only concrete-order target and cannot create another Limit.

DOM and chart draft entry now share the reusable `PaperLimitCreateController` command boundary without sharing
presentation state. Each deliberate DOM placement owns one stable `client_action_id`; completed and definitive
rejected attempts release placement ownership, ambiguous transport retains the same identity and blocks new
placement until reconciliation, and the 300-ms anti-bounce suppresses only an accidental repeat of one gesture.
Two later deliberate DOM selections therefore create two independent intents rather than reusing the prior latch.

Successful state remains exclusively authoritative: `/api/limit` returns the resulting `paper_state`,
`PaperTradingStore` applies it, and Chart, DOM and Panel project that same order set without a DOM-local order
reality. The existing active-LIMIT amend/cancel lifecycle is unchanged. Production assets were rebuilt and this
slice was accepted on the real phone. Master-roadmap Stage 5 remains `PARTIAL`, but its canonical resting-DOM
entry path and LIMIT acceptance-gate DOM-create item are accepted.

This historical checkpoint is superseded by revision 1.88 for fast DOM routing: spread-crossing selections use
canonical Market execution rather than an aggressive Limit confirmation path. Real-phone Done/Enter focus
progression remains `USER-DEFERRED` and is not part of that routing slice.

## 70. Collapsible DOM and Smart Tape structural implementation checkpoint

Revision 1.63 records this right-sidecar micro-slice as
`IMPLEMENTED / TARGETED PASS / BUILD PASS / MANUAL ACCEPTANCE PENDING`.

The former full-height vertical DOM plus Smart Tape handle and its dedicated grid column are removed. The open
workspace is conceptually `[ CHART ][ SMART TAPE ][ DOM ]`; the closed workspace is a full-width Chart. Collapse
and restore use a small absolute-positioned square overlay button that reserves no grid column. Open, the toggle
sits near the upper-left edge of the side panel; closed, restore remains near the upper-right Chart/workspace area.

DOM and Smart Tape remain mounted while collapsed, so collapse/restore does not intentionally reset DOM-local
state. The Chart continues to use Lightweight Charts `autoSize: true`; no manual `chart.resize()` was introduced.
Current local DOM PRICE candidate widths remain `3.05rem` on desktop and `3rem` on mobile. SIZE compaction and
Chart price-scale compaction remain deferred.

Validation evidence for this bounded slice is: isolated collapse/restore test `PASS`; relevant layout test
`PASS`; `npm run build` `PASS` with 63 modules; exact-path project verifier `PASS`; and pager-safe
`git diff --check` `PASS` apart from ordinary LF-to-CRLF warnings. The full `App.test.tsx` run is not green: one
neighboring earlier PAPER Limit assertion remains unresolved and out of scope (`expected 0, received 1`). Manual
desktop/real-phone acceptance has not yet been performed, so this slice is not accepted or closed.

The approved central VPS development/runtime direction does not interrupt this logical Trading Workspace stage.
The current stage must first complete manual acceptance and receive a clean checkpoint; only then does VPS
migration become the next major operational stage. Migration remains planned and unimplemented, and the rented
server's suitability remains subject to inspection. `ARCHITECTURE.md`, `DEVELOPMENT_GUIDE.md` and
`DECISION_LOG.md` own the architecture, isolation and workflow details.

## 71. Account-wide PAPER Open Positions reconciliation checkpoint

Revision 1.64 records the account-wide PAPER Open Positions inventory as implemented with manual/real-phone
acceptance still `PENDING`. Each visible row remains an authoritative `/api/open-positions` projection and its
Full Close continues through the canonical `/api/full-close` command using one per-symbol `client_action_id`.

A `completed` command acknowledgement no longer releases that identity while authoritative inventory still
contains the position or cannot be refreshed. An ambiguous outcome likewise remains locked without blind retry.
Only a successful authoritative refresh that no longer contains the symbol establishes FLAT, settles the attempt,
clears pending/ambiguity state and removes the row. No optimistic position removal or additional close command is
introduced.

Focused regression tests for completed-but-still-open and ambiguous-then-FLAT both pass, the production frontend
build passes, and the fresh money-sensitive change-review reports no material defects in the reviewed scope. These
automated checks do not constitute touch, browser or real-phone acceptance. The exact next action is real-phone
Open Positions acceptance.

## 72. Account-wide PAPER Open Positions completion checkpoint

Revision 1.65 completes the automated implementation scope for the account-wide PAPER Open Positions page while
keeping manual/real-phone acceptance `PENDING`. `/api/open-positions` now enriches each authoritative PAPER
position with that symbol's authoritative instrument `tick_size` and with backend-owned current price plus
unrealized USDT PnL only when a matching normalized order book is fresh. Missing, mismatched, future-dated or
stale market data fails closed as unavailable PnL; the current Workspace ticker is not an account-wide fallback.
Accounting values remain Decimal-backed and presentation formatting alone follows the symbol tick step.

`POST /api/close-all` owns one serialized account-wide PAPER action. Its source inventory is the durable current
PAPER account store, independent of market-data presentation availability. It derives one stable child identity
from the bulk `client_action_id` and symbol and routes every child through the canonical per-symbol Full Close.
Therefore authoritative remaining quantity, no reversal, symbol-scoped FLAT cleanup and durable command
idempotency remain unchanged. The frontend sends one bulk request after explicit confirmation, locks every target,
removes only rows absent from the returned or subsequently refreshed authoritative inventory, preserves the last
projection on refresh failure and never creates a new identity for an ambiguous outcome.

Focused backend tests (23) and Open Positions Vitest tests (6) pass, and the production frontend build passes with
64 modules. Fresh money-sensitive review reports no material defects after decoupling bulk source inventory from
PnL/metadata enrichment. These checks are not touch or device evidence. The exact next action is real-phone Open
Positions completion acceptance for per-symbol PnL/tick formatting, compact row layout, confirmation/Cancel and
full/partial Close All reconciliation.

## 73. Open Positions real-phone presentation refinement checkpoint

Revision 1.66 records the bounded presentation refinement requested by real-phone review while keeping acceptance
`PENDING`. Each position row labels its notional as `Объем:`, labels symbol-tick-formatted average entry as
`Ср. цена:`, and appends canonical Trading Workspace PnL percent to available backend-owned USDT PnL. The percent
reuses the shared `positionPnlPercent` and `formatPositionPnlPercent` semantics already used by ModePanel and Smart
Tape; unavailable authoritative average/current price remains fail-closed without a percentage.

The existing Close All trigger is renamed `Закрыть все` and moved into the Open Positions header immediately
before the overlay close control. Its confirmation order, serialized backend action, deterministic identities,
UNKNOWN reconciliation, row locking and authoritative-FLAT removal semantics are unchanged. Focused Open Positions
tests and the production build pass. Manual/real-phone acceptance remains `PENDING`; the exact next action is the
same real-phone Open Positions completion acceptance using the freshly rebuilt production assets.

## 74. Account-wide PAPER Open Positions real-phone acceptance

Revision 1.67 records real-phone `PASS` and completion acceptance for account-wide PAPER Open Positions. The
accepted production flow displayed multiple symbols with backend-owned per-symbol USDT and percent PnL, formatted
average entry by each symbol's authoritative tick size, and preserved the compact row layout. Individual close
confirmation and Cancel were non-mutating until confirmation; confirmed BTC Full Close affected only BTC, and
the row disappeared only after authoritative state reconciliation while ONGUSDT remained.

Closing the inventory preserved Chart, DOM and Tape workspace state. Close All used the required confirmation,
its Cancel path did not mutate trading state, and one confirmed action closed the remaining ONGUSDT without an
observed duplicate, reversal or error. Authoritative reconciliation then rendered `Нет открытых позиций`.

The exact next work item is `WORKSPACE SYMBOL SWITCHING`: one canonical symbol-transition path shared by the
ticker autocomplete and confirmed Open Positions card navigation, backed by the authoritative supported-instrument
universe and real symbol-propagating market-data/PAPER lifecycle. Manual/real-phone acceptance for this new slice
is `PENDING`.

## 75. Workspace symbol switching implementation checkpoint

Revision 1.68 records `WORKSPACE SYMBOL SWITCHING` as
`IMPLEMENTED / TARGETED PASS / BUILD PASS / MANUAL ACCEPTANCE PENDING`.

`App` owns one `switchWorkspaceSymbol` transition used by both deliberate ticker autocomplete selection and
confirmed Open Positions card navigation. Same-symbol navigation closes the overlay and returns to the workspace
without restarting market data. The card's individual close control stops propagation, and both navigation Cancel
and close Cancel remain non-mutating.

The backend `/api/instruments` universe is loaded from Bybit linear instrument authority with pagination and
filters to currently Trading USDT-settled instruments; frontend search is case-insensitive substring matching and
contains no hardcoded candidate list. `WorkspaceMarketDataManager` owns exactly one active public order-book,
trade and kline session. Activating a supported symbol replaces that session, rebinds the normalized book provider
used by PAPER execution and routes Chart/DOM/Tape through symbol-qualified SSE endpoints. The PAPER account store
remains account-wide, while `/api/paper-state?symbol=...` supplies the selected-symbol projection.

The frontend market-data store exposes explicit transition state by immediately clearing book, trades, candles,
tick size and local own-order projection under the new symbol before reconnecting. Source identity, requested
symbol and timeframe guards reject late responses/events and error callbacks from the prior session. PAPER state
continues to require both selected-symbol identity and monotonic state revision. No trading mutation is part of
navigation.

Focused frontend regressions (22) and backend/runtime regressions (33) pass, Python source compiles, and the
production frontend build passes with 64 modules. Automated checks are not browser/touch/live-stream acceptance.
Manual/real-phone acceptance is `PENDING`; the exact next action is real-phone Workspace symbol-switching
acceptance using freshly rebuilt production assets.

## 76. Workspace symbol switching real-phone refinement checkpoint

Revision 1.69 records the bounded phone-review refinement as
`IMPLEMENTED / TARGETED PASS / BUILD PASS / MANUAL ACCEPTANCE PENDING`.

The separate top Workspace control strip is no longer rendered. The existing authoritative ticker autocomplete
and timeframe control are one Chart-owned overlay in the upper-left visual area and are excluded from drawing,
pan, pinch and fast-Limit pointer capture. Display uses the existing safe `baseAssetFromSymbol` helper, so a
canonical `BTCUSDT` identity renders as `BTC` while non-USDT symbols remain unchanged. The existing PAPER/account
button and menu moved into the lower `paper-limits-shell` beside BUY LIMITS and SELL LIMITS without duplicating
account state or semantics. Removing the header element releases its height to the shared Chart/Tape/DOM market
row rather than hiding or reserving an empty row.

Lightweight Charts continues to own dynamic price-scale width from actual formatted label content. Its supported
layout font size is reduced from the library default 12 to 11 while `minimumWidth` remains zero, so the axis can
contract but expands for symbols whose complete price labels require more room; no canvas CSS override or fixed
maximum width is introduced.

Systematic diagnosis established the first broken DOM-dot layer as presentation CSS. Authoritative selected-symbol
active LIMIT orders reached `PaperTradingStore`, `projectPaperLimitOrders`, compressed display-bucket matching and
the correct `.dom-row`; concrete cancel buttons existed, but `right: calc(100% + 0.12rem)` positioned the entire
dot group outside the row where panel overflow clipped it. The fix positions that same order-id-keyed group inside
the row. No fake dot or DOM-local order truth is introduced, and projection now explicitly rejects an order whose
canonical symbol differs from the selected Workspace symbol.

Focused frontend regressions (34) plus the isolated account-placement regression pass, and the production frontend
build passes with 64 modules. These automated checks are not touch/live-stream acceptance. Workspace symbol
switching manual/real-phone acceptance remains `PENDING`; the exact next action is reload of the fresh production
build followed by real-phone layout, DOM-dot and symbol-switching acceptance.

## 77. Autonomous Android manual terminal future-direction checkpoint

Revision 1.70 records the human-approved documentation checkpoint
`AUTONOMOUS ANDROID MANUAL TRADING TERMINAL — FUTURE DIRECTION RECORDED / IMPLEMENTATION NOT AUTHORIZED`.
The owning direction is `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md` section
`Future track — Autonomous Android Manual Trading Terminal`.

This is a separate `FUTURE / PLANNING ONLY / NOT_IMPLEMENTATION_AUTHORIZED` track after the current terminal
completion and acceptance path. It does not replace the existing desktop/web or Telegram Mini App prototype,
introduce Android code or dependencies, authorize real-money trading, or select Capacitor, another hybrid shell,
Kotlin, React Native, or any final stack. The immediate next item remains
`REAL-PHONE WORKSPACE SYMBOL SWITCHING ACCEPTANCE`.

The future product intent is an autonomous manual terminal whose normal route is `PHONE → BYBIT`, without
requiring `C:\BybitScanner`, the home Windows PC, its Python backend, VPS, Scanner runtime, or the future Robot.
Robot architecture remains separate. The preferred research direction maximizes reuse of the existing
React/TypeScript Workspace UI and contracts through a bridge to an Android-native market-data/trading core; a
native rewrite remains evidence-gated.

Credentials, signing, private API access, and authoritative reconciliation must remain outside
React/JavaScript/WebView state. Future security research covers Android Keystore/hardware backing, minimum
read/trade privileges, forbidden withdrawal permission, rotation/revocation, redaction, backup/export, and device
threats. No secret may be hardcoded in the APK, repository, or frontend bundle, and a separate security gate is
mandatory before real-money implementation.

Start, resume, reconnect, process death, and network transition handling must restore public data and reconcile
private exchange truth before unsafe actions are enabled. Existing safety constraints remain: one normalized
market-data owner for Chart/DOM/Tape, explicit session/symbol authority, generation guards, readiness-before-swap,
stale-consumer isolation, stable command identity, no blind ambiguous retry, duplicate prevention, fail-closed
degraded state, authoritative order/position recovery, and Full Close that cannot flip through zero.

Pre-implementation research gates own packaging/bridge, sustained market-data/device performance, Android
lifecycle/background restrictions, security, then-current Bybit integration and clock/rate constraints,
distribution/signing/update strategy, and observability. Preliminary phases A0–A7 cover research, UI packaging,
autonomous public data, private read-only reconciliation, optional PAPER validation, restricted live commands,
protection/recovery hardening, and real-device acceptance. This ordering remains preliminary.

## 78. Market Data Hub and multiplexed Workspace stream architecture correction

Revision 1.71 records the human-approved checkpoint
`MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM — ARCHITECTURE CORRECTION RECORDED / NOT IMPLEMENTED`.
The owning architecture, contracts, failure evidence, migration M0–M8 and future verification matrix are in
`DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md` section
`MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM — ARCHITECTURE CORRECTION`.

Backend symbol authority and generation isolation have automated PASS evidence. Live ONG probes reached a READY
1000×1000 book plus trades and 5-minute klines, and local UI ONG→BTC→ONG passed, while the real phone still showed
blank Chart, DOM and Smart Tape. The narrow proven failure boundary is therefore backend→proxy/tunnel→mobile
distribution after backend authority. Approximately 65 KB book, 58 KB trades and 96 KB klines payloads, with
approximately 2 MB of book traffic per six seconds, make transport overload a candidate but do not prove it as the
exact cause.

The approved target is one long-lived public linear `MarketDataHub`, an `InstrumentRegistry` and
`SubscriptionRegistry`, per-symbol active/warm `SymbolContext` ownership for authoritative full L2, trades,
candles, health and sequence/subscription state, one readiness-gated `WorkspaceController`, and one multiplexed
Workspace client WebSocket consumed by Chart, DOM and Smart Tape as a single symbol/generation authority.

Switch success requires a fresh sequenced book, healthy trades or recent bootstrap, and healthy candle history/live
state. The previous Workspace remains visible and working until candidate `WORKSPACE_READY`; candidate failure
preserves it. Backend full L2 is projected as a bounded client snapshot plus sequenced deltas; trades and candles
use one-time bootstrap/history followed by bounded new/live updates. Every event carries symbol, generation, kind,
timestamps and state, plus sequence/version where applicable. Previous-symbol warm grace supports rapid A→B→A.

Health is explicit as `NOT_READY`, `SYNCING`, `READY`, `STALE` or `DEGRADED`, with timestamps, sequence,
reconnect/subscription state and latest error. Kline failure cannot destroy healthy book/trades; a quiet Tape cannot
make DOM unavailable. Ambiguous, stale or unsequenced book state is not current liquidity truth; last-known UI may
remain only with visible stale/degraded marking. Existing explicit switch authority, stale-generation rejection,
generation identity, candidate preparation, previous-Workspace preservation and fail-closed behavior remain
binding.

`InstrumentRegistry` admits only transport-supported linear `Trading`, LinearPerpetual-compatible USDT-quoted
instruments with complete tick, quantity, precision and minimum constraints and correct pagination. Autocomplete
must expose only that supported universe. UI consumers do not own exchange subscriptions, and ordinary symbol
switching does not recreate the exchange-facing engine.

The former measured-only transport consolidation is now promoted to required architecture: one multiplexed
Workspace WebSocket replaces separate Workspace market-data SSE streams after migration parity; REST remains the
command path. Migration must proceed through roadmap M0–M8 and prove sequence-gap recovery, stale/out-of-order
isolation, duplicate/quiet trade handling, component failure isolation, candidate failure, rapid A→B→A, warm expiry,
late-generation rejection, reconnect/resume, bounded backpressure and slow-client behavior, followed by local,
proxy/tunnel and real-phone acceptance.

Current status is
`WORKSPACE SYMBOL SWITCHING — BACKEND AUTHORITY FIX AUTOMATED PASS / REAL-PHONE TRANSPORT ACCEPTANCE FAIL`.
The exact next work item is
`MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM — ARCHITECTURE CORRECTION`, beginning with roadmap M0.
This revision changes documentation only and does not claim or authorize that the Hub or multiplexed stream is
already implemented.

## 79. M0 contract and measurement baseline

Revision 1.72 records `M0 — CONTRACT + MEASUREMENT BASELINE` as complete. The owning inventory, 15-second
BTCUSDT/ONGUSDT payload-only measurements, exact resend behavior, target `workspace_snapshot` and incremental
event contracts, composite readiness barrier, health model, measurement-based efficiency goals, additive migration
sequence and later deterministic/chaos acceptance categories are in roadmap sections 10.1–10.4.

The measured current browser path uses three SSE connections. BTCUSDT produced 6.600 messages/s and 452,324
payload B/s combined; ONGUSDT produced 5.067 messages/s and 337,744 payload B/s combined. Every measured book
message contained the full 1000 bids plus 1000 asks, and every measured 5m kline message contained the full 1000
candles. Trade history is bootstrapped per connection and filtered to unseen aggregates thereafter; it is not resent
on every trade event. These bounded local measurements do not prove proxy/tunnel/mobile overload or peak load.

This checkpoint changes documentation only. It does not implement `InstrumentRegistry`, `MarketDataHub`,
`SymbolContext`, `WorkspaceController`, a multiplexed WebSocket, frontend transport changes, or any PAPER/order
semantic change. The next migration stage is M1, subject to its own authorized implementation slice and gate.

## 80. M1 authoritative InstrumentRegistry

Revision 1.73 records `M1 — INSTRUMENT REGISTRY IMPLEMENTED + VERIFIED`. One backend registry now owns the
fully paginated Bybit linear Workspace universe and the existing Decimal-safe `InstrumentSnapshot` metadata.
Eligibility is fail closed to `Trading`, USDT-quoted `LinearPerpetual` instruments with complete valid precision,
step and minimum constraints. Duplicate symbols, repeated pagination cursors, malformed pages and incomplete
upstream refreshes cannot publish a candidate; a prior valid immutable snapshot remains available after refresh
failure.

`/api/instruments`, Workspace symbol/tick-size admission and PAPER instrument lookup consume the same registry
instance, and lookup performs no per-symbol Bybit request. The endpoint preserves its compact existing response
shape. Focused pagination/filter/lookup/atomic-failure tests and the existing PAPER HTTP regression script pass.
M2 `MarketDataHub` and later migration stages remain not implemented. M2 is the exact next gated stage.

## 81. M2 long-lived MarketDataHub

Revision 1.74 records `M2 — MARKET DATA HUB IMPLEMENTED + VERIFIED`. One backend Hub now owns one public linear
WebSocket lifecycle across subscribed symbols, dispatches normalized orderbook/publicTrade messages into reusable
`SymbolContext` instances, and reconnects/resubscribes all retained contexts after failure. Subscription health is
not claimed before a real event is applied; reconnect/error and book sequence/version metadata are observable.

The existing Workspace compatibility manager now switches among Hub contexts without recreating or closing the
exchange-facing book/trade engine. It preserves candidate book readiness, generation identity, stale-generation
rejection, previous-Workspace preservation, fail-closed book/PAPER behavior and existing HTTP/SSE API shapes.
PAPER order semantics are unchanged and only the active context owns the PAPER book-update callback.

Native candle buffers retain their existing REST refresh path inside each context. M2 does not implement bounded
warm-context eviction, composite readiness/WorkspaceController, client book deltas or the multiplexed frontend
WebSocket. Focused Hub tests prove one connection across multiple symbols, deterministic dispatch, unsupported
symbol rejection, reconnect/resubscribe and previous-context reuse. M3 is the exact next gated stage.

## 82. M3 WorkspaceController, composite readiness and warm contexts

Revision 1.75 records `M3 — WORKSPACE CONTROLLER / READINESS / WARM-CONTEXT LIFECYCLE IMPLEMENTED + VERIFIED`.
One controller now owns requested and active symbol, active generation, switch state, pending candidate and latest
switch error. The previous context/generation remains authoritative throughout candidate synchronization and is
replaced only after a single composite readiness decision and successful atomic activation callback.
Initial server availability is gated by the same composite readiness contract.

Readiness requires a valid sequenced non-empty book, acknowledged trades subscription with completed recent-trade
bootstrap (including explicitly empty-valid), completed selected 5-minute candle history and healthy live candle
state. Candidate timeout/failure preserves the previous Workspace and discards a newly created failed context.
Stale context/generation consumers continue to fail closed.

One previous context is retained warm for a tunable default 30-second grace, enabling A→B→A reuse without a new
exchange-facing engine. Limit overflow and grace expiry invoke Hub unsubscribe/discard. The shared Hub, registry,
PAPER behavior and current HTTP/SSE shapes are preserved. M3 does not implement client multiplexing or projection
deltas. M4 efficient snapshot + delta client projections are the exact next gated stage. Chaos/regression
hardening remains M7.

## 83. M4 efficient snapshot + delta client projections

Revision 1.76 records `M4 — EFFICIENT SNAPSHOT + DELTA CLIENT PROJECTIONS IMPLEMENTED / AUTOMATED PASS`.
One backend-owned `ClientMarketProjection` consumes the controller-owned active Hub context and carries symbol,
Workspace generation, kind, projection/source identity, timestamps and health in a common future-M5 envelope.
Stale generations fail closed. The authoritative 1000×2 backend book remains available to PAPER unchanged.

Book bootstrap defaults to configurable 250 levels per side, derived from the 200-row responsive DOM maximum plus
a 25 percent margin. Deltas exactly transform the previous bounded top window into the current one, including
size-zero deletes, edge displacement and hidden-level reveal. Client version mismatch, source-version skip,
identity regression or health recovery produces a bounded resnapshot; untrusted truth produces health/resync and
no current-looking delta. Internal full-book comparison is retained as a quantified replaceable correctness
boundary.

Trade bootstrap is bounded to 80, later batches contain only unseen aggregate IDs, duplicates are suppressed and
quiet bootstrap is valid. Candle bootstrap is bounded to 1000 per interval; later polling emits only changed
open-time records marked `replace` or `append`, unchanged polls emit nothing, and incompatible history reboots.

Migration is additive through `/api/client-market-projection/stream`; legacy SSE payloads and frontend source are
unchanged. A 15.016-second payload-only BTC/ONG run measured combined incremental projection at 7,478 B/s and
12,013 B/s respectively, reductions of 444,846 B/s (98.35 percent) and 325,731 B/s (96.44 percent) from the M0
combined baselines. This excludes HTTP/TLS/tunnel overhead and does not claim the prior phone failure was caused or
resolved by transport volume. M5 one multiplexed Workspace stream is the exact next gated stage; M6+ are not
started and chaos remains M7.

## 84. M5 multiplexed Workspace stream

Revision 1.77 records `M5 — MULTIPLEXED WORKSPACE STREAM IMPLEMENTED / AUTOMATED PASS`. One backend
`WorkspaceStreamBroker` serves additive `/api/workspace/stream` WebSocket sessions scoped to the active symbol and
Workspace generation. The first event is an atomic `workspace_snapshot` containing supported instrument metadata,
bounded book/trade/candle bootstraps, component states and Hub health/sequence/reconnect observability. Incremental
`book_delta`, `trade_batch`, `candle_update` and `health` events share one stream identity and strict monotonically
increasing event sequence.

Resume uses `stream_id` plus `after_sequence` against a 256-event bounded replay window. Missing, invalid or
expired continuity produces an explicit atomic resnapshot; component resnapshot is promoted to the same Workspace
boundary, and a final generation check prevents a mixed or newly stale bootstrap. The broker bounds retained
sessions to 32 and pending output to 64 events. Backpressure, stale generation and write timeout evict fail closed;
ordinary disconnect preserves bounded resume state. Ten-second health heartbeats remain transport observability and
do not assert frontend or trading readiness.

M5 is backend-only and additive. Legacy market-data SSE, the M4 component projection SSE, REST command paths,
authoritative full PAPER L2 and frontend source are unchanged. M6 atomic frontend generation projection and
transport migration are the exact next gated stage and are not started. M8 still owns proxy/tunnel and real-phone
performance acceptance; transport volume remains measured inefficiency rather than a proven phone-failure cause.

## 85. M6 frontend atomic generation projection

Revision 1.78 records `M6 — FRONTEND ATOMIC GENERATION PROJECTION IMPLEMENTED / AUTOMATED + BUILD PASS`. The
default frontend market-data owner is now one `BackendWorkspaceMarketDataStore` consuming the M5 multiplexed
`/api/workspace/stream` WebSocket. Its pure reducer publishes a new `MarketDataSnapshot` only after one complete
READY `workspace_snapshot` validates the requested symbol, Workspace generation, interval, bounded book, empty-valid
trade bootstrap, non-empty candle history and instrument tick metadata.

Incremental events must match the current stream, symbol, generation and interval and advance `event_sequence`
exactly once. Duplicates and foreign authority are ignored. Sequence gaps/regressions, malformed payloads, book
base-version mismatch and invalid candle mutations preserve the prior projection with explicit degradation and
force reconnect without resume for an atomic resnapshot. Ordinary disconnect retains last-known STALE data and
resumes with stream identity plus last sequence. Transport heartbeat cannot independently restore degraded state.

Book deltas update the bounded client window, trades deduplicate and retain 80, candle append/replace retains 1000,
and one external-store publication keeps Chart, DOM and Smart Tape on the same authority. Vite dev/preview proxy
WebSocket upgrade is enabled. The legacy SSE store remains an explicit compatibility class and backend legacy
routes remain available, but default frontend ownership no longer opens three SSE streams. PAPER full L2,
REST commands and order/execution semantics are unchanged.

M6 targeted atomic/transport plus legacy SSE tests pass, the full frontend suite exits zero, and the production
build passes with 66 transformed modules. No browser, tunnel or real-phone acceptance is claimed. M7 deterministic
chaos/regression hardening is the exact next gated stage and is not started; M8 acceptance is also not started.

## 86. M7 deterministic chaos and regression suite

Revision 1.79 records `M7 — DETERMINISTIC CHAOS / REGRESSION SUITE IMPLEMENTED / AUTOMATED PASS`. A new backend
suite deterministically covers replay boundaries and expiry, invalid/future resume, bounded pending overflow,
stale generation, atomic component resnapshot, heartbeat sequencing, duplicate/foreign/unknown attachment,
session pressure and mixed book/trade/candle churn. A new frontend suite covers stale/future/foreign authority,
symbol/interval mismatch, duplicate/gap/regression sequencing, malformed/partial snapshots, authoritative-only
recovery, book displacement/reveal and base mismatch, repeated/out-of-order trades, candle replace/append,
disconnect bursts, stale socket isolation, resume and fresh resnapshot.

The new cases run with the existing M5 and M6 regression suites and require no sleep-heavy timing, live Bybit,
proxy or tunnel. No production defect was found and no production source changed. Backend legacy SSE, the explicit
legacy frontend store, full authoritative PAPER L2, REST commands and order/execution behavior remain unchanged.
M8 local/proxy/tunnel and real-phone performance acceptance is the exact next gated stage and is not started.

## 87. M8 real-browser failure, diagnosis and pending re-acceptance

Revision 1.80 records M8 as `OPEN / REAL-BROWSER FAIL — FIX BUILT, RE-ACCEPTANCE PENDING`. Through the production
preview and temporary tunnel, ONGUSDT initially displayed live DOM and Smart Tape. Switching 5m→1m then made Chart
and DOM expand outside the viewport, removed usable candle presentation and showed `LIVE BOOK UNAVAILABLE` while
last-known Tape values remained visible.

Direct stream evidence shows valid atomic READY snapshots for both intervals with correct candle history, READY
book state and one active Workspace generation; the frontend also accepts 5m→1m→5m without mixed interval or
reconnect/resnapshot loop. The visual root cause was a circular DOM ResizeObserver/grid intrinsic-size feedback in
an unbounded minimum-height shell. A concurrent external WebSocket abort caused the unavailable-book state and was
not a generation mismatch. The minimal correction binds the shell to the Telegram stable viewport or `100vh`, and
the new store regression covers atomic interval transitions, stale-socket isolation, readiness and no reconnect
timer loop. Targeted tests and the required production build pass, and rebuilt local browser geometry remains
bounded. Revision 1.81 records fresh desktop and real-phone Chrome re-acceptance through the active `lhr.life`
tunnel as PASS for ONGUSDT 5m→1m→5m. Chart and DOM remained bounded, candles stayed visible, DOM and Smart Tape
remained live, and `LIVE BOOK UNAVAILABLE` did not recur. M8 is
`COMPLETE / REAL-PHONE + TUNNEL ACCEPTANCE PASS`; payload reduction and device success remain distinct evidence.

## 88. M9 — Workspace Operability / Diagnostics — architecture/documentation checkpoint

Status: `DOCUMENTED / IMPLEMENTATION NOT YET CLAIMED`

Purpose: make Workspace failures diagnosable and operationally deterministic without reopening the completed M0–M8 market-data architecture.

Binding invariants:

1. Preserve semantic root causes across subsystem boundaries. Generic `ValueError`, `LookupError`, `unsupported_symbol`, bare HTTP 409, or transport-only `ECONNABORTED` must not erase the actual failure class.
2. Introduce typed Workspace failure semantics for unsupported instrument, candidate-not-ready, instrument/bootstrap failure, inactive Workspace, unknown stream, and upstream market-data failure.
3. User-facing/API failure envelopes must carry structured fields sufficient for diagnosis, including `code`, `stage`, `requested_symbol`, `active_symbol`, `retryable`, and a request/correlation identity where applicable.
4. Add read-only Workspace diagnostic state exposing requested/active symbol, generation, pending switch, readiness/component state, latest structured error, and relevant upstream/subscription state.
5. `WorkspaceController` remains the sole authoritative symbol owner. Frontend authoritative symbol transition occurs only after backend activation acknowledgement for the new generation; failed candidate activation preserves the previous active Workspace.
6. Reconnect policy must distinguish transport-retryable failures from semantic fatal/non-retryable failures. Blind fixed one-second retry loops for semantic failures are prohibited.
7. Provide one deterministic developer doctor command that checks registry support, switch/activation, readiness, stream availability, and structured failure output for a requested symbol/interval.
8. Add registry→Workspace contract verification so a symbol advertised as Workspace-supported must be activatable by the Workspace transport contract; intentionally unsupported symbols must not be presented as supported.
9. Preserve PAPER semantics, full authoritative L2, M0–M8 generation/sequence/readiness guarantees, and unrelated user-owned dirty work.
10. Do not rewrite the server framework or create a second market-data owner. M9 is a thin operability/control-plane slice over the existing architecture.

Expected implementation surfaces are bounded to semantic exceptions/error envelopes, read-only diagnostics, switch acknowledgement semantics, reconnect classification, the doctor command, and focused contract/regression checks.

---

# 2026-08-30 TERMINAL RECOVERY / LIMIT-EXHAUSTION CHECKPOINT

Status:

ACTIVE_RECOVERY_CHECKPOINT

Baseline:

- branch: `main`;
- local HEAD: `92c51c70fc90c71d6255d8028f3cfcf823bc3a52`;
- origin/main: `92c51c70fc90c71d6255d8028f3cfcf823bc3a52`;
- local HEAD == origin/main: YES;
- working tree: DIRTY by intentional unfinished Terminal work, unfinished workflow experiment, and user-owned files.

## PRIMARY CURRENT PRIORITY

The current priority is again:

`FINISH TRADING WORKSPACE TERMINAL`

Workflow/tooling work must not displace Terminal completion unless a concrete Terminal blocker objectively requires it or the user explicitly changes priority.

Do not introduce additional workflow subsystems during the Terminal completion slice.

## TERMINAL / M9 CONFIRMED STATE

Completed and already committed backend/diagnostic M9 checkpoints include:

- semantic Workspace error boundary;
- read-only `/api/workspace/state`;
- `workspace_doctor`;
- backend diagnostics exposing requested/active symbol, generation, switch state, readiness, upstream state, and stream sessions.

Confirmed 2026-08-30 runtime result:

- backend freshly restarted from current local code;
- backend listening on `127.0.0.1:8765`;
- `workspace_doctor --symbol OGUSDT --interval 5`: PASS;
- authoritative active symbol: `OGUSDT`;
- active generation: `2`;
- Workspace switch state: `READY`;
- book readiness: PASS;
- trades readiness: PASS;
- candle history readiness: PASS;
- live candle readiness: PASS;
- upstream state: `READY`;
- subscription state: `SUBSCRIBED`;
- public book/trade subscriptions: active;
- upstream reconnect count: `0`;
- frontend production build: PASS;
- Vite build transformed 67 modules.

Current unfinished frontend M9/product scope includes transactional symbol-switch work in the dirty `terminal/frontend` tree, including new `workspaceSwitch.ts` and `workspaceSwitch.test.ts`.

## CURRENT AUTHORITATIVE TERMINAL BLOCKER

The present blocking defect is no longer an upstream Bybit readiness failure.

Observed state:

- direct backend `/api/workspace/state` works;
- the same HTTP endpoint through Vite preview on port `4173` works;
- therefore ordinary Vite HTTP proxying to backend is functional;
- frontend creates a Workspace stream session on backend;
- backend reports `session_count = 1`;
- backend reports `attached_count = 0`;
- the Workspace stream session reports `attached = false`;
- UI remains without live chart/DOM data and displays `LIVE BOOK UNAVAILABLE`;
- browser UI may continue to display stale frontend symbol state while backend authoritative symbol is `OGUSDT`.

Therefore the next Terminal investigation must be systemic around the complete frontend <-> Vite preview <-> backend WebSocket lifecycle, not isolated speculative edits.

Required investigation scope:

1. frontend Workspace socket URL construction and lifecycle;
2. Vite preview WebSocket proxy behavior;
3. backend stream creation vs attachment semantics;
4. generation/symbol compatibility during stream attach;
5. reconnect/close/error lifecycle;
6. authoritative symbol projection into UI;
7. only after root cause is established, implement the smallest correction.

Do not add broad reconnect/backoff architecture unless runtime evidence requires it.

## RUNTIME PROCESS NOISE FOUND DURING ACCEPTANCE

Several stale runtime processes caused diagnostic noise:

- old backend processes were still running;
- an older Vite preview was running separately;
- the older preview emitted `WS proxy error` / `ECONNABORTED`;
- stale backend did not expose the new `/api/workspace/state` route.

Recovery actions already completed:

- stale backend process set was stopped;
- fresh current backend was started;
- old Vite preview on port `4174` was closed;
- current production preview is running on port `4173`.

This process duplication is recorded as an environmental/runtime-operability issue, not yet as the root cause of the current `attached=false` defect.

## WORKFLOW / TASK TRANSACTION DETOUR

A substantial part of the current development budget and Codex limits was consumed by a workflow/tooling detour rather than Terminal completion.

Already committed experimental workflow checkpoints:

- `acc91f64ecdda27eae7b1d694890470b0b0e465a` - Task Transaction engine;
- `92c51c70fc90c71d6255d8028f3cfcf823bc3a52` - workflow integration.

The later Phase 3 / Phase 3.1 work remains uncommitted.

### STALE INDEX DEFECT

The alternate-index commit mechanism advanced HEAD while leaving the real `.git/index` at an older tree.

Consequence:

- workflow files appeared as unexpected staged reverse changes;
- checkpoint verification failed even though Phase 3 had not newly staged those files.

Forensic recovery completed:

- stale index was preserved under `.git/bybitscanner/forensics/...`;
- real index was reconciled to HEAD with `git read-tree HEAD`;
- index tree == HEAD tree after recovery;
- staged paths became empty;
- working-tree bytes were preserved.

Local Phase 3.1 then changed the intended transaction invariant so that a successful alternate-index commit reconciles the real index to the newly created HEAD before push.

### WINDOWS ENCODING DEFECT

The next workflow checkpoint then crashed on Windows locale decoding.

Observed failure:

- `subprocess.run(..., text=True)` used locale-dependent Windows decoding;
- Git output containing Cyrillic paths was decoded through `cp1251`;
- `UnicodeDecodeError` occurred;
- downstream code then hit a secondary `NoneType.split()` failure.

Therefore the current Task Transaction / checkpoint workflow is not considered accepted or reliable.

## WORKFLOW EXPERIMENT CURRENT POLICY

The dirty workflow experiment is frozen during Terminal completion.

Current dirty workflow scope includes:

- `tools/dev/workflow.py`;
- `tools/dev/verify.py`;
- `tools/dev/checkpoint.py`;
- `tools/dev/task_transaction.py`;
- `tests/test_dev_workflow.py`;
- `tests/test_task_transaction.py`;
- `tools/dev/isolate_m9_frontend_checkpoint.py`;
- `tests/test_isolate_m9_frontend_checkpoint.py`.

Do not commit these files with the Terminal checkpoint.

Do not delete, reset, restore, or discard them yet.

After Terminal acceptance, perform a dedicated workflow decision:

- determine whether Task Transaction Phase 1/2 provides enough value to retain;
- otherwise revert/remove the Task Transaction subsystem cleanly;
- preserve only minimal useful hardening such as deterministic UTF-8 Git subprocess decoding and a simpler safe checkpoint model if justified;
- avoid recreating a large workflow subsystem without demonstrated product benefit.

## USER-OWNED / NON-TERMINAL FILE PRESERVATION

The following files are outside the Terminal checkpoint and must remain untouched unless explicitly requested:

- `Инструкции +комм строка.txt`;
- `test_100.txt`;
- `test_compare_falling_candidates.py`;
- `Инструкция по запуску на новом компьютере.txt`.

## NEXT EXECUTION ORDER

1. record and commit this recovery/documentation checkpoint;
2. commit only current `terminal/**` product changes as a separate Terminal checkpoint;
3. inspect the complete committed Terminal state systemically;
4. resolve the Workspace WebSocket `attached=false` blocker;
5. rerun targeted tests;
6. run `npm run build`;
7. desktop runtime acceptance;
8. real-phone acceptance;
9. update Trading Workspace acceptance state;
10. only after Terminal is accepted, return to workflow experiment cleanup/revert decision.

No new workflow/tooling expansion is authorized by this checkpoint.

---

# 2026-08-30 WORKSPACE STARTUP AUTHORITY BLOCKER RESOLVED

Status:

PASS - DESKTOP RUNTIME ACCEPTANCE

Resolved blocker:

The previously recorded Workspace WebSocket `attached=false` / `LIVE BOOK UNAVAILABLE`
condition is no longer an active Terminal blocker.

Confirmed root cause:

- Vite preview WebSocket proxy was functional;
- backend Workspace WebSocket transport was functional;
- direct test through `ws://127.0.0.1:4173/api/workspace/stream` returned a complete
  `workspace_snapshot` with READY book/trades/candles;
- frontend startup was using hardcoded local symbol `ONGUSDT`;
- backend authoritative Workspace could already be a different symbol, observed as `OGUSDT`;
- therefore frontend could open its initial Workspace stream against a stale local symbol
  instead of backend authority.

Control experiment:

- backend was switched to `ONGUSDT`;
- with backend and hardcoded frontend symbol matching, chart, DOM and Smart Tape immediately
  became live and `LIVE BOOK UNAVAILABLE` disappeared;
- this isolated startup symbol authority as the defect rather than proxy/transport.

Implemented correction:

- frontend now reads `/api/workspace/state` before starting the market-data store;
- startup authority is taken from backend `workspace.active_symbol`;
- startup generation is taken from backend `workspace.active_generation`;
- the store receives authoritative symbol + generation before opening its Workspace socket;
- route `/api/workspace/state` was added to frontend market API routes.

Validation:

- targeted frontend tests: 3 files PASS;
- targeted frontend tests: 11 / 11 PASS;
- `npm run build`: PASS;
- Vite production build: 67 modules transformed;
- desktop hard-reload acceptance on `http://127.0.0.1:4173/`: PASS;
- frontend automatically adopted backend authoritative `OGUSDT`;
- live Chart: PASS;
- live DOM: PASS;
- live Smart Tape: PASS;
- `LIVE BOOK UNAVAILABLE`: absent;
- backend diagnostics after browser attachment:
  - active_symbol = `OGUSDT`;
  - active_generation = `4`;
  - switch_state = `READY`;
  - readiness.ready = true;
  - attached_count = 1;
  - active browser stream symbol = `OGUSDT`;
  - active browser stream workspace_generation = `4`;
  - active browser stream attached = true.

Historical detached generation-2 stream remains diagnostic history only and is not the
active browser connection.

Committed fix:

`ddcf164580bcf88b8da8f72ae580d7efb25435a0`
`fix: bootstrap frontend from workspace state`

Current Terminal policy:

- do not reopen the Vite/WebSocket proxy investigation unless new runtime evidence requires it;
- continue Terminal completion/acceptance;
- workflow / Task Transaction experiment remains frozen and must not displace Terminal work;
- real-phone acceptance remains a separate required acceptance stage.

---

# 2026-08-30 TERMINAL ACCESS / NETWORKING POLICY UPDATE

Status:

ADOPTED

## USER-FACING ACCESS POLICY

Pinggy and temporary SSH/public tunneling are no longer part of the active
Trading Workspace development or acceptance workflow.

Deprecated / do not use:

- Pinggy;
- `a.pinggy.io`;
- temporary Pinggy URLs;
- old `lhr.life` tunnel URLs;
- similar ephemeral SSH tunnel URLs;
- reopening Terminal for the user through `localhost` or `127.0.0.1`.

Do not automatically propose these access methods in future Terminal sessions.

## LOCALHOST / LOOPBACK ROLE

`localhost` and `127.0.0.1` remain valid only as internal machine-local
transport addresses between development processes.

Example of an allowed internal binding:

- Vite preview proxy -> PAPER backend at `127.0.0.1:8765`.

They are not the canonical user-facing desktop or phone Terminal entry point.

## CURRENT DESKTOP / REAL-PHONE ACCESS

The active local development access model is:

`device -> PC LAN address -> Vite preview -> backend`

Current confirmed Vite preview port:

`4173`

Current observed PC LAN URL:

`http://192.168.100.8:4173/`

This LAN address is environment-dependent and must not be treated as a
permanent hardcoded address. After network changes, reboot, adapter changes,
or DHCP changes, use the current Network URL reported by Vite preview.

Desktop and real-phone acceptance should use the current LAN Vite preview URL
when the devices can reach the same local network.

## EXTERNAL / FUTURE ACCESS

If Trading Workspace requires stable access from outside the local network,
solve it through the planned production/VPS deployment architecture.

Do not restore Pinggy or another temporary tunnel as the default production
or acceptance solution unless the user explicitly requests a temporary
diagnostic exception.

## CURRENT DECISION

Canonical current direction:

- local development runtime: Vite preview;
- internal backend transport: loopback is allowed;
- user-facing local access: current LAN Vite URL;
- phone acceptance: LAN Vite URL;
- temporary public tunnels: deprecated;
- future persistent remote access: VPS / production deployment.

This policy supersedes earlier Pinggy / `lhr.life` development-access
instructions where they conflict with this section.

---

# 2026-08-30 REAL-PHONE ACCEPTANCE PASS

Status:

PASS

## VERIFIED ON REAL PHONE

Trading Workspace was opened through the current Vite LAN URL:

`http://192.168.100.8:4173/`

Observed on the real phone:

- authoritative `OGUSDT` startup selection was applied correctly;
- Chart was live;
- DOM was live;
- Smart Tape was live;
- `LIVE BOOK UNAVAILABLE` was absent;
- mobile layout remained operational without the previously observed viewport regression;
- no Pinggy or temporary public tunnel was used;
- no `localhost` user-facing access was used.

## ACCEPTANCE RESULT

The startup authority fix is now accepted on:

- desktop runtime;
- real phone runtime.

The current local access path is confirmed as:

`phone / desktop -> PC LAN address -> Vite preview -> backend`

This closes the real-phone acceptance requirement for the workspace startup
authority blocker.

## CURRENT TERMINAL DIRECTION

Continue Terminal completion and acceptance from this accepted runtime state.

Do not reopen Pinggy / localhost user-facing access or Vite proxy investigation
without new objective evidence of failure.

Workflow / Task Transaction experiment remains frozen and outside the current
Terminal completion path.

---

# 2026-08-30 M9 WORKSPACE OPERABILITY / DIAGNOSTICS ACCEPTANCE

Status:

COMPLETE / ACCEPTED

## FINAL RUNTIME CONTROL

The authoritative Workspace doctor was rerun after the desktop and real-phone
acceptance checkpoints:

`.\venv\Scripts\python.exe -m tools.dev.workspace_doctor --symbol OGUSDT --interval 5`

Observed result:

- `STATUS PASS`;
- `INSTRUMENT PASS symbol=OGUSDT`;
- `SWITCH PASS active_symbol=OGUSDT generation=4`;
- `READINESS PASS book=true trades=true candles=true`;
- `STREAM PASS kind=workspace_snapshot generation=4`;
- `STATE PASS switch_state=READY active_symbol=OGUSDT generation=4`.

## M9 ACCEPTED CAPABILITIES

M9 now has accepted evidence for:

- typed Workspace semantic failure classes;
- structured semantic error envelopes;
- requested/active symbol and generation authority;
- candidate failure preserving the previous active Workspace;
- read-only `/api/workspace/state` diagnostics;
- stream-session diagnostics;
- authoritative symbol-switch acknowledgement;
- Workspace startup from backend symbol/generation authority;
- deterministic `workspace_doctor`;
- registry / activation / readiness / stream runtime verification;
- desktop runtime acceptance;
- real-phone runtime acceptance through Vite LAN access.

The previous `attached=false` / `LIVE BOOK UNAVAILABLE` condition is historical
diagnostic evidence and is not an active blocker.

## CURRENT STATE

M9 Workspace Operability / Diagnostics is closed.

No further M9 architecture expansion is required without new objective failure
evidence.

The next decision is not another M9 implementation slice. The next step is to
compare the complete current Trading Workspace v1 state against the remaining
CR acceptance requirements and determine whether the Terminal CR itself can be
closed or whether a bounded non-M9 acceptance item remains.

Workflow / Task Transaction work remains frozen during that decision.

## FAST DOM MARKET ROUTING AND OWN-ORDER ACCEPTANCE

Revision 1.88 records the accepted bounded non-M9 slice. Fast DOM classifies intent before command creation:
resting BUY below Ask and SELL above Bid use canonical GTC Limit creation; crossing BUY at or above Ask and
SELL at or below Bid use canonical Market execution and are never created as Limits first. Missing required
book authority remains fail-closed.

Fresh production build and real-phone acceptance are PASS. Crossing selections execute immediately without a
pending Limit confirmation. Own active Limit dots are visible in the mobile DOM, each dot cancels only its
concrete order, and two orders at one price render two independently cancellable dots.

## MOBILE CHART AND DOM/TAPE LAYOUT ACCEPTANCE

Revision 1.89 records real-phone acceptance of the bounded display-only slice. Chart labels use the accepted
9px font; ordinary sub-1 prices retain the leading zero, while prices with at least two consecutive fractional
leading zeros use compact chart-only notation such as `0.003367 -> (2)3367` and
`0.0003367 -> (3)3367`. Authoritative numeric prices, tick-size precision, orders, DOM and execution remain
unchanged.

The mobile DOM fills its panel height, the x3 compression control remains usable as an overlay, unavailable
status no longer obscures data, Smart Tape shares the accepted DOM Y alignment, and the live PnL indicator
clears the side-panel collapse control. Focused DOM/Tape geometry tests are `31/31 PASS`, the fresh production
build is `PASS`, and real-phone acceptance is `PASS`.

After CENTER, the approximately 13/15 visible-row distribution is `USER-DEFERRED / NON-BLOCKING` by explicit
user decision. It is not a failure or blocker for this accepted slice.

## MANUAL TERMINAL V1 COMPLETION SCOPE

Revision 1.91 supersedes the documentation-only conclusion that STOP, TAKE PROFIT, real-account/API management
and real-account execution are future or outside this ChangeRequest. `CR-TRADING-WORKSPACE-001` remains
`IN_PROGRESS` in `IMPLEMENT` until all blockers below are implemented and accepted.

1. **Drawing Tools Ruler:** expose the existing two-point Ruler in the palette with live price-difference and
   percentage measurement, existing time/bar measurement where supported, movement and shared deletion semantics.
2. **Open Positions UX:** show the active Terminal symbol first and visually highlighted; list all other open
   positions below it; move `Закрыть все` closer to the `Открытые позиции` heading and use a red border without
   changing Close All execution semantics.
3. **STOP on PAPER:** implement and accept create, edit, activate and cancel; authoritative projection; quantity
   fixed to 100% of current position with automatic quantity synchronization after size changes; price preserved
   unless explicitly edited; cleanup after confirmed FLAT.
4. **TAKE PROFIT on PAPER:** implement and accept the same lifecycle, projection, 100%-quantity synchronization,
   explicit-only price edits and confirmed-FLAT cleanup while preserving approved signal TAKE proposal semantics.
5. **Real account/API management:** add credentials only through a backend security boundary; never expose API
   Secret to the frontend; support configured account selection and switching with account-scoped state and a
   mutation lock until loading and reconciliation complete.
6. **Real execution/reconciliation:** reuse the established execution architecture for Market, Limit, STOP and
   TAKE on the selected real account; retain fail-closed `UNKNOWN`/`RECONCILING`, authoritative exchange
   reconciliation before success and no blind retries; complete a real-money security and acceptance gate.

Binding order is Drawing Tools Ruler; Open Positions UX; STOP + TAKE on PAPER; real account/API management and switching; real
execution/reconciliation; final Manual Terminal v1 acceptance; then and only then CR closure. CENTER's
approximately 13/15 distribution and Done/Enter focus progression remain `USER-DEFERRED / NON-BLOCKING`.
Robot/AUTOPILOT, Android, MetaScalp, VPS, Scanner and strategy work remain outside this completion sequence.

## RULER ACCEPTANCE AND OPEN POSITIONS UX CHECKPOINT

Revision 1.92 records the Drawing Tools Ruler as `COMPLETE / REAL-PHONE ACCEPTED`. It uses the established
two-point drawing lifecycle, live price and percentage measurement, existing bar/time metrics, movement and shared
deletion. Native browser text/icon selection within Drawing Tools is `USER-DEFERRED / NON-BLOCKING`.

Open Positions UX is the current implementation slice. The bounded implementation derives an active-symbol-first
presentation order from the existing authoritative workspace symbol without mutating server inventory, highlights
that row presentation-only, preserves relative order for all other positions, and moves the unchanged Close All
action beside the heading with a red border. Manual/browser acceptance remains pending.

## FIBONACCI DRAWING UPGRADE CHECKPOINT

Revision 1.93 records the current Drawing Tools slice: the existing two-anchor Fibonacci drawing now uses default
levels `0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236`, including genuine extensions in
either anchor direction. Each level shows coefficient plus a price formatted through existing chart tick-size
authority, and adjacent intervals receive restrained translucent fills beneath readable level lines.

Creation, magnet, anchor movement, selection, persistence and deletion remain on the shared drawing lifecycle.
Open Positions UX remains implemented with manual acceptance pending; Ruler remains complete/accepted; native
browser Drawing Tools selection remains `USER-DEFERRED / NON-BLOCKING`.

## FIBONACCI MOBILE TWO-STAGE PLACEMENT CHECKPOINT

Revision 1.94 makes explicit two-stage touch placement the current Fibonacci acceptance requirement. Selecting Fib
creates nothing. The first deliberate chart touch creates only an internal Anchor A draft; it may be dragged
immediately and after release while the tool waits for a separate second tap. Full levels, fills and labels appear
only after Anchor B is deliberately placed.

While either anchor is initially placed or actively adjusted, a temporary non-persisted horizontal dashed guide
tracks its exact price across the chart and disappears when interaction ends. Tool change/cancel discards an
unfinished one-anchor draft. Completed Fibonacci selection, anchor editing, magnet, movement, persistence and
deletion remain on the shared drawing architecture. Phone acceptance is pending.

## FIBONACCI TOUCH INTERACTION CORRECTION

Revision 1.95 supersedes the prior tap-then-adjust placement detail. Each physical anchor is defined by one
press/optional-drag/release gesture: the first fixes the level-1 anchor without a grid; the second stretches the
level-0 anchor with live levels, extensions, fills and labels, then completes the selected Fib on release. Temporary
horizontal guides follow the anchor during each placement and active anchor edits.

A completed Fib is initially active. An inactive Fib remains fully visible but cannot be moved or edited; a
deliberate tap within its practical rendered levels/bands/anchors/labels region activates it without changing
geometry, and only a subsequent explicit active edit gesture may mutate it. A tap outside deactivates it. Tool
change/cancel still discards a one-anchor draft. Phone acceptance remains pending.

## RULER MOBILE TEMPORARY LIFECYCLE

Revision 1.96 binds Ruler placement to two press/optional-drag/release gestures with live measurement during the
second stretch. Completion starts `ACTIVE`, with independent endpoint editing. The first deliberate outside tap
changes the Ruler to `FIXED` without deleting it; fixed endpoint touches cannot resize it, while a body drag rigidly
translates both endpoints and preserves the measurement span. A subsequent deliberate outside tap dismisses the
fixed temporary Ruler. Internal drag releases never count as outside taps, and tool change discards a one-anchor
draft. Phone acceptance is pending.

## DRAWING TOOLS ACCEPTANCE CHECKPOINT

Revision 1.97 records Ruler and Fibonacci as `ACCEPTED / COMPLETE` by real-phone acceptance. Ruler includes
two-stage touch placement, directed origin-to-destination measurement signs, active endpoint editing, temporary
horizontal anchor guides, first-outside fix, rigid fixed-body translation and second-outside dismissal. Fibonacci
includes the binding levels/fills/labels, corrected anchor order, live second-anchor stretch, active/inactive edit
gate and bounded mobile hit region. Native browser Drawing Tools text/icon selection remains `USER-DEFERRED /
NON-BLOCKING` because the browser is not the intended final Terminal surface.

Open Positions UX remains implemented with focused automated evidence; real-phone visual acceptance remains
pending. The ChangeRequest remains `IN_PROGRESS / IMPLEMENT` for STOP, TAKE PROFIT, real-account/API management
and real execution/reconciliation.

## OPEN POSITIONS UX ACCEPTANCE CHECKPOINT

Revision 1.98 records Open Positions UX as `ACCEPTED / COMPLETE` by real-phone acceptance: active workspace
symbol first, active-row highlight, stable ordering of other rows, Close All beside the heading and a clearly red
Close All border. Close All execution, confirmation and reconciliation semantics are unchanged. The ChangeRequest
remains `IN_PROGRESS / IMPLEMENT`; the next blockers are STOP and TAKE PROFIT on PAPER, followed by real-account/API
management and real execution/reconciliation.

## STOP UNRESTRICTED PLACEMENT AND DEFERRED EDIT-DRAG CHECKPOINT

Revision 1.99 records unrestricted manual PAPER STOP create/amend on either side of authoritative Average Entry
for both LONG and SHORT while preserving closing-only execution, current-position quantity bounds and atomic FLAT
protection cleanup. STOP CREATE and EDIT confirmation controls are real-phone accepted with matched visible
check/cancel sizing, alignment and retained enlarged transparent confirmation touch targets. TAKE semantics remain
unchanged.

`OPEN / DEFERRED`: on a real phone, STOP EDIT mode entered through the pencil persists correctly, but the subsequent
touch used to grab and drag the editable line is intermittently unreliable, approximately every other attempt. No
root cause is proven. Further diagnosis and correction of this second-touch drag interaction are explicitly
deferred by the user and do not revoke the accepted STOP create/amend confirmation or unrestricted placement
semantics recorded above.

## ACCOUNT-WIDE READ-ONLY LIVE RECONCILIATION ARCHITECTURE AMENDMENT

Revision 2.0 records the approved bounded architecture and its subsequently authorized production implementation.
The current `ReconciliationCoordinator` remains the sole L2 symbol/leg authority: it consumes one complete
`RecoveryBundle` for one `PositionKey(account, category, symbol, positionIdx)`, applies normalized facts through
the existing `ExecutionEngine`, and commits the existing position/checkpoint projections. It must not be bypassed
by a second symbol reconciliation implementation and must not be misused as an account-wide discovery API.

One L3 read-only account reconciliation orchestrator may be added above that coordinator. Its bounded ownership is:

1. load one saved Bybit account's credentials only through the backend `CredentialStore`;
2. capture an immutable refresh token containing `account_id`, a monotonic per-account `refresh_generation`, and
   the unchanged `TradingAccountManager.session_token` observed when the refresh begins;
3. freshly validate credentials and require the validated environment to equal the persisted routing environment;
4. use the existing `BybitV5ReadAdapter`, extended narrowly with normalized account-wallet, all-linear-positions
   and all-linear-open-orders reads; raw authenticated Bybit payloads do not cross the adapter;
5. assemble one complete account discovery snapshot before any publish;
6. route each discovered symbol/position leg that requires durable execution-state convergence through the existing
   `ReconciliationCoordinator`; no coordinator call may receive mixed-account or incomplete fabricated evidence;
7. atomically publish the account summary only if the refresh token is still current; otherwise discard the late
   result without status or projection mutation.

The account discovery snapshot is account-scoped and contains only allow-listed normalized fields: account id,
environment, validation-derived permission mode, reconciliation status, refresh generation, exchange evidence
timestamp when available, USDT `walletBalance`, total equity and available balance as distinct Decimal values,
normalized open-position summaries, normalized open-order summaries, counts and safe failure code. `walletBalance`
remains the future Working Volume authority; total equity and available balance do not replace it.

LIVE account summaries require a separate persistence/projection boundary. The existing `paper_accounts` table is
PAPER-only and must not store LIVE wallet state. Durable LIVE rows and every nested position/order key include the
real `trading_account_id`; no LIVE evidence may be written under `paper`. Publishing a new generation replaces one
account's prior account-wide snapshot atomically. Store or coordinator failure leaves the account non-ready and
does not expose a partial new snapshot.

Status transitions are fail-closed:

```text
persisted startup                         -> DISCONNECTED
refresh start                            -> RECONCILING
fresh validation + complete discovery
  trading-capable key                    -> READY
  read-only key                          -> READ_ONLY
validation/environment/snapshot failure  -> ERROR
stale refresh completion                 -> discarded; cannot promote status
```

Inactive refresh never changes `active_account_id` or account session generation. It invokes no mutation adapter,
starts no private WebSocket and grants no trading authority. Future account switching must consume only a current,
complete account snapshot and remains separately gated.

The bounded HTTP surface is credential-free: one refresh command scoped by opaque account id and one read summary
projection. Responses expose normalized status/summary/error codes only—never credentials, credential references,
raw Bybit responses or exception text. Frontend may show Refresh/Reconnect, status, wallet/equity summary and
position/order counts for an inactive account; it must not mark that account Current or expose trading controls.

Implementation acceptance requires regressions for persisted DISCONNECTED startup, READY versus READ_ONLY fresh
validation, environment mismatch, validation/discovery/store/coordinator failure, PAPER authority preservation,
account and generation isolation, stale-result rejection, cross-account contamination, mutation-adapter absence,
credential-free transport and frontend refresh/status rendering. Production implementation was explicitly
authorized on 2026-08-31.

Revision 2.0 is `REAL-PHONE / REAL-BYBIT READ-ONLY RECONCILIATION ACCEPTED / PASS`. After the production build,
a real saved Bybit MAINNET account successfully completed Refresh/Reconnect and fresh validation plus account-wide
reconciliation reached `READY`. The UI displayed real Equity and Wallet together with 33 positions and 13 active
orders. `Paper / Virtual` remained the sole `Current` account, `active_account_id` did not switch, no LIVE mutation
was performed, and no credential exposure was observed. The next stage is `ACTIVE ACCOUNT SWITCHING +
ACCOUNT-SCOPED WORKSPACE ACTIVATION`, still without LIVE mutations.

## ACTIVE ACCOUNT SWITCHING + ACCOUNT-SCOPED WORKSPACE ARCHITECTURE AMENDMENT

Revision 2.1 is a documentation-only bounded amendment. It resolves the conflict found between immutable PAPER
persistence identity and dynamic active-account/session authority. It does not authorize production implementation.

### Identity, authority and atomic switch

`TradingAccountId("paper")` is the permanent PAPER storage identity. PAPER limits, positions, protection,
inventory and close paths always use that key and never derive a storage key from `active_account_id`.
`TradingAccountManager` remains the sole owner of `active_account_id`, `session_generation` and the immutable
`AccountSessionToken`; current status and active/current selection remain separate axes.

The switch transaction validates the target, captures the current session token, requires a complete current LIVE
snapshot for a Bybit target, then atomically changes manager authority and increments `session_generation` exactly
once. Failure changes neither active account nor generation. PAPER `READY` and Bybit `READY` are eligible; Bybit
`READ_ONLY` is eligible only for a read-only Workspace. `DISCONNECTED`, `RECONCILING` and `ERROR` are rejected with
Refresh/Reconnect required. The credential-free switch request contains only the opaque account id; the response
contains the new active account id, session generation and normalized safe status/error.

### Account-scoped projection router

One backend Workspace read router selects projections exclusively from the active session. PAPER reads existing
PAPER projections under the immutable paper key. Bybit reads only the current complete LIVE snapshot for that
account. Its normalized envelope contains account id, provider, environment, status, session generation,
projection generation/version, positions, orders and wallet/account summary where applicable. PAPER and LIVE facts
must never mix. Every response carries account id and session generation; the frontend rejects it if either no
longer matches its current `AccountSessionToken`.

The global `paperTradingStore` ownership must be replaced or generalized into a session-aware Workspace/account
projection store keyed by `account_id + session_generation`. Successful switching immediately makes the prior
projection inaccessible; late HTTP or WebSocket results from that session are discarded, so the UI cannot display
one frame of the previous account. LIVE positions and orders are read-only views with symbol navigation only and no
PAPER close/cancel affordances.

### Mutation and market-data boundaries

All existing trading mutation endpoints share one authoritative backend gate. Mutation is permitted only when the
active account is provider `PAPER`, environment `PAPER`, status `READY`. Market BUY/SELL, Limit create/amend/cancel,
STOP, TAKE, per-position close, Close All and every other current mutation fail closed for any LIVE or read-only
session with a normalized error such as `live_mutations_disabled`; no Bybit mutation adapter is invoked. Frontend
controls are also hidden or disabled for LIVE, but are never the security boundary.

Account switching creates no market-data owner. Chart, candles, DOM, prints/trades, ticker and public order book
remain under the existing Workspace symbol authority and its independent symbol generation. A valid current symbol
is preserved on account switch. Selecting a LIVE position/order symbol uses the existing Workspace-symbol switch
path. Account session generation, LIVE refresh generation and public symbol generation are distinct authority
dimensions: stale switch responses, account projections, LIVE refresh results, PAPER async results and symbol
results are each rejected against their own captured token/generation.

### UX and acceptance gate

The backend `active_account_id` alone projects Current. The active account sorts first; all other accounts retain
stable order and status. Exactly one golden key appears beside the active account name. Selecting a non-current
card enters `IDLE -> CONFIRMING -> SWITCHING -> ACTIVE(new token)` or `FAILED(old token remains authoritative)`;
the dialog names account and environment, and duplicate taps are blocked while switching.

### Revision 2.1 preferred-account restoration and Unified balance semantics

Production implementation and real-phone correction were explicitly authorized after the documentation checkpoint.
The backend persists only a versioned canonical preferred `account_id`; it never persists or restores
`session_generation`. On startup the manager begins with PAPER authority. A preferred Bybit account is registered
as `DISCONNECTED`, freshly reconciled to a complete account snapshot, required to become `READY` or `READ_ONLY`,
and only then activated through `TradingAccountManager`, incrementing generation once. Failed reconciliation,
unknown/deleted identity or an ineligible status leaves PAPER authoritative with its generation unchanged. This
automatic restore does not require a second confirmation because it replays the user's previously confirmed
preference; every new user-initiated switch still requires explicit confirmation.

For Bybit Unified Trading Account wallet reads, normalized account-wide USD semantics are fixed as follows:
Deposit/account funds use `result.list[0].totalWalletBalance`; the accepted second balance metric uses
`result.list[0].totalEquity`. `totalAvailableBalance` and the allow-listed account/USDT raw candidates remain
diagnostic provenance and are not substituted into the accepted two-value key peek. Coin-level `walletBalance`,
unrealized PnL, margin balance and deprecated `availableToWithdraw`/`free` are not substituted for these values.

Implementation acceptance requires regressions proving immutable PAPER storage identity; PAPER-to-LIVE-to-PAPER
projection restoration without mixed facts; every backend mutation blocked for LIVE and READ_ONLY; eligible and
ineligible target behavior; exactly-once generation increment and unchanged failed-switch generation; stale switch,
projection, refresh, PAPER and symbol-result rejection; active-first ordering and one golden key; read-only LIVE
positions/orders without mutation actions; existing symbol navigation and public market-data reuse; credential-free
transport; and absence of any mutation-adapter call.

### Revision 2.1 production implementation and real-phone closure

Revision 2.1 is `PRODUCTION IMPLEMENTED / REAL-PHONE ACCEPTED / COMPLETE` on 2026-09-01. The accepted runtime keeps
`TradingAccountManager` as sole active-account/session authority, immutable PAPER persistence identity, atomic
eligible switching, versioned preferred-account restoration through fresh reconciliation, and account-scoped
PAPER or complete LIVE Workspace projection without mixed facts. LIVE and READ_ONLY remain fail-closed at every
backend mutation route and in the frontend while the public chart/DOM/tape pipeline remains independent from
PAPER execution; active LIVE order-book updates do not enter PAPER matching/context processing.

Frontend ownership rejects stale account/session and lower refresh-generation results, coalesces periodic REST-only
LIVE refresh, and preserves the last valid account-scoped projection on failure. Accepted Unified balances are
Deposit from account-wide `totalWalletBalance` and the second metric from account-wide `totalEquity`, with raw
allow-listed provenance retained. Exactly one golden key identifies Current, short tap opens the dismissible
Accounts modal, 500-ms hold shows refreshed balances, and the account name remains in the isolated lower limits row.
Real-phone acceptance confirms startup restore, read-only LIVE controls, Accounts backdrop/close behavior, removal
of oversized Workspace LIVE cards, original upper trading-control geometry and a continuous full-width lower-row
divider. No PAPER/LIVE state mixing or LIVE mutation-adapter invocation was observed.

### Revision 2.2 LIVE MARKET execution foundation authorization

Revision 2.2 authorizes only manual confirmed MARKET BUY and MARKET SELL for the active writable Bybit MAINNET
account. `TradingAccountManager` remains the sole account/session authority. Every request carries
`client_action_id`, `account_id`, `session_generation`, symbol, side, volume, sizing reference price and slippage;
the backend validates the exact active READY, non-read-only session and rechecks its captured session token
immediately before irreversible dispatch.

A narrow application coordinator above `TradingApplication` and `BybitV5MutationAdapter` owns the mutation. It
atomically binds `(account_id, session_generation, client_action_id)` to one durable command and canonical
Bybit-compatible `orderLinkId`, persists before dispatch, permits at most one adapter invocation, treats ACK as
accepted-pending rather than filled, and never blindly retries an ambiguous mutation. Timeout or transport
ambiguity becomes `UNKNOWN`, blocks conflicting exposure-changing LIVE MARKET work and requires REST-only
correlation of order history, execution history, active orders and current position against the original
`orderLinkId`. Late dispatch or reconciliation results may update only their captured account/session projection.

Backend real-money dispatch requires both a LIVE MARKET capability gate and a separate MAINNET authorization gate,
plus the mutation adapter's existing lower-level gates. All gates default OFF. A separately configured positive
acceptance-notional ceiling is authoritative and rejects, rather than resizes, an oversized request. Startup,
reconnect, refresh and reconciliation cannot place an order. Automated tests must use fakes and must never enable a
real exchange dispatch.

`/api/market` and all PAPER execution, persistence and projection behavior remain unchanged. LIVE uses the separate
`/api/live/market` boundary and explicit confirmation with one stable `client_action_id`. Only MARKET BUY/SELL may
be capability-enabled for a READY writable active LIVE session; LIVE Limit, fast-Limit hold, STOP, TAKE, per-position
close and full-close remain disabled and backend-blocked. Private WebSocket and real-money acceptance are outside
this revision.


## REVISION 2.2 REAL-PHONE ACCEPTANCE CHECKPOINT
Date: 2026-09-02
- Main Bybit restored as READY.
- LIVE BUY/SELL capability gating verified.
- Explicit LIVE confirmation verified on real phone.
- Zero-ceiling fail-closed behavior verified: acceptance_notional_exceeded.
- Mobile blocked-result feedback made visible.
- SQLite live_market_actions remained empty during zero-ceiling test.
- REAL BYBIT ORDER SENT: NO.
- LIVE Market foundation acceptance: PASS for safe non-dispatch path.

### Revision 2.3 restart-safe LIVE MARKET recovery authorization

Revision 2.3 extends only the accepted Revision 2.2 LIVE MARKET foundation. On startup and explicit LIVE account
refresh, the runtime scans durable `live_market_actions` joined to unresolved commands. Persisted `SUBMITTING`,
`ACKNOWLEDGED`, `UNKNOWN` and `RECONCILING` states are recovery work, never evidence that mutation was not sent.
Recovery uses only active orders, order history, execution history and supplemental position reads through the
existing Bybit read adapter, correlated to the original durable `command_id` and `orderLinkId`. No recovery path
may obtain or call the mutation adapter.

Insufficient or unavailable evidence remains fail-closed as `UNKNOWN` or `RECONCILING`; deterministic normalized
evidence may resolve the original command to `OPEN`, `PARTIALLY_FILLED`, `FILLED` or `REJECTED`. Any unresolved
action blocks a new exposure-changing LIVE MARKET action for the same account, including after a process restart.
A repeated `(account_id, client_action_id)` across a newly constructed session returns the original durable command
and `orderLinkId` and cannot redispatch. Durable command resolution may complete for its captured historical
account/session, but projection refresh is permitted only when the captured `account_id + session_generation`
still equals the active session token; stale recovery therefore cannot publish into a newer active session.

Automated acceptance must reconstruct the coordinator and SQLite store over the same database, use fake Bybit
reads, assert zero mutation-adapter calls for recovery/startup/reconnect/refresh, and keep every real-money gate
fail-closed. LIVE Limit, STOP, TAKE, close, private WebSocket, autonomous trading and real-money acceptance remain
outside this revision. `REAL BYBIT ORDER SENT: NO` is binding.

### Revision 2.4 LIVE MARKET final pre-dispatch validation authorization

Immediately before the sole mutation-adapter invocation, the coordinator must revalidate the captured active
account/session token, Bybit MAINNET READY writable eligibility, canonical instrument symbol and BUY/SELL side,
normalized positive quantity, generated canonical `orderLinkId`, supported bounded slippage type/value and
authoritative normalized quantity times authoritative reference price against the configured acceptance-notional
ceiling. The account/session and eligibility fence is checked again at the dispatch boundary so a change after
validation cannot reach the adapter. Any failed check is blocked with zero mutation-adapter calls and no retry.

Automated implementation verification uses only the fake mutation adapter and proves its exact payload. Runtime
real-money gates remain off except during a separately explicit real acceptance window. LIVE Limit, STOP, TAKE,
close, private WebSocket, UI and PAPER semantics remain outside this revision.

## REVISION 2.4 REAL LIVE MARKET ACCEPTANCE CHECKPOINT

Date: 2026-09-02

Status: `FAIL — TWO DISTINCT ACCEPTANCE ORDERS SENT`

The requested one-order acceptance invariant was not met. Two separate UI confirmations created two different
durable `client_action_id`, `command_id` and `orderLinkId` identities. This was not a retry or redispatch of one
command: each command has exactly one durable `SUBMITTING` transition and one exchange acknowledgement.

Both orders were `MARKET SELL ONGUSDT`, normalized quantity `51 ONG`, with approximate requested notional
`5.10 USDT` each:

- `cmd_542e94a282974379aab93b53785eb0c6` / `tw_542e94a282974379aab93b53785eb0c6a` /
  exchange order `20cb9f26-e473-430e-b84c-d99502709f99`: REST order history `FILLED`, cumulative filled quantity
  `51`, average fill price `0.09924`; execution `2a554e02-fd93-5856-ba99-5a4b9dfc5e06`, quantity `51`, value
  `5.06124 USDT`, fee `0.00177144 USDT`.
- `cmd_cd078103629841c898a027f50861bfed` / `tw_cd078103629841c898a027f50861bfed4` /
  exchange order `ab13d849-c747-4843-8b8a-38d7c6c8baaa`: REST order history `FILLED`, cumulative filled quantity
  `51`, average fill price `0.09937`; execution `0c9943a5-a677-5d1e-bf62-42c077bf5631`, quantity `51`, value
  `5.06787 USDT`, fee `0.00177376 USDT`.

Fresh REST position evidence after reconciliation was `ONGUSDT LONG 161`, average entry `0.10670773`, mark price
approximately `0.09956`. This position snapshot is recorded as final observed account state; it is not attributed
only to these two fills because other account activity may coexist.

Immediately after discovery, the backend was restarted fail-closed with
`LIVE_MARKET_MUTATIONS_ENABLED=false`, `LIVE_MAINNET_AUTHORIZED=false` and
`LIVE_MARKET_ACCEPTANCE_NOTIONAL_CEILING=0`; Workspace capability `market=false` was confirmed. `REAL BYBIT ORDER
SENT: YES — TWO ORDERS`. Revision 2.4 real acceptance is not PASS. No further real dispatch is authorized by this
checkpoint.

### Revision 2.5 LIVE single-flight acceptance guard authorization

Revision 2.5 adds an opt-in one-shot guard only for a separately authorized LIVE MARKET acceptance window. The
frontend synchronously consumes the confirmation action before its first request, so a repeated tap or double-tap
cannot create another `client_action_id` or another `/api/live/market` dispatch. At the backend dispatch boundary,
the acceptance permit is consumed immediately after durable dispatch ownership is acquired and before the sole
mutation-adapter call. While acceptance single-flight mode remains enabled, every later distinct LIVE MARKET action
is blocked even if the first command has already reconciled to `FILLED`; replay of the original durable action
continues to return its original command without redispatch.

The permit exists only in the explicitly constructed authorized runtime and can be restored only by a new explicit
runtime authorization. `LIVE_MARKET_ACCEPTANCE_SINGLE_FLIGHT` defaults to false, so ordinary future LIVE trading is
not constrained by this acceptance-only one-shot policy. LIVE Limit, STOP, TAKE, close, private WebSocket and PAPER
semantics remain outside this revision. Verification uses only fake mutation adapters. `REAL BYBIT ORDER SENT: NO`
for Revision 2.5; the failed two-order Revision 2.4 historical checkpoint remains unchanged.

### Revision 2.6 LIVE execution parity backend authorization

Revision 2.6 reuses the existing `TradingApplication`, `ExecutionEngine`, normalized REST evidence and
`BybitV5MutationAdapter` for LIVE LIMIT create, price amend/move, cancel, full-position STOP/TAKE set/amend/delete,
and reduce-only full close. A single LIVE coordinator supplies authoritative REST command context and rechecks the
captured active account/session at every irreversible adapter boundary. Any stale account/session, non-MAINNET,
non-READY or non-writable account is blocked before adapter dispatch. A pending or ambiguous command blocks a
conflicting mutation until REST reconciliation resolves it; no mutation is retried.

The separate `LIVE_PARITY_MUTATIONS_ENABLED` gate and existing `LIVE_MAINNET_AUTHORIZED` gate both default OFF.
PAPER routes and semantics remain unchanged, and no private WebSocket is introduced. This slice exposes bounded
backend LIVE parity routes; shared frontend transport activation remains an explicit open item so account/session
authority is never inferred or omitted. Automated verification uses fake adapters only. `REAL BYBIT ORDER SENT: NO`.

