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


/** V3 records the movement of the formation, never an executable trade side.
 * V1/V2 entries remain immutable and are decoded by their original schema.
 * Manual patterns are unverified examples, not Scanner/Robot admissions.
 */
export const OWNER_CHART_PATTERNS_V3 = [
  "Wedge", "Ikigai Box", "Triangle", "Double Top/Bottom",
  "Head and Shoulders", "G-Shaped",
] as const;
export type OwnerChartPatternV3 = typeof OWNER_CHART_PATTERNS_V3[number];
export type OwnerChartMovement = "UP" | "DOWN";
export type OwnerWedgeSubtype = "SLOWDOWN" | "CORRECTION";
export type OwnerChartDraftV3 = Omit<OwnerChartDraft,
  "schema_version" | "pattern" | "direction"> & {
    schema_version: 3;
    pattern: OwnerChartPatternV3;
    formation_movement: OwnerChartMovement;
    wedge_subtype?: OwnerWedgeSubtype;
  };

/** The editor preserves arbitrary manual geometry as evidence. Neither the
 * selected movement nor the wedge subtype decides an entry/exit direction.
 */
export function buildOwnerChartDraftV3(input: {
  symbol: string;
  timeframe: string;
  pattern: OwnerChartPatternV3;
  formationMovement: OwnerChartMovement;
  wedgeSubtype?: OwnerWedgeSubtype;
  drawings: readonly DrawingObject[];
  frozenCandles: readonly Candle[];
  note: string;
  idempotencyKey: string;
}): OwnerChartDraftV3 {
  if (!OWNER_CHART_PATTERNS_V3.includes(input.pattern) ||
      (input.formationMovement !== "UP" && input.formationMovement !== "DOWN"))
    throw new Error("Выберите паттерн и направление движения графика");
  if (input.pattern === "Wedge" &&
      input.wedgeSubtype !== "SLOWDOWN" && input.wedgeSubtype !== "CORRECTION")
    throw new Error("Выберите подтип клина");
  if (input.pattern !== "Wedge" && input.wedgeSubtype != null)
    throw new Error("Подтип допустим только для клина");
  const periods: Record<string, [OwnerChartDraftV3["timeframe"], number]> = {
    "1": ["1", 60_000], "1m": ["1", 60_000],
    "5": ["5", 300_000], "5m": ["5", 300_000],
    "15": ["15", 900_000], "15m": ["15", 900_000],
    "60": ["60", 3_600_000], "1h": ["60", 3_600_000],
    "D": ["D", 86_400_000], "1d": ["D", 86_400_000],
  };
  const period = periods[input.timeframe];
  if (!period || !/^[A-Z0-9]{2,25}$/.test(input.symbol))
    throw new Error("Недоступны инструмент или таймфрейм для нового сигнала");
  if (input.frozenCandles.length < 20)
    throw new Error("Для примера требуется минимум 20 закрытых свечей");
  // Serialize against the FULL chart first: logical anchor indices belong to
  // that chart, and cannot be silently shifted when selecting archive bars.
  const lines = serializeReviewDrawings(input.drawings, input.frozenCandles);
  const sourceTimes = input.frozenCandles.map((candle) => Date.parse(candle.time));
  const anchorPositions = lines.flatMap((line) => line.anchors.map((anchor) =>
    sourceTimes.indexOf(anchor.bar_open_time_ms)));
  if (!anchorPositions.length || anchorPositions.some((index) => index < 0))
    throw new Error("Опоры разметки отсутствуют в исходных свечах");
  const firstAnchor = Math.min(...anchorPositions);
  const lastAnchor = Math.max(...anchorPositions);
  if (lastAnchor - firstAnchor >= 120)
    throw new Error("Разметка занимает больше 120 свечей. Сузьте участок фигуры");
  // The server's immutable owner-chart contract accepts 20..120 consecutive
  // closed bars. Keep all manual anchors and some preceding context, rather
  // than sending an entire 200-bar Scanner snapshot or dropping early rays.
  const windowStart = input.frozenCandles.length > 120
    ? Math.max(0, Math.min(firstAnchor, Math.max(firstAnchor - 12, lastAnchor - 119)))
    : 0;
  const sourceWindow = input.frozenCandles.slice(windowStart, windowStart + 120);
  const windowTimes = new Set(sourceWindow.map((candle) => Date.parse(candle.time)));
  if (lines.some((line) => line.anchors.some((anchor) =>
    !windowTimes.has(anchor.bar_open_time_ms))))
    throw new Error("Не удалось включить все опоры в сохраняемые свечи");
  const bars = sourceWindow.map((candle, index) => {
    const at = Date.parse(candle.time);
    if (!Number.isSafeInteger(at) || at < 0 || at % period[1] !== 0 ||
        (index > 0 && at !== Date.parse(sourceWindow[index - 1].time) + period[1]))
      throw new Error("Пропуск или неверное время свечи");
    const { open, high, low, close } = candle;
    if ([open, high, low, close].some((value) =>
      !Number.isFinite(value) || value <= 0) ||
      high < Math.max(open, close) || low > Math.min(open, close))
      throw new Error("Некорректные свечи исходного графика");
    return { open_time_ms: at, open, high, low, close };
  });
  if (!input.drawings.length || input.drawings.length > 8 ||
      input.drawings.some((drawing) => drawing.hidden))
    throw new Error("Нарисуйте от одного до восьми видимых инструментов");
  const isBox = input.pattern === "Ikigai Box";
  const isTwoRay = input.pattern === "Wedge" || input.pattern === "Triangle";
  if (isBox && (input.drawings.length !== 1 || input.drawings[0].type !== "fibonacci"))
    throw new Error("Для Коробки нарисуйте одну сетку Фибоначчи первого импульса");
  if (isTwoRay && (input.drawings.length !== 2 ||
      input.drawings.some((drawing) => drawing.type !== "ray")))
    throw new Error("Для клина или треугольника нарисуйте два луча");
  if (input.note.length > 1024)
    throw new Error("Комментарий слишком длинный");
  if (lines.some((line) => line.anchors.length === 2 &&
      line.anchors[0].bar_open_time_ms >= line.anchors[1].bar_open_time_ms))
    throw new Error("Точки инструмента должны идти по времени вперёд");
  const permitted = new Set(["ray", "trend", "horizontal", "horizontal-ray",
    "vertical", "fibonacci", "ruler", "rectangle"]);
  if (lines.some((line) => !permitted.has(line.type)))
    throw new Error("Неподдерживаемый инструмент разметки");
  // User-drawn IDs must stay local and can be arbitrary. Serialise stable
  // numbered IDs for the append-only archive, not Scanner boundary IDs.
  const proposed_boundaries = lines.map((line, i) => ({
    id: isBox ? "first_impulse_fibonacci" : `manual_${i + 1}`,
    type: line.type,
    anchors: line.anchors,
  }));
  return {
    schema_version: 3,
    source_kind: "OWNER_CHART_UNVERIFIED",
    symbol: input.symbol, timeframe: period[0],
    pattern: input.pattern,
    formation_movement: input.formationMovement,
    ...(input.pattern === "Wedge" ? { wedge_subtype: input.wedgeSubtype! } : {}),
    bars, proposed_boundaries,
    note: input.note.trim(), idempotency_key: input.idempotencyKey,
  };
}
