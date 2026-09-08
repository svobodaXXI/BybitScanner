# BybitScanner — Future Standalone Android Trading Terminal Project

Version: 1.0
Date: 2026-09-08
Status: FUTURE PROJECT / RESEARCHED DESIGN DIRECTION
Implementation authorization: NONE
Scope: Manual trading terminal only; standalone Android APK; no Robot runtime scope implied.

Purpose: preserve the current research and architecture direction for a future fully autonomous Android trading terminal that can trade directly from the phone without depending on the VPS, PC, Telegram Mini App, or browser runtime.

---

# 1. TARGET OUTCOME

The long-term target is a **true standalone Android APK** for manual trading.

Target runtime topology:

```text
Android phone
    -> Bybit REST / WebSocket
```

The APK must remain capable of manual trading when the VPS and development PC are unavailable.

This is intentionally different from a Telegram Mini App or remote web client:

```text
Telegram / Web client
    -> VPS authoritative backend
    -> Bybit
```

The Telegram path may remain useful as a separate client, but it does not satisfy the standalone target.

---

# 2. RECOMMENDED TECHNOLOGY DIRECTION

Recommended baseline:

- Android-native application;
- Kotlin;
- Jetpack Compose for UI;
- Kotlin Coroutines / Flow for asynchronous state propagation;
- platform-native Android lifecycle, connectivity, notifications and secure storage integration;
- shared/reusable provider-neutral trading core instead of a second independently implemented trading engine;
- Kotlin Multiplatform (KMP) considered the preferred mechanism for shared portable business/domain logic where it creates real reuse value.

The preferred model is:

```text
ANDROID PLATFORM SHELL
  - Jetpack Compose UI
  - Android lifecycle
  - Android Keystore
  - connectivity monitoring
  - notifications
  - local persistence adapters
  - process/restart integration

SHARED / PORTABLE TRADING CORE
  - trading intents
  - sizing semantics
  - validation
  - price/quantity normalization contracts
  - order lifecycle state machines
  - position/protection state machines
  - idempotency
  - stale-response fencing
  - reconciliation decisions
  - accounting semantics
  - ownership / controller semantics

ANDROID EXECUTION ADAPTERS
  - Bybit REST
  - Bybit WebSocket
  - local database / persistence
  - secure credential access
  - clock / connectivity / notification adapters
```

The Android application is therefore another host for the same trading semantics, not a separately invented product-specific execution engine.

---

# 3. WHY KOTLIN-NATIVE + SHARED CORE

## 3.1 Native Android advantages

Android's official architecture guidance recommends clear UI/data/domain boundaries, single-source-of-truth ownership and unidirectional data flow. Jetpack Compose is the recommended modern Android UI toolkit.

This maps well to BybitScanner requirements because trading correctness depends on explicit ownership of position/order/protection state and predictable mutation flow.

Native Kotlin also removes an unnecessary runtime bridge around the highest-risk parts of the terminal: execution lifecycle, reconnect, reconciliation, process death, secure secrets and Android lifecycle.

## 3.2 Kotlin Multiplatform value

KMP supports gradual sharing of common business logic while retaining platform-specific integrations. It can share isolated logic modules, networking/data logic or the majority of business logic without requiring the UI to be shared.

For BybitScanner this allows a future structure such as:

```text
shared/core
  - models
  - validation
  - lifecycle rules
  - sizing semantics
  - reconciliation decisions
  - provider-neutral command contracts

platform hosts
  - current server/runtime host
  - Android standalone host
  - possible future desktop/iOS host
```

KMP is not required merely for fashion or code-count reduction. It should be used only where it actually prevents duplicated business authority.

---

# 4. ALTERNATIVES CONSIDERED

## 4.1 WebView wrapper around the current React terminal

Advantages:
- fastest path to familiar UI;
- high reuse of current React presentation code.

Disadvantages:
- poor foundation for a truly standalone safety-critical trading runtime;
- Android lifecycle/process death/security boundaries remain awkward;
- risks coupling execution to a web shell;
- does not solve the need for a durable native runtime.

Conclusion: suitable only for a lightweight client/prototype, not the preferred final standalone architecture.

## 4.2 Flutter

