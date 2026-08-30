import type {
  Candle,
  MarketDataSnapshot,
  NormalizedOrderBook,
  PriceLevel,
  TradePrint,
  WorkspaceProjectionAuthority,
} from "../contracts/marketData";
import { projectSweepCenterRow } from "./domProjection";

type JsonRecord = Record<string, unknown>;

export type ProjectionDecision = "APPLIED" | "IGNORED_STALE" | "RESNAPSHOT_REQUIRED";

export interface WorkspaceProjectionState {
  authority: WorkspaceProjectionAuthority | null;
  snapshot: MarketDataSnapshot;
}

export interface ProjectionResult {
  decision: ProjectionDecision;
  state: WorkspaceProjectionState;
}

const record = (value: unknown): JsonRecord | null => (
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonRecord
    : null
);

const positiveInteger = (value: unknown): number | null => (
  Number.isInteger(value) && Number(value) > 0 ? Number(value) : null
);

const finitePositive = (value: unknown): number | null => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

const normalizeLevels = (value: unknown, descending: boolean): PriceLevel[] | null => {
  if (!Array.isArray(value)) return null;
  const levels = value.flatMap<PriceLevel>((raw) => {
    const item = record(raw);
    const price = finitePositive(item?.price);
    const quantity = finitePositive(item?.size);
    return price === null || quantity === null ? [] : [{ price, quantity }];
  });
  if (levels.length !== value.length || levels.length === 0) return null;
  return levels.sort((left, right) => descending
    ? right.price - left.price
    : left.price - right.price);
};

const normalizeCandle = (value: unknown): Candle | null => {
  const item = record(value);
  const startTime = positiveInteger(item?.startTime);
  const open = finitePositive(item?.open);
  const high = finitePositive(item?.high);
  const low = finitePositive(item?.low);
  const close = finitePositive(item?.close);
  if (
    startTime === null || open === null || high === null || low === null || close === null
    || high < Math.max(open, close) || low > Math.min(open, close)
  ) return null;
  return { time: new Date(startTime).toISOString(), open, high, low, close };
};

