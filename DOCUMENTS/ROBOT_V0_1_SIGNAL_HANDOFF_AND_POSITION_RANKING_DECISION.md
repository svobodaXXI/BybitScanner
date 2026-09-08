# Robot v0.1 Signal Handoff and Position Ranking Decision

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Accepted decisions

### Shared position ranking

The Robot `Все позиции` view reuses the previously designed common position-ranking semantics. It must not introduce a Robot-specific competing ranking engine.

The currently selected position is pinned first. Remaining positions are ordered using the shared ranking capability, where larger and more promising positions rank above lower-priority positions. Until the common ranking capability is implemented, Robot v0.1 may use only a minimal deterministic fallback ordering; that fallback is presentation behavior, not a second ranking model.

### Scanner-signal Robot action

Every eligible Scanner signal card exposes a `Робот` action beside the signal.

Pressing `Робот` is an execution-intent action, not merely navigation. It submits the exact existing Scanner signal identity/snapshot to Robot admission, equivalent to approving that signal for Robot observation/trading under the v0.1 policy.

The Robot must consume existing Scanner outputs and must not redetect the wedge, rebuild geometry, or independently recalculate pattern potential.

The handoff is idempotent for the same signal/active Robot idea.

### Availability gate

Before acknowledging acceptance, the Telegram control layer must perform a cheap Robot-runtime availability/admission check through one shared Robot gateway/health boundary.

If Robot is available and the candidate is admitted:
- acknowledge that the signal was accepted by Robot;
- create/transition the candidate to the existing approved/waiting-breakout lifecycle;
- show/open the Robot view for that candidate.

If Robot is unavailable or cannot safely accept the candidate:
- report `Робот недоступен` with the relevant safe reason when known;
- do not create a half-approved candidate and do not pretend the handoff succeeded.

Telegram remains a thin presentation/control layer. It does not own Robot state or market data.

### Runtime-location independence

Scanner signal cards and Telegram UI must not depend on whether Robot runtime is hosted on the user's PC or on a VPS. They address the shared Robot gateway/capability only.

For the fastest initial prototype, Robot may run on the same host/runtime boundary as the Scanner if that minimizes implementation work. Migration to an always-on VPS must not require changing signal, strategy, Telegram, or execution semantics.

Availability should be determined by a lightweight recent heartbeat/health/admission state. Do not create duplicate price polling, candle subscriptions, WebSocket feeds, Scanner processes, or PAPER state stores merely to determine Robot availability.

## Performance invariant

Robot v0.1 consumes existing Scanner signals, existing market/candle data paths, existing PAPER account/position state, and existing execution/protection capabilities. Runtime placement may change; authoritative capabilities do not duplicate.

# END_OF_DOCUMENT
