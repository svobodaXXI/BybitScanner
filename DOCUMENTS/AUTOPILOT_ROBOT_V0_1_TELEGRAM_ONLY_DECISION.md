# BybitScanner — Robot v0.1 Telegram-Only Surface Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Decision

Robot v0.1 does not use Trading Workspace / Terminal UI as an operating surface.

The only user-facing control and observation surface for the prototype is the existing Telegram scanner bot through a `Робот` menu entry / section.

All Robot v0.1 user-visible lifecycle information is delivered there, including:

- candidate signal cards;
- `Взять в работу` / `Пропустить` approval actions;
- candidate and trade statuses;
- entry notification;
- symbol, pattern, timeframe, side and volume;
- actual entry, STOP and TAKE;
- chart image with pattern geometry, entry, STOP and TAKE overlays;
- close notification and exit reason;
- gross/net PnL in USDT and percent;
- fees and funding when available from the shared accounting/runtime source;
- blocked, expired, rejected and error statuses.

## Ownership / manual intervention boundary

The previously accepted ownership-transfer concept remains part of the future architecture, but Robot v0.1 does not implement terminal-based `Взять управление` handoff because the Terminal is outside prototype UI scope.

For this prototype, robot-controlled PAPER positions are observed and managed through Telegram-only robot controls and the existing common PAPER execution/protection lifecycle. No new terminal frontend work is required for Robot v0.1.

## Reuse invariant

Telegram presentation is a consumer of shared robot events and existing scanner/chart/runtime/accounting capabilities. It must not become a second source of trade state, order state, PnL, geometry, market data or execution truth.

Robot v0.1 must not duplicate Trading Workspace components merely to support Telegram. Any adapter or Telegram-specific formatter remains a thin presentation layer over authoritative shared sources.

# END_OF_DOCUMENT
