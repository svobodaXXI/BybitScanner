import type { Candle } from "../contracts/marketData";
import type { DrawingObject } from "../chart/drawingModel";
import { projectSignalGeometry } from "./signalChartBridge";
import type { TimestampDrawing } from "./geometryReviewDraft";

export type SignalGeometryResult =
  | { status: "ready"; boundaries: TimestampDrawing[] }
  | { status: "unavailable"; message: string };

const REASON_TEXT: Record<string, string> = {
  geometry_absent: "в сохранённом сигнале нет геометрии паттерна",
  formation_identity_absent: "сигнал сохранён без идентичности формации",
  index_time_mapping_unproven: "время опорных свечей не подтверждено",
  source_timeframe_unsupported: "таймфрейм сигнала не поддерживается",
};

const unavailable = (detail: string): SignalGeometryResult => ({
  status: "unavailable",
  message: `Линии сигнала недоступны: ${detail}.`,
});

function parseAnchors(raw: unknown): TimestampDrawing["anchors"] | null {
  if (!Array.isArray(raw) || raw.length !== 2) return null;
  const anchors = raw.map((item) => {
    const time = (item as { bar_open_time_ms?: unknown })?.bar_open_time_ms;
    const price = (item as { price?: unknown })?.price;
    return typeof time === "number" && Number.isSafeInteger(time) && time > 0 &&
      typeof price === "number" && Number.isFinite(price) && price > 0
      ? { bar_open_time_ms: time, price }
      : null;
  });
  return anchors.every((anchor) => anchor !== null)
    ? (anchors as TimestampDrawing["anchors"])
    : null;
}

/** Read-only fetch of the frozen Scanner geometry; never throws, never draws a guess. */
export async function loadSignalGeometry(
  signalId: string,
  symbol: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SignalGeometryResult> {
  let response: Response;
  try {
    response = await fetchImpl(`/api/scanner/signal-geometry?signal_id=${encodeURIComponent(signalId)}`);
  } catch {
    return unavailable("backend не отвечает");
  }
  let body: Record<string, unknown> | null = null;
  try {
    body = (await response.json()) as Record<string, unknown>;
  } catch {
    body = null;
  }
  if (response.status === 404) return unavailable("сигнал не найден в сохранённых данных");
  if (response.status === 422) {
    const reason = typeof body?.reason === "string" ? body.reason : "";
    return unavailable(REASON_TEXT[reason] ?? "геометрия не подтверждена");
  }
  if (!response.ok || body?.ok !== true) return unavailable("ответ backend отклонён");
  if (body.symbol !== symbol || body.signal_id !== signalId) {
    return unavailable("ответ относится к другому сигналу");
  }
  const rawBoundaries = body.boundaries;
  if (!Array.isArray(rawBoundaries) || rawBoundaries.length !== 2) {
    return unavailable("получены не две границы паттерна");
  }
  const boundaries: TimestampDrawing[] = [];
  for (const raw of rawBoundaries) {
    const anchors = parseAnchors((raw as { anchors?: unknown })?.anchors);
    const id = (raw as { boundary_id?: unknown })?.boundary_id;
    if (!anchors || typeof id !== "string" || !id) return unavailable("границы повреждены");
    boundaries.push({ id, type: "trend", anchors });
  }
  return { status: "ready", boundaries };
}

/** Project onto the chart's candles; a missing anchor candle is an explicit error. */
export function projectBoundaries(
  boundaries: readonly TimestampDrawing[],
  candles: readonly Candle[],
): { drawings: DrawingObject[]; error: string | null } {
  try {
    return { drawings: projectSignalGeometry(boundaries, candles).referenceDrawings, error: null };
  } catch (error) {
    const reason = error instanceof Error ? error.message : "ошибка";
    return {
      drawings: [],
      error: `Линии сигнала не показаны: опорная свеча паттерна вне загруженного окна графика (${reason}).`,
    };
  }
}