const normalizeTrade = (
  value: unknown,
  book: NormalizedOrderBook,
  browserReceivedAtMs: number,
  expectedSymbol: string,
): TradePrint | null => {
  const trade = record(value);
  if (
    !trade || typeof trade.id !== "string" || trade.symbol !== expectedSymbol
    || (trade.side !== "BUY" && trade.side !== "SELL")
  ) {
    return null;
  }
  const totalQuantity = finitePositive(trade.total_quantity);
  const totalNotionalUsdt = finitePositive(trade.total_notional_usdt);
  const firstExecutionPrice = finitePositive(trade.first_execution_price);
  const lastExecutionPrice = finitePositive(trade.last_execution_price);
  const sweepLowPrice = finitePositive(trade.sweep_low_price);
  const sweepHighPrice = finitePositive(trade.sweep_high_price);
  const tickSize = finitePositive(trade.tick_size);
  const tradeCount = positiveInteger(trade.trade_count);
  const sweptTicks = positiveInteger(trade.swept_ticks);
  const startedAtMs = positiveInteger(trade.started_at_ms);
  const endedAtMs = positiveInteger(trade.ended_at_ms);
  const sweptPriceRange = Number(trade.swept_price_range);
  const firstTradeSeq = positiveInteger(trade.first_trade_seq);
  const lastTradeSeq = positiveInteger(trade.last_trade_seq);
  const backendFirstReceivedAtMs = positiveInteger(trade.backend_first_received_at_ms);
  const backendLastReceivedAtMs = positiveInteger(trade.backend_last_received_at_ms);
  const finalizedAtMs = positiveInteger(trade.finalized_at_ms);
  if (
    totalQuantity === null || totalNotionalUsdt === null || firstExecutionPrice === null
    || lastExecutionPrice === null || sweepLowPrice === null || sweepHighPrice === null
    || tickSize === null || tradeCount === null || sweptTicks === null
    || startedAtMs === null || endedAtMs === null || sweepHighPrice < sweepLowPrice
    || !Number.isFinite(sweptPriceRange) || sweptPriceRange < 0
    || firstTradeSeq === null || lastTradeSeq === null || lastTradeSeq < firstTradeSeq
    || backendFirstReceivedAtMs === null || backendLastReceivedAtMs === null
    || finalizedAtMs === null
  ) return null;
  const correlation = record(trade.book_correlation);
  return {
    id: trade.id,
    side: trade.side,
    startedAtMs,
    endedAtMs,
    tradeCount,
    totalQuantity,
    totalNotionalUsdt,
    firstExecutionPrice,
    lastExecutionPrice,
    sweepLowPrice,
    sweepHighPrice,
    sweptPriceRange,
    sweptTicks,
    tickSize,
    rowOffset: projectSweepCenterRow(book, sweepLowPrice, sweepHighPrice, tickSize),
    firstTradeSeq,
    lastTradeSeq,
    backendFirstReceivedAtMs,
    backendLastReceivedAtMs,
    finalizedAtMs,
    browserReceivedAtMs,
    bookCorrelation: correlation ? {
      basis: "LATEST_BACKEND_KNOWN_AT_FINALIZATION",
      bookVersion: Number(correlation.book_version),
      updateId: Number(correlation.update_id),
      sequence: Number(correlation.sequence),
      exchangeTimestampMs: Number(correlation.exchange_ts_ms),
      matchingEngineCtsMs: correlation.matching_engine_cts_ms == null
        ? null : Number(correlation.matching_engine_cts_ms),
      backendReceivedAtMs: Number(correlation.backend_received_at_ms),
      bestBid: Number(correlation.best_bid),
      bestAsk: Number(correlation.best_ask),
    } : null,
    correlatedBookExchangeSkewMs: correlation
      ? Number(correlation.exchange_ts_ms) - endedAtMs : null,
    correlatedBookCtsSkewMs: correlation?.matching_engine_cts_ms == null
      ? null : Number(correlation.matching_engine_cts_ms) - endedAtMs,
  };
};

const workspaceSnapshot = (
  event: JsonRecord,
  requestedSymbol: string,
  requestedInterval: string,
  browserReceivedAtMs: number,
): WorkspaceProjectionState | null => {
  const symbol = typeof event.symbol === "string" ? event.symbol : "";
  const generation = positiveInteger(event.workspace_generation);
  const sequence = positiveInteger(event.event_sequence);
  const streamId = typeof event.stream_id === "string" ? event.stream_id : "";
  const book = record(event.book);
  const trades = record(event.trades);
  const candles = record(event.candles);
  const instrument = record(event.instrument);
  if (
    symbol !== requestedSymbol || generation === null || sequence === null || !streamId
    || book?.kind !== "book_snapshot" || trades?.kind !== "trade_bootstrap"
    || candles?.kind !== "candle_bootstrap" || candles.interval !== requestedInterval
    || event.state !== "READY" || book.state !== "READY"
    || trades.state !== "READY" || candles.state !== "READY"
  ) return null;
  const bids = normalizeLevels(book.bids, true);
  const asks = normalizeLevels(book.asks, false);
  const tickSize = finitePositive(instrument?.tick_size);
  const bookProjectionVersion = positiveInteger(book.projection_version);
  const bookUpdateId = positiveInteger(book.upstream_update_id);
  const bookSequence = positiveInteger(book.upstream_sequence);
  const tradeProjectionVersion = positiveInteger(trades.projection_version);
  const candleProjectionVersion = positiveInteger(candles.projection_version);
  if (!bids || !asks || tickSize === null || !Array.isArray(candles.candles) || !Array.isArray(trades.trades)) {
    return null;
  }
  if (
    bookProjectionVersion === null || bookUpdateId === null || bookSequence === null
    || tradeProjectionVersion === null || candleProjectionVersion === null
  ) return null;
  const normalizedCandles = candles.candles.map(normalizeCandle);
  if (normalizedCandles.length === 0 || normalizedCandles.some((item) => item === null)) return null;
  const normalizedBook: NormalizedOrderBook = {
    symbol,
    bids,
    asks,
    health: "READY",
    receivedAt: new Date(Number(book.source_timestamp ?? event.event_timestamp)).toISOString(),
    availableDepth: Math.min(bids.length, asks.length),
    backendReceivedAtMs: Number(book.source_timestamp ?? 0),
    updateId: bookUpdateId,
    sequence: bookSequence,
    bookVersion: bookProjectionVersion,
    browserReceivedAtMs,
  };
  const normalizedTrades = trades.trades.map((item) => normalizeTrade(
    item, normalizedBook, browserReceivedAtMs, symbol,
  ));
  if (normalizedTrades.some((item) => item === null)) return null;
  const authority: WorkspaceProjectionAuthority = {
    streamId,
    symbol,
    generation,
    eventSequence: sequence,
    interval: requestedInterval,
    state: event.state === "READY" ? "READY" : "DEGRADED",
  };
  return {
    authority,
    snapshot: {
      book: normalizedBook,
      candles: normalizedCandles as Candle[],
      tickSize,
      trades: normalizedTrades as TradePrint[],
      ownOrders: [],
      source: "LIVE_NORMALIZED",
      workspace: authority,
    },
  };
};

