### 2.2.3 OPERATIONAL ENTRYPOINT TRACE — HARD RULE

If the task is SSH/VPN connectivity, first use the applicable device section
of `DOCUMENTS/WINDOWS_PC_VPS_ACCESS_RECOVERY_20261108.md`. If that resolves the
transport problem, return to the original task rather than continue diagnostics.
For any runtime/trading mutation, `20-runtime-ownership.md` remains applicable;
transport success is not permission to start, stop, deploy or trade.

Before asking the user to start, stop, restart, enable, configure, deploy, or synchronize a BybitScanner component,
resolve the smallest actual operational path **yourself**:

1. Identify the real entrypoint for the requested outcome (launcher, menu command, service, API or task). Read its
   current repository source and trace calls to other launchers, modules, environment/config loaders and relevant
   runtime owners until the processes started, configuration inheritance and material side effects are clear. Use
   the repository connector for committed sources; never ask the user to paste those files. A filename, remembered
   command or previous chat is not evidence of what the entrypoint currently does.
2. Separate repository facts from host reality. For current processes, unsaved edits, ignored local config,
   runtime state, installed services or network access, use existing local evidence; ask for only the specific
   missing host-local fact that cannot be obtained directly. Never request API keys, tokens or secret-bearing
   config contents. Do not infer the Windows or VPS state from the other host.
3. Check whether the path also starts unrelated components, sends Telegram messages, creates duplicate workers,
   changes Robot state, places orders or changes LIVE/PAPER boundaries. Distinguish launching a PAPER backend from
   enabling autonomous trading. Do not silently substitute a multi-component launcher for a scanner-only request;
   explain side effects and secure any necessary authorization before the launch.
4. Give the next safe actionable step only **after** the trace, reusing the project's existing control surface.
   If the path cannot be established, stop at the narrowest missing dependency rather than issuing exploratory
   commands one after another.

Apply the same task-scoped trace when recommending test/build commands (actual harness), Telegram signal enablement
(flag → consumer → sender), Trading Workspace access (frontend build → backend → tunnel), or Git/VPS synchronization
(branch → host → runtime). This rule requires no new skill, global inventory, full Project Sync or repeated checks
when the relevant trace has already been verified and its source/host state has not changed.


### 2.2.3A KNOWN-FAILURE FAST-PATH — HARD RULE

For Scanner / PAPER Robot / Telegram / desktop-runtime incidents, do not begin
as if the subsystem were unfamiliar. Before asking the owner for diagnostic
actions:

1. read `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md`;
2. read the current committed entrypoint/helper for the failing owner action;
3. match the symptom against documented failure signatures and canonical
   recovery routes;
4. use repository tools to recover everything that is not host-local;
5. if host evidence is still required, request one bounded automated read-only
   collector (ready command or delegated prompt) that searches/filters/parses the
   decisive facts for that class; never make the owner manually hunt through
   consoles, logs, files, database rows or process output;
6. use the documented recovery/repair path immediately when the signature
   matches; broaden investigation only when current evidence contradicts it.

A known/repeating incident should normally require no more than **one owner
diagnostic round-trip before the known repair/recovery action**. More steps are
allowed only when a concrete new unknown blocks the fast path; name that unknown
before requesting another owner action.

Never hand-edit durable Robot/Scanner state merely to clear an error. Prefer
the canonical state-machine/API recovery transition already implemented by the
project. After resolving a new repeatable failure, add only its stable
`symptom -> decisive evidence -> canonical action` path to the fast-path
document so future sessions do not rediscover it.

This rule implements the project's primary efficiency objective: owner time is
the scarcest resource. It overrides exploratory one-command-at-a-time diagnosis
when a documented known path already exists, while preserving fail-closed
safety and the user-action preflight.

### 2.2.4 MULTI-COMPONENT READINESS CLAIM GATE — HARD RULE

When the owner asks whether a multi-component BybitScanner outcome is fully
working, ready, complete, or safe to launch, the assistant must not answer
"yes" from partial component evidence. First resolve the complete capability
chain required by that exact outcome and prove every currently material link.

For a real Scanner + PAPER Robot + Telegram interactive run, the minimum
readiness set is:

- the PAPER backend is alive on the intended endpoint and uses the intended
  database/runtime root;
- Robot durable state is appropriate for the requested action, and protection
  coverage is healthy when exposure exists;
- exactly one Telegram update consumer owns the bot callback stream, is
  actually running/ready, and uses the same runtime root/database/backend
  authority as the Robot;
- actionable Telegram buttons have a live callback consumer; the continued
  presence of old buttons or menu entries in Telegram is not evidence that
  the consumer is alive;
- Scanner is started through the one authoritative runtime owner expected by
  the controls. A standalone `main.py` Scanner and backend
  `ScannerControlRuntime` must never be treated as one Scanner or allowed to
  run concurrently for the same acceptance run;
- Scanner pause/continue cursor is in-memory, not restart-durable. A freshly
  constructed backend must recover any persisted stale `SCANNER_RUNNING` or
  `SCANNER_PAUSED` to `SCANNER_STOPPED` before owner lifecycle commands;
  it must never claim to resume a cursor that was lost with the old process.
  On an already-live backend, startup/control routing uses authoritative state:
  `SCANNER_STOPPED -> start`, `SCANNER_PAUSED -> resume`,
  `SCANNER_RUNNING -> reuse/no mutation`; unknown/unavailable state fails
  closed before Scanner mutation;
- the launch path has duplicate-worker prevention and does not create a second
  backend, Telegram poller, Scanner owner, or conflicting runtime checkout;
- production acceptance configuration is proven: ordinary Telegram mode,
  full eligible universe (no accidental symbol cap), required pattern flags,
  and the expected timeframe coverage;
- PAPER/LIVE boundaries are explicit and LIVE mutation gates remain disabled
  unless separately authorized.

A process existing, a port listening, a health endpoint returning liveness, a
durable state row, or a Telegram button being visible proves only that narrow
fact. None may be promoted to a full-readiness claim by inference.

If any required link is unknown or not ready, say that the full outcome is
not yet proven and name the exact missing link. Do not ask the owner to begin
a long acceptance run until this gate passes. Reuse already-proven unchanged
evidence; this rule is a completeness gate, not permission for repetitive
checks.

