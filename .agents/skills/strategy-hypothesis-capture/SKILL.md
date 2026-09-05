---
name: strategy-hypothesis-capture
description: Capture BybitScanner trading observations or strategy hypotheses as minimal research updates, without unvalidated edge claims or trading code changes; exclude chart/UI bug reports without strategy meaning.
---

# Strategy Hypothesis Capture

Use this skill when the user supplies a new trading idea, ordinary-language market observation, chart screenshot,
case study, or refinement to an existing setup, entry, risk, position-building, management or exit hypothesis.

Exclude chart/UI bug reports and screenshots without strategy meaning. Read the current
`DOCUMENTS/TRADING_STRATEGY_SPEC.md` and relevant definitions under protocol §8.9. This procedure is research-only;
no Scanner, trading, runtime, frontend or backend code changes.

## Classify before assigning an ID

Compare the user's meaning with existing setup definitions and hypothesis claims. Classify it as exactly one
primary type:

* `NEW_OBSERVATION`: a concrete episode or chart without a materially new generalized claim;
* `EXISTING_HYPOTHESIS_VARIANT`: new evidence, parameter candidate or mechanism still owned by an existing claim;
* `NEW_SETUP`: materially distinct market structure, state model or opportunity;
* `MECHANICS_REFINEMENT`: risk, entry, ladder, management or exit variant whose owning setup remains unchanged;
* `DUPLICATE`: no new research meaning beyond an existing recorded item.

Use semantic setup identity and falsifiable claim boundaries, not wording similarity. Prefer an observation or a
targeted extension when the existing hypothesis can own the new test without mixing incompatible cohorts. Do not
allocate an H-ID merely because a symbol, timeframe, example price or candidate parameter differs. Allocate a new
ID when the generalized setup/claim is materially distinct or combining it would make validation ambiguous.

If a new ID is necessary, scan the whole hypothesis registry for used and reserved identifiers, choose the next
free `H-xxx`, and add one registry row. Never reuse a reserved or existing ID. State the claim neutrally as a
testable possibility; do not assert profitability, causality, optimality or edge.

## Normalize the research item

Preserve the user's observation faithfully in meaning while translating it into measurable, decision-time
features. Distinguish what was observed from the generalized rule. Add or update only what the idea requires:

* observation/case study and source status;
* formalized setup and relationship to existing hypotheses;
* invariants and invalidation;
* required data and normalized features;
* primary metrics and frozen comparison/control variants;
* validation method, including costs and no-look-ahead controls;
* promotion and kill criteria;
* P0/P1/P2 research-backlog routing.

Keep `ACCEPTED DESIGN`, `BASELINE`, `HYPOTHESIS` and `NEEDS VALIDATION` distinct. Treat a chart as evidence that an
observation was made, never proof of the generalized setup. Do not promote example-specific prices, levels,
percentages, Fibonacci values, channel fractions or apparent outcomes into universal parameters. Candidate bins
may be recorded only as examples for research and must be labelled as unoptimized.

For screenshots or chart files, inspect the available image before describing it. Do not infer unavailable symbol,
timeframe, exact levels or outcome. If the original is worth preserving and the user authorized repository capture,
follow `training/reference_patterns/<SYMBOL>/<CASE_ID>/` and the manifest/before-after integrity rules in
`DOCUMENTS/PROJECT_RULES.md`; otherwise update only the strategy specification and identify missing source facts.

## Minimal patch rule

Patch only the smallest relevant locations in `DOCUMENTS/TRADING_STRATEGY_SPEC.md`. Do not rewrite the whole file,
renumber existing hypotheses or duplicate shared validation methodology. A typical new hypothesis needs one compact
definition, one registry row and one backlog item; an existing-hypothesis refinement may need only a subsection or
sentence plus data/backlog fields. A duplicate may require no repository change.

## Research review

Before completion, check the scoped research delta for mixed authority states, unsupported profitability claims,
accidental broad rewriting and missing validation/invalidation criteria. Report the classification and H-ID decision,
what research meaning changed, and unresolved source facts. Central authority owns the task workflow.
