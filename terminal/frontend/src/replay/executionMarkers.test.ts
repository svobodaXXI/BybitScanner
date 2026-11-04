import { describe, expect, it } from "vitest";
import { syntheticReplay, visibleReplay } from "./replayModel";
import {
  TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR, visibleExecutionMarkers,
} from "./executionMarkers";

describe("existing Telegram position-chart execution semantics", () => {
  it("places only filled Buy/Sell triangles at recorded execution prices, never signals", () => {
    const document = syntheticReplay();
    const final = visibleReplay(document.events, document.events.length);
    const markers = visibleExecutionMarkers(document.events, final.candles);
    expect(markers).toHaveLength(2);
    const entry = document.events.find((x) => x.kind === "ENTRY_FILLED")!;
    const exit = document.events.find((x) => x.kind === "EXIT_FILLED")!;
    expect(markers[0]).toEqual({
      time_ms: entry.time_ms,
      candle_start_ms: entry.time_ms,
      price: entry.price,
      side: "Buy",
      trade_id: entry.trade_id,
    });
    expect(markers[1]).toEqual({
      time_ms: exit.time_ms,
      candle_start_ms: exit.time_ms - 300_000,
      price: exit.price,
      side: "Sell",
      trade_id: exit.trade_id,
    });
    expect(TELEGRAM_BUY_COLOR).toBe("#00a152");
    expect(TELEGRAM_SELL_COLOR).toBe("#d50000");
  });

  it("never shows a fill before its candle closes or substitutes a candle price", () => {
    const document = syntheticReplay();
    const entryIndex = document.events.findIndex((x) => x.kind === "ENTRY_FILLED");
    const before = visibleReplay(document.events, entryIndex + 1);
    expect(visibleExecutionMarkers(document.events.slice(0, entryIndex + 1), before.candles)).toEqual([]);
    const after = visibleReplay(document.events, entryIndex + 2);
    const events = document.events.slice(0, entryIndex + 2);
    const markers = visibleExecutionMarkers(events, after.candles);
    expect(markers).toHaveLength(1);
    expect(markers[0].price).toBe(document.events[entryIndex].price);
    expect(markers[0].candle_start_ms).toBe(after.candles.at(-1)!.start_ms);
  });

  it("keeps SHORT buy-to-cover versus sell-to-enter direction and no invented fills", () => {
    const doc = syntheticReplay();
    const bar = visibleReplay(doc.events, doc.events.length).candles[0];
    const t = bar.start_ms;
    const events = [
      { ...doc.events[0], kind: "ENTRY_FILLED" as const, side: "SHORT" as const,
        trade_id: "SIMULATION:SYNTHETIC_DEMO:short", price: 100, time_ms: t },
      { ...doc.events[0], kind: "EXIT_FILLED" as const, side: "SHORT" as const,
        trade_id: "SIMULATION:SYNTHETIC_DEMO:short", price: 101, time_ms: bar.end_ms },
      { ...doc.events[0], kind: "ENTRY_SIGNAL" as const, side: "SHORT" as const,
        price: 99, time_ms: t },
    ];
    expect(visibleExecutionMarkers(events, [bar]).map(x => x.side)).toEqual(["Sell", "Buy"]);
    expect(visibleExecutionMarkers([
      { ...events[0], price: undefined },
      { ...events[1], time_ms: bar.end_ms + 300_000 },
    ], [bar])).toEqual([]);
  });
});