const applyBookDelta = (state: WorkspaceProjectionState, payload: JsonRecord): WorkspaceProjectionState | null => {
  const baseVersion = positiveInteger(payload.base_version);
  const newVersion = positiveInteger(payload.new_version);
  if (baseVersion !== state.snapshot.book.bookVersion || newVersion === null || newVersion <= baseVersion) return null;
  const apply = (current: readonly PriceLevel[], raw: unknown, descending: boolean): PriceLevel[] | null => {
    if (!Array.isArray(raw)) return null;
    const levels = new Map(current.map((item) => [String(item.price), item.quantity]));
    for (const value of raw) {
      const item = record(value);
      const price = finitePositive(item?.price);
      const quantity = Number(item?.size);
      if (price === null || !Number.isFinite(quantity) || quantity < 0) return null;
      if (quantity === 0) levels.delete(String(price));
      else levels.set(String(price), quantity);
    }
    return [...levels].map(([price, quantity]) => ({ price: Number(price), quantity }))
      .sort((left, right) => descending ? right.price - left.price : left.price - right.price);
  };
  const bids = apply(state.snapshot.book.bids, payload.bids, true);
  const asks = apply(state.snapshot.book.asks, payload.asks, false);
  if (!bids?.length || !asks?.length) return null;
  return {
    ...state,
    snapshot: {
      ...state.snapshot,
      book: {
        ...state.snapshot.book, bids, asks, health: "READY",
        availableDepth: Math.min(bids.length, asks.length),
        bookVersion: newVersion,
        updateId: Number(payload.upstream_update_id ?? state.snapshot.book.updateId),
        sequence: Number(payload.upstream_sequence ?? state.snapshot.book.sequence),
        backendReceivedAtMs: Number(payload.source_timestamp ?? 0),
        browserReceivedAtMs: Date.now(),
      },
    },
  };
};

