import type { TimestampDrawing } from "../geometryFeedback/geometryReviewDraft";
import type { RobotPositionOrigin } from "./robotPositionOrigin";

type ExpectedRobotSignal = {
  candidateId: string;
  symbol: string;
  origin: RobotPositionOrigin;
};

/** Identity-check archived, immutable Scanner anchors for exactly one open Robot trade.
 * Never reconstruct a signal by symbol, live OHLC, or candidate pattern name.
 */
export function parseProvenRobotSignalGeometry(
  payload: unknown, expected: ExpectedRobotSignal,
): TimestampDrawing[] | null {
  if (!payload || typeof payload !== "object" || expected.origin.candidate_id !== expected.candidateId)
    return null;
  const body = payload as Record<string, unknown>;
  const snapshot = body.snapshot;
  if (body.ok !== true || !snapshot || typeof snapshot !== "object") return null;
  const source = snapshot as Record<string, unknown>;
  const tf = expected.origin.signal_timeframe_minutes;
  if (tf === null || !Number.isSafeInteger(tf) || tf <= 0 ||
      source.schema_version !== 1 || source.signal_id !== expected.candidateId ||
      source.symbol !== expected.symbol || String(source.timeframe) !== String(tf))
    return null;

  const bars = source.bars, boundaries = source.boundaries;
  if (!Array.isArray(bars) || bars.length < 2 || bars.length > 2000 ||
      !Array.isArray(boundaries) || boundaries.length < 1 || boundaries.length > 16)
    return null;
  const times = new Set<number>();
  let lastTime = -1;
  for (const item of bars) {
    if (!item || typeof item !== "object") return null;
    const t = (item as Record<string, unknown>).open_time_ms;
    if (typeof t !== "number" || !Number.isSafeInteger(t) || t <= lastTime) return null;
    times.add(t);
    lastTime = t;
  }
  const count: Record<string, number> = {
    ray: 2, segment: 2, horizontal: 1, "horizontal-ray": 1,
  };
  const ids = new Set<string>();
  const output: TimestampDrawing[] = [];
  for (const item of boundaries) {
    if (!item || typeof item !== "object") return null;
    const boundary = item as Record<string, unknown>;
    const id = boundary.boundary_id, kind = boundary.kind, anchors = boundary.anchors;
    if (typeof id !== "string" || !id || ids.has(id) ||
        typeof kind !== "string" || !Object.hasOwn(count, kind) ||
        !Array.isArray(anchors) || anchors.length !== count[kind])
      return null;
    ids.add(id);
    const parsed: TimestampDrawing["anchors"] = [];
    let lastAnchor = -1;
    for (const item of anchors) {
      if (!item || typeof item !== "object") return null;
      const anchor = item as Record<string, unknown>;
      const time = anchor.bar_open_time_ms, price = anchor.price;
      if (typeof time !== "number" || !Number.isSafeInteger(time) ||
          !times.has(time) || time <= lastAnchor ||
          typeof price !== "number" || !Number.isFinite(price) || price <= 0)
        return null;
      parsed.push({ bar_open_time_ms: time, price });
      lastAnchor = time;
    }
    output.push({ id, type: kind as TimestampDrawing["type"], anchors: parsed });
  }
  return output;
}

/** We only align detector pivots with exact candle opens on a supported chart timeframe. */
export function robotSignalTimeframeMatchesChart(
  origin: RobotPositionOrigin, timeframe: string,
): boolean {
  const interval = { "1m": 1, "5m": 5, "15m": 15, "1h": 60 }[timeframe as "1m" | "5m" | "15m" | "1h"];
  return interval !== undefined && origin.signal_timeframe_minutes === interval;
}
