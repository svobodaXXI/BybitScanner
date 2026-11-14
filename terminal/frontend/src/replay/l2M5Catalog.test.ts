import { describe, expect, it } from "vitest";
import { L2M5Catalog } from "./l2M5Catalog";
import type { ReplayCandle, ReplayDocument, ReplayEvent } from "./replayModel";

const base = Date.UTC(2026, 10, 10, 8);
const M5 = 300_000;
const bar = (t: number): ReplayCandle => ({
  start_ms:t, end_ms:t+M5, open:1, high:2, low:.5, close:1, volume:1,
});
const source = { mode:"STRATEGY", symbol:"ICNTUSDT",
  execution_clock:"ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
  events: Array.from({length:3},(_,i)=>({
    kind:"CANDLE_CLOSED",time_ms:base+(i+1)*M5,candle:bar(base+i*M5),
  })) } as ReplayDocument;
const publicM5 = (start:number,count:number,symbol="ICNTUSDT") => ({
  mode:"MARKET_ONLY", symbol, timeframe:"5m",
  market_data_source:"BYBIT_PUBLIC_KLINE",
  events:Array.from({length:count},(_,i)=>({
    kind:"CANDLE_CLOSED",candle:bar(start+i*M5),
  })),
}) as ReplayDocument;

describe("session-local M5 inventory for source L2 replay", () => {
  it("retains every received bar beyond the initial 12-bar chart horizon", () => {
    const catalog = new L2M5Catalog();
    // The source window is 08:00-08:15; public reply already has 80m after.
    catalog.ingest(publicM5(base-288*M5, 288+3+16));
    const expanded = catalog.status("ICNTUSDT",source,base,base+16*M5);
    expect(expanded).toEqual({
      complete:true,covered:16,required:16,missingDays:[],
    });
    const market = catalog.asMarket("ICNTUSDT",base,base+16*M5,source);
    expect(market.events).toHaveLength(16);
    expect(source.events).toHaveLength(3);
  });
  it("only reports genuinely missing days, not already downloaded days", () => {
    const catalog = new L2M5Catalog();
    catalog.ingest(publicM5(base-288*M5,288+3));
    const missing = catalog.status("ICNTUSDT",source,base,base+16*M5);
    expect(missing.complete).toBe(false);
    expect(missing.covered).toBe(3);
    expect(missing.missingDays).toEqual([
      Date.UTC(2026,10,10,0),
    ]);
    expect(() => catalog.asMarket("ICNTUSDT",base,base+16*M5,source))
      .toThrow(/missing M5/);
  });
  it("rejects unrelated symbols and conflicting duplicate bars atomically", () => {
    const catalog = new L2M5Catalog();
    catalog.ingest(publicM5(base,3));
    expect(() => catalog.ingest({
      ...publicM5(base,1),
      events:[{kind:"CANDLE_CLOSED",candle:{...bar(base),close:1.3}}],
    } as ReplayDocument)).toThrow(/Conflicting/);
    expect(catalog.status("ICNTUSDT",source,base,base+3*M5).complete).toBe(true);
    expect(() => catalog.ingest({ ...publicM5(base,1),
      market_data_source:"UNVERIFIED" } as unknown as ReplayDocument)).toThrow();
  });
});
