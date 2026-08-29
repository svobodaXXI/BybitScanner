---
name: workflow-distiller
description: Classify evidence-backed recurring BybitScanner workflow friction into the cheapest appropriate system improvement while keeping candidates review-required and separate from implementation.
---

# Workflow Distiller

Use this skill only when friction has repeated, a manual procedure recurs, the same stale assumption or review defect returns, or one high-severity incident justifies prevention. Two occurrences are a useful signal, not a rigid threshold. A small one-off mistake normally produces no permanent artifact.

## Distill

1. Record concise evidence: what repeated, where, why existing mechanisms did not prevent it, and its real cost in time, turns, context, commands, defects, acceptance, or risk. If evidence is insufficient, return `DO_NOT_DISTILL_YET`.
2. Identify the root cause before proposing process change. Check whether authority or a tool already exists but was unread, poorly routed, duplicated, stale, or incorrectly applied; also distinguish workflow friction from runtime architecture and one-time noncompliance.
3. Reuse or improve discoverability of an existing mechanism before creating another one.
4. Classify the smallest suitable destination into exactly one primary category:

| Classification | Destination |
| --- | --- |
| `RULE / CONTRACT` | Permanent normative constraint, safety invariant, or mandatory subsystem/workflow behavior |
| `ARCHITECTURE / DECISION` | Ownership boundary, durable design choice, or important tradeoff |
| `CURRENT STATE` | Current blocker, next action, temporary scope, Task, or ChangeRequest state |
| `SKILL` | Reusable judgement-heavy LLM procedure describing how to work |
| `SCRIPT / TOOL` | Repeatable algorithmic procedure safer and cheaper to execute deterministically |
| `TEST / VERIFIER` | Executable invariant or regression check |
| `HISTORY` | Completed implementation, old debugging detail, or other information sufficiently owned by Git |
| `NO_CHANGE` | Benefit does not justify permanent complexity |

5. Compare expected benefit—less repeated work, context, error probability, user cost, or risk—with permanent cost—always-loaded context, maintenance, routes, authority duplication, ceremony, and mandatory steps. Prefer, in order: no change; better routing; existing artifact/tool; small amendment; deterministic check; small skill; new governance; new subsystem. Stronger evidence is required farther down this list.
6. Define how the improvement would later be verified and simplified or removed if it does not reduce the observed friction.

## Authority gate

Candidate lifecycle is `OBSERVED → CANDIDATE → REVIEW_REQUIRED → APPROVED/IMPLEMENTED` or `REJECTED`; no persistent candidate database is required. Auto-discovery is not auto-authority.

Generated rules, skills, scripts, tests, architecture changes, or verifier changes remain `REVIEW_REQUIRED`. They do not install themselves, enter always-loaded routing, modify runtime, rewrite governance, or recursively authorize more permanent changes. Changes to rules, contracts, architecture, execution safety, trading behavior, robot risk, or authoritative workflow require the normal human-authorized Task/ChangeRequest process.

Distillation is read-only by default. Do not implement the proposal in the same step unless the current user task explicitly authorizes that exact implementation scope.

## Output

Return only: `FRICTION`, `EVIDENCE`, `ROOT CAUSE`, `CLASSIFICATION`, `PROPOSED CHANGE`, `EXPECTED BENEFIT`, `PERMANENT COST`, `AUTHORITY`, and `STATUS`. Status is one of `DO_NOT_DISTILL_YET`, `REVIEW_REQUIRED`, or `READY_FOR_AUTHORIZED_IMPLEMENTATION`.

Use existing skills only when their workflows apply: `systematic-debugging` for unknown defect causes, `change-review` for recurring review defects, `proof-before-done` for false completion claims, `context-budget` for repeated recovery waste, and `session-handoff` for recurring context loss. Do not load their bodies automatically.
