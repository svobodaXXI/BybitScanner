# Strategic time-first execution policy — OWNER RULE 2026-10-14

**Purpose:** get the owner's actual working result as quickly as possible **without compromising proven safety and data integrity**. This is a decision rule, not a new multi-step bureaucracy.

## Mandatory pre-action decision (silent, seconds not minutes)

1. **Outcome:** name the smallest owner-visible result and how to recognize success.
2. **Existing path:** check the previously working workflow, current GitHub state, saved evidence and already verified artifacts *before* designing anything.
3. **Remove work first:** ask “Do we need this step at all?” and “What can be reused?” before optimizing, automating, inspecting or documenting it.
4. **Fastest safe end-to-end route:** compare minimal and full methods by *total owner wall-clock time*, not a step's local convenience. Include reading/copying, extraction, validation, waiting, device/port handling, agent turns and later cleanup.
5. **Safety boundary:** preserve explicit owner-controlled runtime/trading starts and stops, non-destructive preservation of unique data, SQLite consistency, LIVE/PAPER gates and required acceptance. Do not manufacture a shortcut that bypasses them.
6. **Critical path:** execute only steps necessary to achieve the current outcome. Record unrelated, nonblocking risks in the existing queue instead of turning them into side quests.
7. **Transparent long operations:** for tasks expected to exceed 30 seconds, provide stage, meaningful progress with an honest denominator or UNKNOWN, error state and USB/device release status. But *visibility does not justify work that should have been eliminated*.
8. **Stop condition:** after the target is verified, STOP. Do not append a blanket audit, recovery framework, complete archive or new worktree without demonstrated need.

### Routine computer ↔ laptop handoff: standard path

- **Code/PR/docs**: GitHub first. Fetch and fast-forward tracked code; use remote branches/PRs to recreate required worktrees. Do not copy entire repositories or old worktrees just to follow an already pushed commit.
- **Unpushed work**: check targeted `git status`; preserve only genuinely unique work via authorized commit/push or a narrow patch. Do not mechanically transfer all historical worktrees.
- **Machine-local state**: transfer only necessary, consistent PAPER/SHADOW SQLite snapshots and required current runtime metadata that is absent on the target, after owner-authorized stop and verification. Preserve unique destination state first.
- **Secrets/machine settings**: handle separately; DPAPI may not be portable. Never publish secrets or SQLite state to GitHub.
- **Full USB ZIP**: for disaster recovery/periodic backup, not the default for routine synchronization. If an existing full backup is already verified, do not re-extract it solely to sync code.
- **Do not move history unnecessarily**: charts, reports and old experiments remain in archives unless a concrete task needs them.
- **No runtime launch** by an agent; trading authorization remains owner-only.

### Failure mode to prevent

On 2026-10-14 the assistant turned a routine already-established GitHub sync into a FULL 7.5GB + DELTA USB restore on the laptop. The extra archive extraction, worktree checks and repeated verification wasted owner time. The **planning error** was confusing disaster recovery with daily workflow; adding progress reporting to the unnecessary extraction did not correct the original decision.

### Context recovery and agent bootstrap

- **Persistent authority**: `AGENTS.md` must point here. Agents entering the repository must apply this rule before issuing a task plan; no need for a full document sweep each time.
- **New ChatGPT conversation / context loss**: when working on BybitScanner, retrieve `AGENTS.md` plus this policy (or use the precise pointer in issue [#504](https://github.com/svobodaXXI/BybitScanner/issues/504)). Compare current owner request against the rule. Do not rely on conversational memory as the sole record.
- **Handoff notes**: include the compact mnemonic **Outcome → Reuse → Eliminate → Fastest safe path → Safety → Stop**, with a link to this file. Avoid bulky recurring context dumps.
- **Self-check before each action**: “Is this still the minimum necessary way to reach the owner's result?” If not, change course before delegation; if a significant detour is unavoidable, explain why.
- **On correction**: record a brief concrete failure lesson in the existing GitHub issue; do not spawn an infrastructure epic.

References: [#504](https://github.com/svobodaXXI/BybitScanner/issues/504); `DOCUMENTS/ASSISTANT_PROTOCOL.md`; existing `AGENTS.md` Reuse-First/owner runtime rules.
