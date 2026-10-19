# GEOMETRY FEEDBACK — Scanner/UI cross-owner contract proposal v1

Status: **PROPOSED — requires Scanner/Robot owner approval before any API/storage change**.
Scope: read-only retrieval of a frozen historic signal geometry and append-only owner annotation. No mutation of Scanner/Robot's active state.

## The actual gap verified in code

Existing UI `readScannerSignalContext()` in `terminal/frontend/src/orders/signalTakeProposal.ts` reads only `signal_id`, `symbol`, `target_price` from the terminal URL. The ChartPanel already embeds the editable DrawingOverlay, but its drawing anchors use **relative `logical` coordinates** and cannot be durable Scanner pivots. A URL must not carry the full OHLCV history or editable authoritative geometry. The frontend must request a persisted signal snapshot by ID.

## Scanner -> UI: read-only immutable snapshot

Suggested dedicated path (placeholder, not implemented): `GET /api/scanner/signal-geometry?signal_id=...`.

Fields, schemaVersion=1:
- `signal_id`, `snapshot_revision`, `symbol`, `market_category=linear`, `timeframe`, `pattern_type`, `pattern_stage`, `generated_at_utc`, `detector_version`, `geometry_algorithm_version`;
- `bars`: finite ordered candles `{open_time_ms, open, high, low, close, volume}` covering detection window and including enough context to replay confirmation; `bars_sha256`, `data_source`, `last_closed_bar_ms`;
- `pivots`: `{pivot_id,kind: HIGH|LOW,bar_open_time_ms,price,confirmation_bar_open_time_ms}`; only confirmed pivots may be labelled confirmed;
- `boundaries`: `{boundary_id,kind: upper|lower,anchors:[{bar_open_time_ms,price},{bar_open_time_ms,price}]}` plus pattern-specific attributes when needed;
- `account_scope` only when a signal is legitimately account-scoped, not invented in Scanner for public signals.

Requirements: closed-candle/no-lookahead provenance, original snapshot unchanged after review, each pivot/anchor references a bar within frozen candle window. If context is expired or incomplete, frontend says `Недоступен эталон сигнала`, not reconstructed geometry. Rendering may map timestamps to chart logical positions but persisted payload must **never store only logical positions**.

## UI -> review storage: explicit owner review

Suggested endpoint (placeholder, requires approval): `POST /api/geometry-feedback`, **not** an existing Robot/Scanner trading action. Payload:
- `schema_version=1`, `idempotency_key`, `signal_id`, `snapshot_revision`, `bars_sha256`;
- `label`: `CONFIRMED` | `GEOMETRY_CORRECTED` | `FALSE_POSITIVE` | `UNCERTAIN`;
- `corrected_pivots`, `corrected_boundaries`: full timestamp-based geometry only when `GEOMETRY_CORRECTED`; retain original IDs where same anchor is adjusted; explicitly mark additions/removals;
- `note` optional, bounded;
- reviewer identity and server receive time set **server-side**, not trusted from browser.

Response: `review_id`, `snapshot_revision`, `accepted_at_utc`, `status=RECORDED`. Save append-only, never silently overwrite prior reviews; use idempotency and predictable revision conflict response.

## Conflict and safety policy

- UI isolates a review copy of drawing objects; original signal geometry is immutable and visually distinguishable.
- On outdated revision, invalid pivot/candle times, invalid quantities, non-finite prices, incomplete geometry, invalid label, or multiple conflicting IDs: fail closed with actionable validation message.
- No live feedback to a running detector, active Scanner, PAPER_AUTO, orders, STOP/TAKE, or trade eligibility. Candidate improvements promoted only through offline replay, regression corpus, complete Scanner acceptance and explicit owner release/rollback.
- Store reviews independently of PAPER trading DB; bound storage and avoid long owner-thread calls.

## Approval questions for Scanner/PAPER_AUTO owner

1. Which **existing archive/source-of-truth** owns immutable signal ID, candle snapshot, geometry and detector build? Reuse it instead of adding duplicate storage.
2. What is its authoritative `signal_id`/revision and timestamp coordinate convention (UTC candle OPEN ms)?
3. Can it return geometry without invoking an expensive runtime re-scan or impacting existing owner/WS ingress?
4. Where should append-only feedback live outside the working PAPER DB, and which existing authenticated action mechanism is appropriate?
5. How to represent detector-specific edges (triangle first wave, wedge, horn, L-shape, Ikigai Box) without a lossy two-line-only common schema?

Next after agreement: frontend-only review overlay/label/payload validator using existing ChartPanel/DrawingOverlay; validate on one real full-fidelity archived signal.
