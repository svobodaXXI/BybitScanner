# BybitScanner — AUTOPILOT Portfolio Risk Architecture

Version: 1.1
Date: 2026-09-07
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: define the accepted architecture for account-level AUTOPILOT portfolio risk admission. This document does not authorize runtime, PAPER or LIVE trading changes.

---

# 1. POSITION IN ARCHITECTURE

Every new entry and every position increase must pass through a dedicated portfolio-risk layer:

`STRATEGY`
`-> PORTFOLIO RISK ENGINE`
`-> ACCOUNT-SCOPED ORDER INTENT`
`-> EXECUTION ADAPTER`

The strategy may propose a trade, but the Portfolio Risk Engine owns the final account-level admission decision.

The Portfolio Risk Engine should return an explicit result such as:

- `ACCEPT_FULL`;
- `ACCEPT_REDUCED`;
- `REJECT_ASSET_CAP`;
- `REJECT_CLUSTER_HEAT`;
- `REJECT_DIRECTIONAL_HEAT`;
- `REJECT_TOTAL_EXPOSURE`;
- `REJECT_DATA_UNAVAILABLE`.

---

# 2. ACCEPTED HARD CAPS

## 2.1 Per-asset exposure cap

`MAX_PER_ASSET_EXPOSURE = 2 WV` (`2 РО`).

This is an accepted diversification/risk-control rule, not a setup-quality hypothesis.

The reason is protection against idiosyncratic risk specific to one asset/contract, including but not limited to:

- delisting or delisting announcements;
- trading halt/restriction;
- abrupt disappearance of liquidity;
- abnormal gap or price dislocation;
- contract/ticker-specific failure;
- other force-majeure events that ordinary STOP protection may not reliably contain.

The cap applies to total exposure in the same asset/symbol across entries/additions. A strategy may not bypass the cap by splitting the same asset exposure into several separate entries or setup legs.

If current exposure is below the cap and a new trade would exceed it, the Portfolio Risk Engine may reduce the admitted size to the remaining capacity rather than reject the setup entirely.

Example:

`current SOL exposure = 1.4 WV`

`requested addition = 1.0 WV`

`maximum admissible addition = 0.6 WV`.

## 2.2 Aggregate AUTOPILOT exposure cap

Existing account-level invariant:

`MAX_AUTOPILOT_EXPOSURE = 19 WV`.

This remains an absolute aggregate exposure ceiling for the trading account. Lower-level risk controls may reduce practical capacity below 19 WV.

---

# 3. CORRELATION-AWARE DIVERSIFICATION

Per-asset diversification alone is insufficient because several different tickers may behave as one economic risk.

Example:

`BTC LONG 2 WV + ETH LONG 2 WV + SOL LONG 2 WV`

may comply with the 2 WV per-asset cap but still represent a concentrated market-risk position.

Therefore AUTOPILOT should maintain a dynamic correlation map derived from instrument returns, not raw prices.

Candidate future implementation may use several horizons to distinguish short-regime correlation from more persistent background correlation. Exact windows and update cadence remain `NEEDS VALIDATION`.

Correlation state must be time-varying and should not be treated as a permanent static taxonomy.

---

# 4. DYNAMIC CORRELATION CLUSTERS

Strongly related assets should be grouped into dynamic correlation clusters.

Preferred research direction: correlation-matrix clustering / hierarchical clustering rather than a fully manual immutable sector list.

Manual categories such as `L1`, `L2`, `DEFI`, `MEME`, `AI` may be retained as supplemental metadata, but statistical co-movement should be the primary portfolio-risk input.

For each cluster, maintain:

`CLUSTER_HEAT`

and apply a future configurable cluster exposure ceiling:

`CLUSTER_HEAT <= CLUSTER_LIMIT`.

The exact cluster limit is not yet accepted and remains `NEEDS VALIDATION`.

---

# 5. DIRECTION-AWARE CORRELATION

Correlation must be interpreted together with position direction.

Conceptually:

`effective_correlation = market_correlation * direction_A * direction_B`

where:

- `LONG = +1`;
- `SHORT = -1`.

Therefore two strongly positively correlated LONG positions increase common directional exposure, while a LONG/SHORT pair may offset part of it.

This concept is a design guide; the exact quantitative portfolio-risk formula remains `NEEDS VALIDATION`.

---

# 6. MARKET DIRECTIONAL HEAT

