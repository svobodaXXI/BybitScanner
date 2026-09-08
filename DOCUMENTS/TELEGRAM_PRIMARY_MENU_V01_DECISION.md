# BybitScanner — Telegram Primary Menu v0.1 Decision

Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: DESIGN ONLY

## Purpose

Define the near-term Telegram scanner-bot primary navigation required for the PAPER Robot prototype and adjacent product surfaces.

## Accepted UI change

Replace the current single `Open Workspace` button with one compact menu button.

Opening that menu exposes exactly these near-term entries:

1. `Терминал`
   - This is the existing Workspace surface, renamed from user-facing `Workspace` to `Терминал`.
   - Reuse the existing Workspace/Terminal implementation; do not create a duplicate terminal surface.

2. `Робот`
   - Entry point for PAPER Robot v0.1 status, approval and lifecycle information.
   - Robot v0.1 remains Telegram-first; terminal frontend is not part of the prototype control surface.

3. `Запуск сканера`
   - Entry point for the existing scanner-start action/workflow.
   - Reuse the existing scanner launch capability; the menu must not create a second scanner-control implementation.

4. `Статистика`
   - Entry point for near-term trading/scanner/robot statistics.
   - The surface should consume authoritative existing telemetry/accounting data rather than own duplicate calculations.

## Architecture constraint

This menu is one navigation layer over existing and future authoritative capabilities. It does not own trading, scanning, statistics, robot state, or terminal state.

Apply the project-wide `Reuse Before Build + Single Authoritative Capability` rule:

- one capability -> one authoritative implementation/source;
- the Telegram menu routes to capabilities instead of reimplementing them;
- local presentation adapters/views are allowed, but they must not become a second source of truth;
- avoid extra subscriptions, duplicated calculations, duplicated lifecycle state and unnecessary frontend/runtime scope.

## Near-term scope discipline

For the upcoming PAPER Robot prototype, implement only the minimum menu/navigation work needed to expose `Робот` while preserving the other three entries as the agreed primary navigation structure.

Do not redesign the full Telegram UX, Terminal frontend, scanner engine or statistics subsystem merely to introduce this menu.

# END_OF_DOCUMENT
