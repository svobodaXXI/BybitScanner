# CR-TRADING-INTELLIGENCE-001 — Trading Intelligence and Paper Trader Roadmap Research

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-TRADING-INTELLIGENCE-001",
  "title": "Trading Intelligence and Paper Trader Roadmap Research",
  "status": "IN_PROGRESS",
  "revision": "1.3",
  "lifecycle_stage": "CONTEXT",
  "objective": "Research and record the evidence, architecture boundaries, dependencies and non-final roadmap hypothesis required to evolve the current Scanner into broader Trading Intelligence and a safe event-driven Paper Trader without authorizing implementation.",
  "non_goals": [
    "Implement or modify production Scanner, pattern, market-data, execution or trading behavior",
    "Modify tests or begin Paper Trader, realtime feed or new detector implementation",
    "Treat the planning hypothesis as a final roadmap or authorize any implementation phase",
    "Finalize numeric strategy weights, order-book depth, liquidity thresholds or historical replay policy without evidence",
    "Change existing architecture or contracts as if the researched target design were already approved",
    "Create a parallel identifier, governance, execution or persistence system"
  ],
  "approved_scope": [
    "Preserve the current Scanner-to-Paper-Trader gap analysis and validate it against targeted external references",
    "Research a common PatternObservation and normalized TradingSignal boundary across detector families",
    "Research Flag, Head and Shoulders, Inverse Head and Shoulders, Double Bottom and Double Top detector-family architecture",
    "Research Candlestick Formation Evidence as confirmation/context rather than an independent primary trading engine",
    "Research separate PRE_BREAKOUT_CORRIDOR_SETUP and BREAKOUT_SETUP strategy types",
    "Research Paper Trader domain models, lifecycle, risk, execution, portfolio, persistence, reconciliation and replay",
    "Research event-driven Bybit public trades, full L2 order-book reconstruction and liquidity-aware position management",
    "Measure performance and subscription constraints required to protect Scanner throughput",
    "Produce a dependency-aware proposed roadmap for later human review and approval"
  ],
  "prohibited_scope": [
    "Production code and tests",
    "Implementation authorization or implementation work",
    "Automatic placement of new detector families inside wedge/",
    "Geometry-score modification for LONG preference or candlestick evidence",
    "Candle-only realtime Paper Trader design",
    "Direct execution decisions inside a liquidity analyzer",
    "Unrelated documentation, dirty work, generated artifacts, commit or push"
  ],
  "authoritative_references": [
    "AGENTS.md#Task-and-change-routing",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_STATE.md#TRADING_INTELLIGENCE_PAPER_TRADER_RESEARCH_STATE",
    "DOCUMENTS/ROADMAP.md#CR-TRADING-INTELLIGENCE-001"
  ],
  "context_scope_paths": [
    "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-INTELLIGENCE-001.md",
    "DOCUMENTS/ASSISTANT_PROTOCOL.md",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md",
    "DOCUMENTS/PROJECT_CONTRACTS.md",
    "analyzer/core.py",
    "geometry/engine.py",
    "geometry/model.py",
    "wedge/analyzer.py",
    "wedge/detector.py",
    "structures/classifier.py",
    "signal/filter.py",
    "signal/quality.py",
    "contracts/signal_contract.py",
    "bybit_api.py",
    "confirmation.py",
    "main.py",
    "signal_adapter.py",
    "signal_memory.py"
  ],
  "context_test_paths": [
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py",
    "tests/test_directional_envelope_quality.py",
    "tests/test_signal_admission.py"
  ],
  "context_excerpt_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_STATE.md#TRADING_INTELLIGENCE_PAPER_TRADER_RESEARCH_STATE",
    "DOCUMENTS/ROADMAP.md#CR-TRADING-INTELLIGENCE-001"
  ],
  "approved_decisions": [
    "The existing primary pattern family remains Wedge and Triangle geometry",
    "The desired Trading Intelligence set adds Flag, Head and Shoulders, Inverse Head and Shoulders, Double Bottom and Double Top",
    "New detector families are not automatically placed in wedge/",
    "Shared pivots and geometry primitives feed detector families that publish a common PatternObservation and normalized signal boundary",
    "Flag is an impulse plus consolidation/channel family",
    "Flag is an independent detector family compositionally defined by DirectionalExpansion followed by post-impulse consolidation in an approximately parallel bounded channel; it is not a Wedge subtype and is not automatically placed in wedge/",
    "Flag may reuse shared pivots, boundary fitting, touch measurement, containment and volatility-context primitives, while shared mathematics remains below detector-family semantics and excludes Wedge convergence, apex and Wedge-specific compression semantics",
    "DirectionalExpansion is a roadmap-level shared concept with identity independent of Flag; candidate attributes include direction, origin/end, displacement, duration, velocity, directional efficiency and volatility-normalized magnitude, but no exact schema is approved",
    "Flag pole/body segmentation prefers a confirmed EXPANDING to POTENTIAL_CONSOLIDATION to FLAG_FORMING regime transition rather than one magic candle, fixed candle count or definition-level fixed pivot count; the terminal extreme may move while expansion continues",
    "A FlagCandidate conceptually composes impulse evidence and consolidation evidence rather than using one monolithic scan rule",
    "Flag consolidation requires bounded structure, approximate parallelism, structural integrity or containment and acceptable retracement; countertrend drift supports quality but is not mandatory because approximately horizontal flags are valid candidates",
    "BoundaryRelationship is supported as a shared concept below detector semantics with conceptual PARALLEL, CONVERGING, DIVERGING and UNCERTAIN states, while its exact enum and schema remain open",
    "DirectionalExpansion plus parallel consolidation supports Flag interpretation; expansion plus converging consolidation supports Pennant interpretation; converging geometry without required post-impulse context may support Wedge or Triangle interpretation",
    "Detector-family evidence is separable from final classification; future Pattern Arbitration may resolve competing interpretations on comparable structural horizons, while UNCLASSIFIED and AMBIGUOUS are valid outcomes and nested structures on different horizons are not conflicts",
    "Detector-specific raw scores are not universal probabilities, and Strategy does not determine geometric pattern identity",
    "Flag hard identity conceptually requires valid antecedent directional expansion, post-impulse consolidation, bounded channel structure, approximate parallelism, acceptable retracement and structural integrity, while validity remains separate from quality",
    "Flag quality evidence may include ImpulseQuality, ChannelQuality, ParallelismQuality, RetracementQuality, ContainmentQuality, ConsolidationQuality and VolumeEvidence, without approving exact names, schemas, weights or thresholds",
    "Volume contraction is supporting or contextual evidence and is neither a hard Flag existence requirement nor silently part of geometry validity",
    "Breakout is not required for Flag existence; pre-breakout observations are supported, and boundary interaction, breakout candidate, confirmation and failure are later lifecycle or event evidence with exact policy still open",
    "Flag detection owns neither BUY or SELL decisions nor entry, SL, TP, sizing, directional preference, liquidity policy, portfolio exposure or execution; the boundary remains pattern detection to PatternObservation or normalized boundary to Strategy, Risk and Execution",
    "PatternInstance represents persistent structural identity and lifecycle while PatternObservation represents scanner knowledge at a particular time; evolving pivots, boundaries or quality do not automatically create a new Flag",
    "Preferred roadmap-level candidate processing is Detect, Associate, Update existing or Create new, Observation, Lifecycle transition and Arbitration, using structural continuity rather than an exact geometry hash",
    "Candidate association may consider shared impulse, temporal or consolidation overlap, direction and compatible boundary evolution, with exact thresholds open",
    "Overlapping and nested structures are permitted; arbitration addresses genuine competition on comparable structural horizons rather than suppressing all overlap",
    "INVALIDATED and EXPIRED are distinct: invalidation contradicts continued structural identity, while expiration removes relevance without requiring one destructive event; possible invalidation evidence includes excessive retracement, adverse boundary break and channel collapse",
    "DirectionalExpansion can remain relevant after one Flag candidate terminates and may be reused while structurally relevant, but a newer more directly relevant expansion supersedes older antecedent context; exact decay policy remains open",
    "Confirmed breakout terminates Flag formation or detection lifecycle; continuation, retest, failure and potential or target realization belong to later PatternOutcome and/or Strategy analysis rather than geometric validity",
    "The Flag research documentation checkpoint includes Assistant Protocol v4.9 strengthening for complete user action chains and mandatory canonical hardening after user-reported protocol failures",
    "Head and Shoulders and Inverse Head and Shoulders are an extrema-sequence plus neckline family",
    "Double Bottom and Double Top require topology/extrema or shared reversal-family research rather than automatic reuse of Wedge GeometryModel",
    "Candlestick formations initially provide evidence, confirmation and context for chart-pattern Trading Intelligence",
    "Candlestick scoring is not mixed into geometry detector responsibilities without a separate design decision",
    "LONG setups receive a mild later strategic preference without banning SHORT, applying a large hard bonus, changing Geometry score or changing detector validity",
    "LONG preference belongs to Strategy/Decision policy and its numeric weight remains evidence-dependent",
    "PRE_BREAKOUT_CORRIDOR_SETUP and BREAKOUT_SETUP are distinct strategy/setup types even when they share one GeometryModel",
    "Paper Trader v1 position mode is ONE_WAY; hedge mode is later",
    "Paper Trader v1 margin mode is ISOLATED; cross margin is later",
    "Paper Trader v1 account currency is USDT_ONLY",
    "Paper Trader v1 permits at most one open position per symbol and NO_SCALE_IN as policy/risk rules rather than Position-model limitations",
    "While a position is open all repeated signals are journaled, but same-side and opposite-side signals cause no automatic position change, reversal or SL/TP modification in v1",
    "New scanner entries are formed only from CLOSED candles",
    "Strategy creates market intent or order request and does not choose the actual fill price",
    "Time semantics distinguish source_candle_time, signal_time, order_time and fill_time",
    "Execution uses executable market price; unrealized PnL uses Mark Price; historical fallback may use an explicitly labelled close proxy",
    "Realtime Paper Trader is event-driven over Bybit public trades and full L2 order-book streams rather than candle-only",
    "Candles remain primary for Scanner detection, aggregated context and historical fallback/replay",
    "The local order book uses incremental snapshot/delta updates without pandas in the hot delta path",
    "Deep microstructure monitoring is activated selectively for shortlist symbols, symbols in play, approved signals and open positions",
    "Heavy analysis is not performed on every delta; higher layers receive meaningful liquidity events or observations",
    "Order-book visibility covers the expected path to target or potential plus a safety buffer; fixed depth 50, 200 or 1000 is not approved",
    "LONG corridor visibility examines ask-side liquidity and SHORT corridor visibility examines bid-side liquidity",
    "Liquidity analysis publishes LiquidityObservation to Position Management and does not execute directly",
    "A large order alone is not an approved immediate-exit rule",
    "Historical candle SL/TP ambiguity is fallback/replay behavior, not the primary realtime mechanism",
    "Scanner and pattern subsystems do not know whether a normalized signal is executed on paper or live",
    "Future PaperExecution and LiveBybitExecution share the same Strategy/Risk boundary through ExecutionPort",
    "Tracks A, B and C may proceed in parallel and join through normalized contracts",
    "New trading and microstructure layers must not materially degrade Scanner throughput",
    "Public Bybit L2 is sufficient as the v1 baseline microstructure model, but it provides aggregated price-level liquidity rather than L3/MBO order identity or exact virtual queue position",
    "Order-book and public-trade streams remain separate but correlatable using exchange/event and local receive timestamps without assuming zero latency",
    "LocalOrderBook is initialized or replaced from snapshots, maintained incrementally from validated deltas and requires explicit resnapshot/recovery semantics",
    "Adaptive depth follows MINIMUM_DEPTH_THAT_COVERS_TRADE_HORIZON from executable market area through target/potential plus safety buffer, with later lifecycle-controlled downgrade or unsubscribe",
    "Selective microstructure activation follows ordinary symbol through forming/interesting setup, SYMBOL_IN_PLAY, approved/open trade, lifecycle end, cooldown and downgrade/unsubscribe",
    "The per-delta hot path performs decode, sequence validation, incremental book update and cheap aggregates; heavy analysis and Strategy wakeups use filtered or coalesced meaningful changes",
    "Incremental liquidity aggregates may cover near-spread, distance and trade-target corridors without approving exact bucket boundaries",
    "Liquidity analysis supports price-local LiquidityZone clusters rather than equating one large level with a wall",
    "Liquidity evidence is relative to local instrument/book context and may use robust baselines, but normalization formulas and thresholds remain open",
    "Order-book imbalance supports multiple horizons such as NEAR, MEDIUM and TRADE_HORIZON rather than one global value",
    "LiquidityZone preserves temporal evidence including first_seen, last_seen, age, peak and current size/notional",
    "Book reduction plus nearby aggressive tape supports consumption evidence; reduction without corresponding tape supports pull/cancel evidence without claiming proven causality",
    "Replenishment/absorption and price progress relative to aggressive flow are separate evidence families and do not directly command an exit",
    "Public L2 observations use neutral labels such as LIQUIDITY_PULL, LIQUIDITY_MIGRATION and TRANSIENT_LIQUIDITY; SPOOF_LIKE_BEHAVIOR is heuristic and non-authoritative",
    "LiquidityBarrier or LiquidityZone lifecycle is research-supported conceptually as DETECTED, PERSISTING, APPROACHED and TESTED with possible consuming, absorbing, broken, rejecting, pulled or migrated outcomes",
    "LiquidityEngine publishes LiquidityObservation to Strategy or PositionManager and never opens or closes a Position directly",
    "Liquidity-aware actions HOLD, MOVE_TP, PARTIAL_EXIT and EXIT_BEFORE_BARRIER remain future independently testable policy choices rather than automatic rules",
    "Paper Trader v1 market execution walks available executable L2 levels into simulated fills and VWAP with fees, slippage and account effects instead of fill equals last price",
    "Public L2 volume remains an imperfect simulation because latency and concurrent real-market consumption can alter liquidity",
    "Exact realistic LIMIT execution is excluded from v1 pending an explicit conservative, probabilistic or other documented queue approximation",
    "Touching a limit price does not imply a definite virtual fill",
    "Architecture records exchange/event and local receive timestamps so later measured or simulated latency is possible without making HFT queue simulation a v1 requirement",
    "A forming eligible pattern may activate SYMBOL_IN_PLAY and microstructure monitoring before breakout while exact geometry maturity and entry thresholds remain open"
  ],
  "unresolved_decisions": [
    "Canonical English identity and exact semantics of the user term Восходящая звезда",
    "Exact initial candlestick formation catalog and evidence/scoring policy",
    "Head and Shoulders / Inverse Head and Shoulders and Double Top / Double Bottom detector contracts and shared primitive boundary",
    "Minimum DirectionalExpansion strength and ATR or volatility normalization formula",
    "Flag minimum pivot or touch requirements, parallelism tolerance and acceptable retracement thresholds",
    "Flag minimum and maximum consolidation duration, expiration rules and FORMING to MATURE transition criteria",
    "Flag breakout confirmation policy and failed-breakout semantics",
    "Flag candidate-association thresholds and structural-horizon representation",
    "Pattern Arbitration confidence and normalization model",
    "Detector-quality normalization, weights and volume weighting",
    "Exact DirectionalExpansion reuse, relevance and decay policy",
    "Exact schemas for DirectionalExpansion, ConsolidationObservation, PatternInstance and PatternObservation",
    "Minimum pre-breakout geometry maturity, boundary confidence and touch semantics",
    "Corridor distance/potential threshold, entry trigger, target, SL, risk and invalidation",
    "Apex-proximity cutoff and criteria separating a tradeable corridor from accidental lines",
    "Numeric LONG preference weights and evidence required to approve them",
    "Final normalized PatternObservation, TradingSignal and TradingIntent schemas",
    "Order, fill, position, account, margin, fee, PnL, risk and recovery semantics",
    "Realtime executable-price source and market-order fill/slippage model",
    "Bybit stream subscription topology, order-book depth and dynamic target-corridor strategy",
    "Liquidity-barrier thresholds using relative size, notional, distance, persistence, pull behavior, replenishment, tape consumption, imbalance, wall migration, price response and spoofing risk",
    "Position-management policy for HOLD, MOVE_TP, PARTIAL_EXIT and EXIT_BEFORE_BARRIER",
    "Historical replay policy for SL/TP collisions, lower-timeframe resolution and WORST_CASE fallback",
    "Persistence technology, deterministic replay clock and reconciliation approach",
    "Measured CPU, RAM, network and latency budgets for selective realtime monitoring",
    "Final dependencies, phase boundaries and roadmap authorization",
    "Exact Bybit sequence/update validation, gap detection and resnapshot rules",
    "Exact SYMBOL_IN_PLAY activation, cooldown, downgrade and unsubscribe policy",
    "Liquidity aggregate bucket boundaries, relative normalization formulas and multi-window imbalance thresholds",
    "LiquidityZone and LiquidityBarrier exact schema, lifecycle state names, transitions and confidence thresholds",
    "Consumption, pull, replenishment, absorption and price-response correlation windows",
    "Market-order simulation latency, concurrency haircut, depth exhaustion and insufficient-liquidity policy",
    "Future limit-order queue model, if limit orders enter a later scope",
    "Measured limits for network bandwidth, message rate, CPU, RAM, book-update latency, observation latency and concurrent deep-monitored symbols"
  ],
  "microstructure_research_disposition": {
    "status": "SUFFICIENT_FOR_ROADMAP_LEVEL_DESIGN",
    "implementation_spec_status": "NOT_READY",
    "exact_formulas_thresholds_and_schemas": "OPEN",
    "roadmap_status": "HYPOTHESIS_NOT_FINAL_ADDITIONAL_RESEARCH_REQUIRED",
    "next_external_research_focus": [
      "Flag",
      "Head and Shoulders / Inverse Head and Shoulders",
      "Double Top / Double Bottom",
      "Candlestick Formation Evidence",
      "PRE_BREAKOUT_CORRIDOR_SETUP"
    ]
  },
  "flag_detector_family_research_disposition": {
    "status": "SUFFICIENT_FOR_ROADMAP_LEVEL_DESIGN",
    "implementation_spec_status": "NOT_READY",
    "implementation": "NOT_AUTHORIZED",
    "exact_schemas_formulas_thresholds_weights_and_lifecycle_policies": "OPEN",
    "roadmap_status": "HYPOTHESIS_NOT_FINAL_ADDITIONAL_RESEARCH_REQUIRED",
    "next_detector_family_research": "NOT_STARTED"
  },
  "microstructure_evidence_families": [
    "Relative and clustered liquidity",
    "Multi-window order-book imbalance",
    "Persistence",
    "Consumption",
    "Pull and migration",
    "Replenishment and absorption",
    "Price response relative to aggressive trade flow"
  ],
  "microstructure_later_research": [
    "L3/MBO reconstruction",
    "Exact queue position",
    "Sophisticated iceberg reconstruction",
    "Machine-learning wall prediction",
    "Authoritative spoofing classification",
    "Full HFT latency simulation"
  ],
  "external_reference_conclusions": [
    "Bybit public WebSocket semantics support separate public trade and L2 snapshot/delta sources with exchange-defined update and recovery handling",
    "NautilusTrader supports event-driven separation of data, execution and fill ownership and reinforces the distinction between L2 and L3 semantics",
    "hftbacktest illustrates why queue and latency modelling are explicit approximations under market-by-price data",
    "Microstructure-oriented open-source implementations support treating imbalance, absorption, pulls, sweeps and trade-flow context as independent evidence rather than one wall-size threshold",
    "External projects are architectural references only and are not normative BybitScanner dependencies"
  ],
  "gap_analysis_baseline": [
    "The trading bounded context is absent from the current repository",
    "The Scanner pipeline is suitable as source analytics but not as a trading core",
    "The prior capability matrix found 2 PARTIAL and 38 ABSENT trading capabilities",
    "Current scanner signal dictionaries are not executable TradingIntent contracts",
    "Existing signal history is notification memory rather than a trade journal",
    "Execution, account, order, fill, position, risk, durable trading persistence and replay layers are absent",
    "Paper Trader begins behind a new normalized signal boundary"
  ],
  "preferred_boundary": [
    "Scanner / Pattern subsystem",
    "PatternObservation",
    "Normalized TradingSignal",
    "StrategyDecision",
    "Risk / Sizing",
    "OrderRequest",
    "ExecutionPort",
    "PaperExecution",
    "Orders / Fills",
    "Position / Portfolio / Account",
    "Journal / Reconciliation / Metrics",
    "Later: same Strategy/Risk with LiveBybitExecution"
  ],
  "roadmap_hypothesis": {
    "track_a_scanner_trading_intelligence": [
      "Existing Wedge refinement",
      "Flag",
      "Head and Shoulders / Inverse Head and Shoulders",
      "Double Top / Double Bottom",
      "Candlestick Formation Evidence",
      "Common PatternObservation",
      "Pre-breakout corridor setups"
    ],
    "track_b_trading_foundation": [
      "Normalized contracts",
      "Instrument specification and precision",
      "Deterministic clock and time semantics",
      "Order, fill, position and account models",
      "Strategy decision and risk/sizing",
      "ExecutionPort and PaperExecution",
      "Fees, PnL and margin",
      "Journal and recovery"
    ],
    "track_c_market_microstructure_simulation": [
      "Bybit realtime trades",
      "Full L2 order book and local incremental book",
      "Active-symbol subscription model",
      "Liquidity observations and liquidity-aware management",
      "Historical replay later over compatible domain contracts"
    ]
  },
  "external_research_requirements": [
    "Target high-quality open-source systems for architecture comparison rather than blind copying",
    "Compare order/fill state machines, virtual account, portfolio/positions, fees, SL/TP and paper/live abstractions",
    "Compare persistence, restart recovery, reconciliation, deterministic testing and replay",
    "Compare realtime order-book reconstruction, tape processing, liquidity barriers and performance-sensitive market-data handling",
    "Record source, relevant concept, fit, mismatch, license and adoption risk for each material reference"
  ],
  "performance_requirements": [
    "Separate Scanner cold paths from realtime hot paths",
    "Use incremental computation and selective subscription activation",
    "Keep memory bounded and avoid unnecessary DataFrame allocations in realtime paths",
    "Filter or coalesce high-rate events before expensive higher-level analysis",
    "Define measurable CPU, RAM and network budgets",
    "Require profiling and benchmark criteria before enabling heavy realtime features across the Scanner universe"
  ],
  "acceptance_criteria": [
    "Targeted external research is completed with source-attributed architectural comparisons",
    "Current repository gaps are reconciled with external findings without treating reference implementations as authority",
    "Approved human decisions remain distinct from unresolved research questions",
    "Detector-family boundaries and common PatternObservation hypothesis are described without implementation",
    "Pre-breakout corridor and breakout setups remain explicit separate strategy types",
    "Paper Trader domain and event-driven market-microstructure dependency constraints are explicit",
    "A dependency-aware proposed roadmap covers Tracks A, B and C and identifies their normalized-contract join points",
    "Performance budgets and validation criteria are included in the proposed roadmap",
    "The proposed roadmap is presented for explicit human approval before any implementation request",
    "Production code and tests remain unchanged throughout this planning/research checkpoint"
  ],
  "verification_requirements": [
    "ChangeRequest schema validation",
    "Durable Codex workflow governance validation",
    "Project State, Roadmap and ChangeRequest identity, revision, lifecycle and authorization consistency review",
    "Approved-versus-open decision classification review",
    "Scoped documentation allowlist review",
    "git diff --check and scoped diff/stat",
    "git status review confirming unrelated dirty work is untouched"
  ],
  "risks": [
    "Prematurely treating a research hypothesis as an approved architecture or final roadmap",
    "Coupling Paper Trader directly to Wedge dictionaries or Telegram-oriented signal contracts",
    "Building a candle-only simulator that cannot model realtime execution and position management",
    "Duplicating geometry or topology logic across detector families",
    "Embedding LONG bias, candle evidence or corridor strategy policy inside detector validity or Geometry score",
    "Selecting arbitrary order-book depth or liquidity-wall thresholds without instrument measurements",
    "Overloading the Scanner universe with deep realtime subscriptions and high-rate analysis",
    "Treating transient or spoofed liquidity as an automatic exit command",
    "Designing backtest and realtime execution as separate incompatible trading cores"
  ],
  "rollback_boundaries": [
    "This checkpoint changes only its ChangeRequest, Project State and Roadmap planning records",
    "Rollback removes the new research mission pointer and planning entry without changing production or test behavior",
    "No implementation artifact or derived ContextDump is required to recover the pre-mission state"
  ],
  "implementation_phases": [
    {"id": "RESEARCH", "status": "ACTIVE_HUMAN_AUTHORIZED"},
    {"id": "ROADMAP_SPEC", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "IMPLEMENT", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "VERIFY", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "RECORD", "status": "NOT_STARTED_NOT_AUTHORIZED"}
  ],
  "current_phase": "RESEARCH",
  "current_checkpoint": "FLAG_DETECTOR_FAMILY_RESEARCH_RECORDED",
  "implementation_status": "IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED",
  "next_phase": "ROADMAP_SPEC",
  "next_phase_authorization": "NOT_AUTHORIZED_PENDING_RESEARCH_AND_HUMAN_APPROVAL",
  "related_commits": [
    {"phase": "BASELINE", "commit": "ce747f8a0223306a2128e413ae259df955f5a085"},
    {"phase": "DURABLE_PLANNING_RESEARCH_CHECKPOINT", "commit": "9d8a9c5752dafaad60ecf9676ba8d7b19ab0ce97"}
  ],
  "repository_sync": {
    "branch": "main",
    "baseline_local_head": "ce747f8a0223306a2128e413ae259df955f5a085",
    "baseline_origin_main": "ce747f8a0223306a2128e413ae259df955f5a085",
    "latest_saved_checkpoint": "9d8a9c5752dafaad60ecf9676ba8d7b19ab0ce97",
    "status": "SYNCHRONIZED_AT_LATEST_SAVED_CHECKPOINT"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Human-authorized durable planning and research checkpoint; implementation explicitly not authorized", "date": "2026-08-18"},
    {"revision": "1.1", "reason": "Recorded accumulated market-microstructure research as sufficient for roadmap-level design while preserving open formulas, non-final roadmap and no implementation authorization", "date": "2026-08-18"},
    {"revision": "1.2", "reason": "Recorded Flag detector-family research as sufficient for roadmap-level design while preserving open schemas and thresholds, a non-final roadmap and no implementation authorization", "date": "2026-08-19"},
    {"revision": "1.3", "reason": "Included the authorized Assistant Protocol v4.9 enforcement strengthening in the Flag research documentation checkpoint without changing research lifecycle or implementation authorization", "date": "2026-08-19"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

The current Scanner is the source-analytics side of the future system. Its Wedge/Triangle pipeline,
shared pivots and geometry primitives are useful inputs, but the repository has no trading bounded
context and its signal dictionaries are not executable intents. This mission researches the common
normalized boundary, the remaining desired Trading Intelligence families, Paper Trader foundations
and realtime market-microstructure architecture before a final roadmap is proposed.

Microstructure and Flag detector-family research are now `SUFFICIENT_FOR_ROADMAP_LEVEL_DESIGN`, but
neither is an implementation specification. Flag is recorded as an independent impulse-plus-parallel-
consolidation family with shared primitives below detector semantics, persistent instance/observation
identity, lifecycle separation, and future arbitration across comparable horizons. Exact schemas,
formulas, thresholds, association, arbitration, breakout and expiration policies remain open. Research
and planning remain active; the next detector-family research has not started. The roadmap remains
non-final, ROADMAP_SPEC remains unauthorized, and any later implementation requires explicit human approval.

## Amendment rule

Material scope, approved decision, risk, acceptance, lifecycle or implementation-authorization
changes require a new revision and explicit human approval.
