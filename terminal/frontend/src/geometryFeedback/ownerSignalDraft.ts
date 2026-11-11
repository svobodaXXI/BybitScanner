import type { DrawingObject } from "../chart/drawingModel";
import type { Candle } from "../contracts/marketData";
import { serializeReviewDrawings, type TimestampDrawing } from "./geometryReviewDraft";

export type OwnerSignalDraft = {
  schema_version: 1;
  signal_id: string;
  snapshot_revision: string;
  bars_sha256: string;
  pattern: "Falling Wedge" | "Rising Wedge";
  proposed_boundaries: TimestampDrawing[];
  note: string;
  idempotency_key: string;
  context_as_of_ms?: number;
  context_bars_sha256?: string;
};

/** New geometry is separate from the Scanner correction. Never reuse the
 * review's original boundary ids or claim a trusted Robot candidate here.
 */
export function buildOwnerSignalDraft(input: {
  signalId: string;
  snapshotRevision: string;
  barsSha256: string;
  pattern: OwnerSignalDraft["pattern"];
  drawings: readonly DrawingObject[];
  frozenCandles: readonly Candle[];
  note: string;
  idempotencyKey: string;
  contextAsOfMs?: number | null;
  contextBarsSha256?: string | null;
}): OwnerSignalDraft {
  if (!input.signalId || !/^[0-9a-f]{64}$/i.test(input.snapshotRevision) ||
      !/^[0-9a-f]{64}$/i.test(input.barsSha256))
    throw new Error("Нет подтверждённого исходного сигнала");
  if (input.drawings.length !== 2 || input.drawings.some((d) =>
    d.type !== "ray" || d.anchors.length !== 2 || d.hidden))
    throw new Error("Для нового клина нарисуйте ровно два луча");
  if (input.pattern !== "Falling Wedge" && input.pattern !== "Rising Wedge")
    throw new Error("Неподдерживаемый тип нового сигнала");
  const lines = serializeReviewDrawings(input.drawings, input.frozenCandles);
  if (lines.some((line) =>
    line.anchors[0].bar_open_time_ms >= line.anchors[1].bar_open_time_ms))
    throw new Error("Точки каждого луча должны идти по времени вперёд");
  // Identify upper/lower by the y-value at the last frozen candle. The
  // classifier does not infer a strategy from the two owner-drawn lines.
  const last = Date.parse(input.frozenCandles.at(-1)?.time ?? "");
  const projected = lines.map((line) => {
    const [a, b] = line.anchors;
    const price = a.price + (b.price - a.price) *
      ((last - a.bar_open_time_ms) / (b.bar_open_time_ms - a.bar_open_time_ms));
    return { line, price };
  }).sort((a, b) => b.price - a.price);
  if (!Number.isFinite(projected[0].price) ||
      !Number.isFinite(projected[1].price) ||
      projected[0].price <= projected[1].price)
    throw new Error("Верхняя и нижняя линии неразличимы");
  if (input.note.length > 1024) throw new Error("Комментарий слишком длинный");
  if ((input.contextAsOfMs == null) !== (input.contextBarsSha256 == null))
    throw new Error("Неполный контекст поздних свечей");
  if (input.contextAsOfMs != null &&
      (!Number.isSafeInteger(input.contextAsOfMs) ||
       !/^[0-9a-f]{64}$/i.test(input.contextBarsSha256 ?? "")))
    throw new Error("Неверный контекст поздних свечей");
  return {
    ...(input.contextAsOfMs != null ? {
      context_as_of_ms: input.contextAsOfMs,
      context_bars_sha256: input.contextBarsSha256!,
    } : {}),
    schema_version: 1,
    signal_id: input.signalId,
    snapshot_revision: input.snapshotRevision,
    bars_sha256: input.barsSha256,
    pattern: input.pattern,
    proposed_boundaries: projected.map(({ line }, index) => ({
      id: index === 0 ? "upper" : "lower",
      type: "ray",
      anchors: line.anchors,
    })),
    note: input.note,
    idempotency_key: input.idempotencyKey,
  };
}


/** A human-originated unverified chart annotation, not a trusted trading signal.
 * Ikigai Box uses the exact first-impulse Fibonacci A/B anchors (F0=A,
 * F1=B); the later consolidation/second impulse are preserved in frozen bars.
 */
export type OwnerChartPattern = OwnerSignalDraft["pattern"] | "Ikigai Box";
export type OwnerChartDirection = "LONG" | "SHORT";
export type OwnerChartDraft = {
  schema_version: 2;
  source_kind: "OWNER_CHART_UNVERIFIED";
  symbol: string;
  timeframe: "1" | "5" | "15" | "60" | "D";
  pattern: OwnerChartPattern;
  direction: OwnerChartDirection;
  bars: Array<{ open_time_ms: number; open: number; high: number; low: number; close: number }>;
  proposed_boundaries: TimestampDrawing[];
  note: string;
  idempotency_key: string;
};

