/** Session-local inventory of PUBLIC closed M5; never trade data.
 * Retain every validated candle from a Bybit reply, not just the 24h
 * window currently drawn. No persistence or PAPER/L2 authority is implied.
 */
import type { ReplayCandle, ReplayDocument, ReplayEvent } from "./replayModel";

const M5 = 300_000;
const DAY = 86_400_000;
export class L2M5Catalog {
  private readonly bars = new Map<string, Map<number, ReplayCandle>>();

  ingest(history: ReplayDocument): number {
    if (history.mode !== "MARKET_ONLY" ||
        history.market_data_source !== "BYBIT_PUBLIC_KLINE" ||
        history.timeframe !== "5m" || !history.symbol) {
      throw new Error("Only sourced public Bybit M5 may enter the local catalog");
    }
    const parsed: ReplayCandle[] = [];
    for (const event of history.events) {
      if (event.kind !== "CANDLE_CLOSED" || !event.candle)
        throw new Error("Public catalog rejects trading events");
      const c = event.candle;
      if (!Number.isSafeInteger(c.start_ms) || c.start_ms % M5 ||
          c.end_ms !== c.start_ms + M5 ||
          parsed.some(other => other.start_ms === c.start_ms))
        throw new Error("Malformed or duplicate public M5");
      parsed.push(c);
    }
    if (parsed.length === 0 || parsed.length > 2016)
      throw new Error("Empty or oversized M5 catalog response");
    const existing = this.bars.get(history.symbol) ?? new Map<number, ReplayCandle>();
    // Check ALL conflicts before committing any row.
    for (const c of parsed) {
      const old = existing.get(c.start_ms);
      if (old && JSON.stringify(old) !== JSON.stringify(c))
        throw new Error("Conflicting public M5 evidence; keep original");
    }
    for (const c of parsed) existing.set(c.start_ms, c);
    this.bars.set(history.symbol, existing);
    return parsed.length;
  }

  /** Complete closed M5 coverage, including the original L2 source M5. */
  status(symbol: string, source: ReplayDocument, startMs: number, endExclusiveMs: number) {
    const known = this.bars.get(symbol);
    const original = new Set(source.events
      .filter(e => e.kind === "CANDLE_CLOSED" && e.candle)
      .map(e => e.candle!.start_ms));
    const first = Math.floor(startMs / M5) * M5;
    const end = Math.ceil(endExclusiveMs / M5) * M5;
    if (end <= first || end - first > 90 * DAY || symbol !== source.symbol)
      throw new Error("Invalid selected L2 catalog coverage");
    let required = 0, covered = 0;
    const missingDays = new Set<number>();
    for (let at = first; at < end; at += M5) {
      required++;
      if (original.has(at) || known?.has(at)) covered++;
      else missingDays.add(Math.floor(at / DAY) * DAY);
    }
    return { complete: missingDays.size === 0, covered, required,
      missingDays: [...missingDays].sort((a,b) => a-b) };
  }

  /** Build a transient MARKET_ONLY document from exactly the requested M5.
   * No network, no extra L2 fills, no new Scanner or Robot calculations.
   */
  asMarket(symbol: string, startMs: number, endExclusiveMs: number,
    source: ReplayDocument): ReplayDocument {
    const sourceCandles = new Map(source.events.filter(e =>
      e.kind === "CANDLE_CLOSED" && e.candle).map(e =>
        [e.candle!.start_ms, e.candle!] as const));
    const current = this.bars.get(symbol);
    const first = Math.floor(startMs / M5) * M5;
    const end = Math.ceil(endExclusiveMs / M5) * M5;
    const events: ReplayEvent[] = [];
    for (let at = first; at < end; at += M5) {
      const candle = current?.get(at) ?? sourceCandles.get(at);
      if (!candle) throw new Error("Selected period contains missing M5");
      events.push({ source: "SIMULATION", simulation_run_id: "local_m5_catalog",
        kind: "CANDLE_CLOSED", sequence: events.length+1,
        time_ms: candle.end_ms, candle });
    }
    return {
      source: "SIMULATION", simulation_run_id: "local_m5_catalog",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol, timeframe: "5m", events,
    } as ReplayDocument;
  }
}
