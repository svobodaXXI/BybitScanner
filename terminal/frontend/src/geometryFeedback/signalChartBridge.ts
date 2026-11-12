import type { Candle } from "../contracts/marketData";
import type { DrawingObject } from "../chart/drawingModel";
import { isValidCachedEditorDraft, serializeReviewDrawings, type TimestampDrawing } from "./geometryReviewDraft";

const expectedAnchorCount = (type: DrawingObject["type"]) =>
  ["horizontal", "horizontal-ray", "vertical"].includes(type) ? 1 : 2;

/**
 * Project immutable Scanner candle-time geometry onto the frozen chart window.
 * Never round, clamp, interpolate missing candles or use live market indices.
 */
export function projectSignalGeometry(
  source: readonly TimestampDrawing[],
  frozenCandles: readonly Candle[],
): { referenceDrawings: DrawingObject[]; editableDrawings: DrawingObject[] } {
  if (!frozenCandles.length) throw new Error("Frozen candle window is empty");
  const lookup = new Map<number, number>();
  let previous = -1;
  frozenCandles.forEach((candle, logical) => {
    const time = Date.parse(candle.time);
    if (!Number.isSafeInteger(time) || time < 0 || time <= previous)
      throw new Error("Invalid or unordered frozen candle timestamps");
    lookup.set(time, logical);
    previous = time;
  });

  const ids = new Set<string>();
  const referenceDrawings = source.map((boundary): DrawingObject => {
    if (!boundary.id || ids.has(boundary.id)) throw new Error("Duplicate or empty boundary ID");
    ids.add(boundary.id);
    if (boundary.anchors.length !== expectedAnchorCount(boundary.type))
      throw new Error("Incomplete source boundary");
    const anchors = boundary.anchors.map((anchor) => {
      const logical = lookup.get(anchor.bar_open_time_ms);
      if (logical === undefined) throw new Error("Source pivot candle absent from frozen window");
      if (!Number.isFinite(anchor.price) || anchor.price <= 0)
        throw new Error("Invalid source pivot price");
      return { logical, price: anchor.price };
    });
    if (anchors.length === 2 && anchors[0].logical >= anchors[1].logical)
      throw new Error("Source boundary pivots must advance in frozen candle time");
    return {
      id: boundary.id,
      type: boundary.type,
      anchors,
      style: { color: "#8195aa", lineWidth: 1.5 },
      locked: true,
      hidden: false,
    };
  });

  // Fresh objects and anchor arrays: editing must not modify reference geometry.
  const editableDrawings = referenceDrawings.map((drawing) => ({
    ...drawing,
    id: `editable:${drawing.id}`,
    anchors: drawing.anchors.map((anchor) => ({ ...anchor })),
    style: { color: "#e0b45b", lineWidth: 1.5 },
    locked: false,
  }));
  return { referenceDrawings, editableDrawings };
}


/**
 * Display the original Scanner rays and the owner's last verified/saved
 * correction on another chart of the same signal, as read-only overlays.
 * Preserve exact UTC anchor candles and prices; never snap to a nearby
 * candle, extrapolate from a ticker name, or store these lines as trades.
 *
 * The caller must check signal ID, symbol and timeframe. A missing source
 * candle fails closed instead of shifting rays to a different bar.
 */
export function projectVerifiedSignalOverlay(
  source: readonly TimestampDrawing[],
  signalCandles: readonly Candle[],
  reviewedDrawings: readonly DrawingObject[],
  chartCandles: readonly Candle[],
): DrawingObject[] {
  const frozenReference = projectSignalGeometry(source, signalCandles).referenceDrawings;
  if (!isValidCachedEditorDraft(reviewedDrawings, frozenReference, signalCandles))
    throw new Error("Unverified source/correction geometry");
  const reference = projectSignalGeometry(source, chartCandles).referenceDrawings;
  const corrected = projectSignalGeometry(
    serializeReviewDrawings(reviewedDrawings, signalCandles), chartCandles,
  ).referenceDrawings;
  // Both layers are observations, not editable signal submissions on the
  // current chart. Keep the distinct original/editable styles and IDs.
  return [
    ...reference,
    ...corrected.map((line, index) => ({
      ...line,
      style: { ...reviewedDrawings[index].style },
      referenceStroke: "solid" as const,
      locked: true,
    })),
  ];
}


