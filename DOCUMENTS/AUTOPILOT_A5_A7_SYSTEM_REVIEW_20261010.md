# Autopilot A5–A7 — system review and optimized delivery plan (2026-10-10)

Status: **REVIEW PROPOSAL, not implementation authorization**. Owning baseline: `DOCUMENTS/ROBOT_AUTOPILOT_IMPLEMENTATION_PLAN.md`; authoritative project safety and backlog take precedence. Source line: `stable/adfb50b-forward@7199ed48`; S2 proposed in PR #457 `6b76a739`, **OPEN/not merged** at review time. PAPER_AUTO remains OFF/unavailable. No LIVE work.

## 1. Outcome and architectural decision

Deliver **one** automated PAPER candidate → canonical Robot admission → existing protected execution → close/reconcile flow, without a second executor, scanner, portfolio ledger, or monitor. Reuse immutable source-time Scanner/Box candidates, `RobotAutoAdmissionPolicy`, `admit_robot_candidate`, the existing Robot lifecycle and A3 portfolio transaction. Do not merge main indiscriminately into stable.

The external comparison confirms, rather than replaces, the current separation:
- [Hummingbot V2 controllers/executors](https://hummingbot.org/strategies/v2-strategies/controllers/): controller makes decisions, existing executor owns order lifecycle. **Adopt principle; do not add Hummingbot-like infrastructure**.
- [QuantConnect LEAN Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview): universe/alpha → portfolio/risk → execution. **Keep risk assessment before canonical admission, avoid cross-pattern score comparability**.
- [Freqtrade protections](https://www.freqtrade.io/en/stable/plugins/): cooldown, StoplossGuard and drawdown lockouts. **Defer unapproved thresholds and policies; if adopted, implement as entry-only durable gates, never disable protection of existing positions**.
- [NautilusTrader execution reconciliation](https://nautilustrader.io/docs/latest/concepts/execution/reconciliation/): explicit authoritative position/order reports; missing report does not establish flatness; duplicate/replayed identities are deterministic. **Reuse existing reconciliation and durable source identities; unresolved or unknown state blocks new admission**.

These are architectural precedents, NOT test evidence of safety in BybitScanner.

## 2. Evidence and open gaps

**Known existing:** A3 SHADOW virtual capital: 5000 USDT, RO=250, cap=19, first eligible, append-only audit and atomic reservations; S1 #447 merged in stable but real loaded STOP timeliness not accepted. S2 #448 PR #457 introduces a 60 s recent ingress health gate; zero samples: flat/no armed coverage may be healthy, covered/armed symbols with zero samples are UNKNOWN. S2 thresholds (queue/processing <=2000ms, backlog <50%) remain *provisional* until evidence; no real backend validation.

**Still missing/unknown:** S3 PAPER_AUTO admission bridge; actual transactional revalidation at the mutation boundary; symbol and physical/virtual capital identity transitions; bounded WAIT replay and candidate expiry; per-candidate book/source freshness at admission; durable manual/auto race behavior; real end-to-end loaded PAPER acceptance. A3 source-only virtual reservation release remains deferred and can conservatively hold the 19 RO limit. No baseline evidence for tuning S2 latency cutoffs.

Do NOT interpret read-only SHADOW ALLOW, CI PASS or a quiet ingress snapshot as permission to send a real order.

## 3. Minimal dependency-ordered implementation

### Gate 0 — settle S2 (PR #457, separate owner merge)

Review latest PR head and targeted evidence for idle/covered zero samples, UNKNOWN propagation, overloaded burst, and existing-position protection. Do not make zero samples universally unhealthy: first admission from flat must not deadlock. Keep cutoffs conservative and explicit as provisional; revisit with real SHADOW distributions. Owner alone merges. No runtime started by agents.

### Gate 1 — S3 narrow PAPER_AUTO admission bridge (first code slice)

Use the existing canonical admission endpoint/function and Robot owner thread. On *each* prospective physical admission, re-read the candidate snapshot/identity and source-time validity, canonical Robot READY/reconciliation, symbol ownership/working orders, coverage/ingress health, Autopilot mode and A3 portfolio availability **at the final mutation boundary**. SHADOW read-only ALLOW is advisory and can become WAIT/REJECT by the time of admission.

Perform a **single atomic claim/check/reservation linked to canonical identity**, reusing the existing SQLite transaction/unique constraints and Robot admission operation rather than adding a second queue or journal. Define transaction ordering and locking from actual code before patching. If a final external market preflight cannot share the DB transaction, revalidate immediately after it and before mutation; on uncertainty return WAIT and do not send orders. Never hold a DB lock during network calls. Preserve 1 RO per logical idea across its multiple Box slots; replace SHADOW virtual reserve with physical claim without double counting. Reject manual/auto races and ambiguous in-flight/unfinished submissions fail-closed. No auto-LIVE route.

**Proof:** two concurrent identities competing for the last RO cannot both enter; manual/auto same candidate race yields at most one durable admission; OFF/reconciliation change between evaluation and commit blocks new admission; no order on failed check; already-open protection still executes.

### Gate 2 — bounded retry of WAIT, no new scheduler

Reuse the already-existing decision / closed-candle / owner-task progression if capable. Persist/derive one stable candidate key (source ID, snapshot hash, pattern, symbol, TF). Reevaluate WAIT only on relevant state change or next closed candle, with finite retry budget and age/decision-time invalidation; no tight polling, duplicates, or automatic resurrection of expired candidates. UNKNOWN remains WAIT, not implicit ALLOW. Ensure admission is idempotent through restart and mode OFF→SHADOW→PAPER_AUTO.

**Proof:** WAIT can become ALLOW only on fresh data and passes Gate 1 again; retries stop on expiry; restart doesn't double-admit.

### Gate 3 — evidence-based SHADOW→PAPER acceptance

First run normal owner-controlled SHADOW and gather actual distributions of protection ingress latencies, zero-sample windows, candidate freshness and WAIT reasons. Keep the current S2 limits unless evidence supports a narrow change; do not loosen mandatory protection gates merely to increase throughput. Verify source-time candidates and reserve accounting (virtual A3 reservations may remain until durable terminal proof). Then explicitly authorize PAPER_AUTO and perform owner-run, end-to-end PAPER discovery→admission→fill→STOP/TAKE→close/reconcile under multi-symbol load with Telegram; confirm real STOP timeliness (#447), no ingress overflow, no repeated or orphan orders, correct accounting, restart recovery. CI/replay alone never closes this gate.

## 4. Explicit deferrals / guardrails

- Do not invent ML ranking, cross-pattern score weights, secondary execution engine, new polling daemon, shadow PnL authority, correlation/cluster/daily-loss policy, or new health-monitor subsystem.
- Candidate-specific book freshness needs an authoritative existing source before auto-admission; where unavailable, WAIT. Do not infer freshness from ingress quietness, wall-clock alone, or old chart snapshots.
- Provisional 2s/50%/60s cutoffs require data; they are NOT approved trading performance parameters.
- No automatic merge, no LIVE, no edits to working PAPER DB, no agent runtime launch.
- Preserve manual controls and ongoing position protection when Autopilot is OFF or unhealthy.
- Laptop handoff follows existing reference-first migration rules: compare tracked HEAD, relevant local launchers/shortcuts/environment, runtime STOPPED identity and DB migration/backup evidence; preserve laptop dirty worktrees #396/#397 until classified; do not infer operational parity from Git sync.

## 5. Minimal next steps and acceptance ledger

1. Review PR #457 and request owner merge only after S2 pre-merge review. **Current: OPEN**.
2. Implement Gate 1 as one narrow S3 PR with targeted concurrency/negative tests. **Not started**.
3. Implement Gate 2 only if the existing controller cannot deliver bounded WAIT resumption. **Not started**.
4. Capture owner SHADOW and PAPER results; only real evidence closes #447 and PAPER_AUTO acceptance. **Pending**.
5. Switch to laptop using reference-first diff and repair only proven mismatches. **Blocked on laptop-specific evidence**, not on PC↔GitHub: PC sync PASS.

No XP/achievement awarded for this documentation or proposal.
