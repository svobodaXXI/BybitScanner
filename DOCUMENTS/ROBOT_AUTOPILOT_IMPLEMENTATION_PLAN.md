# BybitScanner — Robot Autopilot Implementation Plan

Status: ACTIVE IMPLEMENTATION PLAN  
Owner direction: 2026-09-27  
Scope: autonomous PAPER candidate discovery, selection and admission using the existing Robot execution/protection lifecycle.  
LIVE trading: PROHIBITED.  
Authoritative prerequisite: PR #288 merged; current main at planning start: `6e865536cd1cd1a5cf7a7211576e1fe5d8b57be8`.

## 1. Product outcome

The target workflow is:

```text
market
→ autonomous discovery of ALL supported patterns
→ immutable/frozen candidate set
→ common eligibility + portfolio/risk gates per candidate
→ cross-candidate arbitration / trade priority
→ automatic canonical admission
→ existing Robot execution
→ existing protection / position / recovery lifecycle
→ durable outcome statistics
```

The owner should not need to press `🤖 Робот` for normal PAPER automation.
The manual button remains available as an explicit owner admission path and
must continue to use the same canonical admission contract.

Autopilot is an admission/discovery layer. It is NOT a second trading engine.

## 2. External architecture lessons adopted

The design follows three mature-engine patterns without copying their engines:

- Hummingbot V2: long-lived Controller decides what should be acted on; existing
  Executor-style machinery owns order lifecycle.
- QuantConnect LEAN Algorithm Framework: separate universe/discovery, signal,
  portfolio/risk, and execution responsibilities.
- Freqtrade: protections/cooldowns are separate admission guards rather than
  strategy-specific order code.

Project-specific conclusion:

> New code may decide WHICH frozen candidate is eligible and WHEN it may be
> admitted. Existing BybitScanner code remains the only authority for HOW the
> trade is executed, protected, reconciled and closed.

## 3. Reuse-first architecture

### 3.1 Existing components that remain authoritative

Do not replace or duplicate:

- Scanner analyzers and pattern detectors;
- `pattern_robot_integration.py` for Wedge/L-shape pre-admission capability;
- Ikigai Box immutable `BOX_PLAN_ONLY` preparation;
- `terminal.application.robot_admission.admit_robot_candidate()`;
- one-owner-per-symbol checks;
- `RobotBreakoutMonitor`;
- PAPER ActionExecutor / execution journal;
- owned LIMIT/Market mutation paths;
- STOP/TAKE protection;
- open-position/trade persistence;
- pause/resume/stop semantics;
- restart/reconciliation;
- Telegram position/lifecycle surfaces.

No discovery component may submit an order directly.

### 3.2 New components

#### RobotDiscoveryController

Responsibilities:

- walk the eligible symbol universe continuously while Autopilot is enabled;
- use the same source-time OHLC and pattern detectors as Scanner;
- process one symbol as 5m then 1m, running every integrated pattern on each;
- freeze only executable, decision-time-valid candidate evidence;
- emit candidate references to the admission layer;
- never submit/cancel/amend orders.

It must not grow a second detector implementation or a second Scanner.

#### RobotAutoAdmissionPolicy

Pure/read-only decision boundary returning a stable result such as:

```text
ALLOW
WAIT
REJECT
```

with machine-readable reason codes.

It evaluates only facts needed before canonical admission:

- Autopilot mode;
- Robot durable mode/recovery state;
- candidate integrity and executable capability;
- pattern-specific freshness/invalidation evidence;
- same-symbol ownership;
- protection/reconciliation health;
- explicit portfolio/risk budget;
- cooldown/protection guards;
- duplicate/idempotent admission state.

It must not alter the candidate or trading state.

#### CandidatePool / RobotCandidateArbiter

Discovery never stops because one supported pattern was already found.

For each decision cycle, preserve every independent executable candidate keyed
by `symbol × timeframe × pattern × formation`. A single market snapshot may
therefore legitimately produce, for example, both a Wedge and an Ikigai Box.

Presentation and trading selection are separate concerns:

- Scanner/Telegram shows every independently admitted pattern card;
- one pattern must never suppress another pattern's detection or delivery;
- Robot policy evaluates every frozen candidate independently;
- only AFTER that evaluation does `RobotCandidateArbiter` decide which
  eligible candidate(s) receive scarce trading capacity;
- losing arbitration never rewrites, deletes or hides the candidate.

For the same symbol, the existing one-owner-per-symbol rule means multiple
simultaneous eligible patterns compete for one trading owner unless that
ownership contract is deliberately changed later.