Advantages:
- fast cross-platform UI development;
- good mobile UI tooling.

Disadvantages for this project:
- platform-specific integrations use an asynchronous Dart <-> host platform channel boundary;
- additional runtime boundary around secure storage, lifecycle and native integrations;
- little strategic benefit because the primary target is Android and existing trading semantics are more important than shared UI.

Conclusion: viable general mobile technology, but not preferred for this terminal.

## 4.3 React Native

Advantages:
- familiar JavaScript/React development model;
- potentially faster UI development.

Disadvantages:
- JS/native boundary around platform-sensitive behavior;
- current React browser UI cannot simply be treated as the future authoritative mobile trading runtime;
- introduces another abstraction layer where native lifecycle/reconciliation behavior matters.

Conclusion: not preferred for the standalone execution terminal.

## 4.4 Full Kotlin rewrite of all trading logic

Advantages:
- simple language/platform story after completion.

Disadvantages:
- highest duplication risk;
- recreates already-proven execution, sizing, protection, reconciliation and accounting semantics;
- creates a second trading engine unless carefully migrated;
- expensive to verify and dangerous for parity.

Conclusion: explicitly not recommended.

---

# 5. REUSE-FIRST ARCHITECTURAL REQUIREMENT

This future project is governed by `DOCUMENTS/ARCHITECTURE_REUSE_FIRST_PRINCIPLE.md`.

The Android project must begin with an **extraction/reuse audit**, not a rewrite.

Before implementation, classify existing terminal capabilities into:

## Portable / domain candidates

Examples:
- order intent models;
- sizing rules;
- validation;
- ownership rules;
- protection semantics;
- state-machine transitions;
- idempotency semantics;
- ambiguous-result handling;
- stale-response/session/generation fencing;
- reconciliation decision rules;
- price/quantity normalization policy;
- accounting definitions.

## Platform/runtime adapters

Examples:
- Bybit REST transport;
- Bybit WebSocket transport;
- secure credential storage;
- Android persistence;
- lifecycle/process death handling;
- connectivity monitoring;
- notifications;
- UI rendering.

The goal is semantic reuse and single ownership, not forcing every implementation into one language or one giant module.

---

# 6. STANDALONE RUNTIME CAPABILITIES REQUIRED

A production standalone APK must contain or host the following capabilities locally:

- Bybit REST connectivity;
- Bybit public/private WebSocket connectivity;
- market-data state;
- active-account/session state;
- secure credentials;
- authoritative local execution orchestration;
- working-volume / sizing integration;
- Market order lifecycle;
- Limit create/amend/cancel lifecycle;
- STOP / TAKE protection lifecycle;
- full-close lifecycle;
- position and order reconciliation;
- durable persistence;
- restart/process-death recovery;
- duplicate prevention and stable client action identity;
- stale-response fencing;
- fail-closed `UNKNOWN` / `RECONCILING` behavior;
- logs/diagnostics;
- chart/DOM/manual trading UI.

The APK must not rely on an always-on VPS to perform any of the above for ordinary manual trading.

---

# 7. SECURITY DIRECTION

Android Keystore should be the basis for protecting cryptographic material used to encrypt or authorize access to locally stored Bybit credentials.

Important security direction:

- do not store plaintext API secrets in ordinary preferences/files;
- use Android Keystore-backed key material;
- prefer hardware-backed/StrongBox support where available and appropriate;
- consider optional user-authentication gating for sensitive credential use;
- keep application logs free of secrets;
- scope Bybit API credentials to the minimum permissions needed;
- do not require withdrawal permission for the terminal;
- define secure credential migration/revocation behavior before LIVE release.

Keystore protects key material from export, but it is not by itself a complete credential-security design. Threat modelling is required before production LIVE use.

---

# 8. ANDROID BACKGROUND-RUNTIME CONSTRAINT

Android must not be treated as a traditional always-on server OS.

Modern Android places significant restrictions on background work and foreground-service startup. The operating system may stop application processes, and user/device battery restrictions may prevent background work.

Therefore the manual terminal architecture must assume:

```text
APP ACTIVE
  -> streams active
  -> trading UI READY

APP PROCESS DIES / APP RETURNS
  -> recover durable local state
  -> obtain authoritative exchange snapshots
  -> reconnect streams
  -> reconcile
  -> only then READY
```