export function buildOwnerChartDraft(input: {
  symbol: string; timeframe: string;
  pattern: OwnerChartPattern;
  direction: OwnerChartDirection;
  drawings: readonly DrawingObject[];
  frozenCandles: readonly Candle[];
  note: string;
  idempotencyKey: string;
}): OwnerChartDraft {
  const periods: Record<string, [OwnerChartDraft["timeframe"], number]> = {
    "1": ["1", 60_000], "1m": ["1", 60_000],
    "5": ["5", 300_000], "5m": ["5", 300_000],
    "15": ["15", 900_000], "15m": ["15", 900_000],
    "60": ["60", 3_600_000], "1h": ["60", 3_600_000],
    "D": ["D", 86_400_000], "1d": ["D", 86_400_000],
  };
  const period = periods[input.timeframe];
  if (!period || !/^[A-Z0-9]{2,25}$/.test(input.symbol))
    throw new Error("Недоступны инструмент или таймфрейм для нового сигнала");
  if (input.frozenCandles.length < 20 || input.frozenCandles.length > 120)
    throw new Error("Для примера требуется от 20 до 120 закрытых свечей");
  if (input.direction !== "LONG" && input.direction !== "SHORT")
    throw new Error("Выберите направление сигнала");
  const isBox = input.pattern === "Ikigai Box";
  if (isBox) {
    if (input.drawings.length !== 1 ||
        input.drawings[0].type !== "fibonacci" ||
        input.drawings[0].hidden ||
        input.drawings[0].anchors.length !== 2)
      throw new Error("Для Икигай-бокса поставьте одну сетку Фибоначчи по первому импульсу (A→B)");
  } else if (input.pattern === "Falling Wedge" || input.pattern === "Rising Wedge") {
    if (input.drawings.length !== 2 || input.drawings.some((line) =>
      line.type !== "ray" || line.anchors.length !== 2 || line.hidden))
      throw new Error("Для клина нарисуйте ровно два луча");
  } else throw new Error("Неподдерживаемый паттерн");
  if (input.note.length > 1024)
    throw new Error("Комментарий слишком длинный");
  const bars = input.frozenCandles.map((candle, index) => {
    const at = Date.parse(candle.time);
    if (!Number.isSafeInteger(at) || at < 0 || at % period[1] !== 0 ||
        (index > 0 && at !== Date.parse(input.frozenCandles[index - 1].time) + period[1]))
      throw new Error("Пропуск или неверное время свечи");
    const { open, high, low, close } = candle;
    if ([open, high, low, close].some((value) =>
      !Number.isFinite(value) || value <= 0) ||
      high < Math.max(open, close) || low > Math.min(open, close))
      throw new Error("Некорректные свечи исходного графика");
    return { open_time_ms: at, open, high, low, close };
  });
  const last = bars.at(-1)!.open_time_ms;
  const lines = serializeReviewDrawings(input.drawings, input.frozenCandles);
  if (lines.some((line) =>
    line.anchors[0].bar_open_time_ms >= line.anchors[1].bar_open_time_ms))
    throw new Error("Точки каждого инструмента должны идти по времени вперёд");
  let proposed_boundaries: TimestampDrawing[];
  if (isBox) {
    const [origin, terminal] = lines[0].anchors;
    if (input.direction === "SHORT" ? terminal.price <= origin.price
        : terminal.price >= origin.price)
      throw new Error("Направление первого импульса не соответствует LONG/SHORT");
    proposed_boundaries = [{ id: "first_impulse_fibonacci", type: "fibonacci", anchors: [origin, terminal] }];
  } else {
    const ordered = lines.map((line) => {
      const [a, b] = line.anchors;
      const price = a.price + (b.price - a.price) *
        ((last - a.bar_open_time_ms) / (b.bar_open_time_ms - a.bar_open_time_ms));
      return { line, price };
    }).sort((a, b) => b.price - a.price);
    if (!Number.isFinite(ordered[0].price) ||
        !Number.isFinite(ordered[1].price) ||
        ordered[0].price <= ordered[1].price)
      throw new Error("Верхняя и нижняя линии неразличимы");
    proposed_boundaries = ordered.map(({ line }, index) => ({
      id: index === 0 ? "upper" : "lower",
      type: "ray", anchors: line.anchors,
    }));
  }
  return {
    schema_version: 2,
    source_kind: "OWNER_CHART_UNVERIFIED",
    symbol: input.symbol, timeframe: period[0],
    pattern: input.pattern, direction: input.direction, bars,
    proposed_boundaries,
    note: input.note.trim(), idempotency_key: input.idempotencyKey,
  };
}