#### RobotAutoAdmissionController

Consumes the full frozen candidate set, policy decisions and arbitration result.

In `SHADOW`:
- records what would happen;
- never calls canonical admission.

In `PAPER_AUTO`:
- after an `ALLOW`, calls the SAME canonical admission function used by
  manual owner approval;
- treats rejection/conflict/ambiguity as fail-closed;
- never bypasses `admit_robot_candidate()`.

#### Decision audit

Prefer existing Scanner diary / Robot trade history for facts and outcomes.
Add only the smallest durable auto-decision ledger required to answer:

- what candidate was evaluated;
- which immutable snapshot/Box source it referred to;
- mode and policy version;
- ALLOW/WAIT/REJECT;
- stable reason code(s);
- evaluation/admission timestamp;
- resulting canonical candidate identity when admitted.

This is NOT a second execution journal.

## 4. Durable Autopilot modes

Autopilot state is independent from Robot runtime state.

Required modes:

### OFF

Default and startup-safe.

- no autonomous discovery/admission mutations;
- manual `🤖 Робот` remains available;
- existing open Robot trades continue normal protection/management.

### SHADOW

- autonomous discovery runs;
- the full admission policy runs;
- every decision is durably observable;
- no candidate crosses canonical admission automatically;
- no orders are created because of Autopilot.

This is the first production-observation mode.

### PAPER_AUTO

- PAPER only;
- autonomous `ALLOW` candidates may cross canonical admission;
- canonical Robot execution/protection then owns the trade;
- no LIVE account or mutation path is reachable.

Changing Autopilot to OFF must stop NEW automatic admissions only. It must
never abandon or force-close an already-open Robot position; existing
protection remains authoritative.

## 5. Candidate identity and pattern adapters

Autopilot does not invent one universal signal schema.

Each pattern keeps its current frozen source:

- Wedge: existing immutable Robot signal snapshot;
- L-shape: existing shared handoff snapshot and frozen terms;
- Ikigai Box CONFIRMED: immutable `BOX_PLAN_ONLY`;
- WATCH: observational only, never auto-admitted;
- future patterns: same Pattern → Robot adapter contract.

The auto layer operates on a small canonical reference:

```text
pattern
symbol
timeframe
source identity / candidate reference
snapshot hash or immutable identity
decision time
```

The full strategy facts stay in the pattern-owned snapshot/plan.

## 6. Discovery scheduling

Do not blindly rescan on a tight timer.

Required behavior:

1. maintain a closed-candle cursor per `symbol × timeframe`;
2. evaluate only when a new closed source candle can change the decision;
3. for each symbol: 5m ALL patterns → collect every result → 1m ALL patterns
   → collect every result → next symbol;
4. never short-circuit the remaining detectors because one pattern was found;
5. reuse one fetched candle snapshot across all compatible pattern detectors;
6. preserve independent `symbol × timeframe × pattern × formation` identity;
7. deliver/show every independently valid owner-visible pattern, even when
   another pattern on the same symbol/timeframe also exists;
8. on one pattern failure, record it and continue other patterns/symbols;
9. respect existing API/rate-limit/backoff infrastructure rather than adding a
   second uncontrolled request loop.

The final implementation may share a lower-level discovery function with the
manual Scanner, but Scanner Telegram delivery and Autopilot admission remain
separate consumers.

## 7. Admission invariants

Automatic admission is allowed only through the common Robot boundary.

Hard invariants:

- Robot must be exactly in the canonical entry-admitting state;
- ambiguity or reconciliation requirement blocks admission;
- a candidate must still be executable at evaluation time;
- same-symbol active exposure ownership remains exclusive;
- stale/invalidated setups are never revived;
- duplicate evaluation/admission is idempotent;
- discovery cannot mutate execution/protection;
- candidate order does not imply permission to trade;
- manual and automatic admission must converge to the same durable candidate
  and downstream lifecycle;
- switching Autopilot OFF/SHADOW never weakens protection for an existing trade;
- no LIVE mutations.

## 8. Portfolio and protection gates

Existing per-symbol ownership is necessary but not sufficient for unattended
trading.

Before `PAPER_AUTO` can be enabled for real PAPER orders, the following
portfolio policy values must be explicit and durable rather than invented by
implementation:

- maximum simultaneous Robot exposures;
- maximum aggregate engaged WV / reserved risk;
- maximum new admissions within the chosen decision window;
- cooldown after a STOP or other loss event;
- daily/session loss or drawdown guard, if enabled;
- any pattern-specific concurrency exclusions.