The application must never assume that in-memory state survived.

For manual trading, this is acceptable because the app need not behave as a 24/7 autonomous robot.

A future autonomous robot has different availability requirements and is not automatically authorized to run only on Android.

---

# 9. PROTECTION ORDERS AND PHONE AVAILABILITY

A critical design requirement is that LIVE STOP/TAKE protection should, wherever supported by the authoritative execution architecture, exist exchange-side rather than depend on an Android process remaining alive.

The safety target is:

```text
phone process killed / network lost / screen off
    !=
position loses exchange-side protection
```

Local Android runtime owns orchestration and reconciliation, but protection should not require a continuously running client process after authoritative exchange acceptance.

This must be validated against the exact Bybit order/protection semantics in force at implementation time.

---

# 10. PROPOSED DELIVERY MODEL

Do not build the standalone APK in one monolithic pass.

Recommended project structure is approximately five large phases with smaller bounded slices inside them.

## Phase A — Portable trading-core boundary

Goals:
- audit current terminal architecture;
- identify reusable provider-neutral semantics;
- define portable/shared module boundaries;
- prohibit duplicated execution/state ownership;
- build parity tests around extracted semantics.

This is the most important architectural phase.

## Phase B — Standalone Android read-only runtime

Goals:
- Android project foundation;
- secure credential storage;
- Bybit connectivity;
- public/private market/account streams;
- account/position/order read state;
- local persistence;
- process death/restart recovery;
- read-only reconciliation;
- chart foundation.

No trading mutation should be enabled merely because read-only data is visible.

## Phase C — PAPER execution parity

Goals:
- Market;
- Limit create/amend/cancel;
- STOP/TAKE;
- full close;
- common sizing;
- ownership/state transitions;
- reconnect and ambiguous-result handling;
- real-device PAPER acceptance.

## Phase D — LIVE manual execution

Enable mutation paths incrementally, one proven lifecycle at a time:

1. LIVE read-only parity;
2. Market;
3. Limit create;
4. Limit amend/cancel;
5. STOP/TAKE;
6. full close;
7. restart/reconciliation acceptance.

Each path remains fail-closed until its required validation and real-device acceptance are complete.

## Phase E — Mobile UX and production hardening

Goals:
- full chart/DOM/tape interaction;
- touch/hold gestures;
- collapsible mobile layout;
- notifications;
- account switching;
- connectivity UX;
- diagnostics;
- process-death tests;
- battery/background behavior tests;
- release signing/update strategy;
- production real-phone acceptance.

---

# 11. ROUGH EFFORT ESTIMATE

These are planning estimates, not delivery commitments.

Assumption: active development several hours on most days, with AI-assisted engineering, and significant reuse of existing project semantics.

## Recommended Kotlin + Compose + shared core

- first useful standalone PAPER version: approximately **3–5 weeks**;
- hardened standalone LIVE manual terminal: approximately **6–10 weeks** total.

A realistic planning target is roughly **two months** for a trustworthy first standalone LIVE manual terminal, assuming no major architectural blocker.

## Comparison estimates

| Approach | Standalone PAPER | Usable LIVE manual | Assessment |
| --- | ---: | ---: | --- |
| WebView/React wrapper | ~1–2 weeks | ~4–6 weeks | Fast start, weak final standalone architecture |
| Flutter / React Native | ~2–4 weeks | ~5–8 weeks | Medium start, extra runtime/platform boundary |
| Kotlin + Compose + shared core | ~3–5 weeks | ~6–10 weeks | Recommended |
| Full Kotlin rewrite of trading logic | ~5–8 weeks | ~10–16+ weeks | Not recommended |

The native/shared-core option is therefore "more expensive at the start" primarily in engineering effort: roughly **1–2 additional weeks** of architectural/core/platform work before the first impressive UI result, or approximately **30–60% more early-stage effort** than a thin web/cross-platform shell.

The expected return is lower duplication, lower long-term migration cost and safer LIVE execution/reconciliation.

---

# 12. APPROXIMATE WORK DISTRIBUTION

Planning estimate only:

