# CR-TRADING-INTELLIGENCE-001 — Trading Intelligence and Paper Trader Roadmap Research

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-TRADING-INTELLIGENCE-001",
  "title": "Trading Intelligence and Paper Trader Roadmap Research",
  "status": "IN_PROGRESS",
  "revision": "1.8",
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
    "Record LONG_CONTINUATION / High-Base continuation as a roadmap-level setup family without final thresholds or implementation authorization",
    "Record the unified Trade Candidate fusion, evidence provenance, guard, trigger-expiry, lifecycle and history architecture without selecting implementation mechanics",
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
    "Head and Shoulders and Inverse Head and Shoulders are one mirror-symmetric extrema-sequence plus neckline detector family",
    "HS/IHS hard geometry is five sequential pivots LS, N1, HEAD, N2 and RS; HS requires the head above both shoulders and IHS mirrors this below both shoulders",
    "HS/IHS neckline is defined through N1 and N2 and may be horizontal, rising or falling",
    "HS/IHS separates hard geometry, quality/scoring, market context, confirmation and signal admission",
    "Perfect shoulder symmetry is not a hard requirement; natural asymmetry belongs to quality/scoring",
    "Prior trend is market context rather than base pivot geometry, and volume is confirmation/confidence evidence rather than a hard geometry gate",
    "HS/IHS candidate lifecycle is conceptually FORMING to STRUCTURALLY_VALID to CONFIRMED or INVALIDATED, and FORMING may be observed before Right Shoulder or neckline-breakout confirmation",
    "Early or right-shoulder, neckline breakout and neckline retest are future trading events separate from detector geometry",
    "HS/IHS profitability is not assumed and requires future historical evaluation and Paper Trader evidence",
    "HS/IHS numeric tolerances remain open for calibration on Bybit perpetual data",
    "The GRVTUSDT falling-wedge example records a future robust wick-aware boundary-fitting hypothesis: representative boundaries should consider significant extrema, near-touches, violation magnitude, tolerated outliers and volatility-normalized tolerance rather than only two anchors",
    "Wick-aware fitting applies symmetrically to upper high-wicks and lower low-wicks, permits limited small outliers and is not asserted to be an already proven optimal algorithm",
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
    "A forming eligible pattern may activate SYMBOL_IN_PLAY and microstructure monitoring before breakout while exact geometry maturity and entry thresholds remain open",
    "LONG_CONTINUATION is a distinct bullish continuation setup concept defined by impulse, gain retention, high-base contraction, continuation pressure and a later execution trigger; it may include Flag-like geometry but does not absorb the independently owned Flag detector family",
    "LONG_CONTINUATION evidence separates Setup Quality, Failure Risk and Trigger Confidence rather than collapsing the concept into one binary pattern flag or one universal score",
    "LONG_CONTINUATION impulse evidence is normalized by volatility and time rather than one fixed percentage across Bybit instruments; volume is supporting evidence and not a mandatory hard filter",
    "LONG_CONTINUATION negative evidence is tracked separately, and loss of structurally important base support may invalidate the setup rather than merely reduce quality",
    "LONG_CONTINUATION Pattern or Strategy identifies where a promising continuation develops, while future Microstructure or Execution decides when entry is justified using price response relative to aggressive flow rather than raw buy/sell volume alone",
    "Controlled lower-base pullback, compression below resistance and breakout-plus-acceptance remain three future LONG_CONTINUATION entry modes without approving execution logic",
    "Structure, Setup, Evidence and Decision or Trade Candidate are separate concepts; overlapping detector observations describing one market opportunity are fused or deduplicated rather than emitted as duplicate independent signals",
    "Trade Candidate fusion considers symbol, timeframe or market region, structural area and temporal overlap; an INVALIDATED candidate is not resurrected when a genuinely new later structure appears",
    "Evidence retains family and source provenance, with initial families GEOMETRY, MOMENTUM, RETENTION, PRICE_STRUCTURE, VOLUME, CANDLE_CONFIRMATION, MARKET_CONTEXT and ORDER_FLOW; overlapping observations are not automatically counted as independent full-weight evidence",
    "Setup Quality, Failure Risk and Trigger Confidence remain separate; structurally decisive negative evidence may hard-veto or invalidate a candidate instead of being numerically overpowered by unrelated positive evidence",
    "Persistent Trade Candidate state is separate from ephemeral execution triggers; triggers have future TTL or expiry semantics, and trigger expiry does not necessarily invalidate the underlying candidate",
    "The conceptual Trade Candidate lifecycle is DETECTED to WATCH to READY to TRIGGERED to ENTERED, with terminal non-success states INVALIDATED and EXPIRED",
    "Each Trade Candidate has a unique candidate_id and preserves lifecycle, structures, setups, evidence fingerprint, quality/failure evolution, trigger history, entry or no-entry reason, invalidation or expiry reason and eventual outcome where applicable",
    "Final scoring formulas, weights, thresholds, TTLs and calibration constants remain parameterizable and require later paper-trading or backtest evidence",
    "The primary economic objective of Scanner, Trading Intelligence, Trading Workspace, Paper Robot and the future Trading Robot is sustainable positive expectancy and financial result at acceptable risk after commissions, slippage, actual execution quality and other execution frictions",
    "Analytical complexity and pattern-detection accuracy are means to the economic objective rather than independent end goals",
    "Geometry Engine remains a core development area, and geometric features must progressively be evaluated by their real trading usefulness without weakening existing Geometry requirements",
    "After a Paper Robot exists, Geometry and Signal Intelligence follow a closed evidence-driven loop from hypothesis through paper trades, execution and outcome data, profitability and risk analysis, feature evaluation, refinement and repeated validation",
    "Primary future Trading Robot evaluation includes realized PnL, expectancy per trade, profit factor, maximum drawdown, robustness across market regimes and survivability through losing streaks without unacceptable risk; win rate and pattern accuracy remain diagnostic",
    "Paper Robot is the transition from technical-correctness verification to empirical validation of positive expectancy under conditions approximating real execution",
    "The economic objective is an empirical validation and optimization target, not a promise or guarantee of profit",
    "This strategic checkpoint does not remove or weaken any existing Geometry, execution or safety requirement"
  ],
  "unresolved_decisions": [
    "Canonical English identity and exact semantics of the user term Восходящая звезда",
    "Exact initial candlestick formation catalog and evidence/scoring policy",
    "Double Top / Double Bottom detector contracts and shared primitive boundary",
    "HS/IHS exact pivot, symmetry, neckline, lifecycle, confirmation and invalidation thresholds calibrated on Bybit perpetual data",
    "Robust wick-aware wedge boundary-fitting objective, volatility normalization, outlier policy and validation dataset",
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
    ,"LONG_CONTINUATION exact schemas, ATR/volatility normalization, thresholds, weights, quality/risk/trigger calibration, duration, invalidation and lifecycle transitions"
    ,"LONG_CONTINUATION exact controlled-pullback, resistance-compression and breakout-acceptance entry criteria"
    ,"Trade Candidate fusion association and deduplication thresholds, structural-region representation and new-candidate boundary after invalidation"
    ,"Evidence fingerprint schema, within-family overlap policy, cross-family independence policy and later expectancy calibration"
    ,"Hard-veto catalog, trigger TTL values, lifecycle transition mechanics and final Setup Quality, Failure Risk and Trigger Confidence formulas"
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
  "hs_ihs_detector_family_research_disposition": {
    "status": "SUFFICIENT_FOR_ROADMAP_LEVEL_DESIGN",
    "research_stage": "COMPLETED",
    "implementation_spec_status": "NOT_READY",
    "implementation": "NOT_STARTED_NOT_AUTHORIZED",
    "exact_thresholds_tolerances_and_data_calibration": "OPEN",
    "next_project_focus": "TRADING_TERMINAL_TRADING_WORKSPACE"
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
  "current_checkpoint": "PROFITABILITY_DRIVEN_SYSTEM_EVALUATION_PRINCIPLE_RECORDED",
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
    "status": "PROFITABILITY_DRIVEN_SYSTEM_EVALUATION_PRINCIPLE_RECORDED_NOT_IMPLEMENTED"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Human-authorized durable planning and research checkpoint; implementation explicitly not authorized", "date": "2026-08-18"},
    {"revision": "1.1", "reason": "Recorded accumulated market-microstructure research as sufficient for roadmap-level design while preserving open formulas, non-final roadmap and no implementation authorization", "date": "2026-08-18"},
    {"revision": "1.2", "reason": "Recorded Flag detector-family research as sufficient for roadmap-level design while preserving open schemas and thresholds, a non-final roadmap and no implementation authorization", "date": "2026-08-19"},
    {"revision": "1.3", "reason": "Included the authorized Assistant Protocol v4.9 enforcement strengthening in the Flag research documentation checkpoint without changing research lifecycle or implementation authorization", "date": "2026-08-19"},
    {"revision": "1.4", "reason": "Recorded the human-authorized Trading Workspace and Telegram Mini App requirements, safety architecture, external references, gap analysis and dependency-aware roadmap while preserving research-only lifecycle and no implementation authorization", "date": "2026-08-20"},
    {"revision": "1.5", "reason": "Closed HS/IHS roadmap-level research, recorded the robust wick-aware wedge boundary-fitting observation and selected Trading Terminal / Trading Workspace as the next active development focus without authorizing implementation", "date": "2026-08-20"},
    {"revision": "1.6", "reason": "Documentation-only roadmap-level checkpoint recording LONG_CONTINUATION / High-Base continuation evidence, anti-evidence, separated quality/failure/trigger semantics, future entry modes and Pattern-versus-Microstructure boundary without final thresholds, detector implementation or change to the active Trading Workspace focus", "date": "2026-08-22"},
    {"revision": "1.7", "reason": "Documentation-only architecture checkpoint recording unified Trade Candidate fusion and deduplication, evidence provenance and anti-double-counting, separate failure guards, ephemeral trigger expiry, conceptual candidate lifecycle and durable history for later evidence-based calibration without final numerical policy, implementation authorization or change to Trading Workspace Stage 8", "date": "2026-08-22"},
    {"revision": "1.8", "reason": "Documentation-only strategic checkpoint recording profitability after execution frictions and acceptable risk as the primary economic objective, Geometry as a continuing core development area, the future Paper Robot evidence loop and economic Robot success criteria without changing Geometry, execution or safety requirements or implementation authorization", "date": "2026-08-24"}
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
and planning remain active. HS/IHS research is complete at roadmap-design level; remaining detector
research is deferred by the Trading Terminal focus. The roadmap remains
non-final, ROADMAP_SPEC remains unauthorized, and any later implementation requires explicit human approval.

## HS / Inverse HS detector-family research closure

HS and IHS are one mirror-symmetric detector family built from five sequential pivots:
`LS — N1 — HEAD — N2 — RS`. In HS the Head is above both shoulders; IHS mirrors this below them.
The neckline passes through N1 and N2 and may be horizontal, rising or falling. Horizontal neckline is
not a validity requirement.

Hard geometry remains separate from quality/scoring, market context, confirmation and signal admission.
Perfect shoulder symmetry is not required; natural price/time asymmetry is quality evidence. Prior trend
is context rather than base pivot geometry. Volume may affect confirmation/confidence but is not a hard
geometry gate.

The conceptual lifecycle is `FORMING — STRUCTURALLY_VALID — CONFIRMED` or `INVALIDATED`. A forming
candidate may be observable before Right Shoulder completion or neckline-breakout confirmation. Early/
right-shoulder, neckline-breakout and neckline-retest events belong to later trading policy, not detector
geometry. Profitability is not assumed and must later be evaluated historically and through Paper Trader.
No numeric tolerance is approved; pivot, symmetry, neckline, confirmation and invalidation thresholds
require calibration on Bybit perpetual data. Research is complete at roadmap-level architecture only;
production implementation is `NOT_STARTED_NOT_AUTHORIZED`.

## Geometry research observation — robust wick-aware wedge boundaries

The user-reviewed GRVTUSDT falling-wedge example suggests that an upper boundary fitted mainly through
two anchors may leave a systematic number of meaningful high-wicks outside the structure. Future Geometry
Engine research should evaluate a representative, tolerance-aware fit using valid touches/near-touches,
extrema-to-line distance, violation magnitude, permitted outliers and structure-scale or volatility
normalization such as ATR. The mirrored principle applies to lower boundaries and low-wicks.

The goal is a geometrically representative boundary supported by the largest meaningful contact set,
not forced containment of every wick. Several small outliers may be valid. This is a research hypothesis
and validation requirement, not a proven optimum, algorithm change or implementation authorization.

## Trading Workspace research checkpoint

The preferred future mobile operator surface is a Telegram Mini App, provisionally named the
BybitScanner Trading Workspace. A Scanner signal may navigate to the exact-symbol workspace, but a
new signal never implies that no position or order already exists. Before any position-changing
operation, normalized domain state must expose mode (`PAPER`, `DEMO`, `LIVE`), origin where known
(`ROBOT`, `TERMINAL`, `PAPER`, `EXTERNAL`, `UNKNOWN`), side, size, entry, mark price, leverage, live
PnL/ROE and active order/protection state. Intent is explicit (`OPEN/ADD LONG`, `OPEN/ADD SHORT`,
`REDUCE`, `CLOSE`); adding exposure shows current, requested and resulting exposure.

The Workspace scope includes symbol selection, live/current candles, Scanner geometry, market-coordinate
drawings, entry/exit and position overlays, Market and Limit commands, TP/SL, partial/full close, Open
Positions, history and live robot reasoning context (`strategy`, `setup`, `pattern`, `signal_id`,
`timeframe`, `entry_reason`, `robot_decision`, confidence/evidence). Scanner, User and Trading layers
remain independently toggleable. Limit, TP and SL lines drag locally and submit only after drag end,
validation and required confirmation; numeric input remains available. Individual close requires
confirmation. Mode-specific Close All Paper/Demo/Live requires two independent confirmation stages.

The UI owns neither execution truth nor mode-specific trading logic. Strategy owns neither exchange
transport nor pattern identity. Paper, later Demo and later Live share `ExecutionPort`. For real modes
Bybit is authoritative; REST/UI acknowledgement is not proof of execution. Reconciliation compares
expected state with actual positions, orders and executions. Outcomes cover match; external close,
partial close, add or reverse; missing/unknown order; mismatches; and unknown/ambiguous. Dangerous
uncertainty stops new automatic entries, reconciles and informs without blindly restoring state.

External trading through Bybit, MetaScalp or other interfaces is supported. Unlinked activity is
`EXTERNAL` or `UNKNOWN`. Manual takeover sets a durable override and blocks robot reassertion until an
explicit safe return to AUTO. Manual, emergency or external close creates a persistent re-entry lock
for the old signal lifecycle. Logical commands require durable identity, trade/signal linkage and
idempotency, including future `orderLinkId` mapping. Timeout after submit is `UNKNOWN` pending
reconciliation, not automatically failed and not blindly retried.

Startup begins with AUTO disabled, fetches actual state and reconciles before automation resumes after
crash, shutdown, power/network loss or private-stream disconnect. Critical protection should reside
exchange-side where supported, separate from smart management. An independent heartbeat/watchdog is a
later requirement because a failed host cannot reliably report its own failure. Presentation feedback
remains replaceable and independent of safety logic; third-party media is not project-owned content.

Persistent history is researched as Trade plus append-only TradeEvent evidence for signals, submissions,
fills, amendments, TP/SL, partial/external/manual changes, reconciliation, close and errors. Exact event
and order-state taxonomies remain open; candidate draft through terminal/unknown states are not final.

### External implementation references

Future research retains Freqtrade (lifecycle, dry-run, persistence, locks and recovery), Hummingbot
(connectors, tracking, user streams and retries), OpenAlgo Charts (chart trading and drawings),
TradeCanvas (execution abstraction and chart integration), and official Bybit V5 documentation as
authoritative for order, execution, position, `orderLinkId`, limits, Demo and TP/SL behavior. Adoption
requires current maintenance, license, compatibility, architecture fit and dependency-risk review;
none is an approved dependency.

### Current repository gap analysis

* `EXISTS`: Scanner candle ingestion, Wedge/Triangle analytics, shared geometry/pivots, public Bybit
  access and Telegram-oriented notifications; these remain upstream evidence capabilities.
* `PARTIAL`: signal identity/memory, chart rendering, realtime data and Paper/replay research; none is
  authoritative trading state or a unified workspace.
* `ABSENT`: trade/order/fill/position/account implementations, event journal, idempotent command store,
  reconciliation, override/re-entry locks, recovery coordinator, private-stream authority, execution
  modes, Mini App/Workspace and watchdog.
* `PLANNED / RESEARCHED ONLY`: Paper/L2 simulation, liquidity observations, Workspace, chart selection,
  Demo/Live and all safety/recovery mechanisms above.

Detector geometry and normalized observations are reusable upstream; detector internals, signal-memory
dictionaries, chart helpers and REST helpers must not acquire trading truth or UI responsibility.

## LONG_CONTINUATION / High-Base continuation concept

`LONG_CONTINUATION` is a roadmap-level bullish continuation setup family for a strong preceding impulse that
retains most of its gain and consolidates near the impulse high before possible continuation. Its canonical
conceptual sequence is:

`IMPULSE -> RETENTION -> HIGH BASE -> CONTRACTION -> CONTINUATION PRESSURE -> EXECUTION TRIGGER`.

Possible geometric manifestations include High Base, High Tight Flag-like structure, Bull Flag, Ascending
Compression, VCP-like Base and Irregular High Base. Textbook geometry is not required when the underlying
continuation structure is present. The family complements Wedge/Triangle, Flag, HS/IHS and Double Top/Bottom;
it does not absorb every Flag or replace the separately owned Flag detector family. Candlestick formations
remain supporting evidence. The existing moderate LONG preference stays in Strategy/Decision and does not
alter geometry ownership.

### Measurable positive evidence

* `Impulse Strength`: displacement, speed and directional efficiency of the preceding bullish move,
  normalized against ATR/recent volatility and elapsed time rather than one universal fixed percentage.
* `Gain Retention`: the fraction of the impulse preserved during consolidation; deep giveback lowers quality.
* `High Proximity`: closeness of the base to the impulse high as evidence, never an independent BUY signal.
* `Base Quality`: duration and structure, pullback depth, possible rising lows, decreasing pullback size and
  ATR/range contraction.
* `Continuation Pressure`: repeated resistance approaches, weak seller displacement, rising lows and reduced
  rejection depth.
* `Volume`: optional supporting evidence that may contract inside the base and expand near continuation; it is
  not a mandatory hard filter.

### Anti-evidence and invalidation

Failure Risk tracks Deep Giveback, Falling Highs, Expanding Pullbacks, Repeated Failed Breakouts, Heavy Sell
Response or strong upper rejection, loss of structural Base Support and Time Decay without progress relative
to the original impulse. Loss of structurally important base support may invalidate the setup rather than
merely subtract score.

### Scoring and future entry boundary

The concept preserves three separate outputs: `Setup Quality` for impulse/retention/base structure,
`Failure Risk` for distribution or failure evidence and `Trigger Confidence` for developing entry evidence.
Illustrative values such as Quality 88, Failure 14 and Trigger 73 are examples only and do not approve any
threshold, weight or formula. Conceptual `WATCH`, `READY` and `INVALIDATED` states may be evaluated later, but
no implementation-specific state machine is selected here.

Future entry research preserves three modes: a controlled pullback/bounce from the lower base, compression
directly below resistance and breakout plus acceptance or successful retest rather than blind purchase of the
first breakout candle.

Pattern/Strategy owns “where is a promising continuation setup developing?” Future Execution/Microstructure
owns “when is the actual entry justified?” Future DOM/Tape evidence may include Ask consumption, aggressive
Buy prints, weak downward response to selling, seller absorption/replenishment and price progress relative to
aggressive volume. Disappearing Bid liquidity or aggressive buying without price progress may be negative
evidence. Raw buy/sell volume alone is insufficient; price response and price progress relative to flow are
required context. No DOM/Tape execution logic is implemented or authorized by this checkpoint.

Exact numerical thresholds, weights, schemas, calibration, invalidation policy and entry logic remain open.
`LONG_CONTINUATION` implementation is `NOT_STARTED_NOT_AUTHORIZED`. This checkpoint does not alter the current
Trading Workspace Stage 8 authorization.

### Dependency-aware roadmap hypothesis

1. Durable requirements, repository gap and architecture checkpoint (this record).
2. Core domain contracts: identity, mode/source/intent, order/fill/position/account, ExecutionPort,
   journal events, idempotency, manual override and re-entry locks.
3. Persistence, deterministic Paper execution and append-only journal, with conservative Limit policy.
4. Reconciliation, startup recovery and uncertain-command safety validated in Paper.
5. Chart-engine decision/prototype comparing OpenAlgo Charts, TradeCanvas and TradingView Lightweight
   Charts plus required custom functionality; no selection or implementation occurs here.
6. Telegram Mini App Paper Workspace MVP after normalized state and safety foundations exist.
7. Bybit Demo after verified Paper lifecycle, recovery and reconciliation.
8. Bybit Live only after explicit safety evidence and separate human authorization.
9. Later observability, drawings, override refinement, watchdog, analytics/replay and presentation.

This moves idempotency, reconciliation, recovery and manual override ahead of the chart MVP. Tracks A
(Trading Intelligence), B (Trading Foundation) and C (Microstructure) can proceed independently; Track D
(Workspace/operator surface) joins only through normalized contracts. HS/IHS implementation remains
not started and not authorized.

### Unresolved Workspace decisions

Exact schemas/states; Demo/Live differences; Bybit private-stream recovery; source linking and
`orderLinkId` policy; Paper Limit approximation; Telegram security, deployment and degraded UX;
watchdog boundary; and chart-engine selection remain open. The chart comparison covers license,
maintenance, mobile touch, Telegram fit, realtime candles, draggable lines, drawings/saved state,
Scanner overlays, performance, integration complexity and dependency risk.

## Trade Candidate fusion and evidence architecture

Independent structure and setup detectors do not compete for one exclusive label. The architecture separates:

* `Structure`: what geometric or structural formation exists, such as Flag, Wedge, Triangle, Double Bottom
  or Irregular High Base;
* `Setup`: what trading scenario the structure participates in, such as `LONG_CONTINUATION`, `PRE_BREAKOUT`
  or `REVERSAL`;
* `Evidence`: why the candidate is credible or risky;
* `Decision / Trade Candidate`: the unified actionable opportunity.

One region may therefore be one `LONG_CONTINUATION` candidate with Bull Flag plus Ascending Compression
structures. Detectors that describe the same opportunity do not emit duplicate independent trade candidates
or signals. Fusion/deduplication considers symbol, timeframe or market region, structural area and temporal
overlap. A structurally `INVALIDATED` candidate is not resurrected: a genuinely new later structure creates a
new candidate.

### Evidence provenance and failure guards

Detectors publish observations/evidence with provenance rather than scores that are naively summed. Initial
conceptual evidence families are `GEOMETRY`, `MOMENTUM`, `RETENTION`, `PRICE_STRUCTURE`, `VOLUME`,
`CANDLE_CONFIRMATION`, `MARKET_CONTEXT` and `ORDER_FLOW`. Multiple observations within a family remain
available for explainability, but overlapping evidence does not automatically receive multiple full weights.
For example, the same range contraction observed by Bull Flag and `LONG_CONTINUATION` is one underlying
`GEOMETRY_COMPRESSION` contribution, not two independent contributions. Genuinely independent information
families may strengthen the candidate.

The evidence fingerprint/provenance is durable so later Paper Trading and backtest analysis can measure which
combinations produce expectancy. Positive Setup Quality remains separate from Failure Risk. Negative evidence
may raise Failure Risk, while a structurally decisive condition may act as a hard veto and move the candidate
to `INVALIDATED`; unrelated positive evidence cannot numerically overpower that structural failure. The exact
hard-veto catalog is open.

### Persistent candidates and ephemeral triggers

A Trade Candidate may remain valid for an extended period, while an execution trigger is short-lived and
state/time bounded. Future Tape/DOM confirmation has TTL/expiry semantics and cannot remain actionable after
its microstructure condition disappears. If a trigger expires without entry, the underlying candidate need
not die; current market state may return or retain it in `READY` or `WATCH` pending fresh confirmation. Exact
TTL values are not approved.

The conceptual lifecycle is:

`DETECTED -> WATCH -> READY -> TRIGGERED -> ENTERED`

with terminal non-success states `INVALIDATED` and `EXPIRED`. `DETECTED` is initial recognition; `WATCH` is
promising but immature; `READY` is mature enough to await execution evidence; `TRIGGERED` owns a currently
valid ephemeral entry trigger; `ENTERED` records that entry decision/execution occurred; `INVALIDATED` records
structural or hard-veto failure; and `EXPIRED` records staleness without requiring structural invalidation.
Implementation mechanics and exact transitions remain open.

### Candidate identity, history and ownership boundaries

Every Trade Candidate has a unique `candidate_id`. Durable history conceptually preserves detection time,
contributing structures/setups, evidence fingerprint/provenance, quality and failure evolution, triggers
created or expired, entry/no-entry reason, invalidation/expiry reason and eventual trade outcome where
applicable. This supports later expectancy, MAE/MFE, win-rate and other outcome analysis instead of arbitrary
manually invented weights.

`Setup Quality`, `Failure Risk` and `Trigger Confidence` remain separate and parameterizable. No formula,
weight, threshold, TTL or calibration constant is approved here. Pattern/Structure owns what exists;
Setup/Strategy owns the trading scenario; Evidence owns credibility and risk; Execution/Microstructure owns
when entry is justified; and Decision owns whether the unified candidate becomes a trade. Candlestick
formations remain supporting evidence rather than duplicate candidates. Future DOM/Tape `ORDER_FLOW` evidence
fits this model without redesign.

This architecture checkpoint is documentation only. Production implementation is
`NOT_STARTED_NOT_AUTHORIZED`, and Trading Workspace Stage 8 authorization is unchanged.

## Profitability-driven system evaluation principle

### Primary economic objective

The ultimate and primary objective of Scanner, Trading Intelligence, Trading Workspace, Paper Robot and the
future Trading Robot is sustainable positive expectancy and financial result at acceptable risk after
commissions, slippage, actual execution quality and other real execution costs and frictions. Their
analytical and infrastructure components are means to this objective rather than independent end goals.
High analytical complexity or nominal pattern-detection accuracy alone does not justify added complexity
unless evidence shows improved trading results or risk management.

This economic objective is an empirical validation and optimization target, not a promise or guarantee of
profit.

### Geometry remains a core development area

This principle neither ends nor lowers the importance of Geometry Engine improvement. Geometry quality
directly affects the ability to distinguish potentially tradeable structures from noise and weak setups.
Geometric features must progressively be evaluated by their real trading usefulness. This strategic
checkpoint does not remove or weaken any existing Geometry requirement, and any later ranking, admission,
formula or threshold change remains evidence-dependent and separately governed.

### Profitability feedback loop

After a Paper Robot exists, Geometry and Signal Intelligence must improve through a closed, evidence-driven
loop rather than visual or expert evaluation alone:

`Geometry / Signal hypothesis -> paper trades -> execution and outcome data -> profitability and risk analysis -> feature evaluation -> refinement -> repeated validation`.

Reproducible evidence that combinations of geometric or signal features produce materially better
expectancy may justify later refinement, subject to the normal ChangeRequest lifecycle and validation.

### Robot success metrics and Paper Robot role

Primary future Trading Robot quality criteria include realized PnL, expectancy per trade, profit factor,
maximum drawdown, robustness across market regimes and survivability through losing streaks without
unacceptable risk. Win rate and pattern accuracy remain useful diagnostics, but they do not replace the
economic objective.

Paper Robot is the transition from verifying that the system works technically to empirically testing
whether the integrated trading system can produce positive expectancy under conditions approximating real
execution. Evaluation must include commissions, slippage, execution quality and other modeled frictions.
All existing execution and safety requirements remain binding and unchanged.

## Amendment rule

Material scope, approved decision, risk, acceptance, lifecycle or implementation-authorization
changes require a new revision and explicit human approval.