/** Frame the original detector anchors when opening a historical Editor snapshot.
 * The ordinary trading chart continues following the latest candle.
 */
export function initialSourceGeometryRange(
  referenceDrawings: readonly DrawingObject[],
): { from: number; to: number } | null {
  const logicals = referenceDrawings.flatMap((drawing) =>
    drawing.anchors.map((anchor) => anchor.logical));
  if (!logicals.length || logicals.some((value) => !Number.isFinite(value) || value < 0))
    return null;
  const earliest = Math.min(...logicals);
  const latest = Math.max(...logicals);
  const margin = Math.max(12, Math.ceil((latest - earliest) * 0.2));
  return { from: earliest - margin, to: latest + margin };
}


/** Reopen the owner's exact frozen correction regardless of stored boundary order.
 * The store may reorder canonical boundaries; array-index matching incorrectly
 * rejects good reviews. Projection still fails closed on invalid UTC anchors,
 * duplicate IDs, malformed prices, or geometry not present in frozen candles.
 */
export function restoreSavedSignalCorrection(
  sourceReferences: readonly DrawingObject[],
  correctedBoundaries: readonly TimestampDrawing[],
  frozenCandles: readonly Candle[],
): DrawingObject[] {
  const saved = projectSignalGeometry(correctedBoundaries, frozenCandles).editableDrawings;
  if (saved.length !== sourceReferences.length || !sourceReferences.length)
    throw new Error("Saved correction topology does not match source lines");
  const byId = new Map(saved.map((drawing) => [drawing.id, drawing]));
  return sourceReferences.map((original) => {
    const editable = byId.get("editable:" + original.id);
    if (!editable || editable.type !== original.type)
      throw new Error("Saved correction topology does not match source lines");
    return editable;
  });
}


export type RetrospectiveOhlc = {
  open_time_ms: number; open: number; high: number; low: number; close: number;
};

/** Add server-verified later closed candles without changing Scanner source.
 * This is a review-time view, NEVER a source-time replacement for a signal.
 */
export function appendRetrospectiveCandles(
  source: readonly Candle[],
  continuation: readonly RetrospectiveOhlc[],
  timeframe: string,
  asOfMs: number,
): Candle[] {
  const intervals: Record<string, number> = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "1d": 86_400_000,
    "1": 60_000, "5": 300_000, "15": 900_000, "60": 3_600_000, "D": 86_400_000,
  };
  const step = intervals[timeframe];
  const originalEnd = Date.parse(source.at(-1)?.time ?? "");
  if (!source.length || !step || !Number.isSafeInteger(originalEnd) ||
      !Number.isSafeInteger(asOfMs) || continuation.length < 1 ||
      continuation.length > 1000 || source.length + continuation.length > 2000 ||
      asOfMs !== originalEnd + continuation.length * step)
    throw new Error("Некорректное продолжение исторических свечей");
  let previous = originalEnd;
  const added = continuation.map((bar) => {
    if (!Number.isSafeInteger(bar.open_time_ms) ||
        bar.open_time_ms !== previous + step) throw new Error("Пропуск свечи в истории");
    const values = [bar.open, bar.high, bar.low, bar.close];
    if (values.some((value) => typeof value !== "number" ||
        !Number.isFinite(value) || value <= 0) ||
        bar.high < Math.max(bar.open, bar.close) ||
        bar.low > Math.min(bar.open, bar.close))
      throw new Error("Некорректная историческая свеча");
    previous = bar.open_time_ms;
    return {
      time: new Date(bar.open_time_ms).toISOString(),
      open: bar.open, high: bar.high, low: bar.low, close: bar.close,
    };
  });
  return [...source, ...added];
}