- UI / Compose: 25–30%;
- Bybit REST/WebSocket + Android platform plumbing: ~20%;
- shared core/domain extraction: 20–25%;
- persistence/recovery/reconciliation: 15–20%;
- testing + real-phone LIVE acceptance: 15–20%.

The dominant risk is not visual UI implementation. It is preserving the already-developed trading correctness model during migration to a second host platform.

---

# 13. TELEGRAM MINI APP RELATIONSHIP

A Telegram Mini App is materially easier because the existing React terminal can be reused as a web client and the VPS can remain the authoritative backend.

Expected rough planning range:

- basic existing terminal in Telegram: 2–4 days;
- useful Telegram/PAPER terminal: around 1–3 weeks;
- hardened LIVE Mini App: around 3–5 weeks.

However, it remains a remote client and therefore does **not** replace this standalone Android project.

A useful sequencing option is:

```text
existing React terminal
    -> Telegram Mini App / mobile web UX validation
    -> standalone Android terminal
```

Mobile UX findings from Telegram can inform Android, but no Telegram-specific trading authority should be introduced.

---

# 14. FAILURE / SAFETY PRINCIPLES

The future Android implementation must preserve current BybitScanner safety principles, including where applicable:

- no blind retry of ambiguous mutations;
- durable client action identity;
- single-attempt ownership;
- reconciliation before re-enabling mutation after ambiguity;
- account/session/generation fencing;
- stale-response fencing;
- no duplicate order lifecycle owner;
- confirmed FLAT before claiming a full close is complete;
- shared STOP/TAKE sizing semantics;
- explicit PAPER/LIVE separation;
- fail-closed degraded states;
- no automatic conversion of uncertain state into optimistic UI truth.

Mobile convenience must not weaken these guarantees.

---

# 15. OPEN QUESTIONS FOR FUTURE PROJECT START

These are intentionally deferred until the Android project is activated:

- exact portable-core technology boundary: pure Kotlin/KMP versus FFI/shared-schema alternatives;
- exact existing Python/TypeScript capabilities to migrate, wrap or leave host-specific;
- Android minimum/target SDK at project start;
- database choice and exact durable event/projection schema;
- credential encryption/authentication UX;
- chart implementation strategy and reuse boundary;
- DOM rendering/performance architecture;
- offline market-data presentation semantics;
- release/distribution path (private APK, internal testing, Play distribution, etc.);
- optional VPS telemetry/synchronization architecture;
- future iOS requirement, if any.

These are not reasons to redesign the current terminal now.

---

# 16. EXTERNAL RESEARCH REFERENCES

Official sources consulted for this design direction:

- Android application architecture and Single Source of Truth / UDF:
  - https://developer.android.com/topic/architecture
  - https://developer.android.com/topic/architecture/recommendations
  - https://developer.android.com/topic/architecture/data-layer

- Android Keystore security model:
  - https://developer.android.com/privacy-and-security/keystore

- Android foreground/background execution restrictions:
  - https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
  - https://developer.android.com/develop/background-work/services/fgs/launch
  - https://developer.android.com/topic/performance/background-optimization

- Kotlin Multiplatform shared-business-logic model and project structure:
  - https://kotlinlang.org/docs/multiplatform/kmp-overview.html
  - https://kotlinlang.org/docs/multiplatform-share-on-platforms.html
  - https://kotlinlang.org/docs/multiplatform/multiplatform-project-recommended-structure.html

- Flutter native integration/platform-channel model used in the alternatives comparison:
  - https://docs.flutter.dev/platform-integration/platform-channels

These references must be rechecked at implementation time because Android, Bybit and Kotlin platform constraints evolve.

---

# 17. CURRENT DECISION SUMMARY

Current preferred future direction:

```text
Standalone manual Android terminal
= Kotlin-native Android shell
+ Jetpack Compose UI
+ reusable/shared provider-neutral trading core
+ Android-specific Bybit/security/persistence/lifecycle adapters
```

Not preferred:

```text
second independently rewritten trading engine
```

This document records a future project direction only. It does not change current Robot v0.1 priorities, does not authorize Android implementation, and does not authorize new LIVE trading mutations.

# END_OF_DOCUMENT