Default behavior for an unset required limit is fail-closed.

Do not infer a universal cross-pattern ranking from current Scanner scores.
Wedge, L-shape and Ikigai Box scores are not assumed comparable.

This does NOT mean "do not choose". It means the chooser must operate on
common, auditable trading facts rather than comparing unrelated raw pattern
scores. Detection/display remains complete; arbitration decides only which
eligible candidate gets trading capacity.

## 9. Candidate selection and ranking

### Initial version — deterministic multi-candidate arbitration

Do not build an ML system, but DO build an explicit deterministic arbiter.

The first version must:

- independently discover, freeze, display and evaluate EVERY supported pattern;
- never let Box/Wedge/L-shape suppress each other at discovery or Telegram
  presentation time;
- remove REJECT/WAIT candidates from the executable competition without hiding
  them from observation/audit;
- arbitrate only among candidates that individually reached `ALLOW`;
- rank using common trading/execution facts that are genuinely comparable
  across patterns, not their native Scanner scores.

Initial comparable inputs, where proven for every competing candidate:

1. executable-now / entry-readiness state;
2. normalized freshness relative to that pattern's own validity window;
3. net planned reward/risk after known fees/costs;
4. distance to invalidation / adverse entry distance;
5. required portfolio capacity / engaged WV;
6. liquidity/slippage evidence when the existing market-data path can prove it;
7. deterministic stable identity as the final tie-break only, never as a
   quality signal.

If a required common value cannot be proven, that candidate must not receive an
invented advantage. The arbiter must expose the missing-comparator reason.

Same-symbol collision rule for v0.1:
- show ALL valid pattern candidates to the owner;
- audit ALL of them;
- because Robot ownership is exclusive per symbol, admit at most one active
  candidate for that symbol;
- choose the highest-priority `ALLOW` candidate using the explicit common
  comparator above.

Across different symbols, portfolio capacity may admit more than one candidate
when the explicit global risk/concurrency budget permits it.

### Later evidence-based selector

After enough PAPER outcomes exist, build comparable statistics from actual
trades:

- net PnL after fees/costs;
- realized reward/risk;
- win/loss;
- MAE/MFE where reliably measurable;
- time from discovery → admission → fill → exit;
- pattern + source timeframe;
- rejection/expiry frequency.

Only then may a CandidateRanker use expected-value evidence. It must not be
trained/tuned against one anecdotal symbol or retrospective chart fit.

## 10. Notifications and owner control

Telegram remains the observation/control surface.

Required Autopilot owner controls eventually:

- current mode: OFF / SHADOW / PAPER_AUTO;
- change mode through one canonical control path;
- concise latest-decision status;
- explicit notification when an automatic candidate is admitted;
- bounded reason when a candidate is rejected by a material safety guard;
- existing position/open/close notifications unchanged.

Do not spam one message for every ordinary rejected universe item. Aggregate
routine shadow statistics; surface material failures and actual admissions.

Manual `🤖 Робот` remains valid while mode is OFF/SHADOW and must stay
idempotent with any already-linked candidate.

## 11. Implementation stages

### Stage A — Autopilot state + pure policy skeleton

Goal: "brain without hands".

Implement:

- durable OFF/SHADOW/PAPER_AUTO state, default OFF;
- policy result model with stable reason codes;
- read-only runtime/candidate/ownership/protection gates;
- minimal decision audit;
- no autonomous admission call yet.

Acceptance:
- restart preserves mode safely;
- OFF cannot mutate candidate/execution state;
- SHADOW decisions are deterministic and durable;
- LIVE remains unreachable.

### Stage B — Shared admission assessment

Goal: manual and automatic paths cannot disagree about basic candidate legality.

Refactor only as needed so the same read-only assessment supports:

- manual `🤖 Робот` admission;
- SHADOW "would admit" evaluation;
- future PAPER_AUTO admission.

Do not duplicate Wedge/L-shape/Box validation in Autopilot.

Acceptance:
- current manual admission behavior unchanged;
- SHADOW gives the same legality result without mutation;
- stale/invalid/duplicate/ownership conflicts have stable reasons.

### Stage C — Autonomous multi-pattern discovery

Goal: Robot finds the complete candidate set without owner input.

Implement `RobotDiscoveryController` using existing analyzers/detectors and
closed-candle cursors.

Start in SHADOW only.

