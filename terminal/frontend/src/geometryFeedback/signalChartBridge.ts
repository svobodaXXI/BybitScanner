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
 * Carry original Scanner rays and the owner's verified correction onto a chart
 * of the SAME signal/ticker even after the source pivots age out of its bars.
 * Reference geometry still comes exclusively from frozen UTC evidence.
 * For rays only, derive two *display-only* points at actual chart candle times
 * from the exact price/time line equation. Do NOT snap old pivots to new bars,
 * move stored anchors, change trading signals, or feed the derived points back
 * into the geometry-feedback store.
 *
 * The caller validates signal identity, symbol and account scope.
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
  if (chartCandles.length < 2)
    throw new Error("Current chart needs two closed candles for a ray");

  const currentTimes = chartCandles.map((candle) => Date.parse(candle.time));
  if (currentTimes.some((time, index) =>
      !Number.isSafeInteger(time) || time < 0 ||
      (index > 0 && time <= currentTimes[index - 1])))
    throw new Error("Invalid current chart timestamps");
  const indexOfTime = new Map(currentTimes.map((time, index) => [time, index]));

  const visible = (boundaries: readonly TimestampDrawing[]): DrawingObject[] => {
    // All source anchors and topology are validated against the immutable
    // historical window before any current-chart extrapolation is considered.
    const exact = projectSignalGeometry(boundaries, signalCandles).referenceDrawings;
    return exact.map((drawing, index) => {
      const original = boundaries[index];
      const indices = original.anchors.map((anchor) => indexOfTime.get(anchor.bar_open_time_ms));
      if (indices.every((at) => at !== undefined)) {
        return { ...drawing, anchors: drawing.anchors.map((anchor, i) => ({
          ...anchor, logical: indices[i]!,
        })) };
      }
      if (drawing.type === "horizontal") {
        return { ...drawing, anchors: [{ logical: 0, price: original.anchors[0].price }] };
      }
      if (drawing.type === "horizontal-ray") {
        const first = currentTimes.findIndex((time) => time >= original.anchors[0].bar_open_time_ms);
        if (first < 0) throw new Error("Source ray begins after the current chart");
        return { ...drawing, anchors: [{ logical: first, price: original.anchors[0].price }] };
      }
      if (drawing.type !== "ray") {
        // Historical finite segments and verticals must NOT be extended.
        throw new Error("Non-ray source pivot candle absent from current chart");
      }
      const [a, b] = original.anchors;
      const first = currentTimes.findIndex((time) => time >= b.bar_open_time_ms);
      if (first < 0 || first >= currentTimes.length - 1)
        throw new Error("Source ray has no two current candle times after its second pivot");
      const slope = (b.price - a.price) / (b.bar_open_time_ms - a.bar_open_time_ms);
      const prices = [currentTimes[first], currentTimes[first + 1]].map((time) =>
        a.price + slope * (time - a.bar_open_time_ms));
      if (prices.some((price) => !Number.isFinite(price) || price <= 0))
        throw new Error("Source ray cannot be projected to positive chart prices");
      return { ...drawing, anchors: [
        { logical: first, price: prices[0] }, { logical: first + 1, price: prices[1] },
      ] };
    });
  };

  const reference = visible(source);
  const corrected = visible(serializeReviewDrawings(reviewedDrawings, signalCandles));
  // Both layers are strictly read-only observations. The source remains dashed,
  // the owner's corrected version is solid, and both keep their original IDs.
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
