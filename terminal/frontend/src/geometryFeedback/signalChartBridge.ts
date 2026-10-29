import type { Candle } from "../contracts/marketData";
import type { DrawingObject } from "../chart/drawingModel";
import type { TimestampDrawing } from "./geometryReviewDraft";

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
    anchors: drawing.anchors.map((anchor) => ({ ...anchor })),
    style: { color: "#e0b45b", lineWidth: 1.5 },
    locked: false,
  }));
  return { referenceDrawings, editableDrawings };
}