export function applyWorkspaceEvent(
  current: WorkspaceProjectionState,
  rawEvent: unknown,
  requestedSymbol: string,
  requestedInterval: string,
  browserReceivedAtMs = Date.now(),
): ProjectionResult {
  const event = record(rawEvent);
  if (!event || typeof event.kind !== "string") return { decision: "RESNAPSHOT_REQUIRED", state: current };
  if (event.kind === "workspace_snapshot") {
    const eventSequence = positiveInteger(event.event_sequence);
    if (current.authority && event.stream_id === current.authority.streamId) {
      if (eventSequence === current.authority.eventSequence) {
        return { decision: "IGNORED_STALE", state: current };
      }
      if (eventSequence === null || eventSequence < current.authority.eventSequence) {
        return { decision: "RESNAPSHOT_REQUIRED", state: current };
      }
    }
    const next = workspaceSnapshot(event, requestedSymbol, requestedInterval, browserReceivedAtMs);
    return next
      ? { decision: "APPLIED", state: next }
      : { decision: "RESNAPSHOT_REQUIRED", state: current };
  }
  const authority = current.authority;
  if (!authority) return { decision: "RESNAPSHOT_REQUIRED", state: current };
  if (event.symbol !== requestedSymbol || authority.interval !== requestedInterval) {
    return { decision: "IGNORED_STALE", state: current };
  }
  if (
    event.stream_id !== authority.streamId || event.symbol !== authority.symbol
    || event.workspace_generation !== authority.generation
  ) return { decision: "IGNORED_STALE", state: current };
  const sequence = positiveInteger(event.event_sequence);
  if (sequence === authority.eventSequence) return { decision: "IGNORED_STALE", state: current };
  if (sequence === null || sequence !== authority.eventSequence + 1) {
    return { decision: "RESNAPSHOT_REQUIRED", state: current };
  }
  const payload = record(event.payload) ?? {};
  let next = current;
  if (event.kind === "book_delta") {
    const projected = applyBookDelta(current, payload);
    if (!projected) return { decision: "RESNAPSHOT_REQUIRED", state: current };
    next = projected;
  } else if (event.kind === "trade_batch") {
    if (!Array.isArray(payload.trades)) return { decision: "RESNAPSHOT_REQUIRED", state: current };
    const incoming = payload.trades.map((item) => normalizeTrade(
      item, current.snapshot.book, browserReceivedAtMs, requestedSymbol,
    ));
    if (incoming.some((item) => item === null)) return { decision: "RESNAPSHOT_REQUIRED", state: current };
    const byId = new Map(current.snapshot.trades.map((item) => [item.id, item]));
    for (const trade of incoming as TradePrint[]) byId.set(trade.id, trade);
    next = { ...current, snapshot: { ...current.snapshot, trades: [...byId.values()].slice(-80) } };
  } else if (event.kind === "candle_update") {
    if (payload.interval !== requestedInterval || !Array.isArray(payload.candles)) {
      return { decision: "RESNAPSHOT_REQUIRED", state: current };
    }
    const byTime = new Map(current.snapshot.candles.map((item) => [item.time, item]));
    for (const raw of payload.candles) {
      const candle = normalizeCandle(raw);
      const action = record(raw)?.action;
      if (!candle || (action !== "append" && action !== "replace")) {
        return { decision: "RESNAPSHOT_REQUIRED", state: current };
      }
      if (action === "replace" && !byTime.has(candle.time)) return { decision: "RESNAPSHOT_REQUIRED", state: current };
      if (action === "append" && byTime.has(candle.time)) return { decision: "RESNAPSHOT_REQUIRED", state: current };
      byTime.set(candle.time, candle);
    }
    next = { ...current, snapshot: { ...current.snapshot, candles: [...byTime.values()].sort(
      (left, right) => Date.parse(left.time) - Date.parse(right.time),
    ).slice(-1000) } };
  } else if (event.kind === "health") {
    const health = event.state === "READY" ? "READY" : event.state === "STALE" ? "STALE" : "DEGRADED";
    next = event.component === "book"
      ? { ...current, snapshot: { ...current.snapshot, book: { ...current.snapshot.book, health } } }
      : current;
  } else {
    return { decision: "RESNAPSHOT_REQUIRED", state: current };
  }
  const nextAuthority: WorkspaceProjectionAuthority = {
    ...authority,
    eventSequence: sequence,
    state: event.kind === "health" && event.component === "stream"
      ? authority.state
      : event.state === "READY" ? "READY" : "DEGRADED",
  };
  return {
    decision: "APPLIED",
    state: { ...next, authority: nextAuthority, snapshot: { ...next.snapshot, workspace: nextAuthority } },
  };
}
