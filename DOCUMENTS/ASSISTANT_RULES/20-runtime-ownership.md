### Owner desktop launch surface — HARD UX CONTRACT (OWNER RULE 2026-09-27)

The owner's canonical manual runtime UX is the existing desktop shortcut surface.
Do not make the owner re-discover or re-explain this path in future sessions.

Current owner-facing surface (canonicalized 2026-09-28; do not rediscover):
- shortcut directory: `C:\\Users\\svobo\\OneDrive\\Рабочий стол`;
- `start_scanner.lnk` -> tracked `C:\\BybitScanner\\start_scanner.bat`, Start In `C:\\BybitScanner`;
- `Запуск робота.lnk` -> tracked `C:\\BybitScanner\\start_robot_runtime.bat`, Start In `C:\\BybitScanner`;
- `Остановить робота.lnk` -> tracked `C:\\BybitScanner\\stop_robot_runtime.bat`, Start In `C:\\BybitScanner`.

Current wiring contract:
- desktop shortcuts must target tracked canonical launchers directly; local/untracked `start_robot.bat` and `stop_robot.bat` are not runtime authority and must not sit in the owner-critical path;
- tracked `tools/sync_owner_shortcuts.ps1` repairs/verifies these three targets without renaming the owner-facing buttons;
- tracked `start_scanner.bat` delegates to tracked `start_robot_runtime.bat` and therefore reaches the canonical readiness/identity/protection/ScannerControlRuntime path;
- tracked `start_robot_runtime.bat` owns the one-action runtime-intent start path;
- tracked `stop_robot_runtime.bat` owns the canonical full safe-stop path through `python -m tools.stop_robot_runtime`;
- the previous local wrapper and `C:\\BybitScanner-box-robot-run\\start_robot_all.cmd` wiring are historical/legacy and are not owner desktop runtime authority.

Assistant obligations:

1. Treat these shortcuts as the stable owner-facing entrypoint. The user should continue
   launching Scanner/Robot manually from the desktop, not from assistant-provided terminal
   commands as the normal workflow.
2. When development changes canonical runtime scripts, startup composition, ownership,
   readiness gates, or acceptance behavior, update/retarget the implementation behind
   this desktop surface as part of the same task. New development must flow into this
   path automatically.
3. Do not repeatedly ask which launcher/shortcut the owner uses once this rule is loaded.
4. Do not invent a parallel owner launch path. If a migration is technically required,
   preserve compatibility or update the existing shortcuts and document the resulting
   target; do not leave the owner with multiple ambiguous launch methods.
5. Before declaring a runtime-related change complete, trace and verify that the desktop
   surface reaches the current canonical runtime path and preserves required safety,
   singleton, identity, admission and protection gates.
6. Agent ownership restriction remains unchanged: ChatGPT/Codex/Claude may inspect,
   repair or upgrade the shortcut path, but only the owner manually starts the real
   Scanner/Robot runtime.

Terminal commands are acceptable only for bounded diagnosis or a one-time repair when the
desktop path itself is broken or its local target must be established. Such diagnosis is
not a replacement owner workflow.

### Unified Signal / Robot integration — HARD UX CONTRACT (OWNER RULE 2026-09-27)

The owner operates all Scanner patterns through one Telegram/Robot product surface.
The canonical detailed standard is
`DOCUMENTS/PATTERN_ROBOT_INTEGRATION_STANDARD.md`.

Assistant obligations:

1. Treat Telegram signal shell, Robot candidate/admission, control menu,
   execution ownership, protection, position cards, lifecycle notifications,
   monitoring and reconciliation as shared platform behavior.
2. Do not implement a second per-pattern copy of those mechanisms.
3. `🤖 Робот` means admission of the exact durable candidate under that signal.
   It must never silently mean "show Robot status" for another pattern.
4. If a pattern is not Robot-capable, do not present a deceptive admission
   affordance; use the explicitly named common status surface instead.
5. A new pattern contributes a strategy adapter: its immutable evidence,
   direction, executability, entry/protection/exit/invalidation rules. Shared
   owner UX and safety remain common.
6. A common UX/control fix must be checked at the platform boundary and applied
   to every Robot-capable adapter, not re-fixed one pattern at a time.
7. The Telegram Menu button is a permanent owner control surface and must remain
   available after owner commands/callbacks; `/scanner` is the state-aware
   Pause/Resume/Start toggle.

### Game reward ledger — HARD PROCESS CONTRACT (OWNER RULE 2026-09-27)

`DOCUMENTS/QUEST_REWARD_LEDGER.md` is the canonical append-only authority for
XP, achievements and reusable loot. `QUEST_STATE.md` is its current projection.

When verified work changes game state, append the reward event and update
QUEST_STATE in the same Definition of Done before announcing the new total as
canonical. A conflicting number stated in chat triggers reconciliation; it is
not sufficient by itself to rewrite the scoreboard.

### Scanner runtime is owner-manual, never an agent job — OWNER RULE 2026-09-23

A real Scanner pass, especially the full eligible-universe Telegram acceptance
pass, is started **only manually by the owner**, through the verified existing
Scanner-only control path. ChatGPT/Codex/Claude Code must never start, resume,
restart, schedule or supervise the Scanner as a long-running agent task, nor
stay active waiting for the scan to finish. The user authorization to prepare
or accept a complete pass is not permission for an agent to launch it.

When a preflight needs host-local state, delegate a single bounded, read-only
inspection to Codex; require it to finish and return immediately with a short
report. Do not have Codex run the scan, continuously poll it, hold a terminal
open for it, or consume quotas during the user's manual run. After verified
preflight and safe entrypoint trace, provide the owner the minimal exact manual
launch step, only when they choose to launch. If an agent task may currently
be running, do not assume the agent process is the Scanner process or claim
that either has stopped. Identify the separate owners and any Robot/position
side effects before advising how to terminate the Scanner. No blind stop or
multi-service restart. This ownership restriction overrides any generic
"delegate actions to Codex" wording in this protocol.