Acceptance:
- no direct order calls exist from discovery;
- one found pattern never short-circuits another detector;
- Wedge + L-shape + Ikigai Box may coexist on one symbol/timeframe;
- all independently valid owner-visible patterns are shown/logged;
- no duplicate candidate per frozen formation identity;
- 5m all patterns → 1m all patterns per-symbol order preserved;
- WATCH never enters executable candidate flow;
- restart does not replay old formations as new opportunities.

### Stage D — arbitration + PAPER_AUTO canonical admission

Goal: remove owner tap while preserving the same execution boundary and
choosing among simultaneous eligible patterns.

Only after explicit portfolio/risk policy values are frozen:

- collect all `ALLOW` candidates for the decision cycle;
- run the deterministic `RobotCandidateArbiter`;
- for a same-symbol collision, select at most one winner under existing symbol
  ownership while keeping every losing pattern visible/auditable;
- selected candidate → canonical `admit_robot_candidate()`;
- downstream existing Robot monitor owns all order/protection mutations;
- idempotent retries never double-admit.

Acceptance:
- automatic admission creates the same durable lifecycle as manual approval;
- no alternate order path;
- pause/stop/reconciliation gates still dominate;
- OFF immediately prevents further new auto admissions.

### Stage E — portfolio protections

Add only evidence-backed guard implementations:

- concurrency budget;
- aggregate WV/risk budget;
- cooldown/lock state;
- optional loss/drawdown guard.

Reuse durable Robot trade outcomes and account state. Do not create a second
PnL authority.

### Stage F — operator UX / telemetry

- Telegram Autopilot mode control/status;
- summary of SHADOW decisions;
- auto-admission notification;
- clear blocker/reconciliation notifications;
- restart/status projection.

### Stage G — evidence-driven ranking

Deferred until PAPER history is sufficient.

No ranking work is required for initial autonomous execution.

## 12. Verification strategy

Developer checks:

- pure policy tests for every reason code;
- idempotency / duplicate candidate tests;
- manual-vs-auto admission equivalence tests;
- Box/Wedge/L-shape adapter conformance;
- restart persistence;
- OFF/SHADOW mutation-negative tests;
- PAPER_AUTO proves canonical admission call only;
- explicit LIVE-negative tests.

Do not rerun unchanged broad suites after every micro-slice. Follow the
project's bounded-test rule.

Real acceptance:

1. owner-run SHADOW period on the real discovery path;
2. inspect durable decisions versus delivered Scanner opportunities;
3. freeze missing portfolio/risk decisions;
4. enable PAPER_AUTO only after SHADOW evidence is acceptable;
5. perform owner-controlled PAPER acceptance with ordinary Telegram and current
   runtime safety gates;
6. LIVE remains out of scope.

Agents do not launch the real Scanner/Robot acceptance run.

## 13. Failure semantics

Fail closed on:

- unknown Robot/autopilot mode;
- stale candidate;
- unresolved reconciliation;
- unhealthy/unproven protection state where admission depends on it;
- ambiguous candidate/source identity;
- duplicate ownership;
- missing required risk budget;
- decision-log persistence failure when it would make unattended action
  unauditable;
- unavailable market/source-time evidence needed by the pattern.

A policy failure must not cancel/alter an existing protected position unless
the existing Robot safety lifecycle independently requires that action.

## 14. Definition of Done

Autopilot v0.1 PAPER is complete only when:

- Robot finds ALL supported pattern candidates without owner input;
- simultaneous Wedge/L-shape/Ikigai candidates are preserved independently and
  remain owner-visible;
- every auto candidate is a frozen immutable source;
- trade priority is chosen only after complete candidate collection and
  per-candidate policy evaluation;
- SHADOW and PAPER_AUTO use the same policy;
- automatic admission uses the same canonical boundary as manual approval;
- no discovery code submits orders directly;
- existing execution/protection/recovery owns every admitted trade;
- portfolio risk limits are explicit and fail-closed;
- OFF/SHADOW/PAPER_AUTO survive restart safely;
- decisions and outcomes are auditable;
- manual Robot controls still work;
- owner-run PAPER acceptance proves autonomous discovery → admission → entry →
  protection → close/reconcile;
- no LIVE mutation capability was introduced.

## 15. First implementation slice

Next code slice:

> Stage A — durable Autopilot state + pure SHADOW policy skeleton.

It must not change order execution, candidate admission, strategy parameters,
or LIVE behavior.

The first useful product result is a SHADOW report answering:

> "Which candidates would the Robot have admitted automatically, and exactly
> why were the others blocked?"

Only after that evidence exists do we connect the same ALLOW result to
canonical PAPER admission.
