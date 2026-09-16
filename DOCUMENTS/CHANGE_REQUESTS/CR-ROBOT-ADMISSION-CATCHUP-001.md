# CR-ROBOT-ADMISSION-CATCHUP-001 — Robot v0.1 Late-Admission Catch-up and Market Entry Viability

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-ADMISSION-CATCHUP-001",
  "title": "Robot v0.1 Late-Admission Catch-up and Market Entry Viability",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "OPEN",
  "revision": "1.0",
  "lifecycle_stage": "SPEC",
  "objective": "Make Robot admission reconstruct the truthful breakout/retest lifecycle from frozen Scanner geometry and missed closed 1m candles, then permit a late-admission Market entry only when the current executable trade still satisfies the accepted risk/reward, expected-reward, slippage, freshness, and ownership gates.",
  "non_goals": [
    "Change Scanner pattern detection, quality scoring, or Telegram signal timing",
    "Refit or mutate frozen candidate geometry after admission",
    "Change the ordinary observed-in-real-time retest LIMIT path",
    "Change Working Volume sizing or the 1 WV per-idea invariant",
    "Change STOP/TAKE formulas, the 2% STOP fallback, or the frozen 90% Scanner-potential TAKE rule",
    "Add LIVE execution",
    "Add a fixed N-candle late-entry rule or a new arbitrary entry-zone percentage for Robot v0.1",
    "Introduce a second order-state, risk, market-data, or persistence subsystem"
  ],
  "authoritative_references": [
    "robot_state_machine.py",
    "robot_entry_limit.py",
    "robot_market_confirmation.py",
    "robot_protection.py",
    "robot_partial_fill.py",
    "terminal/application/robot_breakout_monitor.py",
    "scanner_geometry_cursor.py",
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-BREAKOUT-MONITOR-001.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_IMPLEMENTATION_SLICES.md",
    "DOCUMENTS/GITHUB_FIRST_WORKFLOW.md",
    "AGENTS.md"
  ],
  "approved_decisions": [
    "Frozen pattern geometry remains immutable; mutable lifecycle phase is reconstructed against that frozen geometry.",
    "On first Robot admission, missed authoritative closed 1m candles from the Scanner snapshot cursor through the current closed candle are replayed chronologically through the existing robot_state_machine.process_closed_candle() transition function.",
    "If replay finds no breakout, the candidate remains WAITING_BREAKOUT.",
    "If replay finds breakout but no retest, the candidate resumes from WAITING_RETEST.",
    "If replay finds breakout and retest already completed before admission, Robot must not wait for a second retest and must not reject solely because the retest happened before admission.",
    "A late-admission post-retest candidate is evaluated for immediate MARKET entry using the current expected executable price, not the old Scanner price and not the historical retest boundary price.",
    "Late-admission MARKET entry requires projected whole-trade RR >= 1.5.",
    "Late-admission MARKET entry requires expected remaining reward to TAKE >= 1.0%.",
    "Late-admission MARKET entry requires adverse projected slippage <= 0.5%.",
    "The candidate must still be structurally valid and before the frozen apex; ownership/admission/reconciliation gates remain authoritative and fail closed.",
    "RR and expected reward are evaluated before submission using the expected executable price; after an actual fill, protection is rebuilt/validated from authoritative average_entry through the existing protection pipeline.",
    "For Robot v0.1, freshness is not defined by an extra fixed number of candles or a new fixed entry-zone percentage; price deterioration is primarily captured by the current executable-price RR/reward gates plus frozen-apex validity.",
    "The ordinary live-observation path is unchanged: a retest detected while Robot is already monitoring continues to use the existing retest LIMIT path unless a separately approved change says otherwise.",
    "No Market order is submitted when authoritative depth/price data is unavailable or when expected execution quality cannot be proven."
  ],
  "external_reference_inspiration": [
    "Freqtrade strategy callbacks: confirm_trade_entry() is the final pre-order veto and may abort when the current price is no longer acceptable; custom_entry_price() is evaluated immediately before order placement — https://www.freqtrade.io/en/stable/strategy-callbacks/",
    "Hummingbot PositionExecutor: entry execution is separated from a preconfigured position-management plan with explicit stop/take/time barriers — https://hummingbot.org/strategies/v2-strategies/executors/positionexecutor/",
    "QuantConnect LEAN: market execution is modeled separately from signal intent, with explicit slippage/market-impact models and asynchronous fill state — https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models and https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/market-orders"
  ],
  "context_findings": [
    "Current initialize_state() starts every non-expired approved candidate at WAITING_BREAKOUT and does not inspect candles that occurred after the Scanner snapshot.",
    "Current RobotBreakoutMonitor reads only the latest closed candle per tick, so a candidate admitted after breakout/retest can miss the historical transitions entirely.",
    "Current resume_without_replay() intentionally advances the geometry cursor after downtime without replaying missed candles; that restart behavior is not an admission catch-up mechanism and must not be reused to infer lifecycle events that were never evaluated.",
    "Current robot_market_confirmation.py already provides shared expected_reward_ratio(), risk_reward_ratio(), MarketCommandRequest construction, and a shared PAPER Market execution boundary; these capabilities should be reused rather than duplicated.",
    "Current robot_protection.py already owns structural STOP and frozen TAKE calculation; the late-admission gate must reuse the same strategy math so pre-entry RR and post-fill protection do not diverge.",
    "Current robot_partial_fill.py already uses 0.5% as the accepted maximum adverse move for Market completion; reusing 0.5% as the hard adverse-slippage cap avoids introducing a second near-duplicate execution-quality threshold."
  ],
  "unresolved_implementation_details": [
    "Identify and reuse the smallest existing authoritative market-depth/VWAP preview capability for expected MARKET fill of 1 WV; if no suitable shared capability exists, add the minimum dependency-injected read-only quote/depth provider without duplicating Workspace market-data infrastructure.",
    "Choose the smallest durable representation for catch-up evidence (at minimum breakout_index, retest_index, geometry_cursor and last_event; optional diagnostic timestamps/prices only if they materially improve acceptance/debugging).",
    "Confirm the exact historical-candle range provider boundary needed by RobotBreakoutMonitor so replay fetches each missing closed 1m candle exactly once and remains deterministic/idempotent."
  ],
  "acceptance_criteria": [
    "A candidate admitted before breakout remains WAITING_BREAKOUT.",
    "A candidate admitted after breakout but before retest catches up to WAITING_RETEST without waiting for another breakout.",
    "A candidate admitted after breakout and retest catches up to RETEST_DETECTED without waiting for another retest.",
    "Late-admission post-retest MARKET entry is allowed only when projected RR >= 1.5, expected reward >= 1.0%, adverse projected slippage <= 0.5%, frozen apex has not been reached, admission/ownership are valid, and market data is authoritative.",
    "The same setup is blocked fail-closed if any one of those gates fails; no order is emitted from ambiguous or unavailable price/depth state.",
    "A post-retest candidate whose price has already run too far is naturally rejected by the current-price RR/reward gate rather than by an arbitrary candle-age rule.",
    "The ordinary in-time retest LIMIT path remains unchanged.",
    "Frozen geometry is never refit during catch-up or entry evaluation.",
    "No duplicate Market or LIMIT order can be created by repeated monitor ticks or restart/recovery.",
    "Focused deterministic regression covers replay idempotency, phase restoration, each viability gate, no-second-retest behavior, and no-order-on-ambiguity behavior."
  ],
  "verification_requirements": [
    "Focused robot_state_machine / RobotBreakoutMonitor tests for chronological catch-up replay and idempotent re-entry into the monitor loop.",
    "Focused Market-entry policy tests for RR 1.5 boundary, expected reward 1.0% boundary, adverse slippage 0.5% boundary, apex/freshness failure, and missing-authoritative-market-data failure.",
    "Regression proving the existing live-observed retest LIMIT path is unchanged.",
    "PAPER end-to-end acceptance with at least one candidate admitted after a real breakout/retest and one deliberately poor-RR or excessive-slippage candidate that is correctly blocked."
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Runtime behavior

```text
Scanner immutable snapshot
        ↓
Robot admission
        ↓
chronological replay of missed closed 1m candles
        ↓
truthful current lifecycle phase
        ├─ WAITING_BREAKOUT → continue observing
        ├─ WAITING_RETEST   → continue observing
        └─ RETEST_DETECTED  → late-admission viability gate
                                  ↓
                           expected executable MARKET price
                                  ↓
                    existing STOP + existing TAKE policy
                                  ↓
                         projected whole-trade economics
                                  ↓
              RR >= 1.5 AND reward >= 1% AND slippage <= 0.5%
                                  ↓
                     structure/apex/ownership/admission valid
                                  ↓
                              MARKET entry
```

## Design rule

The Scanner snapshot freezes the setup geometry; it does not freeze the lifecycle phase or execution price. Robot reconstructs missed lifecycle events from authoritative closed candles, then makes the entry decision from current executable economics. A retest that happened shortly before admission remains a valid entry opportunity when the trade still satisfies the accepted gates.

## Mature-project comparison

The design follows a common separation used by mature trading engines: signal/setup state is not itself permission to execute indefinitely. Freqtrade exposes a last-moment entry confirmation and price hook, Hummingbot separates controller intent from executor lifecycle/risk configuration, and LEAN separates signal/order intent from fill/slippage reality. The BybitScanner adaptation keeps frozen pattern geometry while making execution contingent on current executable price, current RR/reward, slippage, and authoritative lifecycle state.

## Implementation order

1. Add deterministic admission catch-up replay over missed closed 1m candles using the existing state machine.
2. Add a pure late-admission viability decision that reuses existing STOP/TAKE and RR/reward math and consumes an expected executable MARKET price/slippage estimate.
3. Integrate the decision immediately before the existing shared PAPER Market command path; do not create a second Market executor.
4. Add focused regression and PAPER runtime acceptance before any LIVE discussion.

# END_OF_DOCUMENT
