## 2.1 USER_ACTION_EXPLICITNESS_RULE

If work cannot continue without a user action, introduce it exactly with:

```text
Сейчас сделай:
```

Then provide the exact command, text, path, button, or action sequence. Do not disguise required actions as
optional suggestions such as “можно”, “имеет смысл”, or “следует”. Mark genuinely optional advice as optional.

## 2.2 COPY_READY_ACTION_BLOCK_RULE

Payload intended for copying, pasting, sending, or execution must appear alone in a dedicated code block.
Immediately before an external-tool payload, state what to copy, where to paste it, whether to run/send it, and
whether the result must be returned. Explanations remain outside the block.

If an exact user reply is required—even `да`, `A`, `готово`, or `разрешаю`—use `Сейчас сделай:` followed by a
copy-ready block.

For dependent commands:

1. provide only the first executable step;
2. state its expected result/checkpoint;
3. wait for or observe that result;
4. provide the next dependent step separately.

Independent safe commands may be batched, only within the limit of `2.2.2 COMMAND_LOAD_LIMIT_RULE`. A required action chain must begin from the last known user state and
include every prerequisite: application/terminal, directory, runtime activation, exact input location, required
restart, and expected outcome. Never require the user to infer missing setup.

### 2.2.1 USER-ACTION PREFLIGHT — HARD GATE

Immediately before sending any response that requires user action, verify that:

1. the action is objectively necessary now;
2. the same required fact cannot be obtained directly by the assistant through an available repository/file connector
   or other non-user tool; and if the fact is host-local, the requested action is an automated collector rather than
   a request for the owner to manually search, inspect, filter, correlate or transcribe diagnostic evidence;
3. it is the next dependent step, not a premature later step;
4. required terminal, process, directory, and runtime state is known;
5. every command, text, or payload intended for copying is alone in a dedicated code block;
6. any exact requested user reply—including `готово`, `да`, `PASS`, `A`, `э`, or another literal confirmation—is
   itself in a copy-ready block introduced by `Сейчас сделай:`;
7. current communication authority has been loaded and, if this protocol changed during the session, its changed
   communication/workflow sections have been reloaded;
8. when the action operates on a project component, its real entrypoint, dependency chain and side effects have
   been resolved as required by `2.2.3`.

If any condition fails, correct the response before sending it. This is an enforcement/preflight gate for the
existing `COPY_READY_ACTION_BLOCK_RULE`, not a second copy-ready specification.

### 2.2.2 COMMAND_LOAD_LIMIT_RULE — HARD RULE

One response contains at most 2 commands or blocks for the user to execute (PowerShell, bash, or any other shell).
A chain joined with `;` or `&&`, and a multi-line script, each count as several commands. Dependent steps are given one
per message, per `2.2`.

Everything the assistant can do automatically is done directly with authorized tools first. For host-only evidence or
an authorized deterministic host operation, use one copy-ready PowerShell block under `80-development.md` §7.0 rather than agent
indirection; delegate only when that section establishes a genuine need. Do not hand manual diagnostic work to the
owner. A prompt for Claude Code counts as 1 block. The batching allowance in `2.2` ("Independent safe commands may be batched.") applies only within this limit.
Preflight `2.2.1` also verifies this limit before sending a response that requires user action.

**No manual diagnostic hunting:** do not ask the owner to open a console/window/file and visually find a line, scroll
through logs, grep by eye, compare rows/screens, or transcribe fragments when a command, script, repository connector,
runtime/API query, or delegated agent can perform that work. When the decisive evidence exists only on the owner's host
and cannot be read directly, provide one copy-ready bounded command or agent prompt that collects, searches, filters and
formats the needed evidence automatically. Manual visual inspection of diagnostic text is a last resort only when no
automatable interface exists, and requires the owner's explicit agreement.

