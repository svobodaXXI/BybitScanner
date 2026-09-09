# BybitScanner — Trading Diary D7 Research Integration

Version: 0.1
Date: 2026-09-09
Status: D7.1 ACCEPTED DESIGN / IMPLEMENTATION PENDING

## 1. Decision

D7 Research Integration uses the following primary integration path:

```text
HYPOTHESIS
  -> SETUP INSTANCE
  -> TRADE / NON-TRADE OUTCOME
  -> RESEARCH DATASET
  -> VALIDATION RESULT
```

The Trading Diary remains the durable factual/research layer. It does not become a second execution engine and does not promote a hypothesis into Robot production behavior automatically.

## 2. Scope of D7.1

The integration must make research identity explicit across eligible observations and outcomes.

Primary research linkage:

* hypothesis ID (`H-ID`) where a hypothesis applies;
* hypothesis definition/version where applicable;
* setup instance identity;
* trade episode identity for executed trades;
* explicit non-trade outcome for eligible setups (`SKIPPED`, `INVALIDATED`, `EXPIRED`, or policy cancellation);
* strategy and entry-mode cohort keys already accepted by the Diary architecture;
* validation result as a separate research artifact/read model rather than a trading-state mutation.

A manual trade without a Scanner setup remains explicitly `MANUAL`; the system must not invent a hypothesis or setup association.

## 3. Research Denominators

D7.1 preserves two distinct denominators:

```text
TRADE DENOMINATOR
= executed trades eligible for the requested metric

SETUP DENOMINATOR
= all eligible setup observations, including non-traded outcomes
```

A skipped or invalidated setup is therefore retained as research evidence. Its later outcome may be attached only as a separately identified follow-up/observation and must not rewrite decision-time evidence.

## 4. Hypothesis Lifecycle

A research hypothesis follows the existing research workflow:

```text
OBSERVATION / CASE STUDY
  -> FORMALIZED SETUP
  -> H-ID HYPOTHESIS
  -> DATASET
  -> VALIDATION
  -> PROMOTION or KILL
  -> BACKLOG
```

`PROMOTION` means a research decision only. D7.1 does not authorize automatic Robot productionization.

Numeric thresholds, statistical significance requirements, sample-size requirements and promotion criteria remain `NEEDS VALIDATION` until explicitly accepted.

## 5. Cohort Integrity

Research analysis must remain separable by the existing Diary cohort dimensions, including:

* hypothesis ID/version;
* setup ID/setup instance;
* pattern/version;
* strategy version;
* entry mode;
* direction;
* timeframe;
* controller/origin;
* regime where available.

Different hypothesis or strategy versions must not be silently pooled.

## 6. Decision-Time Integrity

Decision-time evidence is immutable after the decision event.

Later market information, trade outcome, MAE/MFE or validation results may enrich the research dataset but must never be written back as if they were known at decision time.

Corrections are append-only amendments with provenance.

## 7. Read-Only Research Boundary

D7.1 is a research/data integration boundary.

It may support:

* linking Diary records to hypotheses and setups;
* building research datasets/read models;
* cohort filtering;
* validation/result presentation;
* data-quality and missingness reporting.

It must not by itself:

* place, amend or cancel orders;
* change position ownership;
* change Robot admission;
* alter PAPER/LIVE execution semantics;
* infer a missing trade/setup/hypothesis link from symbol alone.

## 8. Next Implementation Boundary

After this decision is documented, the next implementation step is a small vertical slice that exposes explicit hypothesis/setup identity in the existing Diary data model/read path, with tests for:

1. linked hypothesis/setup observation;
2. executed trade linkage;
3. non-traded setup retention;
4. missing-link fail-closed behavior;
5. version/cohort separation.

No broader Research Workspace UI is required for D7.1.

## 9. Status

Accepted decision: **Option A — Hypothesis → Setup → Trade/Non-trade → Dataset → Validation**.

Implementation authorization for this D7.1 vertical slice is covered by the explicit D7 authorization; no Robot runtime productionization is implied.
