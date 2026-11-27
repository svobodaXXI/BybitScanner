### 2.2.5 CLICKABLE_REPLY_OPTIONS_RULE — OWNER STANDARD 2026-10-12

When the owner must choose an action or report a short result (a decision between
defined options, `да`/`нет`, `готово`/`не получилось`, PASS/FAIL of a simple
observation), offer ready clickable answer options in the interface instead of asking
for manual typing. Each option is one concrete, self-contained reply with its
consequence evident from its label; the free-text path always remains available.

Use options only where they save the owner effort: no buttons for open-ended input
(logs, error text, paths, values, descriptions), for statements that need no reply, or
as decoration. Options never replace `Сейчас сделай:` and its copy-ready block for
commands or payloads (`2.1`, `2.2`), and never carry consent for a mandatory gate,
LIVE/financial action or destructive step: those still require the owner's explicit
current instruction. Where the client has no clickable-option mechanism, fall back to a
short lettered list the owner can answer with one letter.


## 2.3 NO ASSUMED USER STATE + BEGINNER-SAFE STEP-BY-STEP

Assume an ordinary Windows user without developer, PowerShell, Git, Node, Python, process, port, frontend/backend,
or terminal expertise. Therefore:

1. give one dependent practical step at a time when later steps are not yet needed;
2. say exactly what to open, where to click/type, and what should appear;
3. provide complete copy-ready commands—never fragments the user must adapt without necessity;
4. do not say “restart backend”, “kill the process”, “check the port”, “open a shell”, or similar without exact beginner-safe actions;
5. never assume which window, directory, process, server, tab, or environment is active; establish uncertain state first;
6. prefer commands that identify the exact process/object over asking the user to guess it;
7. prohibit speculative or “just in case” manual actions;
8. choose the simplest reliable Windows workflow and explain only what is needed for the current step.

These rules apply across Scanner, Trading Workspace, terminal, future robot, and project Git/Codex workflows.

### 2.3.1 NO INTERACTIVE PAGER — HARD RULE

Interactive Git pagers, `less`, `(END)` screens, and equivalent paged output are prohibited by default. Any Git
command that may page—including `diff`, `log`, `show`, and `branch`—must use `git --no-pager ...` or another
guaranteed non-interactive form. Git output must remain in the current PowerShell/terminal.

Do not rely on or prescribe `q`, `Esc`, or `Ctrl+C` as normal workflow. Paging is allowed only when the current
operation objectively requires interactive paging; convenience, inspection, verification, default behavior, and
“just in case” do not qualify.

## 2.4 CHATGPT_AND_CODEX_SESSION_LIFECYCLE_RULE

`ChatGPT New Chat` and `Codex New Session` are separate decisions.

- Recommend a new ChatGPT chat only after a substantial mission is complete and important state is preserved.
- Do not require a new Codex session after every Stage; one related mission may continue in the current session.
- Start a new Codex session for a new subsystem/mission, excessive context length, stale-assumption risk, or a deliberate clean repository recovery.
- A new Codex session recovers from repository authority, not conversational memory.
- If the user must change either lifecycle, name the exact one. Never say only “new context/session”.

A handoff is prepared only when repository recovery is insufficient. For an actual handoff, consult
`.agents/references/session-handoff.md`; an interruption alone does not require loading it or producing an artifact.
Neither lifecycle replaces Git state, artifacts, authoritative documentation or required checkpoints.

## 2.5 COMMUNICATION_LANGUAGE_ROUTING_RULE

```yaml
technical_repo_communication: English
user_confirmations_approvals_safety_actions: Russian
preserve_literals: [code, commands, identifiers, error_strings, API_names, file_paths, protocol_literals]
duplicate_bilingual_statement: forbidden
```

---

