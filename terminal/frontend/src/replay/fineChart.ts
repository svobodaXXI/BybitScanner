/** Chart-only M1 and 15S from original owner-selected public trades.
 * No aggregation of M5, no virtual execution engine or P&L mutation.
 */
import type { ReplayCandle, ReplayDocument, ReplayEvent } from "./replayModel";

export type FineBarFrame = "1m" | "15s";
export type FineChart = {
  source: "BYBIT_PUBLIC_TRADES_DERIVED_OHLC_LOCAL_ARCHIVE";
  symbol: string;
  start_ms: number;
  end_ms: number;
  raw_trade_sha256: string;
  pinned_original_icnt: boolean;
  missing_m1: number;
  missing_15s: number;
  m1: ReplayCandle[];
  s15: ReplayCandle[];
};

const M1 = 60_000;
const S15 = 15_000;
function record(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v))
    throw new Error("Неверный ответ архива сделок");
  return v as Record<string, unknown>;
}
function validBars(raw: unknown, interval: number,
  start: number, end: number): ReplayCandle[] {
  if (!Array.isArray(raw) || raw.length > (end - start) / interval)
    throw new Error("Неверный размер массива свечей");
  let previous = start - interval;
  return raw.map(value => {
    const c = record(value);
    const nums = [c.start_ms,c.end_ms,c.open,c.high,c.low,c.close,c.volume];
    if (!nums.every(n => typeof n === "number" && Number.isFinite(n)) ||
        (c.start_ms as number) % interval !== 0 ||
        (c.end_ms as number) !== (c.start_ms as number) + interval ||
        (c.start_ms as number) <= previous ||
        (c.start_ms as number) < start || (c.end_ms as number) > end ||
        (c.low as number) <= 0 || (c.volume as number) <= 0 ||
        (c.high as number) < Math.max(c.open as number,c.close as number) ||
        (c.low as number) > Math.min(c.open as number,c.close as number))
      throw new Error("Неподтверждённые свечи из архива сделок");
    previous = c.start_ms as number;
    return c as ReplayCandle;
  });
}
export function parseFineChart(
  raw: unknown, source: ReplayDocument,
): FineChart {
  const data = record(raw);
  if (source.execution_clock !== "ORIGINAL_EVENT_TIME_NOT_OHLC_M1" ||
      data.source !== "BYBIT_PUBLIC_TRADES_DERIVED_OHLC_LOCAL_ARCHIVE" ||
      data.symbol !== source.symbol ||
      typeof data.start_ms !== "number" || typeof data.end_ms !== "number" ||
      data.start_ms % M1 || data.end_ms % M1 ||
      data.end_ms <= data.start_ms ||
      data.end_ms - data.start_ms > 6 * 3_600_000 ||
      typeof data.raw_trade_sha256 !== "string" ||
      !/^[a-f0-9]{64}$/.test(data.raw_trade_sha256) ||
      typeof data.pinned_original_icnt !== "boolean" ||
      !Number.isSafeInteger(data.missing_m1) ||
      !Number.isSafeInteger(data.missing_15s)) {
    throw new Error("Архив M1/15S не соответствует исходному L2-прогону");
  }
  if (source.symbol === "ICNTUSDT" &&
      !data.pinned_original_icnt) {
    throw new Error("Для исходного ICNT требуется оригинальный архив сделок с проверенным SHA");
  }
  const start = data.start_ms as number, end = data.end_ms as number;
  const m1 = validBars(data.m1, M1, start, end);
  const s15 = validBars(data.s15, S15, start, end);
  if (m1.length !== (end-start)/M1 - (data.missing_m1 as number) ||
      s15.length !== (end-start)/S15 - (data.missing_15s as number))
    throw new Error("Недостоверное покрытие M1/15S");
  // Reconcile two visual grids against the SAME public trade prints.
  for (const minute of m1) {
    const group = s15.filter(c => c.start_ms >= minute.start_ms &&
      c.end_ms <= minute.end_ms);
    if (!group.length) throw new Error("M1 отсутствует в 15S-сделках");
    const closeEnough = (a:number,b:number) =>
      Math.abs(a-b) <= 1e-9 * Math.max(1,Math.abs(a),Math.abs(b));
    if (![ [group[0].open,minute.open],
           [group[group.length-1].close,minute.close],
           [Math.max(...group.map(c=>c.high)),minute.high],
           [Math.min(...group.map(c=>c.low)),minute.low],
           [group.reduce((acc,c)=>acc+c.volume,0),minute.volume],
         ].every(([a,b])=>closeEnough(a,b)))
      throw new Error("M1 и 15S не совпадают по исходным публичным сделкам");
  }
  return {...data, m1, s15} as FineChart;
}

/** A pure presentation clock, never serialized as a source event. */
export function finePresentationEvents(
  source: readonly ReplayEvent[], fine: readonly ReplayCandle[],
  sourceFirstMs: number,
): ReplayEvent[] {
  const ticks: ReplayEvent[] = fine.filter(c => c.start_ms >= sourceFirstMs).map(c => ({
    source: "SIMULATION", simulation_run_id: "local_visual_ticks",
    sequence: 0, kind: "CHART_TICK", time_ms: c.end_ms,
  }));
  return [...source,...ticks].sort((a,b) =>
    a.time_ms-b.time_ms || (a.kind === "CHART_TICK" ? 1 : 0) -
      (b.kind === "CHART_TICK" ? 1 : 0));
}
