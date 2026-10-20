import type { Candle } from "../contracts/marketData";
import type { DrawingObject } from "../chart/drawingModel";

/**
 * Draft-only conversion. Use the *frozen* signal candle window, never live market
 * candles. No trading API calls, side effects, persistence or silent index clamping.
 */
export type TimestampAnchor = { bar_open_time_ms: number; price: number };
export type TimestampDrawing = {
  id: string;
  type: DrawingObject["type"];
  anchors: TimestampAnchor[];
};
export type GeometryReviewDraft = {
  schema_version: 1;
  signal_id: string;
  snapshot_revision: string;
  bars_sha256: string;
  label: "CONFIRMED" | "GEOMETRY_CORRECTED" | "FALSE_POSITIVE" | "UNCERTAIN";
  corrected_boundaries: TimestampDrawing[];
};

function candleTimes(candles: readonly Candle[]): number[] {
  if (!candles.length) throw new Error("Frozen candle window is empty");
  const times = candles.map((candle) => Date.parse(candle.time));
  if (times.some((time) => !Number.isSafeInteger(time) || time < 0))
    throw new Error("Invalid candle timestamp");
  if (times.some((time, index) => index > 0 && time <= times[index - 1]))
    throw new Error("Candle timestamps must be strictly increasing");
  return times;
}

export function serializeReviewDrawings(
  drawings: readonly DrawingObject[],
  frozenCandles: readonly Candle[],
): TimestampDrawing[] {
  const times = candleTimes(frozenCandles);
  const ids = new Set<string>();
  return drawings.map((drawing) => {
    if (!drawing.id || ids.has(drawing.id)) throw new Error("Duplicate/empty drawing ID");
    ids.add(drawing.id);
    if (drawing.anchors.length !== (["horizontal", "horizontal-ray", "vertical"].includes(drawing.type) ? 1 : 2))
      throw new Error("Incomplete drawing geometry");
    return {
      id: drawing.id,
      type: drawing.type,
      anchors: drawing.anchors.map(({ logical, price }) => {
        if (!Number.isInteger(logical) || logical < 0 || logical >= times.length)
          throw new Error("Drawing anchor does not map to a frozen candle");
        if (!Number.isFinite(price) || price <= 0)
          throw new Error("Drawing anchor price is invalid");
        return { bar_open_time_ms: times[logical], price };
      }),
    };
  });
}

export function buildGeometryReviewDraft(input: {
  signalId: string;
  snapshotRevision: string;
  barsSha256: string;
  label: GeometryReviewDraft["label"];
  drawings: readonly DrawingObject[];
  frozenCandles: readonly Candle[];
}): GeometryReviewDraft {
  if (!input.signalId.trim() || !input.snapshotRevision.trim() || !/^[0-9a-f]{64}$/i.test(input.barsSha256))
    throw new Error("Immutable signal provenance is missing");
  if (!["CONFIRMED", "GEOMETRY_CORRECTED", "FALSE_POSITIVE", "UNCERTAIN"].includes(input.label))
    throw new Error("Invalid review label");
  const corrected_boundaries = input.label === "GEOMETRY_CORRECTED"
    ? serializeReviewDrawings(input.drawings, input.frozenCandles)
    : [];
  if (input.label === "GEOMETRY_CORRECTED" && !corrected_boundaries.length)
    throw new Error("Corrected geometry is empty");
  return {
    schema_version: 1,
    signal_id: input.signalId,
    snapshot_revision: input.snapshotRevision,
    bars_sha256: input.barsSha256,
    label: input.label,
    corrected_boundaries,
  };
}