AUTOPILOT should separately track broad market directional concentration, independent of cluster assignment.

Candidate account metrics:

- `GROSS_HEAT`;
- `LONG_HEAT`;
- `SHORT_HEAT`;
- `NET_HEAT`.

Example:

`GROSS = 15 WV`

`LONG = 13 WV`

`SHORT = 2 WV`

`NET = +11 WV`.

A portfolio with many nominally different assets can therefore still be rejected or size-reduced when directional concentration becomes excessive.

Exact directional-heat limits remain `NEEDS VALIDATION`.

---

# 7. ADMISSION ORDER

Candidate risk-admission sequence:

1. account/session/reconciliation health;
2. per-asset cap (`2 WV`);
3. aggregate AUTOPILOT cap (`19 WV`);
4. correlation/cluster heat;
5. directional market heat;
6. liquidity/execution-risk constraints;
7. final `ACCEPT_FULL / ACCEPT_REDUCED / REJECT` decision.

Risk decisions must be account-scoped and must preserve the existing fail-closed philosophy when required data is stale, unknown or unreconciled.

---

# 8. EFFECT ON EXISTING POSITIONS

A rise in measured correlation by itself should not automatically force closure of otherwise valid existing positions.

Correlation, cluster heat and directional heat primarily gate:

- new entries;
- position increases/additions.

Existing positions continue to be managed by their setup invalidation, STOP, management and emergency-risk rules unless a stronger global risk condition explicitly requires intervention.

This avoids unstable portfolio churn caused by noisy short-term changes in correlation estimates.

---

# 9. DATA / DIARY REQUIREMENTS

For every admission decision, preserve enough decision-time data to evaluate later whether the Portfolio Risk Engine helped or hurt performance.

Candidate fields:

- `requested_wv`;
- `admitted_wv`;
- `asset_exposure_before`;
- `asset_exposure_after`;
- `aggregate_exposure_before`;
- `aggregate_exposure_after`;
- `cluster_id` and clustering-model version;
- `cluster_heat_before` / `cluster_heat_after`;
- relevant pairwise/effective correlation features;
- `gross_heat`, `long_heat`, `short_heat`, `net_heat`;
- liquidity/execution-risk features;
- final risk-decision code;
- later trade outcome appended without rewriting the original decision state.

Rejected and size-reduced opportunities should remain visible in the trading diary/research dataset so that risk rules can be evaluated rather than assumed beneficial.

---

# 10. VALIDATION BACKLOG

Future research should compare:

- fixed per-asset cap only vs cap + correlation clustering;
- alternative cluster algorithms / thresholds;
- alternative correlation horizons and weighting;
- hard rejection vs size reduction near cluster/directional limits;
- cluster limits across calm, normal and stressed market regimes;
- directional-heat limits;
- static sector labels vs dynamic correlation clusters;
- admission decisions with and without liquidity/execution constraints.

No unvalidated numeric cluster or directional-heat threshold is accepted by this document.

---

# 11. DEGRADED CORRELATION / CLUSTER-DATA POLICY

`ACCEPTED DESIGN`: if correlation/cluster risk data becomes stale, unavailable or materially unreliable, AUTOPILOT enters a degraded-risk mode rather than silently ignoring that layer.

Default policy:

- new entries may be admitted only at a reduced size while degradation is limited and other hard risk data remains healthy;
- position increases/additions are blocked while correlation/cluster data is degraded;
- existing open positions continue ordinary setup/STOP/management logic and are not automatically closed solely because correlation data degraded;
- if degradation becomes prolonged, severe, or combines with other unknown/unreconciled account-risk state, transition to full fail-closed for new risk;
- all degraded-mode admissions/rejections must be logged with the data-health reason and risk-mode state.

Exact reduced-size fraction and exact degradation-duration thresholds remain `NEEDS VALIDATION`; this document accepts the behavior class, not those numeric parameters.

Candidate explicit states:

- `RISK_DATA_HEALTHY`;
- `RISK_DATA_DEGRADED_REDUCED_ONLY`;
- `RISK_DATA_FAIL_CLOSED`.

Candidate decision codes include:

- `ACCEPT_REDUCED_DATA_DEGRADED`;
- `REJECT_ADD_DATA_DEGRADED`;
- `REJECT_DATA_UNAVAILABLE`.

Version 1.1 records this degraded-risk policy.

# END_OF_DOCUMENT
