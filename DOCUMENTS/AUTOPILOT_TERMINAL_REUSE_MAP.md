# AUTOPILOT UI — mandatory reuse of Trading Workspace mechanisms

Date: 2026-10-19. Status: **OWNER DECISION / IMPLEMENTATION ROUTING**.
Scope: AUTOPILOT UI within the existing React/Vite Trading Workspace. This document does not authorize backend or execution mutations.

## Fundamental rule

**Do not reinvent what the Terminal already implements.** AUTOPILOT is a workspace mode and an operator view over shared, authoritative state. Its tab activation is navigation only; it must not arm the Robot, initiate a new Scanner run, alter ownership or submit trading orders.

## Reuse map (verified from branch UI-9 source)

| AUTOPILOT requirement | Existing terminal mechanism | Integration action |
| --- | --- | --- |
| All open positions, selection, existing close semantics | `terminal/frontend/src/components/OpenPositionsOverlay.tsx` used by `ModePanelLegacy.tsx` | Open/reuse the same overlay and account projection; do not build a second positions inventory or closing pipeline |
| Trading statistics and diary | `DiaryOverlay.tsx`, already reused by `AutopilotDiaryControls.tsx` | Keep one diary/analytics UI and canonical episode identity; avoid competing trade-detail implementations |
| Account identity/switching | `AccountMenu.tsx` and `accountWorkspaceStore` | Use existing active-account authority; avoid account-agnostic candidate/position mixing |
| STOP and TAKE controls | `StopSettings.tsx` and existing `ModePanelLegacy` control+mutation flow | Reuse ONLY when authorized for the current owner/mode; never duplicate STOP/TAKE commands in AUTOPILOT |
| Trading confirmations, close/reconciliation | Existing paper/live command controllers and workspace authority in `ModePanelLegacy.tsx` | No new execution pathway; use existing authorized control and recovery semantics |
| Chart, order book/DOM, signal overlay | Existing workspace chart/orderbook and frozen Scanner signal context per `AUTOPILOT_REUSE_TERMINAL_CHART_AND_SIGNAL_OVERLAY_DECISION.md` | Reconfigure existing surfaces for active signal, preserve source geometry; do not add new chart, DOM, drawing engine or reconstruct the pattern |
| Autopilot status | Existing `GET /api/robot/autopilot`, `GET /api/health` | Read and render; a tab click must never POST a mode change |
| Protection status | Existing `GET /api/robot/protection-health` and `GET /api/paper-state` | Show authoritative protection; unknown state must never imply confirmed STOP/TAKE |
| Robot/Scanner pause, stop, resume | Existing verified terminal/operator action handlers, if any | Locate and reuse existing handlers after authority review; **no new implementations or direct POSTs without contract agreement** |
| Candidates + ALLOW/WAIT/BLOCK and ingress | No authoritative frontend read schema confirmed in UI-5 | Resolve `AUTOPILOT_UI_MONITORING_READ_CONTRACT.md` with Robot/PAPER_AUTO owner before wiring |

## Current gap in UI-1..9

`AutopilotFirstScreen.tsx` loads `/api/open-positions`, `/api/paper-state`, and `/api/diary/trades` independently, and paints its own position cards. This is allowed as a **temporary read-only operational summary** but must NOT become a parallel positions workspace, separate order engine, or alternate authoritative store. UI-3 adds a lightweight trade-details dialog while `AutopilotDiaryControls` already opens the shared `DiaryOverlay`; converge the final detailed trade view on canonical episode/diary navigation rather than creating two permanent details systems.

## Safe next implementation

1. Audit existing `ModePanelLegacy` callbacks and `OpenPositionsOverlay` props to expose **the existing position selector/overlay** from AUTOPILOT, without fetching duplicate account inventory on navigation.
2. Route full trade drill-down through the existing `DiaryOverlay` when authoritative `tradeEpisodeId` is available; preserve explicit missing-source state otherwise. Do not guess episode identity from symbol alone.
3. Reuse terminal chart/DOM owner components with frozen scanner signal context. Do not duplicate presentation engines.
4. Reuse validated Robot/Scanner/Autopilot commands only after shared owner explicitly confirms interface and mutation authority. Navigation itself remains inert.

## Acceptance

A finished AUTOPILOT user flow must use the same position account authority, trade lifecycle, chart/DOM, diary and safety gates as Terminal. Tests must demonstrate navigation alone performs zero mutations, shared overlays work in both modes, and missing/ambiguous identity is fail-closed.

Related owner decisions: `DOCUMENTS/AUTOPILOT_FIRST_SCREEN_AND_TRADE_DETAILS_DECISION.md`, `DOCUMENTS/AUTOPILOT_TERMINAL_STATS_ENTRYPOINT_DECISION.md`, `DOCUMENTS/AUTOPILOT_REUSE_TERMINAL_CHART_AND_SIGNAL_OVERLAY_DECISION.md`, `DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md`.

Coordination: Codex owns MIRROR RETEST. No changes to Robot/Scanner/admission/protection/backend, PAPER DB, running runtime, LIVE, or stable merge.
