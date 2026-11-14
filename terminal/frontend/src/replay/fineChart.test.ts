import { describe, expect, it } from "vitest";
import { finePresentationEvents, parseFineChart } from "./fineChart";
import type { ReplayDocument, ReplayCandle, ReplayEvent } from "./replayModel";

const from = Date.UTC(2026,10,10,8);
const bar = (at: number, duration: number, price = 100): ReplayCandle => ({
  start_ms:at,end_ms:at+duration,open:price,high:price+1,
  low:price-1,close:price,volume:1,
});
const source = {
  source:"SIMULATION",mode:"STRATEGY",symbol:"ICNTUSDT",
  execution_clock:"ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
  simulation_run_id:"immutable_original",
  events:[{source:"SIMULATION",simulation_run_id:"immutable_original",
    kind:"CANDLE_CLOSED", sequence:1,time_ms:from+300_000,
    candle:bar(from,300_000)}],
} as ReplayDocument;
const ticks = Array.from({length:8}, (_,i)=>bar(from+i*15_000,15_000));
const minute = [0,1].map(i=>({
  start_ms:from+i*60_000,end_ms:from+(i+1)*60_000,
  open:100,high:101,low:99,close:100,volume:4,
}));
const fixture = {
  source:"BYBIT_PUBLIC_TRADES_DERIVED_OHLC_LOCAL_ARCHIVE",
  symbol:"ICNTUSDT",start_ms:from,end_ms:from+120_000,
  raw_trade_sha256:"a".repeat(64),pinned_original_icnt:true,
  missing_m1:0,missing_15s:0,m1:minute,s15:ticks,
};

describe("verified fine public trade scale", () => {
  it("imports 15s and M1 only from same trade-proven grid", () => {
    const parsed = parseFineChart(fixture,source);
    expect(parsed.m1).toHaveLength(2);
    expect(parsed.s15).toHaveLength(8);
  });
  it("appends only visual ticks, preserving original filled events and time order", () => {
    const original: ReplayEvent[] = [{
      source:"SIMULATION",simulation_run_id:"immutable_original",
      sequence:1,kind:"ENTRY_FILLED",time_ms:from+16_000,
      trade_id:"SIMULATION:immutable_original:1",price:100,side:"LONG",
    }];
    const result = finePresentationEvents(original,ticks,from);
    expect(result).toHaveLength(9);
    expect(result[0].kind).toBe("CHART_TICK");
    expect(result[1]).toEqual(original[0]);
    expect(original).toHaveLength(1);
    expect(result.filter(e=>e.kind==="ENTRY_FILLED")).toHaveLength(1);
  });
  it("rejects partial/forged public trades evidence rather than fabricating candles", () => {
    expect(() => parseFineChart({...fixture,pinned_original_icnt:false},source)).toThrow();
    expect(() => parseFineChart({...fixture,s15:ticks.slice(0,7)},source)).toThrow();
    expect(() => parseFineChart({...fixture,
      m1:[{...minute[0],close:400},minute[1]]},source)).toThrow();
  });
});
