# BYBITSCANNER — Android application and autonomous trading (future concept)

Status: OWNER IDEAS RECORDED / FUTURE DESIGN, NOT IMPLEMENTATION AUTHORIZATION
Date: 2026-10-20
Scope: architectural direction and approximate effort only; current GFL, AUTOPILOT Terminal and MIRROR RETEST delivery remain higher priority.

## 1. Owner's desired outcome

One Android application with the three existing shared workspaces:
- **TERMINAL** — fully independent manual trading client: direct Bybit REST/WebSocket market and private trading connectivity, with no requirement for the owner PC, VPS, browser backend or Scanner/Robot to be online. MARKET/LIMIT, positions, balance, STOP/TAKE, chart, DOM/tape and exchange reconciliation must remain functional with only the smartphone and Bybit network access.
- **AUTOPILOT** — view/control Scanner and Robot through a **configurable remote execution host: existing Windows PC first, VPS later**. PC and VPS use one versioned secure interface. The phone must not be an accidental dependency of continuous server-side execution.
- **EDITOR** — reusable ChartPanel/DrawingOverlay, magnet anchored to verified candle extrema (High/Low with deliberate OHLC options), immutable original Scanner geometry versus editable copy; trade STOP/TAKE/parameters and changes in the trade journal, with explicit distinction between annotation and a protected order mutation. Local editing may continue offline; durable synchronization needs identity, versioning, conflict handling and approval.

**Stretch ideal:** run Scanner and Robot continuously **on Android itself**, including while the UI is closed and screen off, with no PC/VPS. This is a research goal, **not** a promised reliable 24/7 execution mode: Android background execution, power policies, network outages, process termination and device restarts impede guarantee. A foreground service alone does not eliminate these limitations. If unattended 24/7 execution is essential, an always-on PC or VPS is the practical primary execution host.

## 2. Recommended portability path (not a new terminal)

Reuse the existing React/TypeScript UI and shared chart/trading visual components; do not rewrite three separate frontends. Explore **Capacitor** for an Android APK/AAB. A **PWA** can be a cheap installable UI prototype, but is not a substitute for native Android secret handling/background behavior, and wrapping a web UI does not port the existing Python Scanner/Robot backend.

Build a **new mobile-native Bybit transport/adaptor** behind clean contracts for the autonomous manual TERMINAL (authenticated request signing, credential storage through Android Keystore-backed facilities, REST/WS, error handling, retry/idempotency, market data and exchange-state reconciliation). Assess Bybit/API/network/CORS restrictions and rate limits before committing to a specific networking design; native HTTP bridging may be required. Never place a server secret in static web assets or in an untrusted WebView origin.

For AUTOPILOT and Scanner/editor synchronization, separate the remote **control/data plane** from trading execution. A server may run on the PC or VPS; both must offer authenticated encrypted connections with scoped permissions and verified account/position identity. No unauthenticated public exposure of PAPER backend/Robot endpoints. Allow remote-host selection/fail-closed disconnected UX; do not silently promote a shadow/observation signal to executable action.

When the PC is off: mobile manual TERMINAL still uses Bybit directly; AUTOPILOT indicates disconnected; EDITOR retains supported local functions and queues only versioned, non-trading annotations for later synchronized review.

## 3. Order ownership and safety

Two clients (manual phone TERMINAL and remote Robot) can see or touch the same exchange account. Exchange authoritative state, uniquely identified trade/position/order records, version/revision checks, conflict rejection and reconciliation are required. Robot-owned protection/order state must never be silently overwritten by a mobile edit; likewise mobile trade management must not be gated by VPS availability.

Prefer exchange-hosted protective orders; never rely on phone process memory to provide unattended STOP/TAKE. Fail closed on unknown exchange/account state. Preserve owner-only runtime start/stop, existing PAPER/LIVE isolation and protection-health/reconciliation gates. No authorization here to enable LIVE, merge, run Robot or Scanner, or mutate the PAPER database.

Existing **Telegram signal buttons** desired layout: TradingView (remove 'Open'), MetaScalp, Editor and Terminal; replace four legacy feedback buttons, retain legacy review records. No Telegram Mini App now. Use the existing browser terminal in the interim. One-tap startup of HTTPS on a PC from Telegram requires an already running reachable gateway/agent and a stable URL; Telegram cannot wake a powered-off PC or start Vite/tunnel without such service. A production build with HTTPS is preferable to leaving dev Vite publicly exposed. If endpoint is unavailable, report unavailability without false success.

## 4. Suggested stages and provisional estimates

1. Finish and verify existing web TERMINAL + AUTOPILOT + EDITOR and geometry-feedback contract; keep independent MIRROR development isolated.
2. Android proof-of-concept using Capacitor and the shared frontend: **1–3 working days** for initial APK/UI, *contingent on development environment and dependencies*.
3. Mobile layout/gesture adaptation: **3–7 working days**, especially chart and touch interactions.
4. Independent phone→Bybit market/private API and order/protection reconciliation: **1–3 weeks**.
5. Security, device lifecycle, network failures, PAPER/sandbox verification and app packaging: **1–2 weeks**.
6. Overall **rough planning range 3–6 weeks** for a usable standalone manual trading Android terminal *after* the web UI is stable; not a committed delivery date, and potentially longer for Bybit API/environment or compliance blockers.
7. Remote AUTOPILOT bridge (PC first, VPS optional) is a separate delivery/acceptance scope. Fully device-local Python Scanner/Robot and attempted background execution is independent research with no credible fixed estimate before feasibility evidence.

## 5. Deferred decisions / acceptance boundaries

- Android package technology (Capacitor vs alternatives), supported Android versions/devices, app distribution and Bybit API transport compatibility.
- Mobile credentials/security: Android Keystore integration, biometric/lock-screen policy, permission scopes, loss/theft and revocation.
- How phone manual trades and Robot trades coexist (separate subaccounts vs ownership arbitration); STOP/TAKE conflict and reconciliation tests.
- Host remote contract, TLS/VPN/authentication, signal/trade/editor journal provenance and offline synchronization.
- Whether even limited background Scanner on Android is worth evaluating; do not claim reliable 24/7 from OS foreground-service experiments.
- No backend/API changes or MIRROR coordination work without the relevant owner-approved contract.

This is a **future architectural sketch**. It must not displace current accepted owner priorities or be mistaken for an implemented feature.
